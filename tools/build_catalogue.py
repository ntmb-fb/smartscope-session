"""Builds smartscopes/data/catalogue.json: the app's own target catalogue.

Run it by hand when the rules below change (python tools/build_catalogue.py);
the result is committed, so the app never downloads these sources itself.

Sources:
  * OpenNGC (NGC, IC, Messier and an addendum) by Mattia Verga,
    CC-BY-SA-4.0 - https://github.com/mattiaverga/OpenNGC
  * Sharpless' catalogue of H II regions (Sh2, 1959) through VizieR
    (VII/20) - for the big emission nebulae NGC/IC leave out.

Out of ~14,000 objects it keeps the few hundred a 30-50 mm smart
telescope can do something with, and gives each one the fields the
planner works with (the same ones TonightPlan's catalogue has): size,
season, filter, sky quality needed, suggested imaging time and a rough
rating. Those ratings are estimates from size, brightness and type -
smartscopes/catalogue.py lets TonightPlan's hand-made ratings replace
them wherever it knows the object.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import urllib.request

OPENNGC_TAG = "v20260501"
OPENNGC_URL = "https://raw.githubusercontent.com/mattiaverga/OpenNGC/" + OPENNGC_TAG + "/database_files/{}.csv"
SHARPLESS_URL = ("https://vizier.cds.unistra.fr/viz-bin/asu-tsv?-source=VII/20/catalog&-out.max=400"
                 "&-out=Sh2,_RAJ2000,_DEJ2000,Diam,Form,Struct,Bright")
OUT = os.path.join(os.path.dirname(__file__), "..", "smartscopes", "data", "catalogue.json")

GALAXY = {"G", "GPair", "GTrpl", "GGroup"}
EMISSION = {"HII", "EmN", "Neb", "Cl+N", "SNR"}
# (object_type, morphology) in TonightPlan's vocabulary: the planner's Moon
# and twilight rules look for "Cluster" / "Nebula" in these.
KIND = {
    "G": ("Galaxy", "Galaxy"), "GPair": ("Galaxy", "Galaxy Pair"), "GTrpl": ("Galaxy", "Galaxy Group"),
    "GGroup": ("Galaxy", "Galaxy Group"), "OCl": ("Cluster", "Open Cluster"), "*Ass": ("Cluster", "Open Cluster"),
    "GCl": ("Cluster", "Globular Cluster"), "PN": ("Nebula", "Planetary Nebula"),
    "HII": ("Nebula", "Emission Nebula"), "EmN": ("Nebula", "Emission Nebula"), "Neb": ("Nebula", "Emission Nebula"),
    "Cl+N": ("Nebula", "Emission Nebula"), "SNR": ("Nebula", "Supernova Remnant"),
    "RfN": ("Nebula", "Reflection Nebula"), "DrkN": ("Nebula", "Dark Nebula"),
}


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "smartscope-session catalogue build"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def num(text: str | None) -> float | None:
    try:
        return float(text) if text and text.strip() else None
    except ValueError:
        return None


def sexagesimal(text: str) -> float:
    sign = -1 if text.strip().startswith("-") else 1
    a, b, c = (float(p) for p in text.strip().lstrip("+-").split(":"))
    return sign * (a + b / 60 + c / 3600)


def peak_month(ra_h: float) -> str:
    """Month in which the object crosses the meridian around midnight
    (RA 0h does so on about 22 September)."""
    return str((int(9 + 21 / 30 + ra_h / 2) - 1) % 12 + 1)


def brightness_cat(mag: float | None) -> str:
    if mag is None:
        return ""
    return "Very Bright" if mag <= 5 else "Bright" if mag <= 8 else "Moderate" if mag <= 10 else "Faint"


def dimensions(a: float, b: float) -> str:
    def f(v: float) -> str:
        return f"{v:.1f}".rstrip("0").rstrip(".")
    return f"{f(a)}′" if abs(a - b) < 0.05 else f"{f(a)}′ × {f(b)}′"


def rate(kind: str, mag: float | None, a: float, b: float, surf: float | None, known: bool) -> dict | None:
    """The estimated ratings, or None for an object not worth listing."""
    if kind in GALAXY:
        if mag is None or mag > 11 or a < 3:
            return None
        if surf is None:
            surf = mag + 2.5 * math.log10(math.pi / 4 * a * b * 3600)
        impact = "Showstopper" if a >= 20 and mag <= 9 else "Rewarding" if mag <= 9.6 and a >= 6 else "Decent"
        return dict(visual_impact=impact,
                    smart_scope="Excellent" if a >= 15 else "Good" if a >= 6 else "Decent",
                    # The catalogue's mean surface brightness undersells big galaxies
                    # with a bright core (M31: 23.6), so a bright total magnitude wins.
                    imaging_time="1-3h" if mag <= 7 or surf <= 22.8 else "3-6h" if surf <= 24 else "6-15h",
                    sky_conditions="Suburban" if mag <= 9.5 else "Rural",
                    lp_friendly="Dark Skies Recommended", filter_rec="None")
    if kind in ("OCl", "*Ass"):
        if mag is None or mag > 7.5 or a < 5:
            return None
        impact = "Showstopper" if mag <= 4.5 and a >= 20 else "Rewarding" if mag <= 6.5 else "Decent"
        return dict(visual_impact=impact, smart_scope="Excellent", imaging_time="<= 1h",
                    sky_conditions="City", lp_friendly="Moon & LP Friendly", filter_rec="None")
    if kind == "GCl":
        if mag is None or mag > 9 or a < 4:
            return None
        impact = "Showstopper" if mag <= 6.2 and a >= 12 else "Rewarding" if mag <= 7.8 else "Decent"
        return dict(visual_impact=impact, smart_scope="Excellent" if a >= 8 else "Good", imaging_time="<= 1h",
                    sky_conditions="City" if mag <= 7 else "Suburban", lp_friendly="Moon & LP Friendly",
                    filter_rec="None")
    if kind == "PN":
        if (mag is None or mag > 12 or a < 0.5) and not known:
            return None
        bright = mag is not None and mag <= 10.5
        impact = "Showstopper" if a >= 5 and bright else "Rewarding" if a >= 1 and bright else "Decent"
        return dict(visual_impact=impact, smart_scope="Excellent" if a >= 5 else "Good" if a >= 1 else "Decent",
                    imaging_time="1-3h", sky_conditions="City" if bright else "Suburban",
                    lp_friendly="Moon & LP Friendly", filter_rec="Dual / Narrowband")
    if kind in EMISSION:
        if a < 5:
            return None
        impact = ("Showstopper" if a >= 20 else "Rewarding") if known else ("Decent" if a >= 15 else "Subtle")
        return dict(visual_impact=impact, smart_scope="Excellent" if known and a >= 15 else "Good",
                    imaging_time="1-3h" if mag is not None and mag <= 6 else "3-6h",
                    sky_conditions="Suburban", lp_friendly="Some Moon / Moderate LP",
                    filter_rec="Dual / Narrowband")
    if kind in ("RfN", "DrkN"):
        if a < 5:
            return None
        return dict(visual_impact="Rewarding" if known else "Decent", smart_scope="Good", imaging_time="3-6h",
                    sky_conditions="Rural", lp_friendly="Dark Skies Recommended", filter_rec="None")
    return None


def designation(row: dict) -> tuple[str, list[str]]:
    """("M31", ["NGC224"]): Messier number first, catalogue name without zero padding."""
    name = row["Name"]
    for prefix in ("NGC", "IC"):
        if name.startswith(prefix):
            name = prefix + name[len(prefix):].lstrip("0")
    aliases = [name]
    if row.get("M"):
        aliases.insert(0, "M" + row["M"].lstrip("0"))
    return aliases[0], aliases[1:]


def from_openngc() -> list[dict]:
    out = []
    for part in ("NGC", "addendum"):
        for row in csv.DictReader(io.StringIO(fetch(OPENNGC_URL.format(part))), delimiter=";"):
            kind = row["Type"]
            a = num(row["MajAx"])
            if kind not in KIND or a is None or not row["RA"] or not row["Dec"]:
                continue
            b = num(row["MinAx"]) or a
            v, bmag = num(row["V-Mag"]), num(row["B-Mag"])
            mag = v if v is not None else bmag
            names = [n.strip() for n in row["Common names"].split(",") if n.strip()]
            rating = rate(kind, mag, a, b, num(row["SurfBr"]), known=bool(names or row.get("M")))
            if rating is None:
                continue
            id_, aliases = designation(row)
            ra_h, dec_d = sexagesimal(row["RA"]), sexagesimal(row["Dec"])
            object_type, morphology = KIND[kind]
            out.append(dict(
                id=id_, aliases=aliases, common_name=names[0] if names else "",
                object_type=object_type, morphology=morphology, constellation=row["Const"],
                ra_h=round(ra_h, 4), dec_d=round(dec_d, 3), peak_month=peak_month(ra_h),
                apparent_dimensions=dimensions(a, b), moon_width=round(a / 30, 3), moon_height=round(b / 30, 3),
                magnitude=mag, brightness_cat=brightness_cat(mag), **rating))
    return out


def _separation_arcmin(a: dict, ra_h: float, dec_d: float) -> float:
    d_ra = (a["ra_h"] - ra_h) * 15 * math.cos(math.radians(dec_d))
    return math.hypot(d_ra, a["dec_d"] - dec_d) * 60


def drop_parts(targets: list[dict]) -> list[dict]:
    """Drops nebulae that are a piece of a bigger listed object (the
    Rosette's five NGC numbers, the Merope Nebula inside the Pleiades):
    one frame, one entry. Messier objects and dark nebulae stay."""
    def is_part(t: dict) -> bool:
        if t["object_type"] != "Nebula" or t["id"].startswith("M") or t["morphology"] == "Dark Nebula":
            return False
        return any(o is not t and (o["moon_width"], o["id"]) > (t["moon_width"], t["id"])
                   and _separation_arcmin(o, t["ra_h"], t["dec_d"]) < 0.4 * o["moon_width"] * 30
                   for o in targets)
    return [t for t in targets if not is_part(t)]


def from_sharpless(existing: list[dict]) -> list[dict]:
    """Sharpless regions at least 15' across and not rated faint, unless
    an NGC/IC nebula already covers that patch of sky."""
    nebulae = [t for t in existing if t["object_type"] == "Nebula"]
    out = []
    for line in fetch(SHARPLESS_URL).splitlines():
        cells = [c.strip() for c in line.split("\t")]
        if len(cells) != 7 or not cells[0].isdigit():
            continue
        number, ra_deg, dec_d, diam, bright = int(cells[0]), float(cells[1]), float(cells[2]), num(cells[3]), int(cells[6])
        if diam is None or diam < 15 or bright < 2:
            continue
        ra_h = ra_deg / 15

        if any(_separation_arcmin(t, ra_h, dec_d) < max(diam, t["moon_width"] * 30) / 2 for t in nebulae):
            continue
        out.append(dict(
            id=f"Sh2-{number}", aliases=[], common_name="", object_type="Nebula", morphology="Emission Nebula",
            constellation="", ra_h=round(ra_h, 4), dec_d=round(dec_d, 3), peak_month=peak_month(ra_h),
            apparent_dimensions=dimensions(diam, diam), moon_width=round(diam / 30, 3), moon_height=round(diam / 30, 3),
            magnitude=None, brightness_cat="",
            visual_impact="Decent" if bright == 3 else "Subtle", smart_scope="Good" if bright == 3 else "Decent",
            imaging_time="3-6h" if bright == 3 else "6-15h", sky_conditions="Suburban",
            lp_friendly="Some Moon / Moderate LP", filter_rec="Dual / Narrowband"))
    return out


def main() -> None:
    targets = drop_parts(from_openngc())
    targets += from_sharpless(targets)
    targets.sort(key=lambda t: t["ra_h"])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"sources": [f"OpenNGC {OPENNGC_TAG} (Mattia Verga, CC-BY-SA-4.0)",
                               "Sharpless 1959, Sh2 (VizieR VII/20)"],
                   "targets": targets}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(targets)} targets -> {os.path.normpath(OUT)} ({os.path.getsize(OUT) // 1024} KB)")


if __name__ == "__main__":
    main()
