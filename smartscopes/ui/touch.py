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
  .q-btn.q-btn--round { min-width: 48px; min-height: 48px; }
  .q-btn--dense:not(.q-btn--round) { padding-left: 12px; padding-right: 12px; }
  .q-btn .q-icon { font-size: 28px; }
  .q-expansion-item .q-item { min-height: 56px; }
  .q-expansion-item__container > .q-item .q-item__label { font-size: 18px; font-weight: 500; }
  .q-expansion-item__container > .q-item .q-item__section--avatar .q-icon { font-size: 30px; }
  body { zoom: 1.1; }
}
@media (pointer: coarse) and (min-width: 700px) {
  body { zoom: 1.25; font-size: 16px; }
  /* Tablets have the room: one step up for the small text sizes the cards,
     hints and the log viewer use, and for panel titles and icons. "body"
     only lifts these above Tailwind's own rules, which load later. */
  body .text-xs { font-size: 0.875rem; line-height: 1.25rem; }
  body .text-sm, body .md\:text-sm { font-size: 1rem; line-height: 1.5rem; }
  body .md\:text-base { font-size: 1.125rem; line-height: 1.75rem; }
  [style*="monospace"] { font-size: 15px !important; }
  .q-btn .q-icon { font-size: 32px; }
  .q-expansion-item__container > .q-item .q-item__label { font-size: 22px; }
  .q-expansion-item__container > .q-item .q-item__section--avatar .q-icon { font-size: 36px; }
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
