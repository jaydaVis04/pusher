from rich.text import Text
from textual.widgets import DataTable


def fill_hex(
    table: DataTable,
    data: bytes,
    start: int,
    selected: int | None = None,
    previous: bytes | None = None,
) -> None:
    table.clear()
    for row in range(0, len(data), 16):
        chunk = data[row : row + 16]
        hex_text = Text()
        ascii_text = Text()
        for index, byte in enumerate(chunk):
            absolute = start + row + index
            changed = (
                previous is not None
                and row + index < len(previous)
                and previous[row + index] != byte
            )
            style = "bold #d6a0e7" if changed else "#dde7f0"
            if selected == absolute:
                style += " on #254c61"
            hex_text.append(f"{byte:02X} ", style=style)
            ascii_text.append(chr(byte) if 32 <= byte < 127 else ".", style=style)
        table.add_row(
            Text(f"{start + row:08X}", style="#73c9ec"), hex_text, ascii_text, key=str(start + row)
        )
