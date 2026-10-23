"""Extract + Transform ของแต่ละแหล่ง

extract_*   → คืนข้อมูลดิบ (list[dict]) ตามที่แหล่งให้มา
transform_* → แปลงข้อมูลดิบให้เป็น schema เดียวกัน (ดู UNIFIED_FIELDS)
"""

import json
import logging
import math
import re
from typing import Any, Iterator
from urllib.parse import quote

from bs4 import BeautifulSoup

from restaurant_pipeline import config
from restaurant_pipeline.web_client import polite_get, session

log = logging.getLogger(__name__)

UNIFIED_FIELDS = [
    "source", "source_id", "name", "name_norm", "category", "rating", "review_count",
    "price_level", "lat", "lon", "address", "area", "url",
]

# ===========================================================================
# helpers
# ===========================================================================
_GENERIC_WORDS = re.compile(
    r"(ร้าน|ร้านอาหาร|อาหาร|คาเฟ่|สาขา\S*|restaurant|cafe|café|coffee|shop|the|by)",
    re.IGNORECASE,
)


def normalize_name(name: str | None) -> str:
    """ชื่อสำหรับเทียบความเหมือน: ตัดคำทั่วไป เครื่องหมาย และช่องว่าง"""
    if not name:
        return ""
    s = name.lower()
    s = re.sub(r"\(.*?\)", " ", s)        # ตัดวงเล็บ เช่น (สาขากำแพงแสน)
    s = _GENERIC_WORDS.sub(" ", s)
    s = re.sub(r"[^\w฀-๿]+", " ", s)
    return " ".join(s.split())


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_area(lat: float | None, lon: float | None) -> str | None:
    if lat is None or lon is None:
        return None
    best = min(config.AREAS, key=lambda a: haversine_m(lat, lon, a["lat"], a["lon"]))
    return best["name"]


def _to_float(v) -> float | None:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v) -> int | None:
    f = _to_float(v)
    return None if f is None else int(f)


def _record(**kw) -> dict:
    rec = {k: kw.get(k) for k in UNIFIED_FIELDS}
    rec["name"] = (rec["name"] or "").strip()
    rec["name_norm"] = normalize_name(rec["name"])
    rec["source_id"] = str(rec["source_id"])
    return rec


# ===========================================================================
# 1) Wongnai — web scraping ด้วย requests + BeautifulSoup
# ===========================================================================
def extract_wongnai(area: dict) -> list[dict]:
    s = session()
    rows: list[dict] = []
    seen: set[str] = set()
    for page in range(1, config.WONGNAI_MAX_PAGES + 1):
        url = config.WONGNAI_SEARCH_URL.format(query=quote(area["query"]), page=page)
        html = polite_get(s, url).text
        items = parse_wongnai_html(html)
        new = [it for it in items if it["id"] not in seen]
        log.info("Wongnai %s page %d: %d items (%d new)", area["name"], page, len(items), len(new))
        if not new:
            break
        for it in new:
            seen.add(it["id"])
            it["area"] = area["name"]
        rows.extend(new)
    if not rows:
        # ไม่เจออะไรเลย = โครงสร้างหน้าเว็บเปลี่ยน หรือโดนบล็อก → ให้ task fail เพื่อให้เห็นใน Grid view
        raise ValueError(f"Wongnai: parse ไม่ได้สักร้านสำหรับ {area['name']} — ตรวจ URL/parser")
    return rows


def parse_wongnai_html(html: str) -> list[dict]:
    """หาข้อมูลร้านจาก HTML

    ลอง 2 วิธีตามลำดับ (TODO วันสอบ: ตรวจกับหน้าเว็บจริงแล้วปรับ):
      1. JSON-LD (schema.org Restaurant / ItemList)
      2. JSON ที่ฝังใน <script id="__NEXT_DATA__"> — เดินหา object ที่หน้าตาเหมือนร้าน
    """
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, dict] = {}

    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except json.JSONDecodeError:
            continue
        for obj in _walk(data):
            if _ld_type(obj) & {"Restaurant", "FoodEstablishment", "CafeOrCoffeeShop", "LocalBusiness"}:
                it = _from_jsonld(obj)
                if it:
                    found[it["id"]] = it

    # ItemList ใน JSON-LD มีแค่ URL ไม่มีคะแนน/พิกัด → อ่าน state ของหน้าเพิ่มเสมอ
    for state in _embedded_states(soup, html):
        for obj in _walk(state):
            it = _from_next_data(obj)
            if it:
                found.setdefault(it["id"], it)

    return list(found.values())


def _embedded_states(soup: BeautifulSoup, html: str) -> Iterator[Any]:
    """JSON state ที่ฝังในหน้า: __NEXT_DATA__ หรือ window._wn = {...} (หน้า Wongnai ปัจจุบัน)"""
    tag = soup.find("script", id="__NEXT_DATA__")
    if tag and tag.string:
        yield json.loads(tag.string)
    marker = "window._wn = "
    i = html.find(marker)
    if i != -1:
        try:
            yield json.JSONDecoder().raw_decode(html, i + len(marker))[0]
        except json.JSONDecodeError:
            log.warning("Wongnai: อ่าน window._wn ไม่ได้")


def _walk(node: Any) -> Iterator[dict]:
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _ld_type(obj: dict) -> set[str]:
    t = obj.get("@type")
    return set(t) if isinstance(t, list) else {t} if t else set()


def _from_jsonld(obj: dict) -> dict | None:
    name = obj.get("name")
    url = obj.get("url") or obj.get("@id")
    if not name or not url:
        return None
    geo = obj.get("geo") or {}
    agg = obj.get("aggregateRating") or {}
    addr = obj.get("address")
    if isinstance(addr, dict):
        addr = " ".join(str(addr.get(k, "")) for k in ("streetAddress", "addressLocality", "addressRegion")).strip()
    cuisine = obj.get("servesCuisine")
    return {
        "id": url.rstrip("/").split("/")[-1],
        "name": name,
        "url": url,
        "rating": agg.get("ratingValue"),
        "review_count": agg.get("reviewCount") or agg.get("ratingCount"),
        "lat": geo.get("latitude"),
        "lon": geo.get("longitude"),
        "category": ", ".join(cuisine) if isinstance(cuisine, list) else cuisine,
        "price": obj.get("priceRange"),
        "address": addr,
    }


def _from_next_data(obj: dict) -> dict | None:
    """heuristic: object ที่มีชื่อ + (คะแนน หรือ พิกัด) + id ถือว่าเป็นร้าน"""
    name = obj.get("name") or obj.get("displayName")
    if not isinstance(name, str) or not name.strip():
        return None
    rid = obj.get("publicId") or obj.get("rid") or obj.get("id")
    if rid is None:
        return None

    rating = obj.get("rating") or obj.get("averageRating")
    if isinstance(rating, dict):
        rating = rating.get("value") or rating.get("rating")
    stat = obj.get("statistic") or {}
    if not rating and isinstance(stat, dict):
        rating = stat.get("rating")

    loc = obj.get("location") or obj.get("coordinate") or obj
    lat = (loc.get("lat") or loc.get("latitude")) if isinstance(loc, dict) else None
    lon = (loc.get("lng") or loc.get("lon") or loc.get("longitude")) if isinstance(loc, dict) else None

    if rating is None and lat is None:
        return None

    cat = obj.get("categories") or obj.get("category")
    if isinstance(cat, list):
        cat = ", ".join(c.get("name", "") if isinstance(c, dict) else str(c) for c in cat)
    elif isinstance(cat, dict):
        cat = cat.get("name")

    url = obj.get("url") or obj.get("shortUrl")
    if url and not url.startswith("http"):
        url = "https://www.wongnai.com/" + url.lstrip("/")
    return {
        "id": str(rid),
        "name": name,
        "url": url,
        "rating": rating,
        "review_count": (stat.get("numberOfReviews") if isinstance(stat, dict) else None)
        or obj.get("numberOfReviews") or obj.get("reviewCount"),
        "lat": lat,
        "lon": lon,
        "category": cat,
        "price": (obj.get("priceRange") or {}).get("name") if isinstance(obj.get("priceRange"), dict) else obj.get("priceRange"),
        "address": obj.get("address") if isinstance(obj.get("address"), str) else None,
    }


def transform_wongnai(raw: list[dict]) -> list[dict]:
    return [
        _record(
            source="wongnai", source_id=r["id"], name=r["name"], category=r.get("category"),
            rating=_to_float(r.get("rating")), review_count=_to_int(r.get("review_count")),
            price_level=str(r["price"]) if r.get("price") else None,
            lat=_to_float(r.get("lat")), lon=_to_float(r.get("lon")),
            address=r.get("address"), area=r.get("area"), url=r.get("url"),
        )
        for r in raw
    ]


# ===========================================================================
# 2) OpenStreetMap — Overpass API (ไม่มีคะแนนรีวิว)
# ===========================================================================
def extract_osm() -> list[dict]:
    amenity = "|".join(config.OSM_AMENITIES)
    parts = "\n".join(
        f'  nwr(around:{a["radius_m"]},{a["lat"]},{a["lon"]})["amenity"~"^({amenity})$"];'
        for a in config.AREAS
    )
    query = f"[out:json][timeout:120];\n(\n{parts}\n);\nout center tags;"
    s = session()
    resp = s.post(config.OVERPASS_URL, data={"data": query}, timeout=180)
    resp.raise_for_status()
    elements = resp.json().get("elements", [])
    log.info("OSM: %d elements", len(elements))
    return elements


def transform_osm(raw: list[dict]) -> list[dict]:
    out = []
    for e in raw:
        tags = e.get("tags", {})
        name = tags.get("name:th") or tags.get("name") or tags.get("name:en")
        if not name:
            continue  # ร้านที่ไม่มีชื่อ เอาไปใช้ต่อไม่ได้
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lon = e.get("lon") or (e.get("center") or {}).get("lon")
        addr = " ".join(filter(None, [tags.get("addr:housenumber"), tags.get("addr:street"),
                                      tags.get("addr:subdistrict"), tags.get("addr:district")]))
        out.append(_record(
            source="osm", source_id=f'{e["type"]}/{e["id"]}', name=name,
            category=tags.get("cuisine") or tags.get("amenity"),
            lat=_to_float(lat), lon=_to_float(lon), address=addr or None,
            area=nearest_area(_to_float(lat), _to_float(lon)),
            url=f'https://www.openstreetmap.org/{e["type"]}/{e["id"]}',
        ))
    return out


# ===========================================================================
# 3) Overture Maps Places — GeoParquet บน S3 สาธารณะ อ่านด้วย DuckDB (ไม่ต้องใช้ key)
# ===========================================================================
def _overture_latest_release() -> str:
    """หา release ล่าสุดจาก listing ของ bucket (Overture ออก release ใหม่ทุกเดือน)"""
    resp = session().get(config.OVERTURE_BUCKET_URL,
                         params={"list-type": "2", "prefix": "release/", "delimiter": "/"},
                         timeout=config.HTTP_TIMEOUT_SEC)
    resp.raise_for_status()
    releases = re.findall(r"<Prefix>release/([^/<]+)/</Prefix>", resp.text)
    if not releases:
        raise ValueError("Overture: ไม่พบ release ใน bucket")
    return max(releases)


def extract_overture() -> list[dict]:
    import duckdb  # import ในฟังก์ชัน: DAG parse เร็วขึ้น

    release = _overture_latest_release()
    # กรอบสี่เหลี่ยมครอบทุกพื้นที่ (1 องศา ≈ 111 กม.) — DuckDB ใช้ bbox ข้าม row group ที่ไม่เกี่ยว
    pad = [a["radius_m"] / 111_000 for a in config.AREAS]
    min_lat = min(a["lat"] - p for a, p in zip(config.AREAS, pad))
    max_lat = max(a["lat"] + p for a, p in zip(config.AREAS, pad))
    min_lon = min(a["lon"] - p for a, p in zip(config.AREAS, pad))
    max_lon = max(a["lon"] + p for a, p in zip(config.AREAS, pad))

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
    rows = con.execute(f"""
        SELECT id, names."primary" AS name, basic_category AS category, confidence,
               (bbox.ymin + bbox.ymax) / 2 AS lat, (bbox.xmin + bbox.xmax) / 2 AS lon,
               addresses[1].freeform AS address, websites[1] AS website
        FROM read_parquet('{config.OVERTURE_PLACES_GLOB.format(release=release)}')
        WHERE bbox.xmin BETWEEN ? AND ? AND bbox.ymin BETWEEN ? AND ?
          AND list_contains(taxonomy.hierarchy, 'food_and_drink')
          AND confidence >= ?
          AND names."primary" IS NOT NULL
    """, [min_lon, max_lon, min_lat, max_lat, config.OVERTURE_MIN_CONFIDENCE]).fetchall()
    cols = ["id", "name", "category", "confidence", "lat", "lon", "address", "website"]
    places = [dict(zip(cols, r)) for r in rows]

    # กรอบสี่เหลี่ยมกินพื้นที่จังหวัดข้างเคียง → เก็บเฉพาะที่อยู่ในรัศมีของพื้นที่ใดพื้นที่หนึ่ง
    in_scope = [
        p for p in places
        if any(haversine_m(p["lat"], p["lon"], a["lat"], a["lon"]) <= a["radius_m"] for a in config.AREAS)
    ]
    log.info("Overture %s: %d food places in bbox, %d in areas", release, len(places), len(in_scope))
    return in_scope


def transform_overture(raw: list[dict]) -> list[dict]:
    return [
        _record(
            source="overture", source_id=p["id"], name=p["name"],
            category=(p.get("category") or "").replace("_", " ") or None,
            lat=_to_float(p.get("lat")), lon=_to_float(p.get("lon")),
            address=p.get("address"), area=nearest_area(_to_float(p.get("lat")), _to_float(p.get("lon"))),
            url=p.get("website"),
        )
        for p in raw
    ]
