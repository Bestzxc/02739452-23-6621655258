// คลื่นวงกลมรอบร้านที่เลือกบนแผนที่ plotly (scattermapbox) + แก้การซูมของ tile Esri
// รันใน iframe ของ components.html (same-origin) แล้ววาดทับแผนที่ในหน้าหลัก
// TARGET = {lat, lon, color} หรือ null (ถูกประกาศก่อนสคริปต์นี้)
(function () {
  const doc = window.parent.document;
  const STYLE_ID = "ripple-style";
  const CLASS = "ripple-marker";

  let style = doc.getElementById(STYLE_ID);
  if (!style) {
    style = doc.createElement("style");
    style.id = STYLE_ID;
    doc.head.appendChild(style);
  }
  // เขียนทับทุกครั้ง หน้าที่เปิดค้างไว้จะได้ CSS ล่าสุด
  style.textContent = `
    .${CLASS} { position: absolute; width: 0; height: 0; pointer-events: none; z-index: 5; }
    .${CLASS} span { position: absolute; left: -14px; top: -14px; width: 28px; height: 28px;
      border-radius: 50%; border: 2px solid var(--c); box-shadow: 0 0 12px var(--c);
      opacity: 0; animation: ripple-wave 2.4s ease-out infinite; }
    .${CLASS} span:nth-child(2) { animation-delay: 0.8s; }
    .${CLASS} span:nth-child(3) { animation-delay: 1.6s; }
    @keyframes ripple-wave {
      0%   { transform: scale(0.4); opacity: 0.95; }
      100% { transform: scale(3.6); opacity: 0; }
    }`;

  function findMap() {
    for (const gd of doc.querySelectorAll(".js-plotly-plot")) {
      const sub = gd._fullLayout && gd._fullLayout.mapbox && gd._fullLayout.mapbox._subplot;
      if (sub && sub.map) return { gd, map: sub.map };
    }
    return null;
  }

  let bound = null; // map object ที่ผูก event ไว้แล้ว
  let el = null;

  function place() {
    if (!bound || !el) return;
    const p = bound.map.project([TARGET.lon, TARGET.lat]);
    el.style.left = p.x + "px";
    el.style.top = p.y + "px";
  }

  // tile ของ Esri มีข้อมูลถึง zoom 16 เท่านั้น (ลึกกว่านั้นได้ภาพ "Map data not yet available")
  // plotly ตั้ง maxzoom ของ source เองไม่ได้ → แก้ที่ source แล้วโหลดใหม่ ให้แผนที่ขยาย tile ระดับ 16 แทน
  // และจำกัดการซูมที่ 17.5 (ขยายเกินนั้นภาพจะเบลอ)
  const TILE_MAXZOOM = 16, MAP_MAXZOOM = 17.5;
  function fixTileZoom(map) {
    if (map.__tileZoomFixed || !map.style || !map.style.sourceCaches) return;
    // พื้นของ style white-bg เป็นสีขาว → เปลี่ยนเป็นสีมืด ไม่ให้กะพริบขาวระหว่างโหลด tile
    if (map.getLayer("white-bg")) map.setPaintProperty("white-bg", "background-color", "#1b1c1c");
    const ids = Object.keys(map.style.sourceCaches).filter((id) => {
      const s = map.getSource(id);
      return s && (s.tiles || []).some((t) => t.includes("arcgisonline"));
    });
    if (!ids.length) return;  // ยังโหลด source ไม่เสร็จ รอ tick ถัดไป
    ids.forEach((id) => { map.getSource(id).maxzoom = TILE_MAXZOOM; map.style.sourceCaches[id].reload(); });
    map.setMaxZoom(MAP_MAXZOOM);
    map.__tileZoomFixed = true;
  }

  function tick() {
    const found = findMap();
    if (found) fixTileZoom(found.map);

    // ลบคลื่นเก่า (ร้านอื่น หรือยกเลิกการเลือก)
    doc.querySelectorAll("." + CLASS).forEach((n) => { if (n !== el) n.remove(); });
    if (!TARGET) { if (el) { el.remove(); el = null; } return; }
    if (!found) return;
    // plotly สร้างแผนที่ใหม่เมื่อหน้า rerun → ผูกใหม่
    if (!bound || bound.map !== found.map || !el || !el.isConnected) {
      if (el) el.remove();
      el = doc.createElement("div");
      el.className = CLASS;
      el.style.setProperty("--c", TARGET.color);
      el.innerHTML = "<span></span><span></span><span></span>";
      // ใส่ใน container ของแผนที่ (overflow: hidden) → คลื่นที่เลื่อนออกนอกกรอบถูกตัดทิ้ง
      found.map.getContainer().appendChild(el);
      bound = found;
      found.map.on("move", place);
      found.map.on("resize", place);
    }
    place();
  }

  tick();
  setInterval(tick, 500);
})();
