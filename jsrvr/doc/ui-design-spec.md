# remem interface specification

## Intent and domain

An Android researcher sits at a Linux terminal, toggling a test phone's display and
watching shared-memory bytes. The interface must make transitions visible without
losing the current device, boot, region, or capture provenance.

Domain: borrowed mappings, region offsets, MD/AP views, bit transitions, paired
experiments, boot identity, read generations. Palette inspiration: dark instrument
panels, pale engraved labels, cyan address traces, green link indicators, amber
cautions, magenta difference markers.

Signature: one selected offset fans out into MD, AP physical, and AP virtual
addresses; the same offset connects watch rows, hex rows, diffs, and neighborhoods.
Use a workbench layout rather than equally sized summary cards, meaningful status
colors rather than decorative neon, and paired capture controls rather than a
generic file browser.

The user explicitly selected Python/Textual, a dark professional theme, color
semantics, and keyboard controls. This specification applies that established
direction; web HTML previews and web component libraries do not apply to a TUI.

## Tokens and hierarchy

Textual native widgets own focus, keyboard navigation, scrolling, hover, disabled,
and modal behavior. Terminal font is controlled by the user; use its monospace
alignment, bold section labels, and four foreground levels to establish hierarchy.

| Token | Value | Meaning |
| --- | --- | --- |
| scope-canvas | #0c111a | Main terminal workspace |
| scope-panel | #121b27 | Grouped instrument surfaces |
| scope-inset | #090f17 | Inputs and hex content |
| scope-edge | #273548 | Quiet panel boundaries |
| scope-ink | #dde7f0 | Values and primary text |
| scope-secondary | #a5b7c9 | Labels and supporting information |
| scope-muted | #72869a | Metadata and inactive hints |
| scope-address | #73c9ec | Addresses and primary actions |
| scope-good | #8bcaa1 | Connected/root/loaded |
| scope-warning | #e7bb73 | Cautions and observations |
| scope-failure | #ef9292 | Actionable failures |
| scope-change | #d6a0e7 | Changed bytes and bits |

Density: one terminal row between sections, two horizontal cells of panel padding,
one cell between controls. Tables have a single header row and no zebra decoration.
Depth uses restrained borders with closely related dark surfaces; no gradients,
shadows, or large decorative banners. Changes highlight for 1.5 seconds. Polling
has no entrance animation, no overlapping requests, and displays achieved latency.

Last transitions persist as readable evidence while samples continue; temporary
color highlights expire independently. Polling updates table cells in place to
preserve the researcher's cursor and horizontal scroll position.

## Component registry and preimplementation checkpoints

All components share the intent, palette, depth, terminal typography, and spacing
above. Component-specific hierarchy and surface decisions follow:

| Component | Source | Focal hierarchy and states |
| --- | --- | --- |
| AddressMap | remem/widgets/address_map.py | Selected offset above three aligned address branches; panel surface; empty/out-of-bounds text |
| Hex table renderer | remem/widgets/hex_view.py | Selected byte cyan, changed byte magenta; ASCII secondary; exact byte offset input and selectable rows |
| ConfirmUnload | remem/widgets/dialogs.py | Warning above explicit cancel/unload buttons; modal surface, Escape cancels |
| HelpScreen | remem/widgets/dialogs.py | Shortcuts and data semantics; modal surface, close returns focus |
| Main dashboard | remem/app.py | Device strip, live candidate table, region table; initial/disconnected/root-denied/loaded states |
| Live watch | remem/app.py | Current value/XOR/bits lead; previous/time secondary; sampling/paused/error states |
| Captures and analysis | remem/app.py | Explicit OFF/ON pair selectors, full count above capped results; empty/working/error/complete states |
| Diagnostic logs | remem/app.py | Separate command and kernel output panes; text escaped; bounded history |

## Verification

Run Textual headless interaction tests including device selection, region switching,
watch controls, exact address selection, capture pairs, diff filtering, neighborhood
analysis, and unload cancellation. Export SVG screenshots at 140×48, 100×35, and
80×24; inspect for clipping, overlaps, contrast, and scroll access to controls.
