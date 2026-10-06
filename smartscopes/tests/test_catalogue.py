"""The app's own catalogue and its merge with TonightPlan's."""
from datetime import datetime, timezone

from smartscopes import catalogue
from smartscopes import tonightplan as tp

NEW_MOON = datetime(2026, 10, 10, 21, 0, tzinfo=timezone.utc)
CPH = dict(lat=55.68, lon=12.57, tz_name="Europe/Copenhagen")


def by_id():
    return {t["id"]: t for t in catalogue.builtin()}


def test_builtin_has_the_classics_with_planner_fields():
    own = by_id()
    assert 500 < len(own) < 1500
    for id_ in ("M31", "M42", "M13", "M27", "M45", "NGC7000", "NGC891", "IC1805"):
        assert id_ in own, id_
    needed = {"ra_h", "dec_d", "visual_impact", "smart_scope", "imaging_time", "filter_rec", "sky_conditions",
              "peak_month", "moon_width", "moon_height", "morphology", "object_type", "lp_friendly"}
    assert all(needed <= set(t) and t["estimated"] for t in own.values())
    assert "OpenNGC" in catalogue.sources()[0]


def test_estimates_follow_the_object():
    own = by_id()
    assert own["M31"]["visual_impact"] == "Showstopper" and own["M31"]["filter_rec"] == "None"
    assert own["M31"]["peak_month"] in ("9", "10") and own["M42"]["peak_month"] in ("12", "1")
    assert "Narrowband" in own["NGC7000"]["filter_rec"] and "Narrowband" in own["M27"]["filter_rec"]
    assert own["M13"]["imaging_time"] == "<= 1h" and own["M13"]["sky_conditions"] == "City"
    assert own["NGC891"]["imaging_time"] in ("3-6h", "6-15h")      # low surface brightness
    assert own["M31"]["moon_width"] * 30 > 150                     # arcminutes


def test_own_catalogue_alone_ranks_a_night():
    night, ranked = tp.rank_tonight(catalogue.builtin(), **CPH, sky="Suburban", now=NEW_MOON)
    ids = [c.id for c in ranked]
    assert "M31" in ids[:15] and "M42" not in ids                  # Orion is out of season in October
    assert len(ranked) > 20


def curated(id_, ra, dec, **extra):
    return {"id": id_, "common_name": "", "ra_h": ra, "dec_d": dec, "visual_impact": "Rewarding",
            "smart_scope": "Excellent", "moon_width": 1, **extra}


def test_merge_lets_the_curated_entry_replace_ours():
    own = by_id()
    m31 = curated("M31", own["M31"]["ra_h"], own["M31"]["dec_d"], visual_impact="Subtle")
    double = curated("NGC869 & 884", 2.35, 57.13)                  # one entry for both clusters
    by_position = curated("Heart", own["IC1805"]["ra_h"], own["IC1805"]["dec_d"], moon_width=4)
    merged = catalogue.merge(catalogue.builtin(), [m31, double, by_position])
    ids = [t["id"] for t in merged]
    assert ids.count("M31") == 1 and merged[0]["visual_impact"] == "Subtle" and "estimated" not in merged[0]
    assert "NGC869" not in ids and "NGC884" not in ids and "IC1805" not in ids
    assert "M33" in ids and len(merged) == len(own) - 4 + 3


def test_ours_rank_after_the_sites_within_an_impact_tier():
    own = [t for t in catalogue.builtin() if t["id"] in ("M31", "M33")]
    site = curated("NGC7331", 22.62, 34.42, visual_impact="Showstopper", peak_month="10",
                   sky_conditions="Suburban", object_type="Galaxy", morphology="Spiral Galaxy",
                   filter_rec="None", lp_friendly="", brightness_cat="Bright")
    _, ranked = tp.rank_tonight([*own, site], **CPH, sky="Rural", now=NEW_MOON)
    showstoppers = [c.id for c in ranked if c.target["visual_impact"] == "Showstopper"]
    assert showstoppers[0] == "NGC7331" and "M31" in showstoppers


def test_load_falls_back_when_the_site_is_down(tmp_path, monkeypatch):
    def down(**_):
        raise tp.TonightPlanError("Could not reach TonightPlan: offline")

    monkeypatch.setattr(tp, "fetch_catalogue", down)
    monkeypatch.setattr(tp, "_CACHE_PATH", str(tmp_path / "none.json"))
    targets, note = catalogue.load()
    assert len(targets) == len(catalogue.builtin()) and "own ratings only" in note

    (tmp_path / "old.json").write_text('[{"id": "M31", "ra_h": 0.712, "dec_d": 41.27, "visual_impact": "Showstopper"}]')
    monkeypatch.setattr(tp, "_CACHE_PATH", str(tmp_path / "old.json"))
    targets, note = catalogue.load()
    assert "last saved ratings" in note and "estimated" not in targets[0]
