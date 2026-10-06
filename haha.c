static int write_phys_u32(phys_addr_t phys, u32 value)
{
    unsigned long pfn;
    unsigned long page_off;
    struct page *page;
    void *vaddr;

    pfn = PHYS_PFN(phys);
    page_off = offset_in_page(phys);

    if (!pfn_valid(pfn))
        return -EINVAL;

    if (page_off + sizeof(value) > PAGE_SIZE)
        return -EINVAL;

    page = pfn_to_page(pfn);

    vaddr = kmap(page);
    if (!vaddr)
        return -ENOMEM;

    memcpy((u8 *)vaddr + page_off,
           &value,
           sizeof(value));

    flush_dcache_page(page);

    kunmap(page);

    return 0;
}

// this is good too
phys_addr_t ptr_location = 0x6478f29c;
u32 new_ptr = /* desired base_md_view_phy value */;

ret = write_phys_u32(ptr_location, new_ptr);

if (ret)
    pr_err("re_mem: pointer patch failed: %d\n", ret);
else
    pr_info("re_mem: patched PTR_DAT_9078f29c to 0x%08x\n",
            new_ptr);
