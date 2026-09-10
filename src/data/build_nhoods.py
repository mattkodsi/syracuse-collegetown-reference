#!/usr/bin/env python3
"""Neighborhood boundaries for the map: the City of Syracuse "Syracuse Neighborhoods 2017"
polygons (the same layer the study boundary uses). Keeps the neighborhoods that have parcels
in parcels.js, tags the three core ones, computes a label point inside each polygon
(pole of inaccessibility, Mapbox polylabel algorithm), and emits data/nhoods.js (window.NHOODS).

Usage: python3 build_nhoods.py [--refresh]   (re-pulls from the FeatureServer; otherwise reuses _raw)
"""
import json, math, heapq, os, sys, urllib.request, urllib.parse
from build_parcels import CORE_NHOODS

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "_raw", "nhoods_raw.geojson")
OUT = os.path.join(HERE, "nhoods.js")
PARCELS_JS = os.path.join(HERE, "parcels.js")
LAYER = ("https://services.arcgis.com/uDTUpUPbk8X8mXwl/arcgis/rest/services/"
         "Syracuse_Neighborhoods_2017/FeatureServer/0/query")
LOCAL_COPY = os.environ.get("NHOODS_LOCAL", "")   # optional captured copy as a fallback


def pull():
    params = {"where": "1=1", "outFields": "NAME,acres,Neigh_Cate", "returnGeometry": "true",
              "outSR": "4326", "f": "geojson"}
    url = LAYER + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            fc = json.load(r)
        assert fc.get("features"), "empty response"
        print(f"pulled {len(fc['features'])} neighborhood polygons from the FeatureServer")
    except Exception as e:
        if not LOCAL_COPY or not os.path.exists(LOCAL_COPY):
            raise SystemExit(f"FeatureServer pull failed ({e}) and no local copy given (NHOODS_LOCAL=...)")
        fc = json.load(open(LOCAL_COPY))
        print(f"FeatureServer pull failed ({e}); using local copy {LOCAL_COPY} ({len(fc['features'])} polygons)")
    os.makedirs(os.path.dirname(RAW), exist_ok=True)
    json.dump(fc, open(RAW, "w"))
    return fc


# ---- polylabel (Mapbox algorithm): the point inside a polygon farthest from its edges ----
def _seg_dist_sq(px, py, a, b):
    x, y = a; dx = b[0] - x; dy = b[1] - y
    if dx or dy:
        t = ((px - x) * dx + (py - y) * dy) / (dx * dx + dy * dy)
        if t > 1: x, y = b
        elif t > 0: x += dx * t; y += dy * t
    dx = px - x; dy = py - y
    return dx * dx + dy * dy

def _dist(x, y, polygon):
    inside = False; best = math.inf
    for ring in polygon:
        n = len(ring)
        for i in range(n):
            a = ring[i]; b = ring[i - 1]
            if (a[1] > y) != (b[1] > y) and (x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]):
                inside = not inside
            best = min(best, _seg_dist_sq(x, y, a, b))
    return (1 if inside else -1) * math.sqrt(best)

class _Cell:
    __slots__ = ("x", "y", "h", "d", "max")
    def __init__(self, x, y, h, polygon):
        self.x, self.y, self.h = x, y, h
        self.d = _dist(x, y, polygon); self.max = self.d + h * math.sqrt(2)

def polylabel(polygon, precision=1e-5):
    ring = polygon[0]
    minx = min(p[0] for p in ring); maxx = max(p[0] for p in ring)
    miny = min(p[1] for p in ring); maxy = max(p[1] for p in ring)
    w, h = maxx - minx, maxy - miny; size = min(w, h)
    if size == 0: return [minx, miny], 0.0
    cs = size / 2; hh = cs / 2
    heap = []; n = 0
    def push(c):
        nonlocal n; n += 1; heapq.heappush(heap, (-c.max, n, c))
    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            push(_Cell(x + hh, y + hh, hh, polygon)); y += cs
        x += cs
    # seed with the centroid and the bbox centre
    area = cx = cy = 0.0
    for i in range(len(ring)):
        a = ring[i]; b = ring[i - 1]; f = a[0] * b[1] - b[0] * a[1]
        cx += (a[0] + b[0]) * f; cy += (a[1] + b[1]) * f; area += f * 3
    best = _Cell(cx / area, cy / area, 0, polygon) if area else _Cell(ring[0][0], ring[0][1], 0, polygon)
    bc = _Cell(minx + w / 2, miny + h / 2, 0, polygon)
    if bc.d > best.d: best = bc
    while heap:
        _, _, c = heapq.heappop(heap)
        if c.d > best.d: best = c
        if c.max - best.d <= precision: continue
        q = c.h / 2
        for dx in (-1, 1):
            for dy in (-1, 1):
                push(_Cell(c.x + dx * q, c.y + dy * q, q, polygon))
    return [best.x, best.y], best.d


def ring_area(ring):
    return abs(sum(ring[i][0] * ring[i - 1][1] - ring[i - 1][0] * ring[i][1] for i in range(len(ring)))) / 2

def main():
    if os.path.exists(RAW) and "--refresh" not in sys.argv:
        fc = json.load(open(RAW)); print(f"reusing {RAW}")
    else:
        fc = pull()
    t = open(PARCELS_JS, encoding="utf-8").read()
    parcels = json.loads(t[t.index("{"):t.rindex("}") + 1])
    present = {f["properties"].get("nhood") for f in parcels["features"]} - {None}
    out = []
    for f in fc["features"]:
        name = (f["properties"].get("NAME") or "").strip()
        if name not in present: continue
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        biggest = max(polys, key=lambda p: ring_area(p[0]))
        center, d = polylabel(biggest)
        rnd = lambda ring: [[round(p[0], 5), round(p[1], 5)] for p in ring]
        geom = ({"type": "Polygon", "coordinates": [rnd(r) for r in polys[0]]} if len(polys) == 1
                else {"type": "MultiPolygon", "coordinates": [[rnd(r) for r in p] for p in polys]})
        acres = f["properties"].get("acres")
        out.append({"type": "Feature", "geometry": geom, "properties": {
            "name": name, "core": 1 if name in CORE_NHOODS else 0,
            "acres": round(acres, 1) if isinstance(acres, (int, float)) else None,
            "center": [round(center[0], 6), round(center[1], 6)]}})
        inside = _dist(center[0], center[1], biggest) > 0
        print(f"  {'CORE' if name in CORE_NHOODS else 'ctx '} {name:26s} label at {center[0]:.5f},{center[1]:.5f}  inside={inside}  clearance≈{d*111000*0.75:.0f} m")
    out.sort(key=lambda x: (-x["properties"]["core"], x["properties"]["name"]))
    with open(OUT, "w") as fh:
        fh.write("window.NHOODS = "); json.dump({"type": "FeatureCollection", "features": out}, fh, separators=(",", ":")); fh.write(";\n")
    print(f"wrote {len(out)} neighborhoods ({sum(1 for x in out if x['properties']['core'])} core) -> {OUT} ({os.path.getsize(OUT)/1024:.0f} KB)")

if __name__ == "__main__":
    main()
