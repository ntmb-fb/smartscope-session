"""Touch-sized buttons on phones and tablets, for every page of the app.

Quasar's own sizes are tuned for a mouse: a "flat round dense" icon
button is ~34px and a "dense size=sm" one ~24px, both well under the
44px Apple asks for on a touch screen. Scoped to (pointer: coarse) so
the desktop/native window keeps its compact layout, and added once as
shared head HTML rather than by editing each (mostly upstream) button.
"""
from __future__ import annotations

_CSS = """
<style>
@media (pointer: coarse) {
  .q-btn { min-height: 44px; }
  .q-btn.q-btn--round { min-width: 44px; }
  .q-btn--dense:not(.q-btn--round) { padding-left: 12px; padding-right: 12px; }
  .q-btn--dense .q-icon { font-size: 24px; }
}
</style>
"""


def apply() -> None:
    from nicegui import ui

    ui.add_head_html(_CSS, shared=True)
