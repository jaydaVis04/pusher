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
 * Use your REAL header instead if these are already defined there:
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


/* ========================================================= */
/* Module parameters                                         */
/* ========================================================= */

/*
 * LIVE runtime address of getthisguy().
 *
 * Example:
 *
 * insmod re_mem_region.ko \
 *     myaddr=0xffffffXXXXXXXXXX \
 *     region=3
 */
static unsigned long myaddr;

module_param(myaddr, ulong, 0400);
MODULE_PARM_DESC(myaddr,
                 "Live runtime address of getthisguy");


/*
 * Region selection:
 *
 * 1 -> var1
 * 2 -> var2
 * 3 -> var3
 * 4 -> var4
 * 5 -> var5
 */
static unsigned int region = 2;

module_param(region, uint, 0400);
MODULE_PARM_DESC(region,
                 "Region to expose through /dev/re_mem (1-5)");


/* ========================================================= */
/* Function pointer                                          */
/* ========================================================= */

/*
 * MUST exactly match the real function prototype.
 */
typedef struct THISGUY *(*getthisguy_fn_t)(int);


/* ========================================================= */
/* Selected region                                           */
/* ========================================================= */

static void __iomem *re_base;
static size_t re_size;
static phys_addr_t re_phys;


/* ========================================================= */
/* Debug helpers                                             */
/* ========================================================= */

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


/* ========================================================= */
/* /dev/re_mem read                                          */
/* ========================================================= */

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

    /*
     * EOF once user reaches the end of the selected region.
     */
    if ((u64)*offset >= re_size)
        return 0;

    start_offset = *offset;

    available = re_size - (size_t)*offset;

    /*
     * Never allow a read beyond the selected region.
     */
    if (count > available)
        count = available;

    if (!count)
        return 0;

    /*
     * Temporary normal kernel RAM.
     *
     * We copy:
     *
     * __iomem -> tmp -> userspace
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

            /*
             * If some bytes already succeeded,
             * return the partial amount.
             */
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
        "re_mem: READ region=%u offset=0x%llx bytes=%zu\n",
        region,
        (unsigned long long)start_offset,
        total
    );

    return total;
}


/* ========================================================= */
/* llseek                                                    */
/* ========================================================= */

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


/* ========================================================= */
/* File operations                                           */
/* ========================================================= */

static const struct file_operations re_fops = {
    .owner  = THIS_MODULE,
    .read   = re_read,
    .llseek = re_llseek,
};


/* ========================================================= */
/* Misc device                                               */
/* ========================================================= */

static struct miscdevice re_device = {
    .minor = MISC_DYNAMIC_MINOR,
    .name  = "re_mem",
    .fops  = &re_fops,
    .mode  = 0600,
};


/* ========================================================= */
/* Module initialization                                     */
/* ========================================================= */

static int __init re_init(void)
{
    getthisguy_fn_t getthisguy_fn;
    struct THISGUY *guy;
    int ret;

    pr_info("re_mem: loading re_mem_region\n");


    /* ----------------------------------------------------- */
    /* Check getthisguy runtime address                      */
    /* ----------------------------------------------------- */

    if (!myaddr) {
        pr_err("re_mem: myaddr was not provided\n");
        return -EINVAL;
    }

    pr_info("re_mem: getthisguy runtime address = 0x%lx\n",
            myaddr);


    /* ----------------------------------------------------- */
    /* Call getthisguy(0)                                    */
    /* ----------------------------------------------------- */

    getthisguy_fn = (getthisguy_fn_t)myaddr;

    guy = getthisguy_fn(0);

    if (!guy) {
        pr_err("re_mem: getthisguy(0) returned NULL\n");
        return -ENODEV;
    }

    pr_info("re_mem: THISGUY = %px\n", guy);


    /* ----------------------------------------------------- */
    /* Print all five region structures                      */
    /* ----------------------------------------------------- */

    print_x("var1", &guy->var1);
    print_x("var2", &guy->var2);
    print_x("var3", &guy->var3);

    print_y("var4", guy->var4);
    print_y("var5", guy->var5);


    /* ----------------------------------------------------- */
    /* Select region                                         */
    /* ----------------------------------------------------- */

    switch (region) {

    case 1:

        re_base = guy->var1.base_ap_view_vir;
        re_size = guy->var1.size;
        re_phys = guy->var1.base_ap_view_phy;

        break;


    case 2:

        re_base = guy->var2.base_ap_view_vir;
        re_size = guy->var2.size;
        re_phys = guy->var2.base_ap_view_phy;

        break;


    case 3:

        re_base = guy->var3.base_ap_view_vir;
        re_size = guy->var3.size;
        re_phys = guy->var3.base_ap_view_phy;

        break;


    case 4:

        if (!guy->var4) {
            pr_err("re_mem: var4 is NULL\n");
            return -ENODEV;
        }

        re_base = guy->var4->base_ap_view_vir;
        re_size = guy->var4->size;
        re_phys = guy->var4->base_ap_view_phy;

        break;


    case 5:

        if (!guy->var5) {
            pr_err("re_mem: var5 is NULL\n");
            return -ENODEV;
        }

        re_base = guy->var5->base_ap_view_vir;
        re_size = guy->var5->size;
        re_phys = guy->var5->base_ap_view_phy;

        break;


    default:

        pr_err("re_mem: invalid region %u; use 1-5\n",
               region);

        return -EINVAL;
    }


    /* ----------------------------------------------------- */
    /* Validate region                                       */
    /* ----------------------------------------------------- */

    if (!re_base) {

        pr_err(
            "re_mem: region %u has no AP virtual mapping\n",
            region
        );

        re_size = 0;
        re_phys = 0;

        return -ENODEV;
    }


    if (!re_size) {

        pr_err(
            "re_mem: region %u has size zero\n",
            region
        );

        re_base = NULL;
        re_phys = 0;

        return -EINVAL;
    }


    /* ----------------------------------------------------- */
    /* Print selected mapping                                */
    /* ----------------------------------------------------- */

    pr_info("re_mem: selected region %u\n",
            region);

    pr_info("re_mem: physical base = %pa\n",
            &re_phys);

    pr_info("re_mem: virtual base  = %px\n",
            re_base);

    pr_info("re_mem: region size   = 0x%zx (%zu bytes)\n",
            re_size,
            re_size);


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


/* ========================================================= */
/* Module unload                                             */
/* ========================================================= */

static void __exit re_exit(void)
{
    misc_deregister(&re_device);

    /*
     * IMPORTANT:
     *
     * re_base is BORROWED from the original driver.
     *
     * We did not create this mapping, therefore:
     *
     * DO NOT iounmap(re_base);
     */

    re_base = NULL;
    re_size = 0;
    re_phys = 0;

    pr_info("re_mem: re_mem_region unloaded\n");
}


/* ========================================================= */

module_init(re_init);
module_exit(re_exit);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION(
    "Read-only bounded interface to selected shared-memory region"
);
