import streamlit as st

from db import query, table_exists

st.set_page_config(page_title="Pipeline Status", page_icon="🛠️", layout="wide")
st.title("🛠️ สถานะ Pipeline")

if not table_exists("pipeline_runs"):
    st.info("ยังไม่มีประวัติการรัน")
    st.stop()

runs = query("SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 20")
if runs.empty:
    st.info("ยังไม่มีประวัติการรัน")
    st.stop()

ICON = {"success": "🟢", "partial": "🟡", "failed": "🔴", "skipped": "⚪", "upstream_failed": "🟠"}
last = runs.iloc[0]
st.subheader(f"รอบล่าสุด {ICON.get(last['status'], '')} {last['status']}")
c1, c2, c3, c4 = st.columns(4)
c1.metric("แถวใน staging", int(last["staging_rows"]))
c2.metric("ผ่าน QC", int(last["valid_rows"]))
c3.metric("ไม่ผ่าน QC", int(last["rejected_rows"]))
c4.metric("ร้านหลังตัดซ้ำ", int(last["restaurants"]))

st.subheader("สถานะแต่ละแหล่งในรอบล่าสุด")
tasks = query("SELECT * FROM task_runs WHERE run_id = :r ORDER BY task_id, map_index", r=last["run_id"])
src = tasks[tasks["task_id"].str.startswith("sources.")].copy()
src["source"] = src["task_id"].str.split(".").str[1]
src["step"] = src["task_id"].str.split(".").str[2]
cols = st.columns(max(src["source"].nunique(), 1))
for col, (name, g) in zip(cols, src.groupby("source")):
    with col:
        st.markdown(f"**{name}**")
        for _, t in g.iterrows():
            label = t["step"] + (f"[{t['map_index']}]" if t["map_index"] >= 0 else "")
            st.write(f"{ICON.get(t['state'], '⚫')} {label} — {t['state']}")

counts = query("""
    SELECT source, count(*) AS rows,
           count(*) FILTER (WHERE qc_status = 'pass') AS pass,
           count(*) FILTER (WHERE qc_status = 'fail') AS fail,
           max(last_seen_at) AS last_seen
    FROM staging_listings GROUP BY source ORDER BY source
""")
st.dataframe(counts, hide_index=True, use_container_width=True)

st.subheader("ทุก task ในรอบล่าสุด")
st.dataframe(tasks[["task_id", "map_index", "state", "start_date", "end_date", "try_number"]],
             hide_index=True, use_container_width=True)

st.subheader("ประวัติการรัน")
st.dataframe(runs, hide_index=True, use_container_width=True)

st.subheader("แถวที่ไม่ผ่านการตรวจคุณภาพ")
st.dataframe(query("SELECT source, source_id, reason, rejected_at FROM rejected_listings ORDER BY rejected_at DESC"),
             hide_index=True, use_container_width=True)
