static int __init re_init(void)
{
    struct THISGUY *guy;
    int ret;

    /* however you obtain THISGUY */
    guy = get_thisguy();

    if (!guy) {
        pr_err("re_mem: THISGUY is NULL\n");
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
