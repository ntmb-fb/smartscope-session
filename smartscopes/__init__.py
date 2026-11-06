"""Support for non-Dwarf smart telescopes (ZWO Seestar, ...), kept in its
own package so the fork stays easy to merge with upstream.

The upstream code touches this package in exactly four places, all
marked "smartscopes hook":
  * astro_dwarf_ui.py  -> smartscopes.install()
  * pages/dashboard.py -> smartscopes.render_dashboard_section()
  * pages/dashboard.py -> smartscopes.brand_html() (app-name wordmark)
  * pages/programs.py  -> smartscopes.dwarf_tonightplan_button()

See .github/README.md for the architecture and how to add a new telescope.
"""
from __future__ import annotations

_SCHEDULER_INTERVAL_S = 15.0


def install() -> None:
    """Call once at startup: registers drivers, pages and the scheduler."""
    from nicegui import app

    from smartscopes import branding

    branding.apply()  # "Smartscope Session" everywhere, without editing upstream files
    from smartscopes.ui import touch

    touch.apply()     # finger-sized buttons on phones, likewise
    import smartscopes.drivers  # noqa: F401  (registers every driver)
    from smartscopes.manager import get_scope_manager, scheduler_tick
    from smartscopes.ui.pages import build_pages

    from pathlib import Path

    app.add_static_files("/smartscope-images", str(Path(__file__).parent / "ui" / "images"))
    get_scope_manager()
    from smartscopes.ui.https_page import build_https_page

    build_https_page()  # before build_pages(): /scopes/https must win over /scopes/{uid}
    build_pages()
    app.timer(_SCHEDULER_INTERVAL_S, scheduler_tick)

    def _shutdown() -> None:
        for device in get_scope_manager().all():
            device.request_stop()
            device.driver.disconnect()

    app.on_shutdown(_shutdown)


def render_dashboard_section() -> None:
    from smartscopes.ui.dashboard import render_dashboard_section as render

    render()


def dwarf_tonightplan_button(session, on_added) -> None:
    """'Tonight from TonightPlan' icon for upstream's Dwarf programs page."""
    from nicegui import ui

    def open_dialog() -> None:
        from smartscopes.plan_targets import DwarfPlanTarget
        from smartscopes.ui.tonightplan_dialog import open_tonightplan_dialog

        open_tonightplan_dialog(DwarfPlanTarget(session), on_added)

    ui.button(icon="auto_awesome", on_click=open_dialog).props("flat round").tooltip("Tonight from TonightPlan")


def brand_html() -> str:
    """Dashboard wordmark (hook in pages/dashboard.py)."""
    from smartscopes.branding import brand_html as html

    return html()
