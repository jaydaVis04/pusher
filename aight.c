#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/uaccess.h>
#include <linux/io.h>
#include <linux/slab.h>
#include <linux/mm.h>

MODULE_LICENSE("GPL");
MODULE_AUTHOR("re_mem");
MODULE_DESCRIPTION("Bounded physical memory read/write interface");

/*
 * Defaults match the physical window that previously worked:
 *
 *   0x64000000
 *       through
 *   0x73FFFFFF
 *
 * size = 0x10000000
 *
 * They can be overridden at insmod.
 */

static unsigned long long phys_base = 0x64000000ULL;
module_param(phys_base, ullong, 0400);

static unsigned long map_size = 0x10000000UL;
module_param(map_size, ulong, 0400);

#define MAX_MAP_SIZE 0x10000000UL

static void __iomem *mapped_base;


/* ========================================================= */
/* READ                                                      */
/* ========================================================= */

static ssize_t re_read(struct file *file,
		       char __user *user_buf,
		       size_t count,
		       loff_t *ppos)
{
	u8 *tmp;
	size_t total = 0;
	size_t chunk;
	size_t remaining;

	if (!mapped_base)
		return -ENODEV;

	if (*ppos < 0)
		return -EINVAL;

	if ((u64)*ppos >= map_size)
		return 0;

	remaining = map_size - (size_t)*ppos;

	if (count > remaining)
		count = remaining;

	if (!count)
		return 0;

	tmp = kmalloc(PAGE_SIZE, GFP_KERNEL);
	if (!tmp)
		return -ENOMEM;

	while (total < count) {

		chunk = min_t(size_t,
			      PAGE_SIZE,
			      count - total);

		memcpy_fromio(
			tmp,
			(u8 __iomem *)mapped_base +
				(size_t)*ppos +
				total,
			chunk
		);

		if (copy_to_user(user_buf + total,
				 tmp,
				 chunk)) {

			kfree(tmp);

			return total ?
				(ssize_t)total :
				-EFAULT;
		}

		total += chunk;
	}

	kfree(tmp);

	*ppos += total;

	return total;
}


/* ========================================================= */
/* WRITE                                                     */
/* ========================================================= */

static ssize_t re_write(struct file *file,
			const char __user *user_buf,
			size_t count,
			loff_t *ppos)
{
	u8 *tmp;
	size_t total = 0;
	size_t chunk;
	size_t remaining;

	if (!mapped_base)
		return -ENODEV;

	if (*ppos < 0)
		return -EINVAL;

	if ((u64)*ppos >= map_size)
		return -ENOSPC;

	remaining = map_size - (size_t)*ppos;

	if (count > remaining)
		count = remaining;

	if (!count)
		return 0;

	tmp = kmalloc(PAGE_SIZE, GFP_KERNEL);
	if (!tmp)
		return -ENOMEM;

	while (total < count) {

		chunk = min_t(size_t,
			      PAGE_SIZE,
			      count - total);

		if (copy_from_user(
			    tmp,
			    user_buf + total,
			    chunk)) {

			kfree(tmp);

			return total ?
				(ssize_t)total :
				-EFAULT;
		}

		memcpy_toio(
			(u8 __iomem *)mapped_base +
				(size_t)*ppos +
				total,
			tmp,
			chunk
		);

		/*
		 * Ensure the write becomes visible before
		 * continuing with another chunk.
		 */
		wmb();

		total += chunk;
	}

	kfree(tmp);

	*ppos += total;

	return total;
}


/* ========================================================= */
/* SEEK                                                      */
/* ========================================================= */

static loff_t re_llseek(struct file *file,
			loff_t offset,
			int whence)
{
	return fixed_size_llseek(
		file,
		offset,
		whence,
		map_size
	);
}


/* ========================================================= */
/* DEVICE                                                    */
/* ========================================================= */

static const struct file_operations re_fops = {
	.owner	= THIS_MODULE,
	.read	= re_read,
	.write	= re_write,
	.llseek	= re_llseek,
};


static struct miscdevice re_misc = {
	.minor	= MISC_DYNAMIC_MINOR,
	.name	= "re_mem",
	.fops	= &re_fops,
	.mode	= 0600,
};


/* ========================================================= */
/* INIT                                                      */
/* ========================================================= */

static int __init re_init(void)
{
	int ret;

	if (!phys_base) {
		pr_err("re_mem: phys_base cannot be zero\n");
		return -EINVAL;
	}

	if (!map_size || map_size > MAX_MAP_SIZE) {
		pr_err(
			"re_mem: invalid map_size 0x%lx\n",
			map_size
		);
		return -EINVAL;
	}

	pr_info(
		"re_mem: mapping phys 0x%llx - 0x%llx\n",
		phys_base,
		phys_base + map_size - 1
	);

	mapped_base = ioremap_wc(
		(phys_addr_t)phys_base,
		map_size
	);

	if (!mapped_base) {
		pr_err("re_mem: ioremap_wc failed\n");
		return -ENOMEM;
	}

	pr_info(
		"re_mem: mapped at kernel VA %p\n",
		mapped_base
	);

	ret = misc_register(&re_misc);

	if (ret) {
		pr_err(
			"re_mem: misc_register failed: %d\n",
			ret
		);

		iounmap(mapped_base);
		mapped_base = NULL;

		return ret;
	}

	pr_info(
		"re_mem: /dev/re_mem ready, read/write enabled\n"
	);

	return 0;
}


/* ========================================================= */
/* EXIT                                                      */
/* ========================================================= */

static void __exit re_exit(void)
{
	misc_deregister(&re_misc);

	if (mapped_base) {
		iounmap(mapped_base);
		mapped_base = NULL;
	}

	pr_info("re_mem: unloaded\n");
}


module_init(re_init);
module_exit(re_exit);
