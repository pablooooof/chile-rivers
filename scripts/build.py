"""Join regulations + geometry into web/data/waterbodies.geojson for the map.

Computes, per water body, the effective fishing phases for the target season by
layering: national baseline < regional rules < water-body-specific rules.
Validates cross-references (regulation waterbody ids vs registry, geometry files).

Usage: py scripts/build.py [--season 2026-2027]
Output goes to docs/ (served by GitHub Pages).
"""
import argparse
import datetime as dt
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGULATION_FILES = ["baseline.yaml", "los-rios.yaml", "los-lagos.yaml", "aysen.yaml"]

MODE_LABEL = {"catch_and_release": "Pesca con devolución obligatoria",
              "retention": "Pesca con retención"}


def nth_weekday(year, month, weekday, nth=None, last=False):
    """weekday: 0=Mon..6=Sun."""
    if last:
        d = dt.date(year + (month == 12), (month % 12) + 1, 1) - dt.timedelta(days=1)
        while d.weekday() != weekday:
            d -= dt.timedelta(days=1)
        return d
    d = dt.date(year, month, 1)
    while d.weekday() != weekday:
        d += dt.timedelta(days=1)
    return d + dt.timedelta(weeks=nth - 1)


WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6}


def resolve_endpoint(spec, year):
    m = spec["month"]
    if "day" in spec:
        return dt.date(year, m, spec["day"])
    wd = WEEKDAYS[spec["weekday"]]
    if spec.get("last"):
        return nth_weekday(year, m, wd, last=True)
    return nth_weekday(year, m, wd, nth=spec["nth"])


def resolve_window(win, season_start_year):
    s_spec, e_spec = win["start"], win["end"]
    s_year = season_start_year if s_spec["month"] >= 7 else season_start_year + 1
    start = resolve_endpoint(s_spec, s_year)
    e_year = s_year if e_spec["month"] >= s_spec["month"] else s_year + 1
    end = resolve_endpoint(e_spec, e_year)
    return start, end


def season_applies(rule, season):
    return rule.get("seasons") == "all" or season in (rule.get("seasons") or [])


def load_rules():
    rules = []
    for f in REGULATION_FILES:
        doc = yaml.safe_load((ROOT / "data/regulations" / f).read_text(encoding="utf-8"))
        for r in doc.get("rules", []):
            r["_file"] = f
            rules.append(r)
    return rules


def phase_label(win, rule):
    label = MODE_LABEL[win["mode"]]
    if win.get("bag"):
        label += ": " + " ".join(win["bag"].split())
    sp = rule.get("species")
    if isinstance(sp, list):
        label += " (" + ", ".join(s.replace("-", " ") for s in sp) + ")"
    return label


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="2026-2027")
    args = ap.parse_args()
    season = args.season
    y0 = int(season.split("-")[0])

    registry = yaml.safe_load((ROOT / "data/waterbodies/registry.yaml").read_text(encoding="utf-8"))["waterbodies"]
    rules = load_rules()
    reg_ids = {e["id"] for e in registry}

    errors, warnings = [], []
    for r in rules:
        for wid in r.get("waterbodies", []) or []:
            if wid not in reg_ids:
                errors.append(f"rule {r['id']}: unknown waterbody '{wid}'")

    features = []
    for e in registry:
        wid = e["id"]
        geom_path = ROOT / "data/geometry" / f"{wid}.geojson"
        if not geom_path.exists():
            (warnings if e.get("optional") else errors).append(f"no geometry for {wid}")
            continue
        feat = json.loads(geom_path.read_text(encoding="utf-8"))

        applicable = [r for r in rules if season_applies(r, season) and not r.get("partial_zone")]
        wb_rules = [r for r in applicable if r.get("scope") == "waterbodies"
                    and wid in (r.get("waterbodies") or [])]
        base = wb_rules
        level = "waterbody"
        if not base:
            base = [r for r in applicable if r.get("scope") == "region"
                    and r.get("region") == e["region"]
                    and r.get("waterbody_type") in (None, e["type"])
                    and not (isinstance(r.get("species"), list))]
            level = "region"
        if not base:
            base = [r for r in applicable if r.get("scope") == "national"
                    and r.get("species") == "salmonids"]
            level = "national"
        if not base:
            errors.append(f"no applicable rule for {wid}")
            continue

        # species-specific regional overlays (e.g. Aysén chinook) on regional/national base
        overlays = []
        if level != "waterbody":
            overlays = [r for r in applicable if r.get("scope") == "region"
                        and r.get("region") == e["region"]
                        and isinstance(r.get("species"), list)
                        and r.get("waterbody_type") in (None, e["type"])]

        phases = []
        veda_notes, sources, gear_notes, prohib_notes = [], [], [], []
        for r in base + overlays:
            for win in r.get("windows", []):
                start, end = resolve_window(win, y0)
                phases.append({"s": start.isoformat(), "e": end.isoformat(),
                               "mode": win["mode"], "label": phase_label(win, r),
                               "overlay": r in overlays})
            if r.get("veda"):
                veda_notes.append(" ".join(r["veda"].split()))
            if r.get("gear"):
                gear_notes.append(" ".join(r["gear"].split()))
            if r.get("prohibitions"):
                prohib_notes.append(" ".join(r["prohibitions"].split()))
            src = r.get("source", {})
            s_txt = src.get("doc", "")
            if s_txt and s_txt not in [s["doc"] for s in sources]:
                sources.append({"doc": s_txt, "url": src.get("url")})

        # merge identical-window phases (e.g. trout C&R + salmon retention, same dates)
        merged = {}
        for p in sorted(phases, key=lambda p: (p["s"], p["overlay"])):
            key = (p["s"], p["e"])
            if key in merged:
                merged[key]["label"] += " · " + p["label"]
                if p["mode"] == "retention":
                    merged[key]["mode"] = "retention"
            else:
                merged[key] = p
        phases = sorted(merged.values(), key=lambda p: p["s"])
        base_phases = [p for p in phases if not p.get("overlay")]
        if not base_phases:
            base_phases = phases

        opens = base_phases[0]["s"]
        closes = max(p["e"] for p in base_phases)
        om = int(opens[5:7])
        nov_default = nth_weekday(y0, 11, WEEKDAYS["friday"], nth=2).isoformat()
        if om == 9:
            cat = "sep"
        elif om == 10:
            cat = "oct"
        elif om == 11 and opens < nov_default:
            cat = "nov-early"
        elif om == 11:
            cat = "nov"
        else:
            cat = "other"

        feat["properties"].update({
            "season": season, "opens": opens, "closes": closes, "cat": cat,
            "rule_level": level,
            "phases": [{k: p[k] for k in ("s", "e", "mode", "label")} for p in phases],
            "veda": veda_notes, "gear": gear_notes[:2], "prohibitions": prohib_notes[:2],
            "sources": sources,
        })
        # MapLibre renders plain geometries more predictably than GeometryCollections
        if feat["geometry"]["type"] == "GeometryCollection":
            for g in feat["geometry"]["geometries"]:
                features.append({"type": "Feature", "properties": feat["properties"], "geometry": g})
        else:
            features.append(feat)

    if errors:
        print("ERRORS:")
        for e_ in errors:
            print("  -", e_)
    if warnings:
        print("warnings (optional waterbodies without geometry):")
        for w in warnings:
            print("  -", w)

    out = {"type": "FeatureCollection", "features": features}
    outdir = ROOT / "docs/data"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "waterbodies.geojson").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"geojson size: {(outdir / 'waterbodies.geojson').stat().st_size / 1e6:.1f} MB")
    (outdir / "meta.json").write_text(json.dumps({
        "season": season, "built": dt.date.today().isoformat(),
        "waterbodies": len(features),
        "consolidated_source": "Sernapesca, Medidas de administración de pesca recreativa en Chile 2025-2026 (v20260522); Res. Ex. 2075/2025 DZ Los Lagos (D.O. 04-09-2025); Res. Ex. 3004/2024 DZ Aysén y modificaciones; Res. Ex. 04/2024 DZ La Araucanía-Los Ríos.",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nbuilt docs/data/waterbodies.geojson: {len(features)} features, season {season}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
