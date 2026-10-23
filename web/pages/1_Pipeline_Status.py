from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import theme
from db import query, table_exists

st.set_page_config(page_title="Pipeline Status", page_icon="🛠️", layout="wide")
theme.apply("Pipeline_Status")
theme.page_head("สถานะ Pipeline", "ผลการรัน DAG restaurant_pipeline แต่ละรอบ อ่านจากตาราง pipeline_runs และ task_runs")

if not table_exists("pipeline_runs"):
    st.info("ยังไม่มีประวัติการรัน")
    st.stop()

runs = query("SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 20")
if runs.empty:
    st.info("ยังไม่มีประวัติการรัน")
    st.stop()

# สถานะ → (สี, ไอคอน, ป้าย) — สีสถานะใช้คู่กับไอคอน+ข้อความเสมอ ไม่ใช้สีอย่างเดียว
STATUS = {
    "success": ("#0ca30c", "✓", "สำเร็จ"),
    "partial": ("#fab219", "!", "บางแหล่งล่ม"),
    "failed": ("#d03b3b", "✕", "ล้มเหลว"),
    "upstream_failed": ("#ec835a", "↑", "ข้ามเพราะขั้นก่อนล่ม"),
    "skipped": ("#8a8a86", "–", "ข้าม"),
    "running": ("#3987e5", "…", "กำลังรัน"),
}
# ลำดับพื้นที่ของ Wongnai (map_index) — ตรงกับ AREAS ใน dags/restaurant_pipeline/config.py
AREA_NAMES = ["เมืองนครปฐม", "กำแพงแสน", "นครชัยศรี", "ดอนตูม", "บางเลน", "สามพราน", "พุทธมณฑล"]
STEP_ORDER = {"extract": 0, "transform": 1, "load": 2}


def badge(state: str, text: str | None = None) -> str:
    color, icon, label = STATUS.get(state, ("#8a8a86", "?", state))
    return (f'<span class="st-badge" style="background:{theme.tint(color, .18)};border-color:{theme.tint(color, .45)}">'
            f'<b style="background:{color}">{icon}</b>{escape(text or label)}</span>')


def duration(row) -> str:
    if pd.isna(row["started_at"]) or pd.isna(row["finished_at"]):
        return "–"
    secs = int((row["finished_at"] - row["started_at"]).total_seconds())
    return f"{secs // 60} นาที {secs % 60} วินาที" if secs >= 60 else f"{secs} วินาที"


last = runs.iloc[0]
tasks = query("SELECT * FROM task_runs WHERE run_id = :r ORDER BY task_id, map_index", r=last["run_id"])

# ------------------------------------------------------------ รอบล่าสุด
with st.container(border=True):
    st.markdown(
        f'<div class="card-head"><span class="card-title">รอบล่าสุด {badge(last["status"])}</span>'
        f'<span class="chip">{escape(str(last["run_id"]))}</span></div>'
        f'<div class="card-sub" style="margin-top:6px">เริ่ม {last["started_at"]:%d/%m/%Y %H:%M} · '
        f'ใช้เวลา {duration(last)}</div>',
        unsafe_allow_html=True,
    )
    steps = [
        ("แถวใน staging", last["staging_rows"], "ข้อมูลจากทุกแหล่ง"),
        ("ผ่าน QC", last["valid_rows"], f'ไม่ผ่าน {int(last["rejected_rows"]):,} แถว → rejected_listings'),
        ("ร้านหลังตัดซ้ำ", last["restaurants"], "ตาราง restaurants (หน้า Dashboard)"),
    ]
    flow = '<span class="flow-arrow">→</span>'.join(
        f'<div class="flow-step"><span>{label}</span><b>{int(n):,}</b><small>{note}</small></div>'
        for label, n, note in steps
    )
    st.markdown(f'<div class="flow">{flow}</div>', unsafe_allow_html=True)

# ------------------------------------------------------------ แต่ละแหล่ง
src = tasks[tasks["task_id"].str.startswith("sources.")].copy()
src["source"] = src["task_id"].str.split(".").str[1]
src["step"] = src["task_id"].str.split(".").str[2]
counts = query("""
    SELECT source, count(*) AS rows,
           count(*) FILTER (WHERE qc_status = 'pass') AS pass,
           count(*) FILTER (WHERE qc_status = 'fail') AS fail
    FROM staging_listings GROUP BY source
""").set_index("source")

cols = st.columns(max(src["source"].nunique(), 1))
for col, (name, g) in zip(cols, src.groupby("source")):
    g = g.assign(order=g["step"].map(STEP_ORDER)).sort_values(["order", "map_index"])
    worst = ("failed" if (g["state"] == "failed").any()
             else "upstream_failed" if (g["state"] == "upstream_failed").any()
             else "skipped" if (g["state"] == "skipped").all() else "success")
    chips = ""
    for step, sg in g.groupby("order", sort=True):
        step_name = sg["step"].iloc[0]
        if len(sg) > 1 or sg["map_index"].iloc[0] >= 0:  # mapped task: 1 ชิปต่อพื้นที่
            inner = "".join(
                f'<span class="dot-chip" style="background:{theme.tint(STATUS.get(t.state, ("#8a8a86",))[0], .16)};'
                f'border-color:{theme.tint(STATUS.get(t.state, ("#8a8a86",))[0], .5)}" '
                f'title="{AREA_NAMES[t.map_index] if t.map_index < len(AREA_NAMES) else t.map_index}: {t.state}">'
                f'<i style="background:{STATUS.get(t.state, ("#8a8a86",))[0]}"></i>'
                f'{escape(AREA_NAMES[t.map_index] if t.map_index < len(AREA_NAMES) else str(t.map_index))}</span>'
                for t in sg.itertuples()
            )
            ok = (sg["state"] == "success").sum()
            chips += (f'<div class="step-row"><div class="step-name">{step_name} '
                      f'<small>{ok}/{len(sg)} พื้นที่</small></div><div class="dot-chips">{inner}</div></div>')
        else:
            chips += f'<div class="step-row"><div class="step-name">{step_name}</div>{badge(sg["state"].iloc[0])}</div>'
    c = counts.loc[name] if name in counts.index else None
    stats = (f'<div class="stats"><div><span>แถว</span><b>{int(c["rows"]):,}</b></div>'
             f'<div><span>ผ่าน QC</span><b>{int(c["pass"]):,}</b></div>'
             f'<div><span>ไม่ผ่าน</span><b>{int(c["fail"]):,}</b></div></div>') if c is not None else ""
    with col, st.container(border=True):
        st.markdown(
            f'<div class="card-head"><span class="card-title">'
            f'<span class="dot" style="background:{theme.SOURCE_COLORS.get(name, "#888")}"></span>'
            f'{theme.SOURCE_LABELS.get(name, name)}</span>{badge(worst)}</div>{stats}{chips}',
            unsafe_allow_html=True,
        )

# ------------------------------------------------------------ ประวัติการรัน
with st.container(border=True):
    theme.card_head("ประวัติการรัน", f"{len(runs)} รอบล่าสุด")
    hist = runs.sort_values("started_at")
    labels = hist["started_at"].dt.strftime("%d/%m %H:%M")
    fig = go.Figure([
        go.Bar(x=labels, y=hist["restaurants"], name="ร้านหลังตัดซ้ำ", marker=dict(color=theme.ACCENT, cornerradius=4),
               customdata=hist[["status", "valid_rows", "rejected_rows"]].values,
               hovertemplate="%{x}<br>ร้าน <b>%{y:,}</b> · ผ่าน QC %{customdata[1]:,} · "
                             "ไม่ผ่าน %{customdata[2]:,}<br>สถานะ %{customdata[0]}<extra></extra>"),
    ])
    for i, r in enumerate(hist.itertuples()):  # ไอคอนสถานะเหนือแท่ง
        color, icon, _ = STATUS.get(r.status, ("#888", "?", ""))
        fig.add_annotation(x=labels.iloc[i], y=r.restaurants, text=icon, showarrow=False, yshift=12,
                           font=dict(color=color, size=13))
    fig.update_layout(bargap=0.55)
    fig.update_yaxes(title=None)
    st.plotly_chart(theme.style(fig, 240), use_container_width=True, config={"displayModeBar": False})

# ------------------------------------------------------------ รายละเอียด (พับไว้)
with st.expander("ทุก task ในรอบล่าสุด"):
    st.dataframe(tasks[["task_id", "map_index", "state", "start_date", "end_date", "try_number"]],
                 hide_index=True, use_container_width=True)
with st.expander(f"แถวที่ไม่ผ่านการตรวจคุณภาพ ({int(last['rejected_rows']):,} แถว)"):
    st.dataframe(query("SELECT source, source_id, reason, rejected_at FROM rejected_listings ORDER BY rejected_at DESC"),
                 hide_index=True, use_container_width=True)
with st.expander("ประวัติการรันทั้งหมด (ตาราง)"):
    st.dataframe(runs, hide_index=True, use_container_width=True)
