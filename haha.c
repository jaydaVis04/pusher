#define TEST_OFF 0x100

{
    phys_addr_t ptr_location = 0x6478f29c;
    phys_addr_t md_target;
    void __iomem *ap_target;

    u32 original_ptr = 0;
    u32 new_ptr;
    u32 check_ptr = 0;

    u8 old_byte;
    u8 test_byte = 0x5a;
    u8 check_byte;

    if (!guy->var5) {
        pr_err("re_mem: var5 is NULL\n");
        return -ENODEV;
    }

    if (!guy->var5->base_ap_view_vir) {
        pr_err("re_mem: var5 has no AP virtual mapping\n");
        return -ENODEV;
    }

    if (TEST_OFF >= guy->var5->size) {
        pr_err("re_mem: TEST_OFF outside var5\n");
        return -EINVAL;
    }

    /*
     * Same shared-memory location viewed two different ways.
     */
    md_target =
        guy->var5->base_md_view_phy + TEST_OFF;

    ap_target =
        (u8 __iomem *)guy->var5->base_ap_view_vir + TEST_OFF;

    /*
     * lbu uses pointer + 0xe, therefore store
     * target - 0xe in PTR_DAT.
     */
    new_ptr = (u32)(md_target - 0xe);

    pr_info("re_mem: var5 test offset = 0x%x\n", TEST_OFF);
    pr_info("re_mem: MD target = %pa\n", &md_target);
    pr_info("re_mem: AP virtual target = %px\n", ap_target);
    pr_info("re_mem: new firmware pointer = 0x%08x\n", new_ptr);

    /*
     * Save what was originally in PTR_DAT_9078f29c.
     */
    ret = read_phys_ram(ptr_location,
                        &original_ptr,
                        sizeof(original_ptr));

    if (ret) {
        pr_err("re_mem: couldn't read original PTR: %d\n", ret);
        return ret;
    }

    pr_info("re_mem: original PTR = 0x%08x\n",
            original_ptr);


    /*
     * Put a recognizable byte in var5 shared memory.
     */
    old_byte = readb(ap_target);

    pr_info("re_mem: old shared byte = 0x%02x\n",
            old_byte);

    writeb(test_byte, ap_target);

    check_byte = readb(ap_target);

    pr_info("re_mem: shared byte readback = 0x%02x expected=0x%02x\n",
            check_byte,
            test_byte);


    /*
     * Now redirect PTR_DAT_9078f29c.
     */
    ret = write_phys_u32(ptr_location, new_ptr);

    if (ret) {
        pr_err("re_mem: pointer patch failed: %d\n", ret);
        return ret;
    }

    /*
     * Verify the literal changed.
     */
    ret = read_phys_ram(ptr_location,
                        &check_ptr,
                        sizeof(check_ptr));

    if (ret) {
        pr_err("re_mem: pointer readback failed: %d\n", ret);
        return ret;
    }

    pr_info("re_mem: PTR readback = 0x%08x expected=0x%08x\n",
            check_ptr,
            new_ptr);
}
