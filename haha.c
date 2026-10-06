{
    u32 check = 0;

    ret = read_phys_ram(0x6478f29c, &check, sizeof(check));

    if (ret)
        pr_err("re_mem: pointer readback failed: %d\n", ret);
    else
        pr_info("re_mem: pointer readback = 0x%08x\n", check);
}
