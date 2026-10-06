static void print_x(const char *name, struct x *p)
{
    if (!p) {
        pr_info("re_mem: %s = NULL\n", name);
        return;
    }

    pr_info("re_mem: ---- %s ----\n", name);
    pr_info("re_mem: base_md_view_phy = %pa\n",
            &p->base_md_view_phy);
    pr_info("re_mem: base_ap_view_phy = %pa\n",
            &p->base_ap_view_phy);
    pr_info("re_mem: base_ap_view_vir = %px\n",
            p->base_ap_view_vir);
    pr_info("re_mem: size = 0x%x (%u)\n",
            p->size, p->size);
}

static void print_y(const char *name, struct y *p)
{
    if (!p) {
        pr_info("re_mem: %s = NULL\n", name);
        return;
    }

    pr_info("re_mem: ---- %s ----\n", name);
    pr_info("re_mem: id = %u\n",
            p->id);
    pr_info("re_mem: offset = 0x%x (%u)\n",
            p->offset, p->offset);
    pr_info("re_mem: size = 0x%x (%u)\n",
            p->size, p->size);
    pr_info("re_mem: flag = 0x%x (%u)\n",
            p->flag, p->flag);
    pr_info("re_mem: base_md_view_phy = %pa\n",
            &p->base_md_view_phy);
    pr_info("re_mem: base_ap_view_phy = %pa\n",
            &p->base_ap_view_phy);
    pr_info("re_mem: base_ap_view_vir = %px\n",
            p->base_ap_view_vir);
}
