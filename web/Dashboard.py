import json
from html import escape
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

import theme
from db import query, table_exists

RIPPLE_JS = (Path(__file__).parent / "ripple.js").read_text(encoding="utf-8")

st.set_page_config(page_title="ร้านอาหารนครปฐม", page_icon="🍜", layout="wide")
theme.apply()

st.title("ร้านอาหาร จังหวัดนครปฐม")
st.caption("รวมข้อมูลจาก Wongnai · OpenStreetMap · Overture Maps — อ่านจาก PostgreSQL โดยตรง")

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
with st.sidebar:
    st.header("ตัวกรอง")
    areas = st.multiselect("พื้นที่", sorted(df["area"].dropna().unique()))
    all_sources = sorted({s for row in df["sources"] for s in row})
    srcs = st.multiselect("แหล่งข้อมูล", all_sources, format_func=lambda s: theme.SOURCE_LABELS.get(s, s))
    min_rating = st.slider("คะแนนขั้นต่ำ", 0.0, 5.0, 0.0, 0.5)
    only_rated = st.checkbox("เฉพาะร้านที่มีคะแนน", value=False)
    multi_only = st.checkbox("เฉพาะร้านที่พบในหลายแหล่ง", value=False)
    keyword = st.text_input("ค้นหาชื่อร้าน / ประเภท")

f = df
if areas:
    f = f[f["area"].isin(areas)]
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


def _num(v) -> float | None:
    """NaN/None → None"""
    return None if v is None or v != v else float(v)


# ------------------------------------------------- hero: จำนวนร้าน + สัดส่วนแหล่ง
st.markdown('<div class="sec">ภาพรวม</div>', unsafe_allow_html=True)
by_src = f["primary_source"].value_counts()
segs = "".join(
    f'<div class="seg" style="flex:{n};background:{theme.SOURCE_COLORS.get(s, "#888")}" '
    f'title="{theme.SOURCE_LABELS.get(s, s)}: {n:,} ร้าน"></div>'
    for s, n in by_src.items()
)
legend = "".join(
    f'<span><span class="dot" style="background:{theme.SOURCE_COLORS.get(s, "#888")}"></span>'
    f'{theme.SOURCE_LABELS.get(s, s)} <b>{n:,}</b> ({n / len(f):.0%})</span>'
    for s, n in by_src.items()
)
st.markdown(
    f'<div class="hero"><div><div class="num">{len(f):,}<small>ร้าน</small></div>'
    f'<div class="muted" style="margin-top:8px">หลังตัดรายการซ้ำข้ามแหล่ง</div></div>'
    f'<div class="stack"><div class="muted" style="margin-bottom:6px">แหล่งหลักของแต่ละร้าน</div>'
    f'<div class="bar">{segs}</div><div class="legend">{legend}</div></div></div>',
    unsafe_allow_html=True,
)
st.write("")

rated = f.dropna(subset=["avg_rating"])
c1, c2, c3, c4 = st.columns(4)
theme.kpi(c1, "คะแนนเฉลี่ย", f"{rated['avg_rating'].mean():.2f}" if not rated.empty else "–", unit="/ 5",
          note=f"จาก <b>{len(rated):,}</b> ร้านที่มีคะแนน")
theme.kpi(c2, "รีวิวรวม", f"{int(f['total_reviews'].fillna(0).sum()):,}", note="นับจาก Wongnai")
theme.kpi(c3, "พบในหลายแหล่ง", f"{(f['source_count'] > 1).sum():,}", unit="ร้าน",
          note=f"<b>{(f['source_count'] > 1).mean():.1%}</b> ของร้านทั้งหมด")
theme.kpi(c4, "พื้นที่", f"{f['area'].nunique()}", unit="อำเภอ",
          note=f"มากสุด <b>{f['area'].value_counts().idxmax()}</b>")

# ------------------------------------------------------------------- charts
st.markdown('<div class="sec" style="margin-top:1.6rem">สถิติ</div>', unsafe_allow_html=True)
left, mid, right = st.columns(3)


def _hbar(series, color):
    fig = go.Figure(go.Bar(
        x=series.values, y=series.index, orientation="h",
        marker=dict(color=color, cornerradius=4),
        hovertemplate="%{y}: <b>%{x:,}</b> ร้าน<extra></extra>",
    ))
    fig.update_layout(bargap=0.45)
    fig.update_xaxes(gridcolor="#1e1f1f", showgrid=True, nticks=4)
    fig.update_yaxes(showgrid=False)
    return theme.style(fig, 280)


with left, st.container(border=True):
    st.markdown('<div class="card-title">จำนวนร้านตามอำเภอ</div>', unsafe_allow_html=True)
    by_area = f["area"].fillna("ไม่ระบุ").value_counts().sort_values()
    st.plotly_chart(_hbar(by_area, theme.ACCENT), use_container_width=True, config={"displayModeBar": False})

with mid, st.container(border=True):
    st.markdown('<div class="card-title">การกระจายของคะแนน</div>', unsafe_allow_html=True)
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
        fig.update_layout(hovermode="x")
        fig.update_xaxes(range=[1, 5], dtick=1)
        st.plotly_chart(theme.style(fig, 280), use_container_width=True, config={"displayModeBar": False})

with right, st.container(border=True):
    st.markdown('<div class="card-title">ประเภทร้าน 10 อันดับแรก</div>', unsafe_allow_html=True)
    top_cat = (f["category"].dropna().str.split(",").explode().str.strip()
               .replace("", np.nan).dropna().value_counts().head(10).sort_values())
    st.plotly_chart(_hbar(top_cat, "#d6d6d2"), use_container_width=True, config={"displayModeBar": False})

# --------------------------------------------------------------------- map
st.markdown('<div class="sec" style="margin-top:1.6rem">แผนที่ร้าน</div>', unsafe_allow_html=True)
geo = f.dropna(subset=["lat", "lon"])
map_col, detail_col = st.columns([2, 1])
selected_id = st.session_state.get("selected_id")

with map_col, st.container(border=True):
    st.markdown('<div class="card-title">ชี้เพื่อดูชื่อร้าน · คลิกเพื่อดูรายละเอียด</div>', unsafe_allow_html=True)
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
    theme.style(fig, 560)
    # ล็อกไม่ให้เลื่อน/ซูมออกเกินขอบเขตข้อมูล (จ.นครปฐม) — ใช้ข้อมูลทั้งหมด ไม่ใช่ที่กรองแล้ว จึงคงที่
    pad = 0.06
    bounds = dict(west=float(df["lon"].min()) - pad, east=float(df["lon"].max()) + pad,
                  south=float(df["lat"].min()) - pad, north=float(df["lat"].max()) + pad)
    fig.update_layout(mapbox_bounds=bounds)
    fig.update_layout(
        # แผนที่พื้นหลังโทนมืดของ Esri (ไม่ต้องใช้ key) — ฐาน + ชื่อสถานที่
        mapbox=dict(style={"version": 8, "sources": {}, "layers": [  # พื้นมืดระหว่างรอโหลด tile
            {"id": "bg", "type": "background", "paint": {"background-color": "#1b1c1c"}}]}, center=center, zoom=14 if not sel.empty else 9.3, layers=[
            dict(sourcetype="raster", below="traces", source=[
                f"https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/{name}/MapServer/tile/{{z}}/{{y}}/{{x}}"])
            for name in ("World_Dark_Gray_Base", "World_Dark_Gray_Reference")
        ]),
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

with detail_col, st.container(border=True):
    row = df[df["restaurant_id"] == selected_id]
    if row.empty:
        st.markdown('<div class="card-title">รายละเอียดร้าน</div>'
                    '<div class="muted" style="margin-top:8px">คลิกจุดบนแผนที่เพื่อดูรายละเอียดร้าน</div>',
                    unsafe_allow_html=True)
        best = rated[rated["total_reviews"].fillna(0) >= 20].sort_values(
            ["avg_rating", "total_reviews"], ascending=False).head(5)
        if not best.empty:
            items = "".join(
                f'<div class="item" style="--c:{theme.ACCENT}"><div class="src">{escape(r["name"])}</div>'
                f'<div class="info">★ {r["avg_rating"]:.2f} · {int(r["total_reviews"]):,} รีวิว · '
                f'อ.{escape(r["area"] or "-")}</div></div>'
                for _, r in best.iterrows()
            )
            st.markdown(f'<div class="card-sub" style="margin:16px 0 10px">คะแนนสูงสุด (รีวิว ≥ 20)</div>'
                        f'<div class="timeline">{items}</div>', unsafe_allow_html=True)
    else:
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
            link = f'<a href="{escape(m["url"])}" target="_blank">เปิดหน้าต้นทาง ↗</a>' if m["url"] else ""
            items += (f'<div class="item" style="--c:{theme.SOURCE_COLORS.get(m["source"], "#888")}">'
                      f'<div class="src">{theme.SOURCE_LABELS.get(m["source"], m["source"])}</div>'
                      f'<div class="info">{escape(m["name"] or "")}</div>'
                      f'<div class="info">{info}</div>{link}</div>')
        st.markdown(
            f'<div class="detail"><div class="card-sub">รายละเอียดร้าน</div>'
            f'<h3>{escape(r["name"])}</h3>'
            f'<div class="meta">{escape(r["category"] or "ไม่ระบุประเภท")} · อ.{escape(r["area"] or "-")}</div>'
            f'<div class="stats"><div><span>คะแนน</span><b>{f"★ {rating:.2f}" if rating is not None else "–"}</b></div>'
            f'<div><span>รีวิว</span><b>{f"{int(reviews):,}" if reviews is not None else "–"}</b></div>'
            f'<div><span>ราคา</span><b style="font-size:0.85rem">{escape(r["price_level"] or "–")}</b></div></div>'
            f'<div class="meta" style="margin-bottom:14px">{escape(r["address"] or "ไม่มีที่อยู่")}</div>'
            f'<div class="card-sub" style="margin-bottom:10px">พบใน {r["source_count"]} แหล่ง</div>'
            f'<div class="timeline">{items}</div></div>',
            unsafe_allow_html=True,
        )
        if st.button("ล้างการเลือก", use_container_width=True):
            st.session_state.pop("selected_id", None)
            st.rerun()

# -------------------------------------------------------------------- table
st.markdown('<div class="sec" style="margin-top:1.6rem">รายชื่อร้าน</div>', unsafe_allow_html=True)
st.dataframe(
    f[["name", "category", "area", "avg_rating", "total_reviews", "price_level", "sources_str", "address"]]
    .sort_values(["avg_rating", "total_reviews"], ascending=False, na_position="last"),
    column_config={
        "name": "ชื่อร้าน", "category": "ประเภท", "area": "พื้นที่",
        "avg_rating": st.column_config.NumberColumn("คะแนน", format="%.2f"),
        "total_reviews": "รีวิว", "price_level": "ราคา", "sources_str": "แหล่ง", "address": "ที่อยู่",
    },
    hide_index=True, use_container_width=True,
)

st.caption("ข้อมูลแผนที่ © OpenStreetMap contributors (ODbL) · Overture Maps Foundation (CDLA-Permissive-2.0) "
           "· แผนที่พื้นหลัง © Esri · ไม่มีการเก็บข้อมูลส่วนบุคคลของผู้รีวิว")
