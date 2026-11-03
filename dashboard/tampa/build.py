"""One-time builder: turns OpenStreetMap data for downtown Tampa into dashboard/tampa/tampa.json.

The 3D city loads tampa.json; this script is only needed to rebuild it. It needs `shapely`
(not part of requirements.txt):

    pip install shapely
    python dashboard/tampa/build.py <folder with buildings.json roads.json water.json parks.json>

The input files are Overpass API results (`out geom`) for the downtown area. Map data
© OpenStreetMap contributors, available under the Open Database License (ODbL).
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

from shapely.geometry import LineString, MultiLineString, Point, Polygon, box
from shapely.ops import linemerge, polygonize, unary_union

LAT0, LON0 = 27.9490, -82.4590                 # downtown Tampa (Franklin St & Kennedy Blvd area)
M_LAT = 110_540.0
M_LON = 111_320.0 * math.cos(math.radians(LAT0))
VIEW = box(-1500, -1650, 1500, 1500)           # the area drawn in the city, metres (x east, z south)

ROAD_WIDTH = {"motorway": 22, "trunk": 20, "primary": 16, "secondary": 14, "tertiary": 11, "motorway_link": 8,
              "primary_link": 8, "secondary_link": 8, "tertiary_link": 7, "unclassified": 8, "residential": 8,
              "living_street": 6, "service": 5, "pedestrian": 6}
CAR_ROADS = {"motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified"}
LIT_ROADS = {"primary", "secondary", "tertiary"}

# Real towers the fund's agents move into (OSM name → agent id)
LANDMARKS = {
    "Bank of America Plaza": "portfolio_manager",
    "100 North Tampa": "market_analyst",
    "Rivergate Tower": "risk_manager",
    "Truist Place": "fundamentals",
    "WFLA News Channel 8 Studios": "news",
    "Park Tower": "bull",
    "SkyPoint": "bear",
    "Sam M. Gibbons United States Federal Courthouse": "auditor",
}


def xz(lon, lat):
    return (lon - LON0) * M_LON, -(lat - LAT0) * M_LAT


def ring(geom_pts):
    return [xz(p["lon"], p["lat"]) for p in geom_pts]


def flat(coords, nd=1):
    out = []
    for x, z in coords:
        out += [round(x, nd), round(z, nd)]
    return out


def height(tags):
    for key in ("height", "building:height"):
        if key in tags:
            try:
                return float(str(tags[key]).lower().replace("m", "").replace("ft", "").split()[0]) * (0.3048 if "ft" in str(tags[key]) else 1)
            except ValueError:
                pass
    if "building:levels" in tags:
        try:
            return float(tags["building:levels"]) * 3.5 + 1
        except ValueError:
            pass
    kind = tags.get("building", "yes")
    return {"house": 7, "residential": 9, "garage": 4, "shed": 3, "roof": 5, "parking": 14, "apartments": 18,
            "commercial": 12, "office": 18, "retail": 7, "industrial": 9, "church": 12, "hotel": 30}.get(kind, 10)


def main(src: Path, out: Path):
    load = lambda name: json.loads((src / f"{name}.json").read_text())["elements"]
    random.seed(1904)   # the year Tampa's downtown grid was replatted after the 1904 fire — any fixed seed works

    # ---------------- Land and water ----------------
    coast = [LineString(ring(e["geometry"])) for e in load("water") if e.get("tags", {}).get("natural") == "coastline" and e["type"] == "way"]
    merged = linemerge(MultiLineString(coast))
    lines = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
    area = VIEW.buffer(300)
    pieces = list(polygonize(unary_union([*[l for l in lines], area.exterior])))
    land = []
    for poly in pieces:
        if not poly.intersects(area):
            continue
        # Coastlines run with land on the LEFT. Test a point just left of a coastline segment on this polygon's edge.
        verdict = None
        for l in lines:
            if not l.intersects(poly.buffer(0.5)):
                continue
            coords = list(l.coords)
            for (x1, z1), (x2, z2) in zip(coords, coords[1:]):
                mx, mz = (x1 + x2) / 2, (z1 + z2) / 2
                if poly.exterior.distance(Point(mx, mz)) > 0.5:
                    continue
                dx, dz = x2 - x1, z2 - z1
                n = math.hypot(dx, dz) or 1
                # x east, z south: "left" of travel in map terms (north up) is (-dz, dx) flipped by the z axis
                lx, lz = mx + dz / n * 2.0, mz - dx / n * 2.0
                verdict = poly.contains(Point(lx, lz))
                break
            if verdict is not None:
                break
        if verdict:
            land.append(poly.intersection(area))
    land_u = unary_union(land) if land else area

    inland_water = []
    for e in load("water"):
        t = e.get("tags", {})
        if t.get("natural") != "water":
            continue
        if e["type"] == "way" and len(e["geometry"]) > 3:
            poly = Polygon(ring(e["geometry"]))
        elif e["type"] == "relation":
            outers = [LineString(ring(m["geometry"])) for m in e.get("members", []) if m.get("role") == "outer" and m.get("geometry")]
            polys = list(polygonize(linemerge(MultiLineString(outers)))) if outers else []
            poly = unary_union(polys) if polys else None
        else:
            poly = None
        if poly is not None and poly.is_valid and poly.intersects(area):
            inland_water.append(poly.intersection(area))
    water_u = unary_union(inland_water) if inland_water else Polygon()
    land_u = land_u.difference(water_u)

    def polys(g):
        return [g] if g.geom_type == "Polygon" else [p for p in getattr(g, "geoms", []) if p.geom_type == "Polygon"]

    land_rings = [flat(p.simplify(1.5).exterior.coords) for p in polys(land_u) if p.area > 50]
    land_holes = [flat(h.coords) for p in polys(land_u) for h in p.simplify(1.5).interiors if Polygon(h).area > 50]

    # ---------------- Buildings ----------------
    buildings, landmarks = [], {}
    for e in load("buildings"):
        t = e.get("tags", {})
        if e["type"] == "way" and e.get("geometry") and len(e["geometry"]) >= 4:
            poly = Polygon(ring(e["geometry"]))
        elif e["type"] == "relation":
            outers = [Polygon(ring(m["geometry"])) for m in e.get("members", []) if m.get("role") == "outer" and m.get("geometry") and len(m["geometry"]) >= 4]
            poly = max(outers, key=lambda p: p.area) if outers else None
        else:
            poly = None
        if poly is None or not poly.is_valid or poly.area < 12 or not VIEW.contains(poly.centroid):
            continue
        p = poly.simplify(0.4)
        h = round(max(3.0, height(t)), 1)
        name = t.get("name")
        if name in LANDMARKS and LANDMARKS[name] not in landmarks.values():
            landmarks[str(len(buildings))] = LANDMARKS[name]
        buildings.append([h, name if h >= 40 else None, flat(list(p.exterior.coords)[:-1])])

    # ---------------- Roads, lanes, walks, lamps, trees ----------------
    roads, lanes, walks, lamps, trees = [], [], [], [], []
    road_lines, riverwalk_lines = [], []
    for e in load("roads"):
        t = e.get("tags", {})
        kind = t.get("highway")
        g = e.get("geometry")
        if not g or len(g) < 2:
            continue
        line = LineString(ring(g))
        if not line.intersects(VIEW):
            continue
        line = line.intersection(VIEW)
        parts = [line] if line.geom_type == "LineString" else [l for l in getattr(line, "geoms", []) if l.geom_type == "LineString"]
        bridge = 1 if t.get("bridge") in ("yes", "viaduct") or t.get("layer", "0") not in ("0", "-1", "-2") and kind in ("motorway", "motorway_link", "trunk") else 0
        riverwalk = "riverwalk" in (t.get("name", "") or "").lower()
        for part in parts:
            part = part.simplify(0.8)
            if part.length < 4:
                continue
            pts = flat(part.coords)
            if kind in ROAD_WIDTH and not (kind == "service" and t.get("service") in ("parking_aisle", "driveway", "drive-through")):
                w = ROAD_WIDTH[kind]
                roads.append([w, 1 if kind == "pedestrian" else 0, bridge, pts])
                road_lines.append((part, w, kind))
                if kind in CAR_ROADS and part.length > 60:
                    lanes.append([w, 1 if t.get("oneway") == "yes" else 0, bridge, pts])
                if not bridge and kind not in ("motorway", "motorway_link", "trunk"):
                    for side in (-1, 1):
                        off = part.parallel_offset(w / 2 + 2.2, "left" if side < 0 else "right")
                        if off.geom_type == "LineString" and off.length > 30:
                            walks.append(flat(off.simplify(1).coords))
            elif kind in ("footway", "path") and riverwalk:
                roads.append([5, 1, bridge, pts])
                walks.append(pts)
                if not bridge:
                    riverwalk_lines.append(part)
    # street lights and street trees along lit roads
    for part, w, kind in road_lines:
        if kind not in LIT_ROADS:
            continue
        d = 0.0
        while d < part.length:
            a, b = part.interpolate(d), part.interpolate(min(d + 1, part.length))
            dx, dz = b.x - a.x, b.y - a.y
            n = math.hypot(dx, dz) or 1
            nx, nz = -dz / n, dx / n
            for side in (-1, 1):
                lx, lz = a.x + nx * side * (w / 2 + 0.8), a.y + nz * side * (w / 2 + 0.8)
                if land_u.contains(Point(lx, lz)):
                    lamps += [round(lx, 1), round(lz, 1), round(-nx * side, 2), round(-nz * side, 2)]
                tx, tz = a.x + nx * side * (w / 2 + 3.2) + random.uniform(-1, 1), a.y + nz * side * (w / 2 + 3.2) + random.uniform(-1, 1)
                if random.random() < 0.6 and land_u.contains(Point(tx, tz)):
                    trees += [round(tx, 1), round(tz, 1)]
            d += 32

    # ---------------- Riverwalk spots for the stock "data pillars" ----------------
    # The longest stretch of Riverwalk near downtown; pillars stand on its water side, 40 m apart.
    pillars = []
    near = [l for l in riverwalk_lines if l.distance(Point(0, 0)) < 900]
    if near:
        walk = max(linemerge(MultiLineString(near)).geoms if linemerge(MultiLineString(near)).geom_type == "MultiLineString"
                   else [linemerge(MultiLineString(near))], key=lambda l: l.length)
        d = 30.0
        while d < walk.length - 20 and len(pillars) < 24:
            a, b = walk.interpolate(d), walk.interpolate(d + 1)
            dx, dz = b.x - a.x, b.y - a.y
            n = math.hypot(dx, dz) or 1
            for side in (1, -1):              # step toward the water, staying on land
                px, pz = a.x + (-dz / n) * side * 6, a.y + (dx / n) * side * 6
                if land_u.contains(Point(px, pz)):
                    pillars += [round(px, 1), round(pz, 1)]
                    break
            d += 40

    # ---------------- Parks ----------------
    parks = []
    built = unary_union([Polygon(list(zip(b[2][::2], b[2][1::2]))).buffer(0) for b in buildings])
    for e in load("parks"):
        g = e.get("geometry")
        if not g or len(g) < 4:
            continue
        poly = Polygon(ring(g))
        if not poly.is_valid or not poly.intersects(VIEW) or poly.area < 80:
            continue
        poly = poly.intersection(VIEW)
        for p in polys(poly):
            parks.append(flat(p.simplify(1).exterior.coords))
            free = p.difference(built).difference(water_u)
            n = int(min(400, p.area / 140))
            minx, minz, maxx, maxz = p.bounds
            for _ in range(n):
                x, z = random.uniform(minx, maxx), random.uniform(minz, maxz)
                if free.contains(Point(x, z)):
                    trees += [round(x, 1), round(z, 1)]

    data = {
        "attribution": "Map data © OpenStreetMap contributors (ODbL)",
        "origin": [LAT0, LON0],
        "bounds": [round(c) for c in VIEW.bounds],
        "land": land_rings, "land_holes": land_holes,
        "buildings": buildings, "landmarks": landmarks,
        "roads": roads, "lanes": lanes, "walks": walks,
        "parks": parks, "trees": trees, "lamps": lamps, "pillars": pillars,
    }
    out.write_text(json.dumps(data, separators=(",", ":")))
    print(f"wrote {out}: {out.stat().st_size / 1e6:.1f} MB · {len(buildings)} buildings · {len(roads)} road pieces · "
          f"{len(lanes)} car lanes · {len(walks)} walkways · {len(trees) // 2} trees · {len(lamps) // 4} lamps · "
          f"{len(land_rings)} land areas · {len(pillars) // 2} pillar spots · landmarks {sorted(landmarks.values())}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(__file__).with_name("tampa.json"))
