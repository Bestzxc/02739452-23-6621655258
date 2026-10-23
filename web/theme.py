"""สไตล์ร่วมของทุกหน้า: โทนมืด การ์ดขอบมน และค่าตั้งต้นของกราฟ plotly"""

import streamlit as st

FONT = "IBM Plex Sans Thai, Inter, system-ui, sans-serif"
ACCENT = "#5ee6a8"
INK, INK_2, INK_3 = "#ececea", "#a3a3a0", "#6f6f6c"
SURFACE, LINE = "#151616", "#262727"

# สีประจำแหล่ง (ผูกกับแหล่ง ไม่เปลี่ยนตามลำดับ) — 3 ช่องแรกของ categorical palette โหมดมืด
SOURCE_COLORS = {"wongnai": "#3987e5", "overture": "#d95926", "osm": "#199e70"}
SOURCE_LABELS = {"wongnai": "Wongnai", "overture": "Overture Maps", "osm": "OpenStreetMap"}

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@400;500;600&display=swap');
html, body, [class*="st-"], .stMarkdown, button, input {{ font-family: {FONT}; }}
.block-container {{ padding-top: 2rem; max-width: 1400px; }}
[data-testid="stSidebar"] {{ background: #070808; border-right: 1px solid {LINE}; }}
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {{
    border-radius: 16px; border-color: {LINE} !important; background: {SURFACE};
}}
h1, h2, h3 {{ font-weight: 600 !important; letter-spacing: -0.01em; }}
.sec {{ color: {INK_2}; font-size: 1.05rem; margin: 0.4rem 0 0.6rem; }}
.card-title {{ color: {INK}; font-size: 0.95rem; margin-bottom: 0.15rem; }}
.card-sub {{ color: {INK_3}; font-size: 0.8rem; }}
.kpi {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 16px; padding: 16px 18px; height: 100%; }}
.kpi .label {{ color: {INK_2}; font-size: 0.85rem; }}
.kpi .value {{ color: {INK}; font-size: 2rem; font-weight: 500; line-height: 1.2; margin-top: 6px; }}
.kpi .value small {{ color: {INK_3}; font-size: 0.9rem; font-weight: 400; margin-left: 4px; }}
.kpi .note {{ color: {INK_3}; font-size: 0.8rem; margin-top: 4px; }}
.kpi .note b {{ color: {ACCENT}; font-weight: 500; }}
.hero {{ display: flex; align-items: flex-end; gap: 28px; flex-wrap: wrap; }}
.hero .num {{ font-size: 3rem; font-weight: 500; color: {INK}; line-height: 1; }}
.hero .num small {{ font-size: 1rem; color: {INK_2}; margin-left: 6px; }}
.stack {{ flex: 1; min-width: 280px; }}
.stack .bar {{ display: flex; gap: 3px; height: 30px; }}
.stack .seg {{ border-radius: 3px; min-width: 6px;
    -webkit-mask: repeating-linear-gradient(90deg, #000 0 3px, transparent 3px 6px);
            mask: repeating-linear-gradient(90deg, #000 0 3px, transparent 3px 6px); }}
.stack .legend {{ display: flex; gap: 18px; margin-top: 8px; flex-wrap: wrap; font-size: 0.85rem; color: {INK_2}; }}
.stack .legend b {{ color: {INK}; font-weight: 500; }}
.dot {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 6px; }}
.detail h3 {{ margin: 0 0 2px; font-size: 1.3rem; }}
.detail .meta {{ color: {INK_2}; font-size: 0.85rem; }}
.stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 14px 0; }}
.stats div {{ background: #1c1d1d; border: 1px solid {LINE}; border-radius: 12px; padding: 10px 12px; }}
.stats span {{ display: block; color: {INK_3}; font-size: 0.75rem; }}
.stats b {{ color: {INK}; font-size: 1.15rem; font-weight: 500; }}
.timeline {{ border-left: 1px solid {LINE}; margin-left: 6px; padding-left: 16px; }}
.timeline .item {{ position: relative; padding: 0 0 14px; }}
.timeline .item::before {{ content: ""; position: absolute; left: -21px; top: 6px; width: 9px; height: 9px;
    border-radius: 50%; background: var(--c); box-shadow: 0 0 0 3px {SURFACE}; }}
.timeline .src {{ color: {INK}; font-size: 0.9rem; }}
.timeline .info {{ color: {INK_2}; font-size: 0.8rem; }}
.timeline a {{ color: {ACCENT}; text-decoration: none; font-size: 0.8rem; }}
.muted {{ color: {INK_3}; font-size: 0.85rem; }}
</style>
"""


def apply() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def style(fig, height: int = 260):
    """ค่าตั้งต้นของกราฟ: พื้นโปร่ง เส้นกริดจาง ตัวอักษรสีรอง ไม่มีกรอบ"""
    fig.update_layout(
        template="plotly_dark", height=height, showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, color=INK_2, size=12),
        margin=dict(l=4, r=8, t=8, b=4),
        hoverlabel=dict(bgcolor="#1f2020", bordercolor="#333434", font=dict(family=FONT, color=INK)),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=LINE, ticks="", title=None)
    fig.update_yaxes(gridcolor="#1e1f1f", zeroline=False, linecolor=LINE, ticks="", title=None)
    return fig


def kpi(col, label: str, value: str, note: str = "", unit: str = "") -> None:
    unit_html = f"<small>{unit}</small>" if unit else ""
    col.markdown(
        f'<div class="kpi"><div class="label">{label}</div>'
        f'<div class="value">{value}{unit_html}</div><div class="note">{note}</div></div>',
        unsafe_allow_html=True,
    )
