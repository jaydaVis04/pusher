static int read_phys_ram(phys_addr_t phys, void *dst, size_t len)
{
    unsigned long pfn;
    unsigned long page_off;
    struct page *page;
    void *vaddr;

    pfn = PHYS_PFN(phys);
    page_off = offset_in_page(phys);

    if (!pfn_valid(pfn)) {
        pr_err("re_mem: PFN is not valid for phys=%pa\n", &phys);
        return -EINVAL;
    }

    if (page_off + len > PAGE_SIZE) {
        pr_err("re_mem: requested read crosses page boundary\n");
        return -EINVAL;
    }

    page = pfn_to_page(pfn);

    vaddr = kmap(page);
    if (!vaddr) {
        pr_err("re_mem: kmap failed\n");
        return -ENOMEM;
    }

    memcpy(dst,
           (u8 *)vaddr + page_off,
           len);

    kunmap(page);

    return 0;
}

// ADD THIS TOO

{
    phys_addr_t target = 0x63c0748a;
    u8 buf[16];
    int i;

    ret = read_phys_ram(target, buf, sizeof(buf));

    if (ret) {
        pr_err("re_mem: physical RAM test failed: %d\n", ret);
    } else {
        pr_info("re_mem: bytes at %pa:\n", &target);

        for (i = 0; i < sizeof(buf); i++)
            pr_info("re_mem: +0x%x = 0x%02x\n",
                    i, buf[i]);
    }
}
