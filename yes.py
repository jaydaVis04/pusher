static int __init re_init(void)
{
    getthisguy_fn_t getthisguy_fn;
    struct THISGUY *guy;
    int ret;

    if (!getthisguy_addr) {
        pr_err("re_mem: getthisguy_addr was not provided\n");
        return -EINVAL;
    }

    pr_info("re_mem: getthisguy runtime addr = 0x%lx\n",
            getthisguy_addr);

    getthisguy_fn = (getthisguy_fn_t)getthisguy_addr;

    guy = getthisguy_fn(0);

    if (!guy) {
        pr_err("re_mem: getthisguy(0) returned NULL\n");
        return -ENODEV;
    }

    pr_info("re_mem: THISGUY=%px\n", guy);
    pr_info("re_mem: var4=%px\n", guy->var4);
    pr_info("re_mem: var5=%px\n", guy->var5);

    /* your existing mapping setup stays here */

    ret = misc_register(&re_device);
    if (ret)
        return ret;

    return 0;
}
