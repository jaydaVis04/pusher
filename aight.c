#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/uaccess.h>
#include <linux/slab.h>
#include <linux/io.h>
#include <linux/mm.h>
#include <linux/types.h>

MODULE_LICENSE("GPL");
MODULE_AUTHOR("re_mem");
MODULE_DESCRIPTION("Read-only MediaTek memory-region reader");

/*
 * Live runtime address of:
 *
 *     struct THISGUY *getthisguy(int id);
 *
 * Supply with:
 *
 *     myaddr=0x...
 */
static unsigned long myaddr;
module_param(myaddr, ulong, 0400);
MODULE_PARM_DESC(myaddr, "Live runtime address of getthisguy()");

/*
 * Top-level region:
 *
 *   1 = var1
 *   2 = var2
 *   3 = var3
 *
 * We are currently using region=2.
 */
static int region = 2;
module_param(region, int, 0400);
MODULE_PARM_DESC(region, "Top-level memory region (1-3)");

#define SMEM_ENTRY_COUNT 22
#define TARGET_OFFSET    0xFC04

/*
 * Top-level memory region.
 */
struct x {
	phys_addr_t base_md_view_phy;
	phys_addr_t base_ap_view_phy;
	void __iomem *base_ap_view_vir;
	unsigned int size;
};

/*
 * Shared-memory subregion descriptor.
 */
struct y {
	unsigned int id;
	unsigned int offset;
	unsigned int size;
	unsigned int flag;

	phys_addr_t base_md_view_phy;
	phys_addr_t base_ap_view_phy;
	void __iomem *base_ap_view_vir;
};

/*
 * Structure returned by getthisguy().
 */
struct THISGUY {
	struct x var1;
	struct x var2;
	struct x var3;

	struct y *var4;
	struct y *var5;
};

typedef struct THISGUY *(*getthisguy_fn_t)(int id);

static struct THISGUY *guy;

static void __iomem *re_base;
static unsigned int re_size;

/* --------------------------------------------------------- */
/* /dev/re_mem read                                          */
/* --------------------------------------------------------- */

static ssize_t re_read(struct file *file,
		       char __user *user_buf,
		       size_t count,
		       loff_t *ppos)
{
	size_t remaining;
	size_t chunk;
	size_t copied = 0;
	u8 *tmp;

	if (!re_base || !re_size)
		return -ENODEV;

	if (*ppos < 0)
		return -EINVAL;

	if (*ppos >= re_size)
		return 0;

	remaining = re_size - *ppos;

	if (count > remaining)
		count = remaining;

	tmp = kmalloc(PAGE_SIZE, GFP_KERNEL);
	if (!tmp)
		return -ENOMEM;

	while (copied < count) {
		chunk = min_t(size_t, PAGE_SIZE, count - copied);

		memcpy_fromio(
			tmp,
			(u8 __iomem *)re_base + *ppos + copied,
			chunk
		);

		if (copy_to_user(user_buf + copied, tmp, chunk)) {
			kfree(tmp);
			return copied ? copied : -EFAULT;
		}

		copied += chunk;
	}

	kfree(tmp);

	*ppos += copied;

	return copied;
}

/* --------------------------------------------------------- */
/* /dev/re_mem seek                                          */
/* --------------------------------------------------------- */

static loff_t re_llseek(struct file *file,
			loff_t offset,
			int whence)
{
	return fixed_size_llseek(file, offset, whence, re_size);
}

static const struct file_operations re_fops = {
	.owner  = THIS_MODULE,
	.read   = re_read,
	.llseek = re_llseek,
};

static struct miscdevice re_miscdev = {
	.minor = MISC_DYNAMIC_MINOR,
	.name  = "re_mem",
	.fops  = &re_fops,
	.mode  = 0600,
};

/* --------------------------------------------------------- */
/* Debug helpers                                             */
/* --------------------------------------------------------- */

static void dump_top_region(const char *name, struct x *r)
{
	pr_info(
		"re_mem: %s md_phys=0x%llx ap_phys=0x%llx ap_virt=%p size=0x%x\n",
		name,
		(unsigned long long)r->base_md_view_phy,
		(unsigned long long)r->base_ap_view_phy,
		r->base_ap_view_vir,
		r->size
	);
}

/*
 * Dump the runtime var4 shared-memory table and determine
 * which entry contains Region-2 offset 0xFC04.
 */
static void dump_var4_table(struct THISGUY *g)
{
	int i;
	phys_addr_t target_phys;

	if (!g->var4) {
		pr_err("re_mem: var4 is NULL\n");
		return;
	}

	target_phys = g->var2.base_ap_view_phy + TARGET_OFFSET;

	pr_info("re_mem: scanning %d var4 entries\n",
		SMEM_ENTRY_COUNT);

	pr_info("re_mem: target Region2+0xFC04 AP phys = 0x%llx\n",
		(unsigned long long)target_phys);

	for (i = 0; i < SMEM_ENTRY_COUNT; i++) {
		struct y *r = &g->var4[i];
		phys_addr_t start = r->base_ap_view_phy;
		phys_addr_t end = start + r->size;

		pr_info(
			"re_mem: var4[%02d] id=%u off=0x%x size=0x%x "
			"ap_phys=0x%llx end_phys=0x%llx\n",
			i,
			r->id,
			r->offset,
			r->size,
			(unsigned long long)start,
			(unsigned long long)end
		);

		if (start <= target_phys && target_phys < end) {
			pr_info(
				"re_mem: *** FC04 PHYS OWNER *** "
				"index=%d id=%u relative=0x%llx\n",
				i,
				r->id,
				(unsigned long long)(target_phys - start)
			);
		}
	}
}

/* --------------------------------------------------------- */
/* Module init                                               */
/* --------------------------------------------------------- */

static int __init re_mem_init(void)
{
	getthisguy_fn_t getthisguy_fn;
	struct x *selected;
	int ret;

	pr_info("re_mem: loading\n");

	if (!myaddr) {
		pr_err("re_mem: myaddr was not supplied\n");
		return -EINVAL;
	}

	if (region < 1 || region > 3) {
		pr_err("re_mem: region must be 1, 2, or 3\n");
		return -EINVAL;
	}

	/*
	 * myaddr must be the CURRENT LIVE kernel address,
	 * not the static Ghidra/ELF address.
	 */
	getthisguy_fn = (getthisguy_fn_t)myaddr;

	pr_info(
		"re_mem: calling getthisguy at 0x%lx\n",
		myaddr
	);

	guy = getthisguy_fn(0);

	if (!guy) {
		pr_err("re_mem: getthisguy(0) returned NULL\n");
		return -ENODEV;
	}

	pr_info("re_mem: getthisguy returned %p\n", guy);

	/*
	 * Print the three major regions.
	 */
	dump_top_region("var1", &guy->var1);
	dump_top_region("var2", &guy->var2);
	dump_top_region("var3", &guy->var3);

	/*
	 * NEW PART:
	 *
	 * Inspect the 22 runtime SMEM descriptors and see which
	 * actually owns Region-2 offset 0xFC04.
	 */
	dump_var4_table(guy);

	switch (region) {
	case 1:
		selected = &guy->var1;
		break;

	case 2:
		selected = &guy->var2;
		break;

	case 3:
		selected = &guy->var3;
		break;

	default:
		return -EINVAL;
	}

	if (!selected->base_ap_view_vir) {
		pr_err(
			"re_mem: selected region has NULL AP virtual address\n"
		);
		return -ENODEV;
	}

	if (!selected->size) {
		pr_err(
			"re_mem: selected region has zero size\n"
		);
		return -ENODEV;
	}

	/*
	 * Borrow the mapping already established by the MediaTek
	 * driver. Do NOT ioremap() or iounmap() it here.
	 */
	re_base = selected->base_ap_view_vir;
	re_size = selected->size;

	pr_info(
		"re_mem: selected region=%d base=%p size=0x%x\n",
		region,
		re_base,
		re_size
	);

	ret = misc_register(&re_miscdev);

	if (ret) {
		pr_err(
			"re_mem: misc_register failed: %d\n",
			ret
		);

		re_base = NULL;
		re_size = 0;

		return ret;
	}

	pr_info(
		"re_mem: /dev/re_mem ready (read-only)\n"
	);

	return 0;
}

/* --------------------------------------------------------- */
/* Module exit                                               */
/* --------------------------------------------------------- */

static void __exit re_mem_exit(void)
{
	misc_deregister(&re_miscdev);

	/*
	 * re_base is a borrowed mapping.
	 * Do NOT iounmap() it.
	 */
	re_base = NULL;
	re_size = 0;
	guy = NULL;

	pr_info("re_mem: unloaded\n");
}

module_init(re_mem_init);
module_exit(re_mem_exit);
