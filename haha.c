{
    void __iomem *ap_addr;
    phys_addr_t md_addr;
    u8 value;

    if (!guy->var5 || !guy->var5->base_ap_view_vir) {
        pr_err("re_mem: var5 unavailable\n");
        return -ENODEV;
    }

    if (0x100 >= guy->var5->size) {
        pr_err("re_mem: offset 0x100 outside var5\n");
        return -EINVAL;
    }

    md_addr = guy->var5->base_md_view_phy + 0x100;

    ap_addr =
        (u8 __iomem *)guy->var5->base_ap_view_vir + 0x100;

    value = readb(ap_addr);

    pr_info("re_mem: OBSERVE md=%pa ap=%px offset=0x100 value=0x%02x\n",
            &md_addr,
            ap_addr,
            value);
}
