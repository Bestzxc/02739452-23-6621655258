"""SQL ทั้งหมดของ pipeline — ทุกการเขียนใช้ UPSERT เพื่อให้รันซ้ำแล้วจำนวนแถวไม่เพิ่ม"""

from psycopg2.extras import execute_values

from restaurant_pipeline.sources import UNIFIED_FIELDS

DDL = """
-- ข้อมูลจากทุกแหล่งในรูปแบบ schema เดียวกัน (1 แถว = 1 ร้านจาก 1 แหล่ง)
CREATE TABLE IF NOT EXISTS staging_listings (
    source        TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    name          TEXT,
    name_norm     TEXT,
    category      TEXT,
    rating        NUMERIC(3,2),
    review_count  INTEGER,
    price_level   TEXT,
    lat           DOUBLE PRECISION,
    lon           DOUBLE PRECISION,
    address       TEXT,
    area          TEXT,
    url           TEXT,
    qc_status     TEXT NOT NULL DEFAULT 'pending',   -- pending | pass | fail
    qc_reason     TEXT,
    last_run_id   TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source, source_id)
);

-- แถวที่ไม่ผ่านการตรวจคุณภาพ (เส้นทางแยกของ branch)
CREATE TABLE IF NOT EXISTS rejected_listings (
    source      TEXT NOT NULL,
    source_id   TEXT NOT NULL,
    reason      TEXT NOT NULL,
    record      JSONB NOT NULL,
    run_id      TEXT,
    rejected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source, source_id)
);

-- ร้านหลังตัดซ้ำข้ามแหล่งแล้ว (ตารางที่ dashboard ใช้หลัก)
CREATE TABLE IF NOT EXISTS restaurants (
    restaurant_id TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    category      TEXT,
    area          TEXT,
    lat           DOUBLE PRECISION,
    lon           DOUBLE PRECISION,
    address       TEXT,
    avg_rating    NUMERIC(3,2),
    total_reviews INTEGER,
    price_level   TEXT,
    sources       TEXT[] NOT NULL,
    source_count  INTEGER NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- แต่ละร้านมาจากรายการไหนของแหล่งไหนบ้าง
CREATE TABLE IF NOT EXISTS restaurant_sources (
    source        TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    restaurant_id TEXT NOT NULL,
    PRIMARY KEY (source, source_id)
);

-- สถานะ pipeline สำหรับหน้า Pipeline Status บนเว็บ
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id        TEXT PRIMARY KEY,
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    status        TEXT,
    staging_rows  INTEGER,
    valid_rows    INTEGER,
    rejected_rows INTEGER,
    restaurants   INTEGER
);

CREATE TABLE IF NOT EXISTS task_runs (
    run_id     TEXT NOT NULL,
    task_id    TEXT NOT NULL,
    map_index  INTEGER NOT NULL,
    state      TEXT,
    start_date TIMESTAMPTZ,
    end_date   TIMESTAMPTZ,
    try_number INTEGER,
    PRIMARY KEY (run_id, task_id, map_index)
);
"""


def create_tables(conn) -> None:
    with conn, conn.cursor() as cur:
        cur.execute(DDL)


def upsert_staging(conn, rows: list[dict], run_id: str) -> int:
    if not rows:
        return 0
    cols = UNIFIED_FIELDS + ["last_run_id"]
    # ร้านเดียวกันอาจโผล่ในผลค้นหาหลายพื้นที่ → เก็บแถวเดียวต่อ key ไม่งั้น ON CONFLICT จะ error
    unique = {(r["source"], r["source_id"]): r for r in rows}
    values = [tuple(r[c] for c in UNIFIED_FIELDS) + (run_id,) for r in unique.values()]
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("source", "source_id"))
    sql = f"""
        INSERT INTO staging_listings ({", ".join(cols)}) VALUES %s
        ON CONFLICT (source, source_id) DO UPDATE SET
            {updates}, qc_status = 'pending', qc_reason = NULL, last_seen_at = now()
    """
    with conn, conn.cursor() as cur:
        execute_values(cur, sql, values)
    return len(values)


def fetch_listings(conn, where: str = "TRUE", params: tuple = ()) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {', '.join(UNIFIED_FIELDS)} FROM staging_listings WHERE {where}", params)
        names = [d[0] for d in cur.description]
        rows = [dict(zip(names, row)) for row in cur.fetchall()]
    for r in rows:  # NUMERIC → float
        if r["rating"] is not None:
            r["rating"] = float(r["rating"])
    return rows


def set_qc(conn, results: list[tuple[str, str, str, str | None]]) -> None:
    """results: (source, source_id, status, reason)"""
    if not results:
        return
    with conn, conn.cursor() as cur:
        execute_values(cur, """
            UPDATE staging_listings s SET qc_status = v.status, qc_reason = v.reason
            FROM (VALUES %s) AS v(source, source_id, status, reason)
            WHERE s.source = v.source AND s.source_id = v.source_id
        """, results)


def quarantine_failed(conn, run_id: str) -> int:
    with conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO rejected_listings (source, source_id, reason, record, run_id)
            SELECT source, source_id, qc_reason, to_jsonb(s) - 'qc_status' - 'qc_reason', %s
            FROM staging_listings s WHERE qc_status = 'fail'
            ON CONFLICT (source, source_id) DO UPDATE SET
                reason = EXCLUDED.reason, record = EXCLUDED.record,
                run_id = EXCLUDED.run_id, rejected_at = now()
        """, (run_id,))
        # แถวที่เคยถูกปฏิเสธแต่รอบนี้ผ่านแล้ว ให้เอาออกจากตาราง rejected
        cur.execute("""
            DELETE FROM rejected_listings r USING staging_listings s
            WHERE r.source = s.source AND r.source_id = s.source_id AND s.qc_status = 'pass'
        """)
        cur.execute("SELECT count(*) FROM rejected_listings")
        return cur.fetchone()[0]


def replace_restaurants(conn, golden: list[dict]) -> int:
    """UPSERT ร้านที่รวมแล้ว และลบร้านที่ไม่อยู่ในผลรอบนี้ (เช่น ถูกรวมเข้ากับร้านอื่น)"""
    rest_cols = ["restaurant_id", "name", "category", "area", "lat", "lon", "address",
                 "avg_rating", "total_reviews", "price_level", "sources", "source_count"]
    rest_values = [tuple(g[c] for c in rest_cols) for g in golden]
    link_values = [(src, sid, g["restaurant_id"]) for g in golden for src, sid in g["members"]]
    ids = [g["restaurant_id"] for g in golden]

    with conn, conn.cursor() as cur:
        execute_values(cur, f"""
            INSERT INTO restaurants ({", ".join(rest_cols)}) VALUES %s
            ON CONFLICT (restaurant_id) DO UPDATE SET
                {", ".join(f"{c} = EXCLUDED.{c}" for c in rest_cols[1:])}, updated_at = now()
        """, rest_values)
        execute_values(cur, """
            INSERT INTO restaurant_sources (source, source_id, restaurant_id) VALUES %s
            ON CONFLICT (source, source_id) DO UPDATE SET restaurant_id = EXCLUDED.restaurant_id
        """, link_values)
        cur.execute("DELETE FROM restaurants WHERE NOT (restaurant_id = ANY(%s))", (ids,))
        cur.execute("""
            DELETE FROM restaurant_sources rs WHERE NOT EXISTS (
                SELECT 1 FROM staging_listings s
                WHERE s.source = rs.source AND s.source_id = rs.source_id AND s.qc_status = 'pass')
        """)
        cur.execute("SELECT count(*) FROM restaurants")
        return cur.fetchone()[0]


def record_run(conn, run: dict, tasks: list[tuple]) -> None:
    with conn, conn.cursor() as cur:
        cur.execute("""
            SELECT count(*),
                   count(*) FILTER (WHERE qc_status = 'pass'),
                   (SELECT count(*) FROM rejected_listings),
                   (SELECT count(*) FROM restaurants)
            FROM staging_listings
        """)
        staging, valid, rejected, restaurants = cur.fetchone()
        cur.execute("""
            INSERT INTO pipeline_runs (run_id, started_at, finished_at, status,
                                       staging_rows, valid_rows, rejected_rows, restaurants)
            VALUES (%(run_id)s, %(started_at)s, now(), %(status)s, %(s)s, %(v)s, %(r)s, %(n)s)
            ON CONFLICT (run_id) DO UPDATE SET
                finished_at = now(), status = EXCLUDED.status, staging_rows = EXCLUDED.staging_rows,
                valid_rows = EXCLUDED.valid_rows, rejected_rows = EXCLUDED.rejected_rows,
                restaurants = EXCLUDED.restaurants
        """, {**run, "s": staging, "v": valid, "r": rejected, "n": restaurants})
        if tasks:
            execute_values(cur, """
                INSERT INTO task_runs (run_id, task_id, map_index, state, start_date, end_date, try_number)
                VALUES %s
                ON CONFLICT (run_id, task_id, map_index) DO UPDATE SET
                    state = EXCLUDED.state, start_date = EXCLUDED.start_date,
                    end_date = EXCLUDED.end_date, try_number = EXCLUDED.try_number
            """, tasks)

