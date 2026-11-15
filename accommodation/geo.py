"""Add coordinates and driving distances (to the château and to the church) to listings.json.

Usage: python geo.py listings.json geo.json
"""
import json
import sys
import time

import requests

CHATEAU = (46.4665086, 3.6349779)
CHURCH = (46.5210270, 3.6816493)
UA = {"User-Agent": "generic-geo-client"}
BBOX = (45.8, 47.0, 2.9, 4.3)  # lat_min, lat_max, lon_min, lon_max — Allier + neighbours

cache = {}


def in_bbox(lat, lon):
    return lat is not None and lon is not None and BBOX[0] <= lat <= BBOX[1] and BBOX[2] <= lon <= BBOX[3]


def geocode(q):
    if q in cache:
        return cache[q]
    time.sleep(1.1)  # Nominatim usage policy: max 1 request/second
    r = requests.get("https://nominatim.openstreetmap.org/search",
                     params={"q": q, "format": "json", "limit": 1, "countrycodes": "fr"},
                     headers=UA, timeout=30)
    res = r.json()
    hit = (float(res[0]["lat"]), float(res[0]["lon"])) if res else None
    if hit and not in_bbox(*hit):
        hit = None
    cache[q] = hit
    return hit


def locate(l):
    if in_bbox(l.get("lat"), l.get("lon")):
        return (l["lat"], l["lon"]), "listing"
    village = l.get("village", "")
    addr = (l.get("address") or "").strip()
    if addr:
        hit = geocode(f"{addr}, {village}, France") or geocode(f"{addr}, France")
        if hit:
            return hit, "address"
    hit = geocode(f"{village}, Allier, France") or geocode(f"{village}, France")
    return (hit, "village") if hit else (None, "none")


def main(src, dst):
    listings = json.load(open(src))
    points = []
    for l in listings:
        p, how = locate(l)
        l["geo_point"], l["geo_precision"] = p, how
        if p:
            points.append(p)
    uniq = sorted(set(points))
    coords = ";".join(f"{lon},{lat}" for lat, lon in uniq + [CHATEAU, CHURCH])
    n = len(uniq)
    r = requests.get(
        f"https://router.project-osrm.org/table/v1/driving/{coords}",
        params={"sources": ";".join(map(str, range(n))),
                "destinations": f"{n};{n + 1}",
                "annotations": "distance,duration"},
        timeout=60).json()
    table = {pt: (r["distances"][i], r["durations"][i]) for i, pt in enumerate(uniq)}
    for l in listings:
        p = l["geo_point"]
        if p:
            (d_ch, d_cu), (t_ch, t_cu) = table[p]
            l["km_chateau"] = round(d_ch / 1000, 1)
            l["km_church"] = round(d_cu / 1000, 1)
            l["min_church"] = round(t_cu / 60)
        else:
            l["km_chateau"] = l["km_church"] = l["min_church"] = None
    json.dump(listings, open(dst, "w"), ensure_ascii=False, indent=1)
    print(f"{len(listings)} listings, {n} distinct points, "
          f"{sum(1 for l in listings if not l['geo_point'])} without location")


if __name__ == "__main__":
    main(*sys.argv[1:3])
