"""Fetch water-body geometry from OpenStreetMap via Overpass.

Reads data/waterbodies/registry.yaml, writes one GeoJSON Feature per water body to
data/geometry/<id>.geojson. Lakes become (Multi)Polygons; rivers become water
polygons when OSM has them under the same name, otherwise MultiLineStrings from
waterway ways/relations.

Batched: three Overpass requests total (lakes, river waterways, river polygons).
Re-run anytime; it overwrites existing files. Misses are reported at the end.
"""
import json
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OVERPASS = "https://overpass-api.de/api/interpreter"
CHILE_AREA = 3600167454  # OSM relation 167454 (Chile) as Overpass area
SIMPLIFY_TOL = 0.0004    # degrees, ~40 m


def norm(s):
    s = unicodedata.normalize("NFD", s or "").lower()
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip()


def overpass(query, retries=4):
    data = ("data=" + urllib.parse.quote(query)).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(OVERPASS, data=data,
                                         headers={"User-Agent": "chile-rivers-fishing-map/1.0"})
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)
        except Exception as e:
            wait = 30 * (attempt + 1)
            print(f"  overpass error ({e}); retry in {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError("overpass failed after retries")


# ── geometry helpers ─────────────────────────────────────────────────────────

def simplify(coords, tol=SIMPLIFY_TOL):
    """Iterative Douglas-Peucker."""
    if len(coords) < 3:
        return coords
    keep = [False] * len(coords)
    keep[0] = keep[-1] = True
    stack = [(0, len(coords) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        ax, ay = coords[a]
        bx, by = coords[b]
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        dmax, imax = -1.0, -1
        for i in range(a + 1, b):
            px, py = coords[i]
            if seg2 == 0:
                d2 = (px - ax) ** 2 + (py - ay) ** 2
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
                d2 = (px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2
            if d2 > dmax:
                dmax, imax = d2, i
        if dmax > tol * tol:
            keep[imax] = True
            stack.append((a, imax))
            stack.append((imax, b))
    return [c for c, k in zip(coords, keep) if k]


def assemble_rings(ways):
    """Stitch way coordinate lists into closed rings by matching endpoints."""
    segs = [list(w) for w in ways if len(w) >= 2]
    rings = []
    while segs:
        ring = segs.pop()
        progress = True
        while ring[0] != ring[-1] and progress:
            progress = False
            for i, s in enumerate(segs):
                if s[0] == ring[-1]:
                    ring += s[1:]
                elif s[-1] == ring[-1]:
                    ring += s[-2::-1]
                elif s[-1] == ring[0]:
                    ring = s[:-1] + ring
                elif s[0] == ring[0]:
                    ring = s[::-1][:-1] + ring
                else:
                    continue
                segs.pop(i)
                progress = True
                break
        if ring[0] == ring[-1] and len(ring) >= 4:
            rings.append(ring)
    return rings


def way_coords(el):
    return [[round(p["lon"], 6), round(p["lat"], 6)] for p in el.get("geometry") or []]


def polygons_from_elements(elements):
    """Build MultiPolygon coordinates from Overpass ways/relations with geometry."""
    outers, inners = [], []
    for el in elements:
        if el["type"] == "way":
            c = way_coords(el)
            if len(c) >= 4 and c[0] == c[-1]:
                outers.append(c)
        elif el["type"] == "relation":
            o_ways = [way_coords(m) for m in el.get("members", [])
                      if m["type"] == "way" and m.get("role") in ("outer", "")]
            i_ways = [way_coords(m) for m in el.get("members", [])
                      if m["type"] == "way" and m.get("role") == "inner"]
            outers += assemble_rings(o_ways)
            inners += assemble_rings(i_ways)
    if not outers:
        return None
    outers = [simplify(r) for r in outers]
    inners = [simplify(r) for r in inners if len(r) > 20]  # keep only big islands
    # assign inners to the largest outer (good enough for lakes)
    polys = [[o] for o in sorted(outers, key=len, reverse=True)]
    if inners and polys:
        polys[0] += inners
    return polys


def lines_from_elements(elements):
    lines = []
    for el in elements:
        if el["type"] == "way":
            c = way_coords(el)
            if len(c) >= 2:
                lines.append(simplify(c))
        elif el["type"] == "relation":
            for m in el.get("members", []):
                if m["type"] == "way":
                    c = way_coords(m)
                    if len(c) >= 2:
                        lines.append(simplify(c))
    return lines or None


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    reg = yaml.safe_load((ROOT / "data/waterbodies/registry.yaml").read_text(encoding="utf-8"))
    entries = reg["waterbodies"]
    outdir = ROOT / "data/geometry"
    outdir.mkdir(exist_ok=True)

    # name -> entry lookup (normalized, includes alt names)
    lookup = {}
    for e in entries:
        for n in [e["osm_name"]] + e.get("alt_names", []):
            lookup.setdefault(norm(n), []).append(e)

    def name_regex(items):
        names = set()
        for e in items:
            names.add(e["osm_name"])
            names.update(e.get("alt_names", []))
        return "|".join(sorted(n.replace("(", r"\(").replace(")", r"\)") for n in names))

    lakes = [e for e in entries if e["type"] == "lake"]
    rivers = [e for e in entries if e["type"] == "river"]

    print(f"querying {len(lakes)} lakes, {len(rivers)} rivers via Overpass...")

    # NB: (area:...) misses large multipolygon lake relations — use a bbox over
    # southern Chile (south,west,north,east) instead; catches border lakes too.
    q_lakes = f"""[out:json][timeout:300][bbox:-49.7,-76.0,-38.4,-70.7];
(
  way["natural"="water"]["name"~"^({name_regex(lakes)})$"];
  relation["natural"="water"]["name"~"^({name_regex(lakes)})$"];
);
out tags geom;"""
    lakes_res = overpass(q_lakes)
    print(f"  lakes: {len(lakes_res['elements'])} elements")
    time.sleep(5)

    q_waterways = f"""[out:json][timeout:300];
(
  relation["waterway"]["name"~"^({name_regex(rivers)})$"](area:{CHILE_AREA});
  way["waterway"~"^(river|stream)$"]["name"~"^({name_regex(rivers)})$"](area:{CHILE_AREA});
);
out tags geom;"""
    ww_res = overpass(q_waterways)
    print(f"  waterways: {len(ww_res['elements'])} elements")
    time.sleep(5)

    q_rpoly = f"""[out:json][timeout:300];
(
  way["natural"="water"]["water"~"^(river|canal|stream)$"]["name"~"^({name_regex(rivers)})$"](area:{CHILE_AREA});
  relation["natural"="water"]["water"~"^(river|canal|stream)$"]["name"~"^({name_regex(rivers)})$"](area:{CHILE_AREA});
);
out tags geom;"""
    rpoly_res = overpass(q_rpoly)
    print(f"  river polygons: {len(rpoly_res['elements'])} elements")

    # bucket elements per registry id
    buckets = {}
    for res, kind in ((lakes_res, "lake"), (ww_res, "waterway"), (rpoly_res, "rpoly")):
        for el in res["elements"]:
            nm = norm((el.get("tags") or {}).get("name", ""))
            for e in lookup.get(nm, []):
                if (e["type"] == "lake") != (kind == "lake"):
                    continue
                buckets.setdefault(e["id"], {"lake": [], "waterway": [], "rpoly": []})[kind].append(el)

    written, missing = [], []
    for e in entries:
        b = buckets.get(e["id"])
        geom = None
        if e["type"] == "lake" and b and b["lake"]:
            polys = polygons_from_elements(b["lake"])
            if polys:
                geom = {"type": "MultiPolygon", "coordinates": polys}
        elif e["type"] == "river" and b:
            polys = polygons_from_elements(b["rpoly"]) if b["rpoly"] else None
            lines = lines_from_elements(b["waterway"]) if b["waterway"] else None
            if polys and lines:
                geom = {"type": "GeometryCollection", "geometries": [
                    {"type": "MultiPolygon", "coordinates": polys},
                    {"type": "MultiLineString", "coordinates": lines}]}
            elif polys:
                geom = {"type": "MultiPolygon", "coordinates": polys}
            elif lines:
                geom = {"type": "MultiLineString", "coordinates": lines}
        if geom:
            feat = {"type": "Feature", "properties": {"id": e["id"], "name": e["name"],
                    "type": e["type"], "region": e["region"]}, "geometry": geom}
            (outdir / f"{e['id']}.geojson").write_text(
                json.dumps(feat, ensure_ascii=False), encoding="utf-8")
            written.append(e["id"])
        else:
            missing.append((e["id"], e.get("optional", False)))

    print(f"\nwrote {len(written)} geometries")
    req_missing = [m for m, opt in missing if not opt]
    opt_missing = [m for m, opt in missing if opt]
    if req_missing:
        print("MISSING (required):", ", ".join(req_missing))
    if opt_missing:
        print("missing (optional):", ", ".join(opt_missing))
    return 1 if req_missing else 0


if __name__ == "__main__":
    sys.exit(main())
