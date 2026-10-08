/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Definitions preserved from Jaydyn's working re_mem module.
 * If supplied by the real project header (e.g. omgbaby.h), include that header
 * instead of the struct definitions below. Keep the function prototype exact.
 * The vendor driver must keep these borrowed mappings alive while re_mem is loaded.
 */
#ifndef RE_MEM_DRIVER_ABI_H
#define RE_MEM_DRIVER_ABI_H
#include <linux/io.h>
#include <linux/types.h>

struct x {
	phys_addr_t base_md_view_phy;
	phys_addr_t base_ap_view_phy;
	void __iomem *base_ap_view_vir;
	unsigned int size;
};
struct y {
	unsigned int id;
	unsigned int offset;
	unsigned int size;
	unsigned int flag;
	phys_addr_t base_md_view_phy;
	phys_addr_t base_ap_view_phy;
	void __iomem *base_ap_view_vir;
};
struct THISGUY {
	struct x var1;
	struct x var2;
	struct x var3;
	struct y *var4;
	struct y *var5;
};
typedef struct THISGUY *(*getthisguy_fn_t)(int);

static inline int re_mem_driver_describe(struct THISGUY *guy,
					struct re_mem_region out[5])
{
	struct x *x[3] = { &guy->var1, &guy->var2, &guy->var3 };
	struct y *y[2] = { guy->var4, guy->var5 };
	unsigned int i;

	for (i = 0; i < 3; i++) {
		out[i].base = x[i]->base_ap_view_vir;
		out[i].size = x[i]->size;
		out[i].ap_phys = x[i]->base_ap_view_phy;
		out[i].md_phys = x[i]->base_md_view_phy;
	}
	for (i = 0; i < 2; i++) {
		if (!y[i])
			continue;
		/* Preserve the original reader: use these bases directly, not + offset. */
		out[i + 3].base = y[i]->base_ap_view_vir;
		out[i + 3].size = y[i]->size;
		out[i + 3].ap_phys = y[i]->base_ap_view_phy;
		out[i + 3].md_phys = y[i]->base_md_view_phy;
	}
	return 0;
}
#endif
