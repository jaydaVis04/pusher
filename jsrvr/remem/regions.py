from .models import Region, RememError


def parse_info(text: str) -> Region:
    fields: dict[str, str] = {}
    for line in text.strip().splitlines():
        if "=" not in line:
            raise RememError(f"Malformed sysfs info: {line!r}")
        key, value = line.strip().split("=", 1)
        if key in fields:
            raise RememError(f"Duplicate sysfs field: {key}")
        fields[key] = value
    try:
        values = [int(fields[k], 0) for k in ("region", "size", "md_phys", "ap_phys", "ap_virt")]
        region = Region(
            values[0],
            values[1],
            values[2],
            values[3],
            values[4],
            generation=int(fields.get("generation", "0"), 0),
        )
    except (ValueError, KeyError) as exc:
        raise RememError("Incomplete or invalid sysfs region metadata") from exc
    if (
        not 1 <= region.region <= 5
        or region.size <= 0
        or region.generation < 0
        or any(v < 0 or v >= 1 << 64 for v in values[1:])
        or not region.ap_virt
        or any(
            base + region.size > 1 << 64
            for base in (region.md_phys, region.ap_phys, region.ap_virt)
        )
    ):
        raise RememError("Invalid sysfs region bounds or address")
    return region


def parse_regions(text: str) -> list[Region]:
    result = [parse_info(block) for block in text.strip().split("\n\n") if block.strip()]
    if len({r.region for r in result}) != len(result):
        raise RememError("Duplicate region in sysfs regions endpoint")
    return result
