"""ร้านอาหาร จ.นครปฐม (7 อำเภอ) — รวมข้อมูลจาก Wongnai, OpenStreetMap, Overture Maps

create_tables
   └─ sources (TaskGroup, 3 แหล่งรันขนานกัน)
        ├─ wongnai   : extract (map ตามพื้นที่) → transform → load
        ├─ osm       : extract → transform → load
        └─ overture  : extract → transform → load
   └─ quality_check (branch, รันแม้บางแหล่งล่ม)
        ├─ quarantine_bad_rows ─┐
        ├───────────────────────┴─ merge_and_dedup
        └─ no_data_alert
   └─ record_run_status (เขียนสถานะลง DB ให้หน้าเว็บ Pipeline Status)
"""

from __future__ import annotations

import logging

import pendulum
from airflow.decorators import dag, task, task_group
from airflow.exceptions import AirflowFailException, AirflowSkipException
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.utils.state import TaskInstanceState
from airflow.utils.trigger_rule import TriggerRule

from restaurant_pipeline import config, db, dedup, sources

log = logging.getLogger(__name__)


def _conn():
    return PostgresHook(postgres_conn_id=config.POSTGRES_CONN_ID).get_conn()


def _collect(mapped_outputs) -> list[dict]:
    """รวมผลจาก mapped task (บาง instance อาจล้ม → ไม่มีผล ข้ามไป)"""
    rows: list[dict] = []
    for part in mapped_outputs or []:
        if part:
            rows.extend(part)
    return rows


def _no_data(source: str, extract_task_id: str, **context):
    """ไม่มีข้อมูลจาก extract: ถ้าทุก instance ถูก skip → skip ต่อ, ไม่งั้นถือว่าแหล่งล่ม"""
    states = {
        ti.state for ti in context["dag_run"].get_task_instances()
        if ti.task_id == extract_task_id
    }
    if states and states <= {TaskInstanceState.SKIPPED}:
        raise AirflowSkipException(f"{source}: ถูกข้าม")
    raise AirflowFailException(f"{source}: ดึงข้อมูลไม่ได้เลย (states={states})")


def _load(rows: list[dict], **context) -> int:
    n = db.upsert_staging(_conn(), rows, context["run_id"])
    log.info("upsert %d rows", n)
    return n


@dag(
    dag_id="restaurant_pipeline",
    schedule="@daily",
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Bangkok"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": pendulum.duration(seconds=30)},
    tags=["02739452", "restaurants"],
    doc_md=__doc__,
)
def restaurant_pipeline():

    @task
    def create_tables():
        db.create_tables(_conn())

    # ------------------------------------------------------------------ sources
    @task_group(group_id="sources")
    def extract_all_sources():

        @task_group(group_id="wongnai")
        def wongnai():
            @task(max_active_tis_per_dag=1)  # scrape ทีละพื้นที่ ไม่ยิงเว็บพร้อมกัน
            def extract(area: dict) -> list[dict]:
                return sources.extract_wongnai(area)

            @task(trigger_rule=TriggerRule.ALL_DONE)
            def transform(raw, **context) -> list[dict]:
                rows = sources.transform_wongnai(_collect(raw))
                if not rows:
                    _no_data("wongnai", "sources.wongnai.extract", **context)
                return rows

            @task
            def load(rows: list[dict], **context) -> int:
                return _load(rows, **context)

            load(transform(extract.expand(area=config.AREAS)))

        @task_group(group_id="osm")
        def osm():
            @task
            def extract() -> list[dict]:
                return sources.extract_osm()

            @task
            def transform(raw: list[dict]) -> list[dict]:
                return sources.transform_osm(raw)

            @task
            def load(rows: list[dict], **context) -> int:
                return _load(rows, **context)

            load(transform(extract()))

        @task_group(group_id="overture")
        def overture():
            @task
            def extract() -> list[dict]:
                return sources.extract_overture()

            @task
            def transform(raw: list[dict]) -> list[dict]:
                return sources.transform_overture(raw)

            @task
            def load(rows: list[dict], **context) -> int:
                return _load(rows, **context)

            load(transform(extract()))

        wongnai()
        osm()
        overture()

    # ---------------------------------------------------------- quality check
    @task.branch(trigger_rule=TriggerRule.ALL_DONE)
    def quality_check() -> str:
        """ตรวจทุกแถวใน staging แล้วเลือกเส้นทาง"""
        conn = _conn()
        rows = db.fetch_listings(conn)
        if not rows:
            return "no_data_alert"

        bbox = config.THAILAND_BBOX
        max_dist = {a["name"]: a["radius_m"] * 1.5 for a in config.AREAS}
        results = []
        for r in rows:
            reasons = []
            if not r["name"]:
                reasons.append("ไม่มีชื่อร้าน")
            if r["rating"] is not None and not 0 <= r["rating"] <= 5:
                reasons.append(f"คะแนนผิดช่วง ({r['rating']})")
            if r["review_count"] is not None and r["review_count"] < 0:
                reasons.append("จำนวนรีวิวติดลบ")
            if r["lat"] is not None and r["lon"] is not None:
                if not (bbox["min_lat"] <= r["lat"] <= bbox["max_lat"]
                        and bbox["min_lon"] <= r["lon"] <= bbox["max_lon"]):
                    reasons.append("พิกัดอยู่นอกประเทศไทย")
                else:
                    area = sources.nearest_area(r["lat"], r["lon"])
                    a = next(a for a in config.AREAS if a["name"] == area)
                    if sources.haversine_m(r["lat"], r["lon"], a["lat"], a["lon"]) > max_dist[area]:
                        reasons.append("อยู่นอกขอบเขตพื้นที่")
            elif r["source"] != "wongnai":
                reasons.append("ไม่มีพิกัด")
            results.append((r["source"], r["source_id"], "fail" if reasons else "pass",
                            "; ".join(reasons) or None))

        db.set_qc(conn, results)
        failed = sum(1 for x in results if x[2] == "fail")
        log.info("quality check: %d rows, %d failed", len(results), failed)
        if len(results) - failed == 0:
            return "no_data_alert"
        return "quarantine_bad_rows" if failed else "merge_and_dedup"

    @task
    def quarantine_bad_rows(**context) -> int:
        n = db.quarantine_failed(_conn(), context["run_id"])
        log.warning("ย้ายแถวที่ไม่ผ่าน QC ไป rejected_listings แล้ว (ทั้งหมด %d แถว)", n)
        return n

    @task
    def no_data_alert():
        raise AirflowFailException("ไม่มีข้อมูลที่ผ่านการตรวจเลย — ทุกแหล่งล่มหรือ parser เสีย")

    @task(trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS)
    def merge_and_dedup(**context) -> int:
        conn = _conn()
        db.quarantine_failed(conn, context["run_id"])  # เคลียร์แถวที่กลับมาผ่านแล้วออกจาก rejected
        rows = db.fetch_listings(conn, "qc_status = 'pass'")
        groups = dedup.cluster(rows)
        golden = [dedup.build_golden(g) for g in groups]
        total = db.replace_restaurants(conn, golden)
        multi = sum(1 for g in golden if g["source_count"] > 1)
        log.info("%d listings → %d restaurants (%d พบในหลายแหล่ง)", len(rows), total, multi)
        if total < config.MIN_TOTAL_ROWS:
            log.warning("จำนวนร้าน %d < %d ตามข้อกำหนด — ขยาย AREAS ใน config.py", total, config.MIN_TOTAL_ROWS)
        return total

    @task(trigger_rule=TriggerRule.ALL_DONE)
    def record_run_status(**context):
        dag_run = context["dag_run"]
        tis = [t for t in dag_run.get_task_instances() if t.task_id != "record_run_status"]
        bad = {TaskInstanceState.FAILED, TaskInstanceState.UPSTREAM_FAILED}
        merged = any(t.task_id == "merge_and_dedup" and t.state == TaskInstanceState.SUCCESS for t in tis)
        has_failure = any(t.state in bad for t in tis)
        # partial = บางแหล่งล่ม แต่ยังรวมข้อมูลจากแหล่งที่เหลือได้
        status = ("partial" if has_failure else "success") if merged else "failed"
        db.record_run(
            _conn(),
            {"run_id": dag_run.run_id, "started_at": dag_run.start_date, "status": status},
            [(dag_run.run_id, t.task_id, t.map_index, t.state, t.start_date, t.end_date, t.try_number)
             for t in tis],
        )
        if status == "failed":
            raise AirflowFailException("pipeline ไม่ได้รวมข้อมูลรอบนี้ — ดูรายละเอียดในหน้า Pipeline Status")

    # -------------------------------------------------------------- wiring
    qc = quality_check()
    quarantine = quarantine_bad_rows()
    merge = merge_and_dedup()
    alert = no_data_alert()

    create_tables() >> extract_all_sources() >> qc
    qc >> [quarantine, merge, alert]
    quarantine >> merge
    [merge, alert] >> record_run_status()


restaurant_pipeline()
