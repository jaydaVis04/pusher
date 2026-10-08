from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, Static


class ConfirmUnload(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static("UNLOAD KERNEL MODULE", classes="section-title")
            yield Static(
                "This removes /dev/re_mem and stops active readers.\n"
                "Quitting remem normally leaves the module loaded."
            )
            with Horizontal(classes="controls"):
                yield Button("Cancel", id="cancel", variant="primary")
                yield Button("Unload explicitly", id="confirm", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")

    def action_cancel(self) -> None:
        self.dismiss(False)


class HelpScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape", "close", "Close")]

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Markdown("""# remem · read-only memory workbench

**q** quit · **r** refresh · **1–5** region · **w** watch · **h** hex

**c** captures · **d** diff · **l** logs · **?** help

Digits alone are decimal. Use `0x` for explicit hex; `fc04` is also hex.

Click table rows to select addresses. Enter an exact offset in the Hex reader
or address-map field. Changes appear in magenta for 1.5 seconds.

OFF/ON labels are observations, not proven semantics. Captures read changing
shared memory sequentially; they are not atomic modem snapshots.

Module loading resolves the symbol freshly for this boot. Region switching uses
sysfs. Quitting never unloads. Diagnostics and command output live in Logs.
""")
            yield Button("Close", id="close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)
