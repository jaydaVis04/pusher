from rich.text import Text
from textual.widgets import Static

from ..models import Region, RememError


class AddressMap(Static):
    def show_address(self, region: Region | None, offset: int) -> None:
        if region is None:
            self.update("ADDRESS MAP  ·  Select a live region or a capture first")
            return
        try:
            md, ap, virtual = region.addresses(offset)
        except RememError as exc:
            self.update(Text(str(exc), style="#e7bb73"))
            return
        text = Text()
        text.append(f"REGION {region.region}  +  0x{offset:X}\n", style="bold #dde7f0")
        text.append("          ┌───────────────┼────────────────┐\n", style="#72869a")
        text.append("          ↓               ↓                ↓\n", style="#72869a")
        text.append("      MD VIEW         AP PHYSICAL      AP VIRTUAL\n", style="#a5b7c9")
        text.append(f"  {md:#018x}  {ap:#018x}  {virtual:#018x}", style="#73c9ec")
        self.update(text)
