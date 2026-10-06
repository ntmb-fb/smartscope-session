"""Shares one night's targets between several telescopes.

Given the targets ticked in the TonightPlan list and the telescopes that
take part, decides which telescope images which target, and when:

  * framing - a target goes to the telescope whose frame it fills best:
    small objects to the narrow field (Seestar S50), big ones to the
    wide field (Dwarf 3), and anything bigger than every frame to a
    telescope that can mosaic;
  * time - TonightPlan's suggested imaging time ("1-3h", "3-6h", ...)
    says how long a slot wants to be: minutes up to the low end count
    fully, minutes up to the high end count half, anything beyond that
    barely counts;
  * sky - a slot lies inside the target's window above 20 deg, and
    minutes near the transit count more than minutes near its edges.

Each telescope images its targets back to back in transit order; where
one slot ends and the next begins is solved exactly (dynamic programming
on a 10-minute grid). Which target goes to which telescope starts from
the best framing and is then improved by moving or swapping targets
between telescopes for as long as the night's total value goes up -
that is what spreads targets out when they would otherwise queue on one
telescope while another sits idle.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from smartscopes import tonightplan as tp

_STEP = timedelta(minutes=10)
_STEP_MIN = 10
_MIN_STEPS = 3                   # shortest slot: 30 minutes, as tp.schedule()
_DEFAULT_HOURS = (1.0, 3.0)      # targets without a suggested imaging time
_EXTRA_PER_HOUR = 0.02           # value of time beyond the suggested maximum
_EDGE_WEIGHT = 0.6               # a minute at the window's edge vs. one at transit
_MOSAIC_MAX = 1.8                # as plan_targets._DWARF_MOSAIC_MAX
_MAX_ROUNDS = 50

# Framing quality (0..1) by the site's fit verdict.
_Q_UNKNOWN = 0.8                 # no size or no field of view known: neutral
_Q_SMALL = 0.6                   # fits, but is a speck in the frame
_Q_FILLS = 0.5                   # ...up to 1.0 once it spans this share of the frame
_Q_DEPENDS = 0.9                 # fits in one orientation only
_Q_MOSAIC = 0.7                  # covered by a mosaic (less depth per panel)
_Q_TIGHT = 0.55                  # edges cropped
_Q_MOSAIC_PARTIAL = 0.4          # bigger than the largest mosaic
_Q_TOO_BIG = 0.25                # centre only


@dataclass(frozen=True)
class Scope:
    uid: str
    name: str
    fov: tuple[float, float] | None     # arcmin, as tp.fov_fit()
    mosaic: bool = False                # can cover targets bigger than its frame


@dataclass
class NightPlan:
    # scope uid -> (candidate with .fit set for that scope, start, end), in time order:
    # the same shape PlanTarget.save_programs() takes.
    slots: dict[str, list[tuple[tp.Candidate, datetime, datetime]]] = field(default_factory=dict)
    unplaced: list[tp.Candidate] = field(default_factory=list)


def imaging_hours(t: dict) -> tuple[float, float]:
    """TonightPlan's suggested imaging time as (low, high) hours."""
    text = t.get("imaging_time") or ""
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)]
    if not nums:
        return _DEFAULT_HOURS
    if len(nums) == 1:
        return (nums[0] / 2, nums[0]) if "<" in text else (nums[0], nums[0])
    return nums[0], nums[1]


def _size_arcmin(t: dict) -> tuple[float, float]:
    return ((t.get("moon_width") or 0) * 30,
            (t.get("moon_height") or t.get("moon_width") or 0) * 30)


def framing(t: dict, scope: Scope) -> tuple[str, float]:
    """(the site's fit verdict, framing quality 0..1) of a target on a telescope."""
    tw, th = _size_arcmin(t)
    if not scope.fov or not tw or not th:
        return "yes", _Q_UNKNOWN
    fw, fh = scope.fov
    fit = tp.fov_fit(fw, fh, t)
    best = max(min(fw / tw, fh / th), min(fh / tw, fw / th))
    if fit in ("yes", "depends"):
        quality = _Q_SMALL + (1 - _Q_SMALL) * min(1.0, (1 / best) / _Q_FILLS)
        return fit, quality * (_Q_DEPENDS if fit == "depends" else 1.0)
    if scope.mosaic:
        big, small = max(tw, th), min(tw, th)
        need = max(big / max(fw, fh), small / min(fw, fh)) * 1.1
        return fit, _Q_MOSAIC if need <= _MOSAIC_MAX else _Q_MOSAIC_PARTIAL
    return fit, _Q_TIGHT if fit == "tight" else _Q_TOO_BIG


def order_for_scopes(candidates: list[tp.Candidate], scopes: list[Scope]) -> list[tp.Candidate]:
    """tp.rank_tonight()'s order (Showstopper, Rewarding, the rest; then
    score), with targets too big for every telescope last in each group."""
    def too_big(c: tp.Candidate) -> bool:
        return bool(scopes) and all(framing(c.target, s)[1] < _Q_TIGHT for s in scopes)

    return sorted(candidates, key=lambda c: (tp._IMPACT_ORDER.get(c.target["visual_impact"], 2),
                                             bool(c.target.get("estimated")), too_big(c), -c.score))


# --- one telescope's night --------------------------------------------------------------------

@dataclass
class _Item:
    cand: tp.Candidate
    first: int                   # grid index range the slot may use
    last: int
    minutes: list[float]         # sky-weighted minutes from `first` up to each grid index
    lo: float                    # suggested imaging time, minutes
    hi: float


def _time_value(minutes: float, lo: float, hi: float) -> float:
    if minutes <= lo:
        return minutes / lo
    if minutes <= hi:
        return 1 + 0.5 * (minutes - lo) / (hi - lo)
    return (1.5 if hi > lo else 1.0) + _EXTRA_PER_HOUR * (minutes - hi) / 60


def _item(c: tp.Candidate, origin: datetime, steps: int, not_before: datetime | None) -> _Item:
    earliest = max(c.window_start, not_before) if not_before else c.window_start
    first = max(0, math.ceil((earliest - origin) / _STEP - 1e-6))
    last = min(steps, math.floor((c.window_end - origin) / _STEP + 1e-6))
    half = max(c.peak_time - c.window_start, c.window_end - c.peak_time, _STEP)
    minutes, total = [0.0] * (steps + 1), 0.0
    for k in range(steps):
        if first <= k < last:
            x = min(1.0, abs((origin + (k + 0.5) * _STEP - c.peak_time) / half))
            total += _STEP_MIN * (_EDGE_WEIGHT + (1 - _EDGE_WEIGHT) * (1 - x * x))
        minutes[k + 1] = total
    lo, hi = imaging_hours(c.target)
    return _Item(c, first, last, minutes, lo * 60, hi * 60)


def _schedule_scope(items: list[_Item], weights: list[float], steps: int):
    """Best back-to-back slots for one telescope's targets, already in
    transit order: (value, [(item, start index, end index)])."""
    value = [0.0] * (steps + 1)      # best value with every slot ended by index t
    picks = []
    for item, weight in zip(items, weights):
        cur = value[:]               # None = this target gets no slot
        pick: list[int | None] = [None] * (steps + 1)
        for end in range(item.first + _MIN_STEPS, item.last + 1):
            best, arg = cur[end], None
            for start in range(item.first, end - _MIN_STEPS + 1):
                v = value[start] + weight * _time_value(item.minutes[end] - item.minutes[start], item.lo, item.hi)
                if v > best + 1e-9:
                    best, arg = v, start
            cur[end], pick[end] = best, arg
        for t in range(1, steps + 1):
            if cur[t - 1] > cur[t]:
                cur[t], pick[t] = cur[t - 1], -1     # -1 = same as one step earlier
        picks.append(pick)
        value = cur
    slots, t = [], steps
    for item, pick in zip(reversed(items), reversed(picks)):
        while pick[t] == -1:
            t -= 1
        if pick[t] is not None:
            slots.append((item, pick[t], t))
            t = pick[t]
    return value[steps], slots[::-1]


# --- the whole night ---------------------------------------------------------------------------

def plan_night(candidates: list[tp.Candidate], scopes: list[Scope],
               not_before: datetime | None = None) -> NightPlan:
    plan = NightPlan(slots={s.uid: [] for s in scopes})
    if not candidates or not scopes:
        plan.unplaced = list(candidates)
        return plan

    ordered = sorted(candidates, key=lambda c: c.peak_time)
    origin = min(c.window_start for c in ordered)
    steps = math.ceil((max(c.window_end for c in ordered) - origin) / _STEP)
    items = [_item(c, origin, steps, not_before) for c in ordered]
    fits = [[framing(c.target, s) for s in scopes] for c in ordered]
    impact = [tp._IMPACT_MULT.get(c.target.get("visual_impact"), 1.0) for c in ordered]
    n, m = len(ordered), len(scopes)

    cache: dict[tuple[int, frozenset[int]], tuple] = {}

    def scope_night(j: int, members: frozenset[int]):
        if (j, members) not in cache:
            idx = sorted(members)        # `ordered` is in transit order, so is this
            cache[j, members] = _schedule_scope([items[i] for i in idx],
                                                [impact[i] * fits[i][j][1] for i in idx], steps)
        return cache[j, members]

    def total(assign: list[int]) -> float:
        return sum(scope_night(j, frozenset(i for i in range(n) if assign[i] == j))[0] for j in range(m))

    assign = [max(range(m), key=lambda j: (fits[i][j][1], -j)) for i in range(n)]
    best = total(assign)
    for _ in range(_MAX_ROUNDS):
        better = None
        trials = [[(i, j)] for i in range(n) for j in range(m) if j != assign[i]]
        trials += [[(i, assign[k]), (k, assign[i])]
                   for i in range(n) for k in range(i + 1, n) if assign[i] != assign[k]]
        for changes in trials:
            trial = assign[:]
            for i, j in changes:
                trial[i] = j
            value = total(trial)
            if value > best + 1e-6:
                best, better = value, trial
        if better is None:
            break
        assign = better

    index = {id(item): i for i, item in enumerate(items)}
    placed: set[str] = set()
    for j, scope in enumerate(scopes):
        _, slots = scope_night(j, frozenset(i for i in range(n) if assign[i] == j))
        out = plan.slots[scope.uid]
        for item, start, end in slots:
            c = item.cand
            fit = fits[index[id(item)]][j][0]
            # The grid only reaches the last full step: give the tail of the window back.
            end_time = c.window_end if end == item.last else origin + end * _STEP
            out.append((replace(c, fit=fit), origin + start * _STEP, end_time))
            placed.add(c.id)
        for a, b in zip(range(len(out)), range(1, len(out))):
            if out[a][2] > out[b][1]:
                out[a] = (out[a][0], out[a][1], out[b][1])
    plan.unplaced = [c for c in ordered if c.id not in placed]
    return plan
