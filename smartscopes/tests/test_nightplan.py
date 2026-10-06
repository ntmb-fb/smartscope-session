"""Sharing a night's targets between telescopes (smartscopes/nightplan.py)."""
from datetime import datetime, timedelta, timezone

import pytest

from smartscopes import nightplan as npl
from smartscopes import tonightplan as tp

BASE = datetime(2026, 10, 10, 18, tzinfo=timezone.utc)
S50 = npl.Scope("s50", "Seestar S50", (44, 77))
D3 = npl.Scope("d3", "Dwarf 3", (176, 99), mosaic=True)


def cand(id_, start_h, end_h, *, size=(1, 1), time="1-3h", impact="Rewarding", peak_h=None):
    t = {"id": id_, "common_name": "", "visual_impact": impact, "imaging_time": time,
         "moon_width": size[0], "moon_height": size[1]}
    peak = (start_h + end_h) / 2 if peak_h is None else peak_h
    return tp.Candidate(target=t, window_start=BASE + timedelta(hours=start_h),
                        window_end=BASE + timedelta(hours=end_h), peak_time=BASE + timedelta(hours=peak),
                        peak_alt=60, usable_min=300, moon_dist=90, moon_status="good", score=1, fit="yes")


def ids(plan, scope):
    return [c.id for c, _, _ in plan.slots[scope.uid]]


def hours(plan, scope, id_):
    return next((e - s).total_seconds() / 3600 for c, s, e in plan.slots[scope.uid] if c.id == id_)


@pytest.mark.parametrize("text,expected", [
    ("<= 1h", (0.5, 1)), ("1-3h", (1, 3)), ("3-6h+", (3, 6)), ("15h+", (15, 15)), (None, (1, 3)),
])
def test_imaging_hours(text, expected):
    assert npl.imaging_hours({"imaging_time": text}) == expected


def test_framing_prefers_the_frame_a_target_fills():
    small, big = cand("small", 0, 8, size=(0.5, 0.4)).target, cand("big", 0, 8, size=(3, 2.5)).target
    assert npl.framing(small, S50)[1] > npl.framing(small, D3)[1]
    assert npl.framing(big, D3) == ("yes", 1.0)
    assert npl.framing(big, S50)[0] == "no" and npl.framing(big, S50)[1] < 0.5
    huge = cand("huge", 0, 8, size=(8, 6)).target                  # 240' x 180': a 1.5 x 2 mosaic
    assert npl.framing(huge, D3)[0] == "no"
    assert npl.framing(huge, D3)[1] < npl.framing(cand("m", 0, 8, size=(6.5, 3)).target, D3)[1]


def test_big_goes_wide_and_small_goes_narrow():
    plan = npl.plan_night([cand("galaxy", 0, 8, size=(0.4, 0.3)), cand("nebula", 0, 8, size=(4, 3))], [D3, S50])
    assert ids(plan, S50) == ["galaxy"] and ids(plan, D3) == ["nebula"]
    assert plan.slots["s50"][0][0].fit == "yes" and not plan.unplaced
    assert hours(plan, S50, "galaxy") == 8 and hours(plan, D3, "nebula") == 8      # nothing else waiting


def test_small_targets_spill_over_instead_of_queueing():
    # Four small targets up together all night: the S50 frames them best,
    # but two hours each beats the Dwarf standing idle.
    targets = [cand(f"g{i}", 0, 8, size=(0.4, 0.3), time="3-6h", peak_h=3 + i * 0.5) for i in range(4)]
    plan = npl.plan_night(targets, [D3, S50])
    assert len(ids(plan, S50)) == 2 and len(ids(plan, D3)) == 2 and not plan.unplaced


def test_targets_at_different_times_stay_on_their_best_frame():
    evening, morning = cand("evening", 0, 4, size=(0.4, 0.3)), cand("morning", 4, 8, size=(0.4, 0.3))
    plan = npl.plan_night([morning, evening], [D3, S50])
    assert ids(plan, S50) == ["evening", "morning"] and ids(plan, D3) == []


def test_suggested_imaging_time_sizes_the_slots():
    quick, deep = cand("quick", 0, 8, time="<= 1h", peak_h=1), cand("deep", 0, 8, time="6-15h", peak_h=5)
    plan = npl.plan_night([deep, quick], [S50])
    assert ids(plan, S50) == ["quick", "deep"]
    assert hours(plan, S50, "quick") <= 1.5 and hours(plan, S50, "deep") >= 6.5


def test_slots_stay_in_window_in_order_and_after_now():
    targets = [cand("a", 0, 5), cand("b", 1, 7), cand("c", 3, 9), cand("d", 2, 6, size=(4, 3))]
    now = BASE + timedelta(hours=1, minutes=37)
    plan = npl.plan_night(targets, [D3, S50], not_before=now)
    for slots in plan.slots.values():
        for (c, start, end), nxt in zip(slots, slots[1:] + [None]):
            assert max(c.window_start, now) <= start < end <= c.window_end
            assert end - start >= timedelta(minutes=30)
            assert nxt is None or end <= nxt[1]


def test_window_that_is_already_over_is_reported():
    gone = cand("gone", 0, 2)
    plan = npl.plan_night([gone, cand("ok", 0, 8)], [S50], not_before=BASE + timedelta(hours=1, minutes=45))
    assert ids(plan, S50) == ["ok"] and [c.id for c in plan.unplaced] == ["gone"]


def test_end_of_window_off_the_grid_is_not_lost():
    c = cand("a", 0, 5.07)                                   # the night ends between two 10-minute steps
    plan = npl.plan_night([c], [S50])
    assert plan.slots["s50"][0][2] == c.window_end


def test_order_for_scopes_puts_too_big_last_within_impact():
    a = cand("fits", 0, 8, impact="Showstopper")
    b = cand("giant", 0, 8, size=(12, 10), impact="Showstopper")
    c = cand("plain", 0, 8, impact="Rewarding")
    b.score = 5
    assert [x.id for x in npl.order_for_scopes([c, b, a], [S50])] == ["fits", "giant", "plain"]
    assert [x.id for x in npl.order_for_scopes([c, b, a], [])] == ["giant", "fits", "plain"]
