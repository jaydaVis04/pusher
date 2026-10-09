// SPDX-License-Identifier: GPL-2.0
/* Read-only access to borrowed vendor shared-memory mappings. */
#include <linux/capability.h>
#include <linux/err.h>
#include <linux/fs.h>
#include <linux/init.h>
#include <linux/io.h>
#include <linux/kernel.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/rwsem.h>
#include <linux/slab.h>
#include <linux/types.h>
#include <linux/uaccess.h>

/* Exact layouts from the original working reader. */
struct x {
	phys_addr_t base_md_view_phy;
	phys_addr_t base_ap_view_phy;
	void __iomem *base_ap_view_vir;
	unsigned int size;
};

struct y {
	unsigned int id;
	unsigned int offset;
	unsigned int size;
	unsigned int flag;
	phys_addr_t base_md_view_phy;
	phys_addr_t base_ap_view_phy;
	void __iomem *base_ap_view_vir;
};

struct THISGUY {
	struct x var1;
	struct x var2;
	struct x var3;
	struct y *var4;
	struct y *var5;
};

/* This must match the real getthisguy(int) prototype exactly. */
typedef struct THISGUY *(*getthisguy_fn_t)(int);

struct re_mem_region {
	void __iomem *base;
	size_t size;
	phys_addr_t ap_phys;
	phys_addr_t md_phys;
};

/* Copy metadata only; all mappings remain owned by the vendor driver. */
static inline int re_mem_driver_describe(struct THISGUY *guy,
					struct re_mem_region out[5])
{
	struct x *x[3] = { &guy->var1, &guy->var2, &guy->var3 };
	struct y *y[2] = { guy->var4, guy->var5 };
	unsigned int i;

	for (i = 0; i < 3; i++) {
		out[i].base = x[i]->base_ap_view_vir;
		out[i].size = x[i]->size;
		out[i].ap_phys = x[i]->base_ap_view_phy;
		out[i].md_phys = x[i]->base_md_view_phy;
	}
	for (i = 0; i < 2; i++) {
		if (!y[i])
			continue;
		/* Preserve the original reader: use these bases directly, not + offset. */
		out[i + 3].base = y[i]->base_ap_view_vir;
		out[i + 3].size = y[i]->size;
		out[i + 3].ap_phys = y[i]->base_ap_view_phy;
		out[i + 3].md_phys = y[i]->base_md_view_phy;
	}
	return 0;
}

static unsigned long myaddr;
module_param(myaddr, ulong, 0400);
MODULE_PARM_DESC(myaddr, "Verified LIVE getthisguy address from this device boot");
static unsigned int region = 2;
module_param(region, uint, 0400);
MODULE_PARM_DESC(region, "Initial region (1..5); use misc sysfs to switch at runtime");

static struct re_mem_region regions[5];
static DECLARE_RWSEM(region_lock);
static void __iomem *re_base;
static size_t re_size;
static phys_addr_t re_phys;
static phys_addr_t re_md_phys;
static u64 generation;

struct re_mem_file {
	u64 generation;
};

static int select_region(unsigned int requested)
{
	struct re_mem_region *selected;

	if (requested < 1 || requested > ARRAY_SIZE(regions))
		return -EINVAL;
	down_write(&region_lock);
	selected = &regions[requested - 1];
	if (!selected->base || !selected->size) {
		up_write(&region_lock);
		return -ENODEV;
	}
	if (region != requested || !re_base) {
		re_base = selected->base;
		re_size = selected->size;
		re_phys = selected->ap_phys;
		re_md_phys = selected->md_phys;
		region = requested;
		generation++;
		pr_info("re_mem: selected region %u, size=0x%zx\n", region, re_size);
	}
	up_write(&region_lock);
	return 0;
}

static int re_mem_open(struct inode *inode, struct file *file)
{
	struct re_mem_file *context;

	if ((file->f_flags & O_ACCMODE) != O_RDONLY)
		return -EACCES;
	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	context = kzalloc(sizeof(*context), GFP_KERNEL);
	if (!context)
		return -ENOMEM;
	down_read(&region_lock);
	context->generation = generation;
	up_read(&region_lock);
	file->private_data = context;
	return 0;
}

static int re_mem_release(struct inode *inode, struct file *file)
{
	kfree(file->private_data);
	return 0;
}

static ssize_t re_mem_read(struct file *file, char __user *buf, size_t count, loff_t *pos)
{
	struct re_mem_file *context = file->private_data;
	u8 *temporary;
	size_t available, total = 0, chunk, not_copied;
	loff_t start_offset;
	ssize_t result;

	if (!count)
		return 0;
	if (*pos < 0)
		return -EINVAL;
	down_read(&region_lock);
	/* A multi-syscall cat/dd must never concatenate different regions. */
	if (context->generation != generation) {
		result = -ESTALE;
		goto unlock;
	}
	if (!re_base || !re_size) {
		result = -ENODEV;
		goto unlock;
	}
	if ((u64)*pos >= re_size) {
		result = 0;
		goto unlock;
	}
	start_offset = *pos;
	available = re_size - (size_t)*pos;
	count = min(count, available);
	temporary = kmalloc(PAGE_SIZE, GFP_KERNEL);
	if (!temporary) {
		result = -ENOMEM;
		goto unlock;
	}
	/* Keep the original page-sized loop; hold the region lock for the whole read. */
	while (total < count) {
		chunk = min_t(size_t, PAGE_SIZE, count - total);
		/* The driver owns this mapping. Never remap, unmap or write to it. */
		memcpy_fromio(temporary,
			(u8 __iomem *)re_base + (size_t)start_offset + total, chunk);
		not_copied = copy_to_user(buf + total, temporary, chunk);
		total += chunk - not_copied;
		if (not_copied)
			break;
	}
	kfree(temporary);
	*pos += total;
	result = total ? (ssize_t)total : -EFAULT;
	pr_debug_ratelimited("re_mem: READ region=%u offset=0x%llx bytes=%zu\n",
		region, (unsigned long long)start_offset, total);
unlock:
	up_read(&region_lock);
	return result;
}

static loff_t re_mem_llseek(struct file *file, loff_t offset, int whence)
{
	struct re_mem_file *context = file->private_data;
	loff_t result;

	down_read(&region_lock);
	if (context->generation != generation)
		result = -ESTALE;
	else if (!re_base || !re_size)
		result = -ENODEV;
	else
		result = fixed_size_llseek(file, offset, whence, (loff_t)re_size);
	up_read(&region_lock);
	return result;
}

static const struct file_operations re_mem_fops = {
	.owner = THIS_MODULE,
	.open = re_mem_open,
	.release = re_mem_release,
	.read = re_mem_read,
	.llseek = re_mem_llseek,
};

static ssize_t region_show(struct device *dev, struct device_attribute *attr, char *buf)
{
	ssize_t length;

	down_read(&region_lock);
	length = scnprintf(buf, PAGE_SIZE, "%u\n", region);
	up_read(&region_lock);
	return length;
}

static ssize_t region_store(struct device *dev, struct device_attribute *attr,
			   const char *buf, size_t count)
{
	unsigned int requested;
	int error;

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	error = kstrtouint(buf, 10, &requested);
	if (error)
		return error;
	error = select_region(requested);
	return error ? error : count;
}
static DEVICE_ATTR_RW(region);

static ssize_t info_show(struct device *dev, struct device_attribute *attr, char *buf)
{
	ssize_t length;

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	down_read(&region_lock);
	length = scnprintf(buf, PAGE_SIZE,
		"region=%u\nsize=0x%zx\nmd_phys=0x%llx\nap_phys=0x%llx\n"
		"ap_virt=0x%lx\ngeneration=%llu\n",
		region, re_size, (unsigned long long)re_md_phys,
		(unsigned long long)re_phys, (unsigned long)re_base,
		(unsigned long long)generation);
	up_read(&region_lock);
	return length;
}
static DEVICE_ATTR_RO(info);

static ssize_t regions_show(struct device *dev, struct device_attribute *attr, char *buf)
{
	size_t length = 0;
	unsigned int i;

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	down_read(&region_lock);
	for (i = 0; i < ARRAY_SIZE(regions); i++) {
		struct re_mem_region *r = &regions[i];

		if (!r->base || !r->size)
			continue;
		length += scnprintf(buf + length, PAGE_SIZE - length,
			"region=%u\nsize=0x%zx\nmd_phys=0x%llx\nap_phys=0x%llx\n"
			"ap_virt=0x%lx\n\n", i + 1, r->size,
			(unsigned long long)r->md_phys, (unsigned long long)r->ap_phys,
			(unsigned long)r->base);
	}
	up_read(&region_lock);
	return length;
}
static DEVICE_ATTR_RO(regions);

static struct attribute *re_mem_attrs[] = {
	&dev_attr_region.attr, &dev_attr_info.attr, &dev_attr_regions.attr, NULL,
};
ATTRIBUTE_GROUPS(re_mem);

static struct miscdevice re_mem_device = {
	.minor = MISC_DYNAMIC_MINOR,
	.name = "re_mem",
	.fops = &re_mem_fops,
	.mode = 0400,
	.groups = re_mem_groups,
};

static int __init re_mem_init(void)
{
	getthisguy_fn_t getthisguy_fn;
	struct THISGUY *guy;
	unsigned int i;
	int error;

	/* These checks cannot prove a function's ABI; userspace must verify it. */
	if (sizeof(unsigned long) != 8 || !myaddr || (myaddr & 3) ||
	    (myaddr >> 48) != 0xffff) {
		pr_err("re_mem: a verified live ARM64 getthisguy address is required\n");
		return -EINVAL;
	}
	pr_info("re_mem: getthisguy runtime address = 0x%lx\n", myaddr);
	getthisguy_fn = (getthisguy_fn_t)myaddr;
	guy = getthisguy_fn(0);
	if (IS_ERR_OR_NULL(guy))
		return guy ? PTR_ERR(guy) : -ENODEV;
	error = re_mem_driver_describe(guy, regions);
	if (error)
		return error;
	for (i = 0; i < ARRAY_SIZE(regions); i++) {
		struct re_mem_region *r = &regions[i];

		if (IS_ERR_OR_NULL(r->base) || !r->size ||
		    r->size > ULONG_MAX - (unsigned long)r->base ||
		    r->size > U64_MAX - r->ap_phys || r->size > U64_MAX - r->md_phys) {
			/* An unavailable optional region must not prevent using a valid one. */
			pr_warn("re_mem: region %u is unavailable\n", i + 1);
			memset(r, 0, sizeof(*r));
			continue;
		}
		pr_info("re_mem: region=%u size=0x%zx md=%pa ap=%pa virtual=%px\n",
			i + 1, r->size, &r->md_phys, &r->ap_phys, r->base);
	}
	error = select_region(region);
	if (error)
		return error;
	error = misc_register(&re_mem_device);
	if (error)
		pr_err("re_mem: misc_register failed: %d\n", error);
	else
		pr_info("re_mem: read-only module ready, region %u\n", region);
	return error;
}

static void __exit re_mem_exit(void)
{
	misc_deregister(&re_mem_device);
	/* All region mappings are borrowed. Their owner retains them. */
	pr_info("re_mem: unloaded explicitly\n");
}
module_init(re_mem_init);
module_exit(re_mem_exit);
MODULE_LICENSE("GPL");
MODULE_AUTHOR("Jaydyn");
MODULE_DESCRIPTION("Read-only vendor shared-memory region selector");
