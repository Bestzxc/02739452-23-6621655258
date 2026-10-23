"""ตัดรายการซ้ำข้ามแหล่ง

ร้านสองรายการถือเป็นร้านเดียวกันเมื่อ
  - มีพิกัดทั้งคู่: ห่างกัน ≤ DEDUP_MAX_DISTANCE_M และชื่อคล้ายกัน ≥ DEDUP_NAME_SIMILARITY
  - ฝั่งใดไม่มีพิกัด: อยู่พื้นที่เดียวกัน และชื่อคล้ายกัน ≥ DEDUP_NAME_SIMILARITY_NO_GEO
ไม่จับคู่รายการจากแหล่งเดียวกัน (แหล่งเดียวกันถือว่าเป็นคนละร้านอยู่แล้ว)
และไม่จับคู่ถ้าตัวเลขในชื่อต่างกัน (เช่น "ร้าน 7" กับ "ร้าน 77")
จากนั้นรวมเป็นกลุ่มด้วย union-find (A=B, B=C → A,B,C เป็นร้านเดียวกัน)
"""

import re
from collections import defaultdict

from rapidfuzz import fuzz

from restaurant_pipeline import config
from restaurant_pipeline.sources import haversine_m

_CELL_DEG = 0.002  # ≈ 220 ม. ใช้แบ่งตารางเพื่อไม่ต้องเทียบทุกคู่


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def _similar(a: dict, b: dict, threshold: int) -> bool:
    if a["source"] == b["source"] or not a["name_norm"] or not b["name_norm"]:
        return False
    if re.findall(r"\d+", a["name_norm"]) != re.findall(r"\d+", b["name_norm"]):
        return False
    # ภาษาไทยไม่เว้นวรรคระหว่างคำ จึงเทียบแบบตัดช่องว่างทิ้งด้วย แล้วใช้ค่าที่มากกว่า
    score = max(
        fuzz.token_sort_ratio(a["name_norm"], b["name_norm"]),
        fuzz.ratio(a["name_norm"].replace(" ", ""), b["name_norm"].replace(" ", "")),
    )
    return score >= threshold


def cluster(rows: list[dict]) -> list[list[dict]]:
    uf = _UnionFind(len(rows))

    # 1) แถวที่มีพิกัด: เทียบเฉพาะแถวในช่องตารางเดียวกัน/ข้างเคียง
    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        if r["lat"] is not None and r["lon"] is not None:
            grid[(int(r["lat"] // _CELL_DEG), int(r["lon"] // _CELL_DEG))].append(i)

    for (cy, cx), members in grid.items():
        neighbours = [j for dy in (-1, 0, 1) for dx in (-1, 0, 1) for j in grid.get((cy + dy, cx + dx), [])]
        for i in members:
            for j in neighbours:
                if j <= i:
                    continue
                a, b = rows[i], rows[j]
                if (haversine_m(a["lat"], a["lon"], b["lat"], b["lon"]) <= config.DEDUP_MAX_DISTANCE_M
                        and _similar(a, b, config.DEDUP_NAME_SIMILARITY)):
                    uf.union(i, j)

    # 2) แถวที่ไม่มีพิกัด: เทียบกับทุกแถวในพื้นที่เดียวกัน ต้องชื่อเหมือนมากกว่า
    by_area: dict[str | None, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        by_area[r["area"]].append(i)
    for i, r in enumerate(rows):
        if r["lat"] is not None and r["lon"] is not None:
            continue
        for j in by_area[r["area"]]:
            if j != i and _similar(r, rows[j], config.DEDUP_NAME_SIMILARITY_NO_GEO):
                uf.union(i, j)

    groups: dict[int, list[dict]] = defaultdict(list)
    for i, r in enumerate(rows):
        groups[uf.find(i)].append(r)
    return list(groups.values())


def build_golden(group: list[dict]) -> dict:
    """รวมหลายแหล่งให้เหลือ 1 ร้าน — id ผูกกับสมาชิกที่น่าเชื่อถือที่สุด จึงคงที่เมื่อรันซ้ำ"""
    ordered = sorted(group, key=lambda r: (config.SOURCE_PRIORITY.get(r["source"], 99), r["source_id"]))
    primary = ordered[0]

    def first(field):
        return next((r[field] for r in ordered if r[field] not in (None, "")), None)

    rated = [r for r in group if r["rating"] is not None]
    weights = [max(r["review_count"] or 0, 1) for r in rated]
    avg_rating = round(sum(r["rating"] * w for r, w in zip(rated, weights)) / sum(weights), 2) if rated else None
    reviews = [r["review_count"] for r in group if r["review_count"] is not None]

    return {
        "restaurant_id": f'{primary["source"]}:{primary["source_id"]}',
        "name": primary["name"],
        "category": first("category"),
        "area": first("area"),
        "lat": first("lat"),
        "lon": first("lon"),
        "address": first("address"),
        "avg_rating": avg_rating,
        "total_reviews": sum(reviews) if reviews else None,
        "price_level": first("price_level"),
        "sources": sorted({r["source"] for r in group}),
        "source_count": len({r["source"] for r in group}),
        "members": [(r["source"], r["source_id"]) for r in group],
    }
