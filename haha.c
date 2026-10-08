#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/uaccess.h>
#include <linux/mm.h>
#include <linux/highmem.h>
#include <linux/slab.h>
#include <linux/string.h>


/*
 * Physical RAM page we want to observe.
 *
 * 0x63c0748a is inside this page:
 *
 * 0x63c0748a - 0x63c07000 = 0x48a
 */
static unsigned long phys_base = 0x63c07000;

module_param(phys_base, ulong, 0400);
MODULE_PARM_DESC(
    phys_base,
    "Physical page base to expose (must be page aligned)"
);


/* ========================================================= */
/* Read normal System RAM                                    */
/* ========================================================= */

static int read_phys_ram(phys_addr_t phys,
                         void *dst,
                         size_t len)
{
    unsigned long pfn;
    unsigned long page_off;
    struct page *page;
    void *vaddr;

    pfn = PHYS_PFN(phys);
    page_off = offset_in_page(phys);

    /*
     * This helper only allows access within one page.
     */
    if (page_off + len > PAGE_SIZE)
        return -EINVAL;

    /*
     * Make sure this corresponds to normal RAM.
     */
    if (!pfn_valid(pfn)) {
        pr_err(
            "re_screen_snapshot: invalid PFN for phys=%pa\n",
            &phys
        );

        return -EINVAL;
    }

    page = pfn_to_page(pfn);

    /*
     * Your kernel uses the older kmap()/kunmap() API.
     */
    vaddr = kmap(page);

    if (!vaddr) {
        pr_err("re_screen_snapshot: kmap failed\n");
        return -ENOMEM;
    }

    memcpy(
        dst,
        (u8 *)vaddr + page_off,
        len
    );

    kunmap(page);

    return 0;
}


/* ========================================================= */
/* /dev/re_screen_snapshot read                              */
/* ========================================================= */

static ssize_t snapshot_read(struct file *file,
                             char __user *user_buffer,
                             size_t count,
                             loff_t *offset)
{
    u8 *tmp;
    size_t available;
    size_t total = 0;
    size_t chunk;
    phys_addr_t phys;
    int ret;

    if (*offset < 0)
        return -EINVAL;

    /*
     * Device exposes exactly one 4 KiB page.
     */
    if ((u64)*offset >= PAGE_SIZE)
        return 0;

    available = PAGE_SIZE - (size_t)*offset;

    if (count > available)
        count = available;

    if (!count)
        return 0;

    tmp = kmalloc(PAGE_SIZE, GFP_KERNEL);

    if (!tmp)
        return -ENOMEM;

    while (total < count) {

        chunk = count - total;

        /*
         * Since our entire device is one page,
         * this should never exceed PAGE_SIZE.
         */
        if (chunk > PAGE_SIZE)
            chunk = PAGE_SIZE;

        phys =
            (phys_addr_t)phys_base +
            (phys_addr_t)*offset +
            total;

        ret = read_phys_ram(
            phys,
            tmp,
            chunk
        );

        if (ret) {
            kfree(tmp);

            if (total) {
                *offset += total;
                return total;
            }

            return ret;
        }

        if (copy_to_user(
                user_buffer + total,
                tmp,
                chunk)) {

            kfree(tmp);

            if (total) {
                *offset += total;
                return total;
            }

            return -EFAULT;
        }

        total += chunk;
    }

    kfree(tmp);

    *offset += total;

    return total;
}


/* ========================================================= */
/* llseek                                                    */
/* ========================================================= */

static loff_t snapshot_llseek(struct file *file,
                              loff_t offset,
                              int whence)
{
    return fixed_size_llseek(
        file,
        offset,
        whence,
        PAGE_SIZE
    );
}


/* ========================================================= */
/* File operations                                           */
/* ========================================================= */

static const struct file_operations snapshot_fops = {
    .owner  = THIS_MODULE,
    .read   = snapshot_read,
    .llseek = snapshot_llseek,
};


/* ========================================================= */
/* Misc device                                               */
/* ========================================================= */

static struct miscdevice snapshot_device = {
    .minor = MISC_DYNAMIC_MINOR,
    .name  = "re_screen_snapshot",
    .fops  = &snapshot_fops,
    .mode  = 0600,
};


/* ========================================================= */
/* Init                                                      */
/* ========================================================= */

static int __init snapshot_init(void)
{
    phys_addr_t base;
    phys_addr_t target;
    unsigned long pfn;
    int ret;

    base = (phys_addr_t)phys_base;

    /*
     * Require page-aligned base.
     */
    if (offset_in_page(base) != 0) {
        pr_err(
            "re_screen_snapshot: phys_base must be page aligned\n"
        );

        return -EINVAL;
    }

    pfn = PHYS_PFN(base);

    if (!pfn_valid(pfn)) {
        pr_err(
            "re_screen_snapshot: physical page %pa is not valid System RAM\n",
            &base
        );

        return -EINVAL;
    }

    target = base + 0x48a;

    pr_info("re_screen_snapshot: loading\n");
    pr_info("re_screen_snapshot: physical page = %pa\n",
            &base);
    pr_info("re_screen_snapshot: page size = 0x%lx\n",
            PAGE_SIZE);

    pr_info(
        "re_screen_snapshot: target offset 0x48a = %pa\n",
        &target
    );

    ret = misc_register(&snapshot_device);

    if (ret) {
        pr_err(
            "re_screen_snapshot: misc_register failed: %d\n",
            ret
        );

        return ret;
    }

    pr_info(
        "re_screen_snapshot: /dev/re_screen_snapshot registered\n"
    );

    return 0;
}


/* ========================================================= */
/* Exit                                                      */
/* ========================================================= */

static void __exit snapshot_exit(void)
{
    misc_deregister(&snapshot_device);

    pr_info("re_screen_snapshot: unloaded\n");
}


/* ========================================================= */

module_init(snapshot_init);
module_exit(snapshot_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Jaydyn");
MODULE_DESCRIPTION(
    "Read-only 4 KiB physical System RAM snapshot interface"
);
