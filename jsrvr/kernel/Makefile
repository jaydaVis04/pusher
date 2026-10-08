ifneq ($(KERNELRELEASE),)
obj-m += re_mem_region.o
else
KDIR ?=
ARCH ?= arm64
ABI_VERIFIED ?= 0
.PHONY: all clean
all:
	@test "$(ABI_VERIFIED)" = "1" || (echo "Verify the real driver ABI, then set ABI_VERIFIED=1"; exit 1)
	@test -f re_mem_driver_abi.h || (echo "Supply re_mem_driver_abi.h from real vendor definitions"; exit 1)
	@test -n "$(KDIR)" || (echo "Set KDIR to the configured device kernel build tree"; exit 1)
	$(MAKE) -C $(KDIR) M=$(CURDIR) ARCH=$(ARCH) modules
clean:
	@test -n "$(KDIR)" || (echo "Set KDIR"; exit 1)
	$(MAKE) -C $(KDIR) M=$(CURDIR) ARCH=$(ARCH) clean
endif
