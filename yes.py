static int __init re_init(void)
{
    unsigned long addr;
    getthisguy_fn_t getthisguy_fn;
    struct THISGUY *guy;
    int ret;

    addr = kallsyms_lookup_name("getthisguy");

    if (!addr) {
        pr_err("re_mem: could not find getthisguy\n");
        return -ENOENT;
    }

    pr_info("re_mem: getthisguy address = 0x%lx\n", addr);

    getthisguy_fn = (getthisguy_fn_t)addr;

    guy = getthisguy_fn(0);

    if (!guy) {
        pr_err("re_mem: getthisguy(0) returned NULL\n");
        return -ENODEV;
    }

    pr_info("re_mem: THISGUY = %px\n", guy);
    pr_info("re_mem: var4 = %px\n", guy->var4);
    pr_info("re_mem: var5 = %px\n", guy->var5);

    ret = misc_register(&re_device);
    if (ret) {
        pr_err("re_mem: misc_register failed: %d\n", ret);
        return ret;
    }

    pr_info("re_mem: loaded\n");
    return 0;
}
