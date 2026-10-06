// above re_init
static void check_md_region(const char *name,
                            phys_addr_t md_base,
                            void __iomem *ap_virt,
                            size_t size,
                            phys_addr_t target)
{
    phys_addr_t end;
    phys_addr_t off;
    void __iomem *ap_target;
    u8 value;

    if (!size)
        return;

    end = md_base + size;

    pr_info("re_mem: %s MD range %pa - %pa\n",
            name, &md_base, &end);

    if (target < md_base || target >= end)
        return;

    pr_info("re_mem: *** TARGET IS INSIDE %s ***\n", name);

    off = target - md_base;

    pr_info("re_mem: target offset = 0x%llx\n",
            (unsigned long long)off);

    if (!ap_virt) {
        pr_info("re_mem: %s has no AP virtual mapping\n", name);
        return;
    }

    ap_target = (u8 __iomem *)ap_virt + off;

    value = readb(ap_target);

    pr_info("re_mem: %s AP target = %px\n",
            name, ap_target);

    pr_info("re_mem: ORIGINAL BYTE = 0x%02x\n",
            value);
}

// in re_init
phys_addr_t original_target = 0x63c0748a;

check_md_region("var1",
                guy->var1.base_md_view_phy,
                guy->var1.base_ap_view_vir,
                guy->var1.size,
                original_target);

check_md_region("var2",
                guy->var2.base_md_view_phy,
                guy->var2.base_ap_view_vir,
                guy->var2.size,
                original_target);

check_md_region("var3",
                guy->var3.base_md_view_phy,
                guy->var3.base_ap_view_vir,
                guy->var3.size,
                original_target);

if (guy->var4)
    check_md_region("var4",
                    guy->var4->base_md_view_phy,
                    guy->var4->base_ap_view_vir,
                    guy->var4->size,
                    original_target);

if (guy->var5)
    check_md_region("var5",
                    guy->var5->base_md_view_phy,
                    guy->var5->base_ap_view_vir,
                    guy->var5->size,
                    original_target);
