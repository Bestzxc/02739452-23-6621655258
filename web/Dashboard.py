import plotly.express as px
import streamlit as st

from db import query, table_exists

st.set_page_config(page_title="ร้านอาหารนครปฐม", page_icon="🍜", layout="wide")
st.title("🍜 ร้านอาหาร จังหวัดนครปฐม")
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

# ------------------------------------------------------------------ filters
with st.sidebar:
    st.header("ตัวกรอง")
    areas = st.multiselect("พื้นที่", sorted(df["area"].dropna().unique()))
    all_sources = sorted({s for row in df["sources"] for s in row})
    srcs = st.multiselect("แหล่งข้อมูล", all_sources)
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

# ---------------------------------------------------------------------- KPI
c1, c2, c3, c4 = st.columns(4)
c1.metric("จำนวนร้าน", f"{len(f):,}")
c2.metric("คะแนนเฉลี่ย", f"{f['avg_rating'].mean():.2f}" if f["avg_rating"].notna().any() else "–")
c3.metric("พบในหลายแหล่ง", f"{(f['source_count'] > 1).sum():,}")
c4.metric("รีวิวรวม", f"{int(f['total_reviews'].fillna(0).sum()):,}")

# ------------------------------------------------------------------- charts
left, right = st.columns(2)
with left:
    by_area = f.groupby("area", dropna=False).size().reset_index(name="ร้าน")
    st.plotly_chart(px.bar(by_area, x="area", y="ร้าน", title="จำนวนร้านตามพื้นที่",
                           labels={"area": "พื้นที่"}), use_container_width=True)
with right:
    rated = f.dropna(subset=["avg_rating"])
    st.plotly_chart(px.histogram(rated, x="avg_rating", nbins=20, title="การกระจายของคะแนน",
                                 labels={"avg_rating": "คะแนนเฉลี่ย"}), use_container_width=True)

src_counts = (f.explode("sources").groupby("sources").size()
              .reset_index(name="ร้าน").rename(columns={"sources": "แหล่ง"}))
top_cat = (f["category"].dropna().str.split(",").explode().str.strip()
           .value_counts().head(10).reset_index())
top_cat.columns = ["ประเภท", "ร้าน"]
l2, r2 = st.columns(2)
l2.plotly_chart(px.pie(src_counts, names="แหล่ง", values="ร้าน", title="ร้านจากแต่ละแหล่ง (นับซ้ำได้)"),
                use_container_width=True)
r2.plotly_chart(px.bar(top_cat, x="ร้าน", y="ประเภท", orientation="h", title="ประเภทร้าน 10 อันดับแรก"),
                use_container_width=True)

geo = f.dropna(subset=["lat", "lon"])
if not geo.empty:
    st.subheader("แผนที่")
    st.map(geo, latitude="lat", longitude="lon", size=20)

# -------------------------------------------------------------------- table
st.subheader("รายชื่อร้าน")
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

st.caption("ข้อมูลแผนที่ © OpenStreetMap contributors (ODbL) · Overture Maps Foundation (CDLA-Permissive-2.0) · ไม่มีการเก็บข้อมูลส่วนบุคคลของผู้รีวิว")
