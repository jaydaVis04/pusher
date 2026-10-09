"""Exercise the build wrapper against a fake Kbuild, without compiling a kernel."""

import shutil
import subprocess
from pathlib import Path

import pytest

KERNEL = Path(__file__).resolve().parents[1] / "kernel"
pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make is unavailable")


@pytest.mark.parametrize("target", ["all", "clean"])
@pytest.mark.parametrize("explicit_clang", [False, True])
def test_kbuild_receives_device_build_settings(
    tmp_path: Path, target: str, explicit_clang: bool
) -> None:
    build = tmp_path / "device kernel build"
    build.mkdir()
    (build / "Makefile").write_text(
        "KERNELRELEASE := fake-device-kernel\n"
        "include $(M)/Makefile\n"
        ".PHONY: modules clean\n"
        "modules clean:\n"
        "\t@printf '%s\\n' 'target=$@' 'arch=$(ARCH)' 'module=$(obj-m)' "
        "'llvm=$(LLVM)' 'ias=$(LLVM_IAS)' 'cross=$(CROSS_COMPILE)' "
        "'cross32=$(CROSS_COMPILE_ARM32)' 'cc=$(CC)' 'includes=$(ccflags-y)'\n"
    )
    arguments = [
        "make",
        "--no-print-directory",
        "-s",
        "-C",
        str(KERNEL),
        target,
        f"KDIR={build}",
        "ARCH=arm64",
        "LLVM=/toolchain/bin/",
        "LLVM_IAS=1",
        "CROSS_COMPILE=aarch64-linux-gnu-",
        "CROSS_COMPILE_ARM32=arm-linux-gnueabi-",
        "VENDOR_INCLUDE=/vendor/include",
    ]
    if explicit_clang:
        arguments.append("CLANG=/vendor/clang/bin/clang")
    result = subprocess.run(arguments, capture_output=True, text=True, check=True)
    settings = dict(line.split("=", 1) for line in result.stdout.splitlines())
    assert settings["target"] == ("modules" if target == "all" else "clean")
    assert settings["arch"] == "arm64"
    assert settings["module"] == "re_mem.o"
    assert settings["llvm"] == "/toolchain/bin/"
    assert settings["ias"] == "1"
    assert settings["cross"] == "aarch64-linux-gnu-"
    assert settings["cross32"] == "arm-linux-gnueabi-"
    assert settings["includes"] == "-I/vendor/include"
    if explicit_clang:
        assert settings["cc"] == "/vendor/clang/bin/clang"


@pytest.mark.parametrize("invalid_directory", ["", "/missing/android/kernel/tree"])
def test_build_requires_explicit_device_kernel_tree(invalid_directory: str) -> None:
    result = subprocess.run(
        ["make", "-s", "-C", str(KERNEL), f"KDIR={invalid_directory}"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "KDIR" in result.stdout
