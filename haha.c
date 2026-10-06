static int read_phys_ram(phys_addr_t phys, void *dst, size_t len)
{
    unsigned long pfn;
    unsigned long page_off;
    struct page *page;
    void *vaddr;

    pfn = PHYS_PFN(phys);
    page_off = offset_in_page(phys);

    if (!pfn_valid(pfn)) {
        pr_err("re_mem: invalid RAM PFN for %pa\n", &phys);
        return -EINVAL;
    }

    if (page_off + len > PAGE_SIZE) {
        pr_err("re_mem: read crosses page boundary\n");
        return -EINVAL;
    }

    page = pfn_to_page(pfn);

    vaddr = kmap_local_page(page);

    memcpy(dst,
           (u8 *)vaddr + page_off,
           len);

    kunmap_local(vaddr);

    return 0;
}
