"""'Plan tonight' dialog for all telescopes at once: the same ranked
TonightPlan list as the per-telescope dialog, but the ticked targets are
shared out between the telescopes by smartscopes/nightplan.py (framing,
suggested imaging time, sky window) and shown as a plan before anything
is queued."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nicegui import run, ui

from smartscopes import nightplan
from smartscopes import tonightplan as tp
from smartscopes.plan_targets import FIT_TEXT, PlanOptions, PlanTarget, get_pref, set_pref
from smartscopes.ui.tonightplan_dialog import _IMPACT_COLOR, _local_tz_name

_PREF_UID = "_all"               # this dialog's own remembered location / sky
_AUTO_TICK_PER_SCOPE = 2


def _names(targets: list[PlanTarget]) -> dict[str, str]:
    """A distinct display name per telescope (two Dwarf 3s -> "Dwarf 3", "Dwarf 3 (2)")."""
    names, seen = {}, {}
    for t in targets:
        seen[t.label] = seen.get(t.label, 0) + 1
        names[t.uid] = t.label if seen[t.label] == 1 else f"{t.label} ({seen[t.label]})"
    return names


def _duration(start: datetime, end: datetime) -> str:
    minutes = round((end - start).total_seconds() / 60)
    return f"{minutes // 60}h{minutes % 60:02d}"


def open_nightplan_dialog(targets: list[PlanTarget]) -> None:
    names = _names(targets)
    locations = {}
    for t in targets:
        for loc in t.locations():
            locations.setdefault(loc.label, loc)

    with ui.dialog() as dialog, ui.card().classes("w-full max-w-3xl"):
        with ui.row().classes("items-center justify-between w-full"):
            ui.label("Plan tonight · all telescopes").classes("text-lg")
            ui.link("tonightplan.cosmiccaptures.com", tp.SITE_URL, new_tab=True).classes("text-xs")
        problem = ("No telescope yet: pair a Dwarf or add a Seestar first." if not targets else
                   "No location known: add a Site with a location first (dashboard → 📍)." if not locations else "")
        if problem:
            ui.label(problem).classes("text-negative")
            ui.button("Close", on_click=dialog.close).props("flat")
            dialog.open()
            return

        default_loc = get_pref(_PREF_UID, "tonightplan_location") or next(
            (t.default_location() for t in targets if t.default_location() in locations), None)
        if default_loc not in locations:
            default_loc = next(iter(locations))
        with ui.row().classes("items-end gap-3 w-full"):
            loc_sel = ui.select(list(locations), value=default_loc, label="Location").classes("min-w-48")
            sky_sel = ui.select(list(tp.SKY_QUALITIES), label="Your sky",
                                value=get_pref(_PREF_UID, "tonightplan_sky", "Suburban")).classes("w-32")
            refresh_btn = ui.button(icon="refresh").props("flat round").tooltip("Fetch again from TonightPlan")
        with ui.row().classes("items-center gap-4"):
            use = {t.uid: ui.checkbox(names[t.uid], value=True) for t in targets}
        summary = ui.label().classes("text-sm text-grey-7")
        body = ui.column().classes("w-full gap-1")
        ui.separator()
        plan_box = ui.column().classes("w-full gap-2")
        exp, gain, af, use_filter, mosaic = {}, {}, {}, {}, {}
        with ui.expansion("Camera settings per telescope", icon="tune").classes("w-full"):
            for t in targets:
                ui.label(names[t.uid]).classes("text-sm font-medium")
                with ui.row().classes("items-end gap-3 w-full"):
                    exp[t.uid] = ui.select(t.exposures, value=t.default_exposure, label="Exposure (s)").classes("w-28")
                    gain[t.uid] = ui.number("Gain", value=t.default_gain, format="%d").classes("w-20")
                    af[t.uid] = ui.checkbox(t.autofocus_label, value=t.autofocus_default)
                    if t.filter_label:
                        use_filter[t.uid] = ui.checkbox(t.filter_label, value=True)
                    if t.supports_mosaic:
                        mosaic[t.uid] = ui.checkbox("Mosaic for targets bigger than the frame", value=True)
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            add_btn = ui.button("Add to queues")
        ui.label("Ratings and notes © Tim Ciasto / Cosmic Captures. Moon-greyed and "
                 "smart-scope 'Challenging' targets are left out.").classes("text-xs text-grey-6")

    state: dict = {"candidates": [], "checks": {}, "tz": None, "plan": None, "generation": 0}

    def active() -> list[PlanTarget]:
        return [t for t in targets if use[t.uid].value]

    def scopes(of: list[PlanTarget]) -> list[nightplan.Scope]:
        return [nightplan.Scope(t.uid, names[t.uid], t.fov,
                                mosaic=t.uid in mosaic and bool(mosaic[t.uid].value)) for t in of]

    def ticked() -> list[tp.Candidate]:
        return [c for c in state["candidates"] if state["checks"].get(c.id) and state["checks"][c.id].value]

    async def load(force: bool = False) -> None:
        loc = locations[loc_sel.value]
        tz_name = loc.tz or _local_tz_name()
        try:
            ZoneInfo(tz_name)
        except Exception:
            tz_name = _local_tz_name()
        state["tz"] = tz = ZoneInfo(tz_name)
        state["candidates"], state["plan"] = [], None
        plan_box.clear()
        body.clear()
        with body:
            ui.spinner()
        try:
            catalogue = await run.io_bound(tp.fetch_catalogue, force=force)
            night, candidates = await run.io_bound(
                lambda: tp.rank_tonight(catalogue, lat=loc.lat, lon=loc.lon, tz_name=tz_name, sky=sky_sel.value))
        except tp.TonightPlanError as exc:
            body.clear()
            with body:
                ui.label(str(exc)).classes("text-negative")
            return
        state["candidates"] = nightplan.order_for_scopes(candidates, scopes(targets))
        dark = "darkness" if not night.twilight_tier else ("nautical twilight only", "civil twilight only")[night.twilight_tier - 1]
        summary.set_text(f"{dark} {night.evening.astimezone(tz):%H:%M}–{night.morning.astimezone(tz):%H:%M} · "
                         f"Moon {night.moon_illum}% (up to {night.moon_peak_alt}°) · {len(candidates)} targets")
        render()
        await replan()

    def render() -> None:
        body.clear()
        tz = state["tz"]
        state["checks"] = {}
        can_mosaic = {t.uid for t in targets if t.supports_mosaic}
        all_scopes = scopes(targets)
        auto_tick = _AUTO_TICK_PER_SCOPE * max(1, len(active()))
        with body:
            if not state["candidates"]:
                ui.label("Nothing suitable tonight (bright Moon?). Try another night.").classes("text-grey-7")
                return
            for i, c in enumerate(state["candidates"]):
                t = c.target
                with ui.row().classes("items-center w-full gap-2 no-wrap"):
                    state["checks"][c.id] = ui.checkbox(value=i < auto_tick, on_change=lambda _: replan())
                    ui.badge(t["visual_impact"], color=_IMPACT_COLOR.get(t["visual_impact"], "grey")).classes("w-24")
                    with ui.column().classes("gap-0 grow"):
                        ui.label(c.label).classes("text-sm")
                        bits = [f"{c.window_start.astimezone(tz):%H:%M}–{c.window_end.astimezone(tz):%H:%M}",
                                f"peak {c.peak_alt:.0f}° at {c.peak_time.astimezone(tz):%H:%M}"]
                        if t.get("apparent_dimensions"):
                            bits.append(t["apparent_dimensions"])
                        bits.append(f"suggested {t.get('imaging_time', '?')}")
                        if c.moon_status == "ok":
                            bits.append("some Moon")
                        ui.label(" · ".join(bits)).classes("text-xs text-grey-7")
                        fits = [(s, nightplan.framing(t, s)[0]) for s in all_scopes]
                        ui.label(" · ".join(
                            f"{s.name}: {'too big' if fit == 'no' and s.uid not in can_mosaic else FIT_TEXT[fit]}"
                            for s, fit in fits)).classes("text-xs text-grey-6")

    async def replan() -> None:
        state["generation"] += 1
        generation = state["generation"]
        chosen, taking_part = ticked(), scopes(active())
        plan = None
        if chosen and taking_part:
            not_before = datetime.now().astimezone() + timedelta(minutes=2)
            plan = await run.io_bound(nightplan.plan_night, chosen, taking_part, not_before)
            if generation != state["generation"]:
                return                    # ticks changed while this was being worked out
        state["plan"] = plan
        render_plan(taking_part)

    def _fit_text(c: tp.Candidate, scope: nightplan.Scope) -> str:
        if c.fit in ("tight", "no") and scope.mosaic:
            return "mosaic"
        return "bigger than the frame" if c.fit == "no" else FIT_TEXT[c.fit]

    def render_plan(taking_part: list[nightplan.Scope]) -> None:
        plan_box.clear()
        plan, tz = state["plan"], state["tz"]
        with plan_box:
            if plan is None:
                ui.label("Tick targets and at least one telescope to see the plan.").classes("text-sm text-grey-7")
                return
            for scope in taking_part:
                with ui.column().classes("gap-0 w-full"):
                    ui.label(scope.name).classes("text-sm font-medium")
                    if not plan.slots[scope.uid]:
                        ui.label("Nothing tonight").classes("text-xs text-grey-6")
                    for c, start, end in plan.slots[scope.uid]:
                        ui.label(f"{start.astimezone(tz):%H:%M}–{end.astimezone(tz):%H:%M} · {c.label}").classes("text-sm")
                        ui.label(f"{_duration(start, end)} of {c.target.get('imaging_time') or '?'} suggested · "
                                 f"{_fit_text(c, scope)}").classes("text-xs text-grey-7")
            if plan.unplaced:
                ui.label("No room left tonight for " + ", ".join(c.label for c in plan.unplaced)).classes(
                    "text-sm text-warning")

    async def add() -> None:
        await replan()                    # so that nothing starts in the past
        plan = state["plan"]
        if plan is None or not any(plan.slots.values()):
            ui.notify("Tick at least one target and one telescope", type="warning")
            return
        queued, failed, unarmed = [], [], []
        for t in active():
            slots = plan.slots[t.uid]
            if not slots:
                continue
            opts = PlanOptions(exposure=str(exp[t.uid].value), gain=int(gain[t.uid].value or t.default_gain),
                               autofocus=af[t.uid].value,
                               use_filter=t.uid in use_filter and bool(use_filter[t.uid].value),
                               mosaic=t.uid in mosaic and bool(mosaic[t.uid].value))
            try:
                t.save_programs(slots, opts, state["tz"])
            except Exception as exc:
                failed.append(f"{names[t.uid]}: {exc}")
                continue
            queued.append(f"{names[t.uid]}: {len(slots)}")
            if not t.is_armed():
                unarmed.append(names[t.uid])
        if failed:
            ui.notify("Could not save programs for " + "; ".join(failed), type="negative", multi_line=True)
        if not queued:
            return
        set_pref(_PREF_UID, "tonightplan_sky", sky_sel.value)
        set_pref(_PREF_UID, "tonightplan_location", loc_sel.value)
        msg = "Queued programs · " + " · ".join(queued)
        if plan.unplaced:
            msg += "; no room left for " + ", ".join(c.id for c in plan.unplaced)
        ui.notify(msg, type="warning" if plan.unplaced else "positive", multi_line=True)
        if unarmed:
            ui.notify(f"Arm the scheduler on {', '.join(unarmed)} to run them automatically", type="info")
        if not failed:
            dialog.close()

    loc_sel.on_value_change(lambda _: load())
    sky_sel.on_value_change(lambda _: load())
    refresh_btn.on_click(lambda: load(force=True))
    for box in (*use.values(), *mosaic.values()):
        box.on_value_change(lambda _: replan())
    add_btn.on_click(add)
    dialog.open()
    ui.timer(0.1, load, once=True)
