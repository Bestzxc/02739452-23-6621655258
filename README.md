# ร้านอาหาร จังหวัดนครปฐม — Restaurant Data Pipeline

รายวิชา 02739452 แพลตฟอร์มข้อมูลขนาดใหญ่และการวิเคราะห์ · ข้อสอบปลายภาค ภาคต้น 2569

## หัวข้อและขอบเขต
รวบรวม **ข้อมูลร้านอาหารและคาเฟ่** (ชื่อร้าน ประเภท พิกัด คะแนนเฉลี่ย จำนวนรีวิว ช่วงราคา)
ใน **จ.นครปฐม ทั้ง 7 อำเภอ** (เมืองนครปฐม, กำแพงแสน, นครชัยศรี, ดอนตูม, บางเลน, สามพราน, พุทธมณฑล)
จากหลายแหล่ง แล้วรวมเป็นชุดเดียว
ด้วย Apache Airflow → PostgreSQL → เว็บ dashboard (Streamlit)

> เก็บเฉพาะข้อมูลระดับร้าน **ไม่เก็บข้อความรีวิว ชื่อ หรือโปรไฟล์ผู้รีวิว** (สอดคล้องกับ PDPA)

## แหล่งข้อมูล
| # | แหล่ง | วิธีดึง | หมายเหตุ |
|---|---|---|---|
| 1 | Wongnai | **Web scraping** (requests + BeautifulSoup, ไม่ใช้ Selenium) | เช็ก robots.txt ทุกครั้งก่อนดึง และเว้นระยะตาม Crawl-delay |
| 2 | OpenStreetMap | Overpass API (ไม่ต้องใช้ key) | © OpenStreetMap contributors, ODbL |
| 3 | Overture Maps Places | อ่าน GeoParquet บน S3 สาธารณะด้วย DuckDB (ไม่ต้องใช้ key ฟรี) | รวมข้อมูลจาก Meta, Foursquare, AllThePlaces · CDLA-Permissive-2.0 · เลือก release ล่าสุดอัตโนมัติ |

## สถาปัตยกรรม
```
create_tables
  └─ sources (TaskGroup — 3 แหล่งรันขนานกัน)
       ├─ wongnai        : extract (Dynamic Task Mapping ตามพื้นที่) → transform → load
       ├─ osm            : extract → transform → load
       └─ overture       : extract (DuckDB กรองด้วย bbox + หมวด food_and_drink) → transform → load
  └─ quality_check  (branch; trigger_rule=all_done → รันต่อแม้บางแหล่งล่ม)
       ├─ quarantine_bad_rows → merge_and_dedup   (มีแถวไม่ผ่าน → แยกไป rejected_listings)
       ├─ merge_and_dedup                         (ผ่านทั้งหมด)
       └─ no_data_alert                           (ไม่มีข้อมูลเลย)
  └─ record_run_status  (บันทึกสถานะลง DB สำหรับหน้า Pipeline Status)
```

| ตาราง (DB `restaurant_db`) | ความหมาย |
|---|---|
| `staging_listings` | ข้อมูลทุกแหล่งในรูปแบบ schema เดียวกัน — UPSERT ด้วย key `(source, source_id)` |
| `rejected_listings` | แถวที่ไม่ผ่านการตรวจคุณภาพ พร้อมเหตุผล |
| `restaurants` | ร้านหลังตัดรายการซ้ำข้ามแหล่งแล้ว (dashboard ใช้ตารางนี้) |
| `restaurant_sources` | ร้านแต่ละร้านมาจากรายการไหนของแหล่งไหน |
| `pipeline_runs`, `task_runs` | สถานะของแต่ละรอบการรัน |

### งานแต่ละระดับ
| ระดับ | ทำอย่างไร |
|---|---|
| 1 | DAG แบบ extract → transform → load → PostgreSQL → เว็บมีตารางและกราฟ |
| 2 | 3 แหล่งรันขนานกันใน TaskGroup · แปลงเป็น schema เดียว · `INSERT … ON CONFLICT DO UPDATE` (รันซ้ำแล้วจำนวนแถวไม่เพิ่ม) · เว็บมี KPI และตัวกรอง |
| 3 | `trigger_rule=all_done` ทำให้รวมข้อมูลต่อได้เมื่อบางแหล่งล่ม · ตัดรายการซ้ำข้ามแหล่ง (ชื่อคล้ายกัน ≥ 85% ด้วย rapidfuzz + ห่างกันไม่เกิน 150 ม.) · ตรวจคุณภาพข้อมูลแล้วแยกเส้นทางด้วย `@task.branch` |
| โบนัส | Dynamic Task Mapping (`.expand(area=AREAS)`) และหน้า **Pipeline Status** บนเว็บ |

**กฎตรวจคุณภาพข้อมูล:** ต้องมีชื่อร้าน · คะแนนอยู่ระหว่าง 0–5 · จำนวนรีวิวไม่ติดลบ · พิกัดอยู่ในประเทศไทยและในขอบเขตพื้นที่ · ทุกแหล่งยกเว้น Wongnai ต้องมีพิกัด

## วิธีรัน
ต้องมี Docker Desktop (หรือ Docker Engine กับ Compose v2)

```bash
cp .env.example .env          # แก้รหัสผ่าน (ไม่ต้องใช้ API key ใด ๆ)
docker compose up -d --build  # รันครั้งแรกใช้เวลาประมาณ 3–5 นาที
```

| บริการ | URL | หมายเหตุ |
|---|---|---|
| Airflow | http://localhost:8080 | ล็อกอินด้วย `AIRFLOW_ADMIN_USER` / `AIRFLOW_ADMIN_PASSWORD` ใน `.env` |
| Dashboard | http://localhost:8501 | มีหน้า Pipeline Status อยู่ที่เมนูด้านซ้าย |
| PostgreSQL | localhost:5433 | ฐานข้อมูล `restaurant_db` |

DAG `restaurant_pipeline` เปิดใช้งานอัตโนมัติและรันวันละครั้ง ถ้าต้องการรันทันทีให้กด ▶ Trigger DAG ใน Airflow

ปิดระบบ: `docker compose down` (ถ้าต้องการลบข้อมูลด้วยให้เพิ่ม `-v`)

## โครงสร้างโปรเจกต์
```
dags/
  restaurant_pipeline_dag.py   # DAG
  restaurant_pipeline/
    config.py                  # พื้นที่, URL, เกณฑ์ตัดซ้ำ (แก้ขอบเขตที่นี่)
    sources.py                 # extract + transform ของแต่ละแหล่ง
    dedup.py                   # ตัดรายการซ้ำข้ามแหล่ง
    db.py                      # DDL + UPSERT
    web_client.py              # HTTP ที่เคารพ robots.txt / Crawl-delay
web/
  Dashboard.py                 # หน้าหลัก: KPI, ตัวกรอง, กราฟ, แผนที่, ตาราง
  pages/1_Pipeline_Status.py   # หน้าสถานะ pipeline
docker-compose.yml · Dockerfile · requirements.txt · .env.example
```

## จริยธรรมและข้อกฎหมาย
- ตรวจ `robots.txt` ด้วย `urllib.robotparser` ทุกครั้งก่อนดึง ถ้าไม่อนุญาตจะไม่ดึง
- ระบุ User-Agent ของโปรเจกต์ และเว้นระยะอย่างน้อย 2 วินาทีต่อ request
- ไม่เก็บข้อมูลส่วนบุคคล (ชื่อ, โปรไฟล์ หรือข้อความรีวิวของผู้ใช้)
- ไม่มีรหัสผ่านหรือ API key ใน repo มีแค่ `.env.example`
