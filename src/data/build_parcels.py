#!/usr/bin/env python3
"""Pull study-area parcels (a wider context extent around the three core neighborhoods)
from the City of Syracuse 2025 Q3 Parcel Map FeatureServer, classify ownership,
carry the full public record per parcel, simplify geometry, and emit
data/parcels.js (window.PARCELS).

Usage:
  python3 build_parcels.py --raw-only
  python3 build_parcels.py [--refresh]
"""
import json, sys, os, time, urllib.parse, urllib.request
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "_raw", "parcels_raw.geojson")
OUT = os.path.join(HERE, "parcels.js")
CORR = os.path.join(HERE, "owner_corrections.json")   # audit corrections keyed by owner string

LAYER = ("https://services6.arcgis.com/bdPqSfflsdgFRVVM/arcgis/rest/services/"
         "Syracuse_Parcel_Map_(2025_Q3)_view/FeatureServer/0/query")
# Wider context extent around the three core neighborhoods (University Hill,
# University Neighborhood, Westcott = City NHOOD polygons; south edge 43.020 so the
# whole University Neighborhood polygon is captured) plus surroundings west to
# I-81/downtown. Core parcels stay visually dominant in the map.
BBOX = "-76.160,43.020,-76.104,43.056"
CORE_NHOODS = {"University Hill", "University Neighborhood", "Westcott"}
OUTFIELDS = ("TAX_ID,PRINTKEY,ADDRESSNAM,FullAddres,REZONE,ZONE_DIST_,Owner,OwnerFullA,"
             "Add4_OwnCi,total_av,land_av,LU_parcel,LUC_parcel,n_ResUnits,IPSVacant,IPS_Condit,"
             "yr_built,ACRES,FRONT,DEPTH,NHOOD,TNT_NAME,CITY_WARD,DPW_Quad,InPD,PDNAME,"
             "CT_2020,CTLAB_2020,LATITUDE,LONGITUDE")
PAGE = 2000

CNY = {"SYRACUSE", "EAST SYRACUSE", "NORTH SYRACUSE", "DEWITT", "DE WITT", "MANLIUS",
       "FAYETTEVILLE", "JAMESVILLE", "LIVERPOOL", "CICERO", "CLAY", "BALDWINSVILLE",
       "CAMILLUS", "MARCELLUS", "SKANEATELES", "TULLY", "CAZENOVIA", "FABIUS", "LAFAYETTE",
       "LA FAYETTE", "MINOA", "SOLVAY", "WESTVALE", "MATTYDALE", "BREWERTON", "POMPEY",
       "ONONDAGA", "SALINA"}
HOSPITAL = ("UPSTATE", "CROUSE", "HOSPITAL", "VETERAN", "MEDICAL CENTER", "DIALYSIS",
            "HEALTH SYSTEM", "HEALTHCARE", "MEDICAL UNIVERSITY")
GOVERNMENT = ("CITY OF SYR", "COUNTY OF ONON", "ONONDAGA COUNTY", "STATE OF NEW YORK",
              "NEW YORK STATE", "STATE UNIV", "SUNY", "ESF", "ENVIRONMENTAL SCIENCE",
              "URBAN RENEWAL", "HOUSING AUTH", "LAND BANK", "GREATER SYRACUSE",
              "BOARD OF EDUC", "SCHOOL DIST")
NONPROFIT = ("CHURCH", "DIOCESE", "METHODIST", "TEMPLE", "SYNAGOGUE", "PARISH", "FOUNDATION",
             "YMCA", "YWCA", "MINISTR", "CHAPEL", "CONGREGATION", "CATHOLIC", "PRESBYTERIAN",
             "BAPTIST", "LUTHERAN", "SOCIETY")


def owner_class(owner):
    o = (owner or "").upper()
    if not o:
        return "private"
    if o.startswith("SYRACUSE UNIV") or "SYRACUSE UNIVERSITY" in o:
        return "su"
    if any(k in o for k in HOSPITAL) and "HOSPITALITY" not in o:   # hotels are not hospitals
        return "hospital"
    if any(k in o for k in GOVERNMENT):
        return "government"
    if any(k in o for k in NONPROFIT):
        return "nonprofit"
    return "private"


def load_corrections():
    """Owner-class overrides from the September 11, 2026 ownership audit (owner_corrections.json)."""
    if not os.path.exists(CORR):
        return {}
    d = json.load(open(CORR))
    return {k.strip().upper(): v for k, v in d["by_owner"].items()}


def parse_city_state(s):
    if not s:
        return ("", "")
    toks = s.upper().replace(",", " ").split()
    if toks and toks[-1].replace("-", "").isdigit():
        toks = toks[:-1]
    if not toks:
        return ("", "")
    if len(toks) >= 2 and len(toks[-1]) == 2 and toks[-1].isalpha():
        return (" ".join(toks[:-1]), toks[-1])
    return (" ".join(toks), "")


def owner_scope(owner_city_raw, cls):
    if cls != "private":
        return "na"
    city, state = parse_city_state(owner_city_raw)
    if state and state != "NY":
        return "national"
    if city in CNY:
        return "local"
    if state == "NY":
        return "nyother"
    return "unknown"


def _get(offset):
    params = {
        "geometry": BBOX, "geometryType": "esriGeometryEnvelope", "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects", "where": "1=1",
        "outFields": OUTFIELDS, "returnGeometry": "true", "outSR": "4326", "f": "geojson",
        "resultOffset": str(offset), "resultRecordCount": str(PAGE),
    }
    url = LAYER + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=180) as r:
        return json.load(r)


def pull():
    feats, offset = [], 0
    while True:
        fc = _get(offset)
        batch = fc.get("features", [])
        feats.extend(batch)
        print(f"  offset {offset}: +{len(batch)} (total {len(feats)})")
        if len(batch) < PAGE:
            break
        offset += PAGE
        time.sleep(0.3)
    os.makedirs(os.path.dirname(RAW), exist_ok=True)
    json.dump({"type": "FeatureCollection", "features": feats}, open(RAW, "w"))
    print(f"pulled {len(feats)} features -> {RAW}")
    return feats


def round_coords(geom, nd=5):
    def ring(rg):
        return [[round(p[0], nd), round(p[1], nd)] for p in rg]
    t = geom.get("type")
    if t == "Polygon":
        geom["coordinates"] = [ring(r) for r in geom["coordinates"]]
    elif t == "MultiPolygon":
        geom["coordinates"] = [[ring(r) for r in poly] for poly in geom["coordinates"]]
    return geom


def clean(v):
    if isinstance(v, str):
        v = v.strip()
        return v if v else None
    return v


def build(feats):
    corr = load_corrections()
    applied = Counter()
    out = []
    for f in feats:
        g = f.get("geometry")
        p = f.get("properties", {})
        if not g or not g.get("coordinates"):
            continue
        owner = p.get("Owner")
        cls = owner_class(owner)
        note = None
        fix = corr.get((owner or "").strip().upper())
        if fix:
            cls, note = fix["ownerClass"], fix.get("note")
            applied[(owner or "").strip().upper()] += 1
        scope = owner_scope(p.get("Add4_OwnCi"), cls)
        vac = (p.get("IPSVacant") or "").strip()
        tract = p.get("CT_2020")
        pr = {
            "taxId": clean(p.get("TAX_ID")), "printkey": clean(p.get("PRINTKEY")),
            "addr": (p.get("FullAddres") or "").strip(), "street": (p.get("ADDRESSNAM") or "").strip(),
            "tract": tract, "tractLab": clean(p.get("CTLAB_2020")),
            "core": 1 if clean(p.get("NHOOD")) in CORE_NHOODS else 0,
            "zone": clean(p.get("REZONE")), "zoneOld": clean(p.get("ZONE_DIST_")),
            "owner": clean(owner), "ownerFull": clean(p.get("OwnerFullA")),
            "ownerCity": clean(p.get("Add4_OwnCi")), "ownerClass": cls, "ownerScope": scope,
            "ownerNote": note,
            "av": p.get("total_av") or 0, "landAv": p.get("land_av") or 0,
            "landUse": clean(p.get("LU_parcel")), "landUseCode": clean(p.get("LUC_parcel")),
            "units": p.get("n_ResUnits") or 0, "vacant": bool(vac and vac not in ("", " ")),
            "condition": clean(p.get("IPS_Condit")), "year": p.get("yr_built") or None,
            "acres": round(p["ACRES"], 3) if p.get("ACRES") else None,
            "front": p.get("FRONT") or None, "depth": p.get("DEPTH") or None,
            "nhood": clean(p.get("NHOOD")), "tnt": clean(p.get("TNT_NAME")),
            "ward": clean(p.get("CITY_WARD")), "dpwQuad": clean(p.get("DPW_Quad")),
            "pd": clean(p.get("PDNAME")), "lat": p.get("LATITUDE"), "lon": p.get("LONGITUDE"),
        }
        pr = {k: v for k, v in pr.items() if v is not None}   # drop empties to save size
        out.append({"type": "Feature", "geometry": round_coords(g), "properties": pr})

    fc = {"type": "FeatureCollection", "features": out}
    with open(OUT, "w") as f:
        f.write("window.PARCELS = ")
        json.dump(fc, f, separators=(",", ":"))
        f.write(";\n")

    kb = os.path.getsize(OUT) / 1024
    for k in corr:
        if not applied.get(k):
            print(f"  WARNING: correction for {k!r} matched no parcel")
    print(f"  audit corrections applied: {sum(applied.values())} parcels across {len(applied)} owners: {dict(applied)}")
    core_n = sum(1 for x in out if x["properties"].get("core"))
    nh = Counter(x["properties"].get("nhood") for x in out if x["properties"].get("core"))
    print("  core parcels by neighborhood:", dict(nh))
    oc = Counter(x["properties"]["ownerClass"] for x in out if x["properties"].get("core"))
    val = defaultdict(float)
    for x in out:
        if x["properties"].get("core"):
            val[x["properties"]["ownerClass"]] += x["properties"]["av"]
    tot = sum(val.values()) or 1
    print(f"wrote {len(out)} parcels ({core_n} core / {len(out)-core_n} context) -> {OUT} ({kb:.0f} KB)")
    print("  core ownerClass:", dict(oc))
    print("  core value share:", {k: f"{100*v/tot:.1f}%" for k, v in sorted(val.items(), key=lambda kv: -kv[1])})


if __name__ == "__main__":
    raw_only = "--raw-only" in sys.argv
    if os.path.exists(RAW) and "--refresh" not in sys.argv:
        print(f"reusing {RAW} (pass --refresh to re-pull)")
        feats = json.load(open(RAW))["features"]
    else:
        feats = pull()
    if raw_only:
        sys.exit(0)
    build(feats)
