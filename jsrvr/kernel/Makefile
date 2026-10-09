# Build with the configured Android kernel tree and its matching toolchain.
# Command-line LLVM, LLVM_IAS, CROSS_COMPILE and CROSS_COMPILE_ARM32 variables
# propagate to recursive make. CLANG optionally sets an explicit CC executable.
ifneq ($(KERNELRELEASE),)
obj-m += re_mem.o
ifneq ($(strip $(VENDOR_INCLUDE)),)
ccflags-y += -I$(VENDOR_INCLUDE)
endif
else
KDIR ?=
ARCH ?= arm64
CLANG ?=
VENDOR_INCLUDE ?=
ifneq ($(strip $(CLANG)),)
COMPILER_ARG := CC="$(CLANG)"
endif
.PHONY: all clean check-kdir
all: check-kdir
	$(MAKE) -C "$(KDIR)" M="$(CURDIR)" ARCH="$(ARCH)" $(COMPILER_ARG) modules
clean: check-kdir
	$(MAKE) -C "$(KDIR)" M="$(CURDIR)" ARCH="$(ARCH)" $(COMPILER_ARG) clean
check-kdir:
	@test -n "$(KDIR)" || (echo "Set KDIR to the configured Android device kernel build tree"; exit 1)
	@test -f "$(KDIR)/Makefile" || (echo "KDIR must contain the device kernel build Makefile"; exit 1)
endif
