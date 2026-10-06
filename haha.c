{
    phys_addr_t dump_addr = 0x6478f27c;
    u8 buf[0x40];
    int i;

    ret = read_phys_ram(dump_addr, buf, sizeof(buf));

    if (ret) {
        pr_err("re_mem: dump failed: %d\n", ret);
    } else {
        pr_info("re_mem: dump phys %pa (Ghidra 0x9078f27c):\n",
                &dump_addr);

        for (i = 0; i < sizeof(buf); i += 16) {
            pr_info("re_mem: +0x%02x: "
                    "%02x %02x %02x %02x "
                    "%02x %02x %02x %02x "
                    "%02x %02x %02x %02x "
                    "%02x %02x %02x %02x\n",
                    i,
                    buf[i+0],  buf[i+1],
                    buf[i+2],  buf[i+3],
                    buf[i+4],  buf[i+5],
                    buf[i+6],  buf[i+7],
                    buf[i+8],  buf[i+9],
                    buf[i+10], buf[i+11],
                    buf[i+12], buf[i+13],
                    buf[i+14], buf[i+15]);
        }
    }
}
