import io
import json
import re
from datetime import date
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

import theme
from db import query, table_exists

RIPPLE_JS = (Path(__file__).parent / "ripple.js").read_text(encoding="utf-8")

# แผนที่พื้นหลังโทนมืดของ Esri (ไม่ต้องใช้ key) — ฐาน + ชื่อสถานที่ วางบน style "white-bg"
# (style แบบ object ทำให้ plotly diff แล้ว mapbox validate ไม่ผ่านตอน rerun)
# ripple.js เปลี่ยนพื้นเป็นสีมืด และตั้ง maxzoom ของ tile เป็น 16 (Esri มีข้อมูลถึงระดับนั้น)
MAP_STYLE = "white-bg"
MAP_LAYERS = [
    dict(sourcetype="raster", below="traces", source=[
        f"https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/{name}/MapServer/tile/{{z}}/{{y}}/{{x}}"])
    for name in ("World_Dark_Gray_Base", "World_Dark_Gray_Reference")
]

st.set_page_config(page_title="ร้านอาหารนครปฐม", page_icon="🍜", layout="wide")
theme.apply("Dashboard")

head_left, head_right = st.columns([4, 1], vertical_alignment="bottom")
with head_left:
    theme.page_head("ร้านอาหาร จังหวัดนครปฐม",
                    "รวมข้อมูลจาก Wongnai · OpenStreetMap · Overture Maps — อ่านจาก PostgreSQL โดยตรง")

if not table_exists("restaurants"):
    st.warning("ยังไม่มีข้อมูล — เปิด Airflow (http://localhost:8080) แล้วรัน DAG `restaurant_pipeline` ก่อน")
    st.stop()

df = query("SELECT * FROM restaurants")
if df.empty:
    st.warning("ตาราง restaurants ยังว่าง — รอ DAG รันให้เสร็จ")
    st.stop()

df["avg_rating"] = df["avg_rating"].astype(float)
df["sources_str"] = df["sources"].apply(lambda s: ", ".join(s))
# แหล่งหลักของร้าน = แหล่งที่ id ของร้านผูกอยู่ (แหล่งที่น่าเชื่อถือที่สุดในกลุ่ม)
df["primary_source"] = df["restaurant_id"].str.split(":").str[0]

# ------------------------------------------------------------------ filters
def _split_cats(text: str) -> list[str]:
    """1 ร้านมีได้หลายประเภท: Wongnai คั่นด้วย , ส่วน OSM คั่นด้วย ; (เช่น thai;sausage;breakfast)"""
    return [c.strip().replace("_", " ").lower() for c in re.split(r"[,;]", text or "") if c.strip()]


def _categories(s: pd.Series) -> pd.Series:
    """นับแยกทีละประเภท"""
    return s.dropna().map(_split_cats).explode().dropna()


# ค่าที่มาจากการคลิกกราฟ: ต้องตั้งให้ widget ก่อนสร้าง (ตั้งหลังสร้างแล้ว Streamlit ไม่ยอม)
for k, v in st.session_state.pop("_pending_filters", {}).items():
    st.session_state[k] = v


def _set_filter(**values) -> None:
    st.session_state["_pending_filters"] = values
    st.rerun()


cat_counts = _categories(df["category"]).value_counts()
cat_counts = cat_counts[cat_counts >= 3]  # ประเภทที่มีร้านน้อยกว่า 3 ร้านไม่แสดงในรายการ (รกเกินไป)
with st.sidebar:
    st.header("ตัวกรอง")
    areas = st.multiselect("พื้นที่", sorted(df["area"].dropna().unique()), key="f_area", placeholder="ทุกอำเภอ")
    cats = st.multiselect("ประเภทร้าน", cat_counts.index.tolist(), key="f_cat", placeholder="ทุกประเภท",
                          format_func=lambda c: f"{c} ({cat_counts[c]:,})")
    all_sources = sorted({s for row in df["sources"] for s in row})
    srcs = st.multiselect("แหล่งข้อมูล", all_sources, key="f_src", placeholder="ทุกแหล่ง",
                          format_func=lambda s: theme.SOURCE_LABELS.get(s, s))
    st.markdown('<div class="side-label">คะแนนขั้นต่ำ</div>', unsafe_allow_html=True)
    star = st.feedback("stars", key="f_stars")  # None หรือ 0–4 (ดาวที่ 1–5)
    min_rating = 0.0 if star is None else float(star + 1)
    rate_note, rate_clear = st.columns([2, 1], vertical_alignment="center")
    rate_note.caption(f"{min_rating:.0f} ดาวขึ้นไป" if min_rating else "ทุกคะแนน")
    if star is not None and rate_clear.button("✕ ล้าง", key="clear_stars"):
        _set_filter(f_stars=None)
    only_rated = st.checkbox("เฉพาะร้านที่มีคะแนน", value=False, key="f_rated")
    multi_only = st.checkbox("เฉพาะร้านที่พบในหลายแหล่ง", value=False, key="f_multi")
    keyword = st.text_input("ค้นหาชื่อร้าน / ประเภท", key="f_kw", placeholder="เช่น ก๋วยเตี๋ยว, cafe")

f = df
if areas:
    f = f[f["area"].isin(areas)]
if cats:
    wanted = set(cats)
    f = f[f["category"].fillna("").apply(lambda c: any(x in wanted for x in _split_cats(c)))]
if srcs:
    f = f[f["sources"].apply(lambda s: any(x in s for x in srcs))]
if only_rated or min_rating > 0:
    f = f[f["avg_rating"].fillna(-1) >= min_rating]
if multi_only:
    f = f[f["source_count"] > 1]
if keyword:
    mask = f["name"].str.contains(keyword, case=False, na=False) | \
        f["category"].fillna("").str.contains(keyword, case=False)
    f = f[mask]

if f.empty:
    st.info("ไม่มีร้านที่ตรงกับตัวกรอง")
    st.stop()

# กรองตามแหล่งที่คลิกบนแถบ "แหล่งข้อมูลหลัก" (ใช้กับทุกส่วนของหน้า) — แถบเองยังแสดงทุกแหล่งจาก f_base
f_base = f
focus = st.query_params.get("src")  # ?src=wongnai มาจากลิงก์บนแถบ
if focus not in set(f_base["primary_source"]):
    focus = None
if focus:
    f = f_base[f_base["primary_source"] == focus]


def _num(v) -> float | None:
    """NaN/None → None"""
    return None if v is None or v != v else float(v)


# ------------------------------------------------------------------- export
EXPORT_COLS = {
    "name": "ชื่อร้าน", "category": "ประเภท", "area": "อำเภอ", "avg_rating": "คะแนนเฉลี่ย",
    "total_reviews": "จำนวนรีวิว", "price_level": "ช่วงราคา", "address": "ที่อยู่",
    "lat": "ละติจูด", "lon": "ลองจิจูด", "sources_str": "แหล่งข้อมูล", "source_count": "จำนวนแหล่ง",
}


# ไฟล์ SQL: คอลัมน์ภาษาอังกฤษ + ชนิดข้อมูลของ PostgreSQL
SQL_TABLE = "restaurants_nakhonpathom"
SQL_COLS = [
    ("restaurant_id", "TEXT PRIMARY KEY"), ("name", "TEXT NOT NULL"), ("category", "TEXT"), ("area", "TEXT"),
    ("avg_rating", "NUMERIC(3,2)"), ("total_reviews", "INTEGER"), ("price_level", "TEXT"), ("address", "TEXT"),
    ("lat", "DOUBLE PRECISION"), ("lon", "DOUBLE PRECISION"), ("sources", "TEXT"), ("source_count", "INTEGER"),
]


def _sql_value(v, sql_type: str) -> str:
    if v is None or (not isinstance(v, (list, tuple)) and pd.isna(v)):
        return "NULL"
    if sql_type.startswith("INTEGER"):
        return str(int(v))
    if sql_type.startswith(("NUMERIC", "DOUBLE")):
        return repr(float(v))
    return "'" + str(v).replace("'", "''") + "'"


def _to_sql(data: pd.DataFrame, batch: int = 500) -> str:
    """สคริปต์ PostgreSQL: สร้างตาราง + INSERT ทีละ 500 แถว (นำเข้าซ้ำได้ ไม่เกิดแถวซ้ำ)"""
    rows = data.assign(sources=data["sources_str"])
    names = ", ".join(c for c, _ in SQL_COLS)
    lines = [
        f"-- ร้านอาหาร จ.นครปฐม ({len(rows):,} ร้าน) ส่งออกเมื่อ {date.today():%Y-%m-%d}",
        f"-- นำเข้า: psql -d <database> -f <ไฟล์นี้>",
        "BEGIN;",
        f"CREATE TABLE IF NOT EXISTS {SQL_TABLE} (\n    "
        + ",\n    ".join(f"{c} {t}" for c, t in SQL_COLS) + "\n);",
    ]
    records = rows[[c for c, _ in SQL_COLS]].itertuples(index=False, name=None)
    values = ["(" + ", ".join(_sql_value(v, t) for v, (_, t) in zip(rec, SQL_COLS)) + ")" for rec in records]
    for i in range(0, len(values), batch):
        lines.append(f"INSERT INTO {SQL_TABLE} ({names}) VALUES\n"
                     + ",\n".join(values[i:i + batch]) + "\nON CONFLICT (restaurant_id) DO NOTHING;")
    lines.append("COMMIT;")
    return "\n".join(lines) + "\n"


@st.cache_data(show_spinner=False)
def export_files(data: pd.DataFrame) -> dict[str, bytes]:
    """ไฟล์ทุกแบบจากข้อมูลที่กรองแล้ว: csv / xlsx / json / sql"""
    out = data[list(EXPORT_COLS)].rename(columns=EXPORT_COLS)
    summary = (data.groupby("area", dropna=False)
               .agg(ร้าน=("name", "size"), คะแนนเฉลี่ย=("avg_rating", "mean"),
                    รีวิวรวม=("total_reviews", "sum"), พบหลายแหล่ง=("source_count", lambda s: int((s > 1).sum())))
               .round(2).reset_index().rename(columns={"area": "อำเภอ"}).sort_values("ร้าน", ascending=False))
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        out.to_excel(xw, sheet_name="ร้านอาหาร", index=False)
        summary.to_excel(xw, sheet_name="สรุปตามอำเภอ", index=False)
    return {
        "csv": out.to_csv(index=False).encode("utf-8-sig"),  # BOM ให้ Excel อ่านภาษาไทยได้
        "xlsx": buf.getvalue(),
        "json": data[[c for c, _ in SQL_COLS if c != "sources"] + ["sources"]]
        .to_json(orient="records", force_ascii=False, indent=1).encode("utf-8"),
        "sql": _to_sql(data).encode("utf-8"),
    }


EXPORT_FORMATS = [  # (key, ปุ่ม, คำอธิบาย, mime)
    ("csv", "CSV", "เปิดใน Excel / Google Sheets", "text/csv"),
    ("xlsx", "Excel (.xlsx)", "2 ชีต: รายชื่อร้าน + สรุปตามอำเภอ",
     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("sql", "SQL (PostgreSQL)", f"สร้างตาราง {SQL_TABLE} + ข้อมูล", "application/sql"),
    ("json", "JSON", "สำหรับโปรแกรม / API", "application/json"),
]

files = export_files(f)
stem = f"restaurants_nakhonpathom_{date.today():%Y%m%d}"
with head_right, st.popover("⬇ ดาวน์โหลดข้อมูล", use_container_width=True):
    st.markdown(f'<div class="dl-head"><div class="card-title">เลือกรูปแบบไฟล์</div>'
                f'<div class="card-sub">ตามตัวกรองตอนนี้ · {len(f):,} ร้าน</div></div>', unsafe_allow_html=True)
    for key, label, desc, mime in EXPORT_FORMATS:
        st.download_button(f"{label}  ·  {len(files[key]) / 1024:,.0f} KB", files[key], f"{stem}.{key}", mime,
                           use_container_width=True, key=f"dl_{key}")
        st.markdown(f'<div class="dl-desc">{desc}</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------------ KPI
rated = f.dropna(subset=["avg_rating"])
c1, c2, c3, c4 = st.columns(4)
theme.kpi(c1, "ร้านทั้งหมด", f"{len(f):,}", unit="ร้าน", featured=True,
          note=(f"เฉพาะ <b>{theme.SOURCE_LABELS.get(focus, focus)}</b>" if focus else "หลังตัดซ้ำ")
          + f" · <b>{f['area'].nunique()}</b> อำเภอ")
theme.kpi(c2, "คะแนนเฉลี่ย", f"{rated['avg_rating'].mean():.2f}" if not rated.empty else "–", unit="/ 5",
          note=f"จาก <b>{len(rated):,}</b> ร้านที่มีคะแนน")
theme.kpi(c3, "รีวิวรวม", f"{int(f['total_reviews'].fillna(0).sum()):,}", note="นับจาก Wongnai")
theme.kpi(c4, "พบในหลายแหล่ง", f"{(f['source_count'] > 1).sum():,}", unit="ร้าน",
          note=f"<b>{(f['source_count'] > 1).mean():.1%}</b> ของร้านทั้งหมด")

# ---------------------------------------------------------- สัดส่วนแหล่งข้อมูล
# แต่ละช่วงเป็นลิงก์ ?src=<แหล่ง> → กรองทั้งหน้าเหลือร้านจากแหล่งนั้น · คลิกช่วงเดิมซ้ำ (ลิงก์ "?") = ยกเลิก
by_src = f_base["primary_source"].value_counts()


def _state(s: str) -> str:
    return "on" if s == focus else ("off" if focus else "")


segs = "".join(
    f'<a class="seg {_state(s)}" href="{"?" if s == focus else f"?src={s}"}" target="_self" '
    f'style="flex:{n};background:{theme.SOURCE_COLORS.get(s, "#888")}" '
    f'title="{theme.SOURCE_LABELS.get(s, s)}: {n:,} ร้าน — {"คลิกเพื่อยกเลิกการกรอง" if s == focus else "คลิกเพื่อกรอง"}"></a>'
    for s, n in by_src.items()
)
legend = "".join(
    f'<a class="{_state(s)}" href="{"?" if s == focus else f"?src={s}"}" target="_self">'
    f'<span class="dot" style="background:{theme.SOURCE_COLORS.get(s, "#888")}"></span>'
    f'{theme.SOURCE_LABELS.get(s, s)} <b>{n:,}</b> ({n / len(f_base):.0%})</a>'
    for s, n in by_src.items()
)
chip = (f'<a class="chip clear" href="?" target="_self">✕ ล้างตัวกรอง: {theme.SOURCE_LABELS.get(focus, focus)}</a>'
        if focus else '<span class="chip">คลิกแถบเพื่อกรองตามแหล่ง</span>')
with st.container(border=True):
    st.markdown(f'<div class="card-head"><span class="card-title">แหล่งข้อมูลหลักของแต่ละร้าน</span>{chip}</div>'
                f'<div class="stack"><div class="bar">{segs}</div><div class="legend">{legend}</div></div>',
                unsafe_allow_html=True)

# ------------------------------------------------------------------- charts
left, mid, right = st.columns(3)


def _hbar(series, color, selected=()):
    fig = go.Figure(go.Bar(
        x=series.values, y=series.index, orientation="h",
        # แท่งที่ถูกเลือกเป็นตัวกรองอยู่ = สีเต็ม แท่งอื่นจางลง
        marker=dict(color=color, cornerradius=4,
                    opacity=[1 if not selected or y in selected else 0.35 for y in series.index]),
        hovertemplate="%{y}: <b>%{x:,}</b> ร้าน<br>คลิกเพื่อกรอง<extra></extra>",
    ))
    fig.update_layout(bargap=0.45)
    fig.update_xaxes(gridcolor="#1e1f1f", showgrid=True, nticks=4)
    fig.update_yaxes(showgrid=False)
    return theme.style(fig, 280)


def _clicked(fig, name: str):
    """แสดงกราฟแบบคลิกได้ (ลาก/ซูมไม่ได้) แล้วคืนจุดที่คลิก หรือ None
    key มีตัวนับต่อท้าย → หลังคลิกเปลี่ยน key เพื่อล้าง selection ค้างของ plotly"""
    # ไม่ใช้ fixedrange: plotly จะไม่รับคลิกเลือกแท่ง (Streamlit ตั้ง dragmode เป็น pan ให้เอง ลากคลุมเลือกไม่ได้)
    n = st.session_state.get(f"_{name}_n", 0)
    event = st.plotly_chart(fig, use_container_width=True, key=f"{name}_{n}", on_select="rerun",
                            selection_mode="points", config={"displayModeBar": False})
    points = event.get("selection", {}).get("points", []) if event else []
    if points:
        st.session_state[f"_{name}_n"] = n + 1
        return points[0]
    return None


with left, st.container(border=True):
    theme.card_head("จำนวนร้านตามอำเภอ", "คลิกเพื่อกรอง")
    by_area = f["area"].fillna("ไม่ระบุ").value_counts().sort_values()
    p = _clicked(_hbar(by_area, theme.ACCENT, areas), "area_chart")
    if p:  # คลิกอำเภอเดิมที่เลือกอยู่ = ยกเลิก
        _set_filter(f_area=[] if areas == [p["y"]] else [p["y"]])

with mid, st.container(border=True):
    theme.card_head("การกระจายของคะแนน", "คลิกเพื่อตั้งคะแนนขั้นต่ำ")
    if rated.empty:
        st.markdown('<div class="muted">ไม่มีร้านที่มีคะแนนในตัวกรองนี้</div>', unsafe_allow_html=True)
    else:
        edges = np.arange(1.0, 5.01, 0.25)
        counts, _ = np.histogram(rated["avg_rating"].clip(1, 5), bins=edges)
        mids = (edges[:-1] + edges[1:]) / 2
        fig = go.Figure(go.Scatter(
            x=mids, y=counts, mode="lines", line=dict(color=theme.ACCENT, width=2, shape="spline"),
            fill="tozeroy", fillcolor="rgba(94,230,168,0.14)",
            hovertemplate="คะแนน %{x:.2f}: <b>%{y:,}</b> ร้าน<extra></extra>",
        ))
        avg = rated["avg_rating"].mean()
        fig.add_vline(x=avg, line=dict(color=theme.INK_3, dash="dash", width=1))
        fig.add_annotation(x=avg, y=1, yref="paper", text=f"avg {avg:.2f}", showarrow=False,
                           xanchor="right", xshift=-6, font=dict(color=theme.INK_2, size=11))
        if min_rating:  # แรเงาช่วงที่ผ่านตัวกรองคะแนน
            fig.add_vrect(x0=min_rating, x1=5, fillcolor=theme.ACCENT, opacity=0.06, line_width=0)
        fig.update_layout(hovermode="x")
        fig.update_xaxes(range=[1, 5], dtick=1)
        p = _clicked(theme.style(fig, 280), "rating_chart")
        if p:  # คลิกที่คะแนน x → ตั้งดาวขั้นต่ำ = floor(x) (คลิกระดับเดิม = ยกเลิก)
            new_star = int(min(max(np.floor(p["x"]), 1), 5)) - 1
            _set_filter(f_stars=None if star == new_star else new_star)

with right, st.container(border=True):
    theme.card_head("ประเภทร้าน 10 อันดับแรก", "คลิกเพื่อกรอง")
    top_cat = _categories(f["category"]).value_counts().head(10).sort_values()
    p = _clicked(_hbar(top_cat, "#d6d6d2", cats), "cat_chart")
    if p:
        _set_filter(f_cat=[] if cats == [p["y"]] else [p["y"]])

# --------------------------------------------------------------------- map
geo = f.dropna(subset=["lat", "lon"])
selected_id = st.session_state.get("selected_id")

with st.container(border=True):
    theme.card_head("แผนที่ร้าน", "ชี้เพื่อดูชื่อ · คลิกเพื่อดูรายละเอียด")
    fig = go.Figure()
    for src, g in geo.groupby("primary_source"):
        fig.add_trace(go.Scattermapbox(
            lat=g["lat"], lon=g["lon"], mode="markers",
            name=theme.SOURCE_LABELS.get(src, src),
            marker=dict(size=8, color=theme.SOURCE_COLORS.get(src, "#888"), opacity=0.85),
            customdata=g[["restaurant_id", "name"]].values,
            hovertemplate="<b>%{customdata[1]}</b><extra></extra>",
        ))
    sel = geo[geo["restaurant_id"] == selected_id]
    if not sel.empty:  # จุดของร้านที่เลือก (คลื่นวงกลมวาดทับด้วย ripple.js ด้านล่าง)
        fig.add_trace(go.Scattermapbox(
            lat=sel["lat"], lon=sel["lon"], mode="markers", hoverinfo="skip", showlegend=False,
            marker=dict(size=12, color="#ffffff"),
        ))
    center = (dict(lat=float(sel["lat"].iloc[0]), lon=float(sel["lon"].iloc[0])) if not sel.empty
              else dict(lat=float(geo["lat"].mean()), lon=float(geo["lon"].mean())))
    theme.style(fig, 640)
    # ล็อกไม่ให้เลื่อน/ซูมออกเกินขอบเขตข้อมูล (จ.นครปฐม) — ใช้ข้อมูลทั้งหมด ไม่ใช่ที่กรองแล้ว จึงคงที่
    pad = 0.06
    bounds = dict(west=float(df["lon"].min()) - pad, east=float(df["lon"].max()) + pad,
                  south=float(df["lat"].min()) - pad, north=float(df["lat"].max()) + pad)
    fig.update_layout(mapbox_bounds=bounds)
    fig.update_layout(
        mapbox=dict(style=MAP_STYLE, layers=MAP_LAYERS, center=center, zoom=14 if not sel.empty else 9.3),
        showlegend=True, margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(orientation="h", x=0.01, y=0.99, bgcolor="rgba(21,22,22,0.85)", font=dict(color=theme.INK_2)),
    )
    event = st.plotly_chart(fig, use_container_width=True, key="map", on_select="rerun",
                            selection_mode="points", config={"displayModeBar": False, "scrollZoom": True})
    target = (json.dumps({"lat": float(sel["lat"].iloc[0]), "lon": float(sel["lon"].iloc[0]), "color": theme.ACCENT})
              if not sel.empty else "null")
    components.html(f"<script>const TARGET = {target};</script><script>{RIPPLE_JS}</script>", height=0)

points = event.get("selection", {}).get("points", []) if event else []
if points:
    p = points[0]
    cd = p.get("customdata")
    if cd:
        new_id = cd[0]
    else:  # fallback: หาร้านจากพิกัดที่คลิก
        dist = (geo["lat"] - p.get("lat", 0)) ** 2 + (geo["lon"] - p.get("lon", 0)) ** 2
        new_id = geo.loc[dist.idxmin(), "restaurant_id"]
    if new_id != selected_id:
        st.session_state["selected_id"] = new_id
        st.rerun()

# แผงรายละเอียดร้าน: เลื่อนออกมาจากขอบขวาของจอเมื่อคลิกร้าน
# (container นี้ถูกจัดเป็น position: fixed ด้วย CSS ที่จับ .drawer-marker ดู theme.py)
row = df[df["restaurant_id"] == selected_id]
if not row.empty:
    with st.container(border=True):
        top, close = st.columns([5, 1], vertical_alignment="center")
        top.markdown('<span class="drawer-marker"></span><div class="card-sub">รายละเอียดร้าน</div>',
                     unsafe_allow_html=True)
        if close.button("✕", key="close_drawer", help="ปิด"):
            st.session_state.pop("selected_id", None)
            st.rerun()
        r = row.iloc[0]
        rating, reviews = _num(r["avg_rating"]), _num(r["total_reviews"])
        members = query("""
            SELECT s.source, s.name, s.category, s.rating, s.review_count, s.url
            FROM restaurant_sources rs
            JOIN staging_listings s ON s.source = rs.source AND s.source_id = rs.source_id
            WHERE rs.restaurant_id = :rid ORDER BY s.source
        """, rid=selected_id)
        items = ""
        for _, m in members.iterrows():
            m_rating, m_reviews = _num(m["rating"]), _num(m["review_count"])
            info = " · ".join(x for x in [
                escape(m["category"] or ""),
                f"★ {m_rating:.2f}" if m_rating is not None else "",
                f"{int(m_reviews):,} รีวิว" if m_reviews is not None else "",
            ] if x)
            # Overture ให้ได้แค่เว็บไซต์ของร้าน (ส่วนใหญ่ไม่มี) ไม่มีหน้าร้านแบบ Wongnai/OSM
            link = (f'<a href="{escape(m["url"])}" target="_blank">เปิดหน้าต้นทาง ↗</a>' if m["url"]
                    else '<div class="info muted">แหล่งนี้ไม่มีลิงก์หน้าร้าน</div>')
            items += (f'<div class="item"><i class="tl-dot" style="background:{theme.SOURCE_COLORS.get(m["source"], "#888")}"></i>'
                      f'<div class="src">{theme.SOURCE_LABELS.get(m["source"], m["source"])}</div>'
                      f'<div class="info">{escape(m["name"] or "")}</div>'
                      f'<div class="info">{info}</div>{link}</div>')
        st.markdown(
            f'<div class="detail"><h3>{escape(r["name"])}</h3>'
            f'<div class="meta">{escape(r["category"] or "ไม่ระบุประเภท")} · อ.{escape(r["area"] or "-")}</div>'
            f'<div class="stats"><div><span>คะแนน</span><b>{f"★ {rating:.2f}" if rating is not None else "–"}</b></div>'
            f'<div><span>รีวิว</span><b>{f"{int(reviews):,}" if reviews is not None else "–"}</b></div>'
            f'<div><span>ราคา</span><b style="font-size:0.85rem">{escape(r["price_level"] or "–")}</b></div></div>'
            f'<div class="meta" style="margin-bottom:14px">{escape(r["address"] or "ไม่มีที่อยู่")}</div>'
            f'<div class="card-sub" style="margin-bottom:10px">พบใน {r["source_count"]} แหล่ง</div>'
            f'<div class="timeline">{items}</div>'
            # ลิงก์ที่ใช้ได้กับทุกร้าน: ปักหมุดตามพิกัดใน Google Maps
            + (f'<a class="maps-link" href="https://www.google.com/maps/search/?api=1&query={r["lat"]},{r["lon"]}" '
               f'target="_blank">📍 เปิดตำแหน่งใน Google Maps ↗</a>' if r["lat"] == r["lat"] and r["lat"] is not None else "")
            + '</div>',
            unsafe_allow_html=True,
        )

# -------------------------------------------------------------------- table
# พับไว้ไม่ให้หน้ารก แต่ยังมีตารางข้อมูลตามข้อกำหนดของโจทย์
with st.expander(f"รายชื่อร้านทั้งหมด ({len(f):,} ร้าน · เรียงตามคะแนน)", expanded=False):
    st.dataframe(
        f[["name", "category", "area", "avg_rating", "total_reviews", "price_level", "sources_str", "address"]]
        .sort_values(["avg_rating", "total_reviews"], ascending=False, na_position="last"),
        column_config={
            "name": "ชื่อร้าน", "category": "ประเภท", "area": "พื้นที่",
            "avg_rating": st.column_config.NumberColumn("คะแนน", format="%.2f"),
            "total_reviews": "รีวิว", "price_level": "ราคา", "sources_str": "แหล่ง", "address": "ที่อยู่",
        },
        hide_index=True, use_container_width=True, height=420,
    )

st.caption("ข้อมูลแผนที่ © OpenStreetMap contributors (ODbL) · Overture Maps Foundation (CDLA-Permissive-2.0) "
           "· แผนที่พื้นหลัง © Esri · ไม่มีการเก็บข้อมูลส่วนบุคคลของผู้รีวิว")
