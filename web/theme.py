"""สไตล์ร่วมของทุกหน้า: โลโก้ โทนมืด การ์ดขอบมน ระยะห่างสม่ำเสมอ สถานะ hover/active และค่าตั้งต้นของกราฟ plotly"""

from pathlib import Path

import streamlit as st

FONT = "IBM Plex Sans Thai, Inter, system-ui, sans-serif"
ACCENT = "#5ee6a8"
ACCENT_DEEP = "#1f7a55"
INK, INK_2, INK_3 = "#ececea", "#a3a3a0", "#6f6f6c"
SURFACE, SURFACE_2, LINE, LINE_HOVER = "#151616", "#1c1d1d", "#262727", "#3a3b3b"
RADIUS = "20px"
GAP = "1rem"  # ระยะห่างระหว่างการ์ด ใช้ค่าเดียวทั้งหน้า

# สีประจำแหล่ง (ผูกกับแหล่ง ไม่เปลี่ยนตามลำดับ) — 3 ช่องแรกของ categorical palette โหมดมืด
SOURCE_COLORS = {"wongnai": "#3987e5", "overture": "#d95926", "osm": "#199e70"}
SOURCE_LABELS = {"wongnai": "Wongnai", "overture": "Overture Maps", "osm": "OpenStreetMap"}

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@400;500;600&display=swap');
html, body, [class*="st-"], .stMarkdown, button, input {{ font-family: {FONT}; }}

/* ---------- layout & spacing ---------- */
.block-container {{ padding: 2.25rem 2.5rem 3rem; max-width: 1440px; }}
[data-testid="stVerticalBlock"] {{ gap: {GAP}; }}
[data-testid="stHorizontalBlock"] {{ gap: {GAP}; }}
[data-testid="stHeader"] {{ background: transparent; }}
/* Streamlit ดึง markdown ขึ้น -16px → บล็อก HTML ของเราทับกัน */
[data-testid="stMarkdownContainer"]:has(> .page-head, > .kpi, > .card-head, > .stack, > .detail, > .timeline) {{
    margin-bottom: 0; }}
h1, h2, h3 {{ font-weight: 600 !important; letter-spacing: -0.015em; }}

.page-head {{ padding-bottom: 0.5rem; }}
.page-head h1 {{ font-size: 2.1rem; margin: 0; padding: 0; line-height: 1.25; }}
.page-head p {{ color: {INK_3}; margin: 6px 0 0 !important; font-size: 0.95rem; }}

/* ---------- cards: st.container(border=True) — กล่องไม่มีกรอบใช้ class ว่าง st-emotion-cache-0 ---------- */
[data-testid="stVerticalBlockBorderWrapper"]:not(.st-emotion-cache-0) {{
    border-radius: {RADIUS}; border-color: {LINE} !important; background: {SURFACE};
    padding: 1.1rem 1.25rem; transition: border-color .2s ease, box-shadow .2s ease;
}}
[data-testid="stVerticalBlockBorderWrapper"]:not(.st-emotion-cache-0):hover {{
    border-color: {LINE_HOVER} !important; box-shadow: 0 8px 28px rgba(0,0,0,.35);
}}
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"] {{ gap: 0.6rem; }}
.card-head {{ display: flex; justify-content: space-between; align-items: center; }}
.card-title {{ color: {INK}; font-size: 1rem; font-weight: 500; }}
.card-sub {{ color: {INK_3}; font-size: 0.8rem; }}
.chip {{ font-size: 0.72rem; color: {INK_2}; border: 1px solid {LINE}; border-radius: 999px; padding: 2px 10px; }}

/* ---------- KPI ---------- */
.kpi {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: {RADIUS}; padding: 20px 22px;
        height: 100%; transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease; }}
.kpi:hover {{ transform: translateY(-3px); border-color: {LINE_HOVER}; box-shadow: 0 10px 30px rgba(0,0,0,.4); }}
.kpi .label {{ color: {INK}; font-size: 0.95rem; font-weight: 500; }}
.kpi .value {{ color: {INK}; font-size: 2.6rem; font-weight: 500; line-height: 1.1; margin: 14px 0 10px; }}
.kpi .value small {{ color: {INK_3}; font-size: 0.95rem; font-weight: 400; margin-left: 6px; }}
.kpi .note {{ color: {INK_3}; font-size: 0.8rem; }}
.kpi .note b {{ color: {ACCENT}; font-weight: 500; }}
.kpi.featured {{ background: linear-gradient(135deg, {ACCENT_DEEP} 0%, #0f4a33 100%); border-color: transparent; }}
.kpi.featured .label, .kpi.featured .value {{ color: #ffffff; }}
.kpi.featured .value small, .kpi.featured .note {{ color: rgba(255,255,255,.75); }}
.kpi.featured .note b {{ color: #ffffff; }}
.kpi.featured:hover {{ box-shadow: 0 12px 34px rgba(31,122,85,.45); }}

/* ---------- source mix bar: ช่วงเป็นลิงก์กรอง · ลายขีดใส่ที่ทั้งแถบ ระยะขีดจึงเท่ากันตลอด ---------- */
.stack .bar {{ display: flex; height: 34px; margin-top: 10px;
    -webkit-mask: repeating-linear-gradient(90deg, #000 0 3px, transparent 3px 6px);
            mask: repeating-linear-gradient(90deg, #000 0 3px, transparent 3px 6px); }}
.stack .seg {{ display: block; min-width: 6px; cursor: pointer; transition: opacity .2s ease, filter .2s ease; }}
.stack .seg:hover {{ filter: brightness(1.35); }}
.stack .seg.off {{ opacity: .22; }}
.stack .seg.off:hover {{ opacity: .5; }}
.stack .legend a {{ color: inherit; text-decoration: none; padding: 4px 10px; margin: -4px -10px;
    border-radius: 999px; transition: background .15s ease, opacity .2s ease; }}
.stack .legend a:hover {{ background: {SURFACE_2}; }}
.stack .legend a.off {{ opacity: .4; }}
.stack .legend a.on {{ background: {SURFACE_2}; color: {INK}; }}
.stack .legend a.on .dot {{ box-shadow: 0 0 0 3px rgba(255,255,255,.18); }}
.chip.clear {{ color: {INK}; border-color: {LINE_HOVER}; text-decoration: none; transition: background .15s ease; }}
.chip.clear:hover {{ background: {SURFACE_2}; border-color: {INK_3}; }}
.stack .legend {{ display: flex; gap: 22px; margin-top: 12px; flex-wrap: wrap; font-size: 0.85rem; color: {INK_2}; }}
.stack .legend b {{ color: {INK}; font-weight: 500; }}
.dot {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 6px; }}

/* ---------- buttons ---------- */
[data-testid="stDownloadButton"] button, [data-testid="stButton"] button {{
    border-radius: 999px; padding: 0.55rem 1.3rem; font-weight: 500; border: 1px solid {LINE_HOVER};
    background: transparent; color: {INK}; transition: background .15s ease, border-color .15s ease, transform .1s ease;
}}
[data-testid="stDownloadButton"] button:hover, [data-testid="stButton"] button:hover {{
    background: {SURFACE_2}; border-color: {INK_3}; color: {INK};
}}
[data-testid="stDownloadButton"] button:active, [data-testid="stButton"] button:active {{ transform: scale(0.97); }}
[data-testid="stDownloadButton"] button[kind="primary"] {{
    background: linear-gradient(135deg, {ACCENT_DEEP}, #145c3f); border-color: transparent; color: #fff;
}}
[data-testid="stDownloadButton"] button[kind="primary"]:hover {{ background: linear-gradient(135deg, #24905f, #1a6e4b); }}
button:focus-visible {{ outline: 2px solid {ACCENT} !important; outline-offset: 2px; }}
/* ปุ่มดาวน์โหลด (popover) = ปุ่มหลักสีเขียว */
[data-testid="stPopover"] button {{
    border-radius: 999px; padding: 0.6rem 1.3rem; font-weight: 500; color: #fff; border: none;
    background: linear-gradient(135deg, {ACCENT_DEEP}, #145c3f); transition: filter .15s ease, transform .1s ease;
}}
[data-testid="stPopover"] button:hover {{ filter: brightness(1.18); color: #fff; }}
[data-testid="stPopover"] button:active {{ transform: scale(0.97); }}
[data-testid="stPopoverBody"] {{ border-radius: 16px; border: 1px solid {LINE}; background: {SURFACE}; min-width: 300px; }}
[data-testid="stPopoverBody"] [data-testid="stDownloadButton"] button {{ justify-content: flex-start; border-radius: 12px; }}

/* ---------- inputs ---------- */
[data-baseweb="select"] > div, [data-testid="stTextInput"] input {{
    border-radius: 12px !important; transition: border-color .15s ease;
}}
[data-baseweb="select"] > div:hover, [data-testid="stTextInput"] > div > div:hover {{ border-color: {INK_3} !important; }}
[data-testid="stTextInput"] > div > div:focus-within {{ border-color: {ACCENT} !important; }}
[data-testid="stCheckbox"] label:hover span {{ border-color: {ACCENT}; }}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] {{ background: #070808; border-right: 1px solid {LINE}; }}
/* โลโก้มุมซ้ายบน: ขยายจากค่าเริ่มต้น (สูง 24px) ให้เต็มความกว้าง sidebar */
[data-testid="stSidebarHeader"] {{ height: auto; padding: 1.25rem 1.25rem 0.5rem; align-items: flex-start; }}
[data-testid="stSidebarHeader"] [data-testid="stLogo"] {{
    height: auto; max-height: none; width: 100%; max-width: 100%; object-fit: contain; }}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{ padding: 1rem 1.25rem; }}
[data-testid="stSidebarNav"] {{ padding: 0.5rem 0.75rem 0; }}
/* ช่องกรอกใน sidebar: พื้นสว่างกว่าพื้น sidebar + ขอบชัด ให้มองเห็นว่าเป็นช่อง */
[data-testid="stSidebar"] [data-baseweb="select"] > div,
[data-testid="stSidebar"] [data-testid="stTextInput"] > div > div {{
    background: {SURFACE_2} !important; border: 1px solid {LINE_HOVER} !important; }}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p, .side-label {{
    color: {INK} !important; font-weight: 500; font-size: 0.9rem; }}
[data-testid="stSidebar"] [data-testid="stCheckbox"] label p {{ color: {INK}; }}
[data-testid="stSidebar"] h2 {{ font-size: 1.15rem; padding-bottom: 0.25rem; }}
[data-testid="stSidebar"] [data-baseweb="tag"] {{ background: {ACCENT_DEEP} !important; }}
/* ไอคอน (เช่น ดาว) ใช้ฟอนต์ไอคอนของ Streamlit — กฎ font-family ด้านบนห้ามทับ */
[data-testid="stIconMaterial"] {{ font-family: "Material Symbols Rounded" !important; }}
/* ดาวเลือกคะแนน */
/* ดาวทุกดวงขนาดเท่ากันเสมอ (ทั้งที่เลือกและไม่เลือก) — ขนาดถูกกำหนดที่ span ห่อไอคอน จึงตั้งทั้งคู่ */
[data-testid="stSidebar"] [data-testid="stButtonGroup"] button,
[data-testid="stSidebar"] [data-testid="stButtonGroup"] button span {{
    font-size: 24px !important; width: auto !important; height: auto !important; line-height: 1 !important; }}
[data-testid="stSidebar"] [data-testid="stButtonGroup"] button {{ padding: 2px !important; transform: none !important; }}
/* ดาวที่เลือกแล้ว Streamlit วาดเป็นรูป svg 20px ส่วนดาวที่ยังไม่เลือกเป็นฟอนต์ไอคอน → ตั้งรูปให้เท่ากัน */
[data-testid="stSidebar"] [data-testid="stButtonGroup"] button img {{ width: 24px !important; height: 24px !important; }}
/* ปุ่ม "ล้าง" ใน sidebar: เล็ก ไม่เต็มความกว้าง */
[data-testid="stSidebar"] [data-testid="stButton"] button {{
    padding: 0.15rem 0.75rem; min-height: 0; font-size: 0.8rem; width: auto; white-space: nowrap; }}
[data-testid="stSidebar"] [data-testid="stButton"] button p {{ white-space: nowrap; font-size: 0.8rem; }}
[data-testid="stSidebarNavLink"] {{ position: relative; border-radius: 12px; padding: 0.55rem 0.9rem; margin: 2px 0;
    background: transparent !important; transition: background .15s ease; }}
[data-testid="stSidebarNavLink"] span {{ color: {INK_2}; transition: color .15s ease; }}
[data-testid="stSidebarNavLink"]:hover {{ background: {SURFACE_2} !important; }}
[data-testid="stSidebarNavLink"]:hover span {{ color: {INK}; }}

/* ---------- แผงรายละเอียดร้าน: เลื่อนออกมาจากขอบขวา (container ที่มี .drawer-marker) ---------- */
[data-testid="stVerticalBlockBorderWrapper"]:not(.st-emotion-cache-0):has(.drawer-marker) {{
    position: fixed; top: 0.75rem; right: 0.75rem; bottom: 0.75rem; width: min(400px, calc(100vw - 1.5rem));
    z-index: 999990; overflow-y: auto; background: {SURFACE}; border-color: {LINE_HOVER} !important;
    box-shadow: -18px 0 50px rgba(0,0,0,.6); animation: drawer-in .38s cubic-bezier(.2,.8,.2,1);
}}
@keyframes drawer-in {{ from {{ transform: translateX(calc(100% + 1rem)); opacity: .3; }}
                         to {{ transform: none; opacity: 1; }} }}
[data-testid="stVerticalBlockBorderWrapper"]:has(.drawer-marker) [data-testid="stButton"] button {{
    padding: 0.25rem 0.75rem; min-height: 0; }}

/* ---------- map detail panel ---------- */
.detail h3 {{ margin: 4px 0 4px; font-size: 1.35rem; }}
.detail .meta {{ color: {INK_2}; font-size: 0.85rem; }}
.stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 16px 0; }}
.stats div {{ background: {SURFACE_2}; border: 1px solid {LINE}; border-radius: 14px; padding: 12px 14px;
    transition: border-color .15s ease; }}
.stats div:hover {{ border-color: {LINE_HOVER}; }}
.stats span {{ display: block; color: {INK_3}; font-size: 0.75rem; }}
.stats b {{ color: {INK}; font-size: 1.15rem; font-weight: 500; }}
.timeline {{ border-left: 1px solid {LINE}; margin-left: 6px; padding-left: 18px; }}
.timeline .item {{ position: relative; padding: 6px 10px 8px; margin: 0 0 6px -10px; border-radius: 12px;
    transition: background .15s ease; }}
.timeline .item:hover {{ background: {SURFACE_2}; }}
.timeline .item::before {{ content: ""; position: absolute; left: -19px; top: 12px; width: 9px; height: 9px;
    border-radius: 50%; background: var(--c); box-shadow: 0 0 0 3px {SURFACE}; }}
.timeline .src {{ color: {INK}; font-size: 0.9rem; }}
.timeline .info {{ color: {INK_2}; font-size: 0.8rem; }}
.timeline a {{ color: {ACCENT}; text-decoration: none; font-size: 0.8rem; }}
.timeline a:hover {{ text-decoration: underline; }}
.muted {{ color: {INK_3}; font-size: 0.85rem; }}

/* ---------- table ---------- */
[data-testid="stDataFrame"] {{ border-radius: 14px; overflow: hidden; }}
</style>
"""


LOGO = str(Path(__file__).parent / "assets" / "logo.png")  # พื้นหลังโปร่งใส


def apply(page: str) -> None:
    """page = ชื่อไฟล์หน้า (เช่น "Dashboard", "Pipeline_Status") ใช้ไฮไลต์เมนูที่กำลังเปิด"""
    st.logo(LOGO)
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(f"""<style>
[data-testid="stSidebarNavLink"][href$="/{page}"] {{ background: {SURFACE_2} !important; }}
[data-testid="stSidebarNavLink"][href$="/{page}"] span {{ color: {INK}; font-weight: 500; }}
[data-testid="stSidebarNavLink"][href$="/{page}"]::before {{ content: ""; position: absolute; left: -0.75rem;
    top: 20%; bottom: 20%; width: 4px; border-radius: 0 4px 4px 0; background: {ACCENT}; }}
</style>""", unsafe_allow_html=True)


def page_head(title: str, subtitle: str) -> None:
    st.markdown(f'<div class="page-head"><h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)


def card_head(title: str, chip: str = "") -> None:
    chip_html = f'<span class="chip">{chip}</span>' if chip else ""
    st.markdown(f'<div class="card-head"><span class="card-title">{title}</span>{chip_html}</div>',
                unsafe_allow_html=True)


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


def kpi(col, label: str, value: str, note: str = "", unit: str = "", featured: bool = False) -> None:
    unit_html = f"<small>{unit}</small>" if unit else ""
    cls = "kpi featured" if featured else "kpi"
    col.markdown(
        f'<div class="{cls}"><div class="label">{label}</div>'
        f'<div class="value">{value}{unit_html}</div><div class="note">{note}</div></div>',
        unsafe_allow_html=True,
    )
