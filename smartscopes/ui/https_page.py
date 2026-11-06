"""/scopes/https - upstream's HTTPS-for-phones card, reachable without a Dwarf
(upstream only shows it in a Dwarf's settings)."""
from __future__ import annotations

from nicegui import ui

from components.https_card import render_https_card


def build_https_page() -> None:
    @ui.page("/scopes/https", title="Smartscope Session - HTTPS for phones")
    def https_page() -> None:
        from smartscopes.ui.pages import _header

        _header("HTTPS for phones")
        with ui.column().classes("w-full max-w-2xl mx-auto gap-3 p-4"):
            render_https_card()
