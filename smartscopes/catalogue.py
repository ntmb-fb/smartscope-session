"""The planner's target catalogue: our own, with TonightPlan on top.

The base is smartscopes/data/catalogue.json, built by
tools/build_catalogue.py from OpenNGC and Sharpless and shipped with the
app: a few hundred objects a smart telescope can image, each with an
*estimated* rating, imaging time, filter and sky quality. It needs no
network and no other site.

TonightPlan's catalogue (smartscopes/tonightplan.py) is laid over it
when it can be had: its hand-made entry replaces ours for every object
it knows, because a person's judgement of what looks good beats a
formula. If the site is unreachable or changes its page, the last copy
we fetched is used, and failing that our own catalogue alone.
"""
from __future__ import annotations

import json
import math
import os
import re
from functools import lru_cache

from smartscopes import tonightplan as tp

_PATH = os.path.join(os.path.dirname(__file__), "data", "catalogue.json")
_SAME_OBJECT_ARCMIN = 6          # two entries this close are the same object
_INSIDE_FRAME = 0.4              # ...or one lies this deep inside the other's extent


@lru_cache(maxsize=1)
def _builtin() -> tuple[tuple[dict, ...], tuple[str, ...]]:
    with open(_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return tuple({**t, "estimated": True} for t in data["targets"]), tuple(data["sources"])


def builtin() -> list[dict]:
    return list(_builtin()[0])


def sources() -> list[str]:
    return list(_builtin()[1])


def _key(name: str) -> str:
    return re.sub(r"[\s\-_]", "", name).upper()


def _names(tp_id: str) -> set[str]:
    """Every designation in a TonightPlan id: "NGC869 & 884" -> NGC869, NGC884."""
    names, prefix = set(), ""
    for part in re.split(r"[&/,+]", tp_id):
        part = _key(part)
        if not part:
            continue
        if part.isdigit():
            part = prefix + part
        else:
            prefix = re.match(r"[A-Z]*", part).group(0)
        names.add(part)
    return names


def _separation_arcmin(a: dict, b: dict) -> float:
    d_ra = (a["ra_h"] - b["ra_h"]) * 15 * math.cos(math.radians(b["dec_d"]))
    return math.hypot(d_ra, a["dec_d"] - b["dec_d"]) * 60


def merge(own: list[dict], curated: list[dict]) -> list[dict]:
    """curated entries, plus every entry of ours they don't already cover."""
    names = set().union(*(_names(t["id"]) for t in curated)) if curated else set()

    def covered(t: dict) -> bool:
        if names & {_key(n) for n in (t["id"], *t.get("aliases", ()))}:
            return True
        return any(_separation_arcmin(t, c) < max(_SAME_OBJECT_ARCMIN, _INSIDE_FRAME * (c.get("moon_width") or 0) * 30)
                   for c in curated if abs(c["dec_d"] - t["dec_d"]) < 6)

    return list(curated) + [t for t in own if not covered(t)]


def load(*, force: bool = False) -> tuple[list[dict], str]:
    """(targets, note): note is empty, or says why TonightPlan's ratings
    are stale or missing."""
    note = ""
    try:
        curated = tp.fetch_catalogue(force=force)
    except tp.TonightPlanError as exc:
        try:
            with open(tp._CACHE_PATH, encoding="utf-8") as f:
                curated = json.load(f)
            note = f"TonightPlan unreachable, using its last saved ratings ({exc})"
        except (OSError, ValueError):
            curated = []
            note = f"TonightPlan unreachable, own ratings only ({exc})"
    return merge(builtin(), curated), note
