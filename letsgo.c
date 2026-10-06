#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/uaccess.h>
#include <linux/io.h>
#include <linux/slab.h>
#include <linux/mm.h>

/*
 * Replace this with your actual header if these structs
 * are already defined there.
 *
 * Example:
 *
 * #include "omgbaby.h"
 */

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


/* --------------------------------------------------------- */
/* Runtime address of getthisguy()                           */
/* --------------------------------------------------------- */

static unsigned long myaddr;

module_param(myaddr, ulong, 0400);
MODULE_PARM_DESC(myaddr, "Runtime kernel address of getthisguy()");


/*
 * MUST match the real function prototype exactly.
 */
typedef struct THISGUY *(*getthisguy_fn_t)(int);


/* --------------------------------------------------------- */
/* Selected memory region                                    */
/* --------------------------------------------------------- */

/*
 * For now these point to var1.
 *
 * re_base is BORROWED from the original driver.
 * Do NOT iounmap() it.
 */
static void __iomem *re_base;
static size_t re_size;
static phys_addr_t re_phys;


/* --------------------------------------------------------- */
/* Debug printing                                            */
/* --------------------------------------------------------- */

static void print_x(const char *name, struct x *p)
{
    if (!p) {
        pr_info("re_mem: %s = NULL\n", name);
        return;
    }

    pr_info("re_mem: ---- %s ----\n", name);

    pr_info("re_mem: base_md_view_phy = %pa\n",
            &p->base_md_view_phy);

    pr_info("re_mem: base_ap_view_phy = %pa\n",
            &p->base_ap_view_phy);

    pr_info("re_mem: base_ap_view_vir = %px\n",
            p->base_ap_view_vir);

    pr_info("re_mem: size = 0x%x (%u)\n",
            p->size,
            p->size);
}


static void print_y(const char *name, struct y *p)
{
    if (!p) {
        pr_info("re_mem: %s = NULL\n", name);
        return;
    }

    pr_info("re_mem: ---- %s ----\n", name);

    pr_info("re_mem: id = %u\n",
            p->id);

    pr_info("re_mem: offset = 0x%x (%u)\n",
            p->offset,
            p->offset);

    pr_info("re_mem: size = 0x%x (%u)\n",
            p->size,
            p->size);

    pr_info("re_mem: flag = 0x%x (%u)\n",
            p->flag,
            p->flag);

    pr_info("re_mem: base_md_view_phy = %pa\n",
            &p->base_md_view_phy);

    pr_info("re_mem: base_ap_view_phy = %pa\n",
            &p->base_ap_view_phy);

    pr_info("re_mem: base_ap_view_vir = %px\n",
            p->base_ap_view_vir);
}


/* --------------------------------------------------------- */
/* /dev/re_mem read                                          */
/* --------------------------------------------------------- */

static ssize_t re_read(struct file *file,
                       char __user *user_buffer,
                       size_t count,
                       loff_t *offset)
{
    u8 *tmp;
    size_t available;
    size_t total = 0;
    size_t chunk;
    loff_t start_offset;

    if (!re_base || !re_size)
        return -ENODEV;

    if (*offset < 0)
        return -EINVAL;

    if ((u64)*offset >= re_size)
        return 0;

    start_offset = *offset;

    available = re_size - (size_t)*offset;

    if (count > available)
        count = available;

    if (!count)
        return 0;

    /*
     * Use ordinary kernel RAM as an intermediate buffer.
     * Read from __iomem into tmp, then copy tmp to userspace.
     */
    tmp = kmalloc(PAGE_SIZE, GFP_KERNEL);

    if (!tmp)
        return -ENOMEM;

    while (total < count) {

        chunk = min_t(size_t,
                      PAGE_SIZE,
                      count - total);

        memcpy_fromio(
            tmp,
            (u8 __iomem *)re_base +
                (size_t)start_offset +
                total,
            chunk
        );

        if (copy_to_user(user_buffer + total,
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

    pr_info_ratelimited(
        "re_mem: READ offset=0x%llx bytes=%zu\n",
        (unsigned long long)start_offset,
        total
    );

    return total;
}


/* --------------------------------------------------------- */
/* llseek                                                    */
/* --------------------------------------------------------- */

static loff_t re_llseek(struct file *file,
                        loff_t offset,
                        int whence)
{
    if (!re_size)
        return -ENODEV;

    return fixed_size_llseek(
        file,
        offset,
        whence,
        (loff_t)re_size
    );
}


/* --------------------------------------------------------- */
/* file_operations                                           */
/* --------------------------------------------------------- */

static const struct file_operations re_fops = {
    .owner  = THIS_MODULE,
    .read   = re_read,
    .llseek = re_llseek,
};


/* --------------------------------------------------------- */
/* misc device                                               */
/* --------------------------------------------------------- */

static struct miscdevice re_device = {
    .minor = MISC_DYNAMIC_MINOR,
    .name  = "re_mem",
    .fops  = &re_fops,
    .mode  = 0600,
};


/* --------------------------------------------------------- */
/* Module init                                               */
/* --------------------------------------------------------- */

static int __init re_init(void)
{
    getthisguy_fn_t getthisguy_fn;
    struct THISGUY *guy;
    int ret;

    pr_info("re_mem: loading\n");


    /* ----------------------------------------------------- */
    /* Check supplied runtime function address               */
    /* ----------------------------------------------------- */

    if (!myaddr) {
        pr_err("re_mem: myaddr was not provided\n");
        return -EINVAL;
    }

    pr_info(
        "re_mem: getthisguy runtime address = 0x%lx\n",
        myaddr
    );


    /* ----------------------------------------------------- */
    /* Call getthisguy(0)                                    */
    /* ----------------------------------------------------- */

    getthisguy_fn = (getthisguy_fn_t)myaddr;

    guy = getthisguy_fn(0);

    if (!guy) {
        pr_err(
            "re_mem: getthisguy(0) returned NULL\n"
        );

        return -ENODEV;
    }

    pr_info(
        "re_mem: THISGUY = %px\n",
        guy
    );


    /* ----------------------------------------------------- */
    /* Print all regions                                     */
    /* ----------------------------------------------------- */

    print_x("var1", &guy->var1);
    print_x("var2", &guy->var2);
    print_x("var3", &guy->var3);

    print_y("var4", guy->var4);
    print_y("var5", guy->var5);


    /* ----------------------------------------------------- */
    /* Select var1 for /dev/re_mem                           */
    /* ----------------------------------------------------- */

    re_base = guy->var1.base_ap_view_vir;
    re_size = guy->var1.size;
    re_phys = guy->var1.base_ap_view_phy;


    if (!re_base) {
        pr_err(
            "re_mem: var1 base_ap_view_vir is NULL\n"
        );

        re_size = 0;

        return -ENODEV;
    }


    if (!re_size) {
        pr_err(
            "re_mem: var1 size is zero\n"
        );

        re_base = NULL;

        return -EINVAL;
    }


    pr_info("re_mem: selected var1\n");

    pr_info(
        "re_mem: physical base = %pa\n",
        &re_phys
    );

    pr_info(
        "re_mem: virtual base  = %px\n",
        re_base
    );

    pr_info(
        "re_mem: region size   = 0x%zx (%zu bytes)\n",
        re_size,
        re_size
    );


    /* ----------------------------------------------------- */
    /* Register /dev/re_mem                                  */
    /* ----------------------------------------------------- */

    ret = misc_register(&re_device);

    if (ret) {

        pr_err(
            "re_mem: misc_register failed: %d\n",
            ret
        );

        re_base = NULL;
        re_size = 0;
        re_phys = 0;

        return ret;
    }


    pr_info(
        "re_mem: /dev/re_mem registered successfully\n"
    );

    return 0;
}


/* --------------------------------------------------------- */
/* Module exit                                               */
/* --------------------------------------------------------- */

static void __exit re_exit(void)
{
    misc_deregister(&re_device);

    re_base = NULL;
    re_size = 0;
    re_phys = 0;

    pr_info("re_mem: unloaded\n");
}


/* --------------------------------------------------------- */

module_init(re_init);
module_exit(re_exit);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Read-only interface to selected device memory region");
