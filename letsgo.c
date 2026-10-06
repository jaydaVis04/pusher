switch (region) {
case 1:
    re_base = guy->var1.base_ap_view_vir;
    re_size = guy->var1.size;
    re_phys = guy->var1.base_ap_view_phy;
    break;

case 2:
    re_base = guy->var2.base_ap_view_vir;
    re_size = guy->var2.size;
    re_phys = guy->var2.base_ap_view_phy;
    break;

case 3:
    re_base = guy->var3.base_ap_view_vir;
    re_size = guy->var3.size;
    re_phys = guy->var3.base_ap_view_phy;
    break;

case 4:
    if (!guy->var4)
        return -ENODEV;

    re_base = guy->var4->base_ap_view_vir;
    re_size = guy->var4->size;
    re_phys = guy->var4->base_ap_view_phy;
    break;

case 5:
    if (!guy->var5)
        return -ENODEV;

    re_base = guy->var5->base_ap_view_vir;
    re_size = guy->var5->size;
    re_phys = guy->var5->base_ap_view_phy;
    break;

default:
    pr_err("re_mem: invalid region %u\n", region);
    return -EINVAL;
}
