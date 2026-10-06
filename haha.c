static unsigned int test_value = 1;
module_param(test_value, uint, 0400);
MODULE_PARM_DESC(test_value, "Byte value for var5 experiment: 0 or 1");

static u32 saved_original_ptr;
static u8 saved_original_byte;
static void __iomem *saved_test_ap_addr;
static bool experiment_active;

#define TEST_OFF      0x100
#define PTR_LOCATION  ((phys_addr_t)0x6478f29c)

// next
// re init

{
    phys_addr_t md_target;
    void __iomem *ap_target;
    u32 new_ptr;
    u32 ptr_check = 0;
    u8 byte_check;

    if (test_value > 1) {
        pr_err("re_mem: test_value must be 0 or 1\n");
        return -EINVAL;
    }

    if (!guy->var5) {
        pr_err("re_mem: var5 is NULL\n");
        return -ENODEV;
    }

    if (!guy->var5->base_ap_view_vir) {
        pr_err("re_mem: var5 AP mapping is NULL\n");
        return -ENODEV;
    }

    if (TEST_OFF >= guy->var5->size) {
        pr_err("re_mem: TEST_OFF outside var5\n");
        return -EINVAL;
    }

    /*
     * Same shared-memory byte:
     *
     * modem sees:
     *     base_md_view_phy + TEST_OFF
     *
     * AP sees:
     *     base_ap_view_vir + TEST_OFF
     */
    md_target =
        guy->var5->base_md_view_phy + TEST_OFF;

    ap_target =
        (u8 __iomem *)guy->var5->base_ap_view_vir + TEST_OFF;

    /*
     * Firmware instruction is:
     *
     *     lbu ..., 0xe(pointer)
     *
     * therefore:
     *
     *     pointer = desired_MD_address - 0xe
     */
    new_ptr = (u32)(md_target - 0xe);

    pr_info("re_mem: --- experiment setup ---\n");
    pr_info("re_mem: TEST_OFF = 0x%x\n", TEST_OFF);
    pr_info("re_mem: MD target = %pa\n", &md_target);
    pr_info("re_mem: AP target = %px\n", ap_target);
    pr_info("re_mem: test value = 0x%02x\n",
            (u8)test_value);
    pr_info("re_mem: new PTR = 0x%08x\n",
            new_ptr);


    /*
     * Save original firmware pointer.
     */
    ret = read_phys_ram(PTR_LOCATION,
                        &saved_original_ptr,
                        sizeof(saved_original_ptr));

    if (ret) {
        pr_err("re_mem: couldn't save original PTR: %d\n",
               ret);
        return ret;
    }


    /*
     * Save original shared byte.
     */
    saved_original_byte = readb(ap_target);
    saved_test_ap_addr = ap_target;

    pr_info("re_mem: saved original PTR = 0x%08x\n",
            saved_original_ptr);

    pr_info("re_mem: saved original byte = 0x%02x\n",
            saved_original_byte);


    /*
     * Put our controlled boolean into shared memory.
     */
    writeb((u8)test_value, ap_target);

    /*
     * Ensure the data write happens before redirecting
     * the firmware pointer.
     */
    wmb();

    byte_check = readb(ap_target);

    pr_info("re_mem: shared byte = 0x%02x expected=0x%02x\n",
            byte_check,
            (u8)test_value);


    /*
     * Redirect PTR_DAT_9078f29c.
     */
    ret = write_phys_u32(PTR_LOCATION, new_ptr);

    if (ret) {
        pr_err("re_mem: pointer patch failed: %d\n", ret);

        /* restore byte because pointer patch didn't happen */
        writeb(saved_original_byte, ap_target);
        saved_test_ap_addr = NULL;

        return ret;
    }


    /*
     * Confirm pointer write.
     */
    ret = read_phys_ram(PTR_LOCATION,
                        &ptr_check,
                        sizeof(ptr_check));

    if (ret) {
        pr_err("re_mem: pointer readback failed: %d\n",
               ret);
        return ret;
    }

    pr_info("re_mem: PTR readback = 0x%08x expected=0x%08x\n",
            ptr_check,
            new_ptr);

    experiment_active = true;

    pr_info("re_mem: EXPERIMENT ACTIVE\n");
}

// re exit
static void __exit re_exit(void)
{
    int ret;

    if (experiment_active) {

        /*
         * Restore firmware pointer FIRST.
         */
        ret = write_phys_u32(PTR_LOCATION,
                             saved_original_ptr);

        if (ret) {
            pr_err("re_mem: FAILED to restore original PTR: %d\n",
                   ret);
        } else {
            pr_info("re_mem: restored original PTR = 0x%08x\n",
                    saved_original_ptr);
        }

        /*
         * Make sure firmware pointer restoration becomes
         * visible before altering our test byte.
         */
        wmb();

        if (saved_test_ap_addr) {
            writeb(saved_original_byte,
                   saved_test_ap_addr);

            pr_info("re_mem: restored shared byte = 0x%02x\n",
                    saved_original_byte);
        }

        experiment_active = false;
    }

    misc_deregister(&re_device);

    pr_info("re_mem: unloaded\n");
}
