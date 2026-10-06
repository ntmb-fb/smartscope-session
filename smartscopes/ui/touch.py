"""Touch-sized buttons and readable text on phones and tablets, for every
page of the app.

Quasar's own sizes are tuned for a mouse: a "flat round dense" icon
button is ~34px and a "dense size=sm" one ~24px, both well under the
44px Apple asks for on a touch screen. Scoped to (pointer: coarse) so
the desktop/native window keeps its compact layout, and added once as
shared head HTML rather than by editing each (mostly upstream) button.

Text: the pages lean on 12-14px labels, small at arm's length on a
tablet. The whole page is zoomed instead of restyling each label, so
text, icons, fields and spacing grow together. The pages are narrow
centred columns (about 640px), so the zoom steps up with the screen's
width until the column fills most of it: 10% on phones, where width is
scarce, up to 70% on a 13" iPad held sideways.
"""
from __future__ import annotations

_CSS = """
<style>
@media (pointer: coarse) {
  .q-btn { min-height: 44px; }
  .q-btn.q-btn--round { min-width: 44px; }
  .q-btn--dense:not(.q-btn--round) { padding-left: 12px; padding-right: 12px; }
  .q-btn--dense .q-icon { font-size: 24px; }
  body { zoom: 1.1; }
}
@media (pointer: coarse) and (min-width: 700px) {
  body { zoom: 1.25; }
}
@media (pointer: coarse) and (min-width: 1000px) {
  body { zoom: 1.5; }
}
@media (pointer: coarse) and (min-width: 1300px) {
  body { zoom: 1.7; }
}
</style>
"""


def apply() -> None:
    from nicegui import ui

    ui.add_head_html(_CSS, shared=True)
