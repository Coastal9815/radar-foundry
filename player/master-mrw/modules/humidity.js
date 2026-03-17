/**
 * Humidity module — Humidity, Dew Point, Solar, UV with daily extremes.
 * Self-contained module for Master MRW dashboard. LOCKED.
 *
 * MOVE: Set SLOTS[newIndex] = "humidity", SLOTS[oldIndex] = null. Module works in any box 1–8.
 * REMOVE: Set SLOTS[i] = null for the box.
 * ADD BACK: Set SLOTS[i] = "humidity". Script is always loaded; module registers on load.
 *
 * Data: now.json, extremes.json via pi-wx proxy (/pi-wx-data/data/*).
 * Extremes: Hi + time for Solar, UV only (no Lo; no Hum/Dew extremes).
 *
 * Color scales:
 * - Dew point: 0–64.9 base; 65–69.9 yellow; 70–74.9 orange; 75–79.9 dark orange; 80+ red
 * - UV: 0–3.9 base; 4–5.9 yellow; 6–7.9 orange; 8–10.9 red; 11+ purple
 */
(function () {
  "use strict";

  const module = {
    render(slotId) {
      return `<div class="humTile">
            <div class="humLabel" style="position:absolute;top:9px;left:16px;">Humidity</div>
            <div class="humMain humMain-left" style="position:absolute;top:48px;left:14px;max-width:336px;overflow:hidden;"><span class="hum-val">--</span><span class="humUnit">%</span></div>
            <div class="humLabel" style="position:absolute;top:9px;right:16px;left:auto;text-align:right;">Dew Point</div>
            <div class="humMain humMain-right" style="position:absolute;top:48px;right:14px;left:auto;text-align:right;max-width:336px;overflow:hidden;"><span class="dew-val">--</span><span class="degF"><span class="deg">°</span><span class="f">F</span></span></div>
            <div class="humLabel" style="position:absolute;top:183px;left:16px;">Solar</div>
            <div class="humMain humMain-solar" style="position:absolute;top:222px;left:14px;max-width:686px;overflow:hidden;"><span class="solar-val">--</span><span class="humUnit"> W/m²</span></div>
            <div class="humHiLo humHiLo-solar-hi" style="top:269px;"><span class="humHiLo-lbl">Hi</span> <span class="solar-hi">--</span></div>
            <div class="humTime" style="top:298px;"><span class="solar-hi-time">--</span></div>
            <div class="humLabel" style="position:absolute;top:341px;left:16px;">UV</div>
            <div class="humMain" style="position:absolute;top:375px;left:14px;max-width:686px;overflow:hidden;"><span class="uv-val">--</span></div>
            <div class="humHiLo" style="top:418px;"><span class="humHiLo-lbl">Hi</span> <span class="uv-hi">--</span></div>
            <div class="humTime" style="top:447px;"><span class="uv-hi-time">--</span></div>
          </div>`;
    },
    mount(container, slotId) {},
    async refresh(container, dataBase) {
      if (container._refreshInProgress) return;
      container._refreshInProgress = true;
      try {
        const results = await Promise.allSettled([
          fetchJSON(dataBase + "/data/now.json"),
          fetchJSON(dataBase + "/data/extremes.json")
        ]);
        const now = results[0].status === "fulfilled" ? results[0].value : null;
        const extremes = results[1].status === "fulfilled" ? results[1].value : null;
        const n = (now && now.now) ? now.now : (now || {});
        const ex = extremes?.extremes || {};

        const fmt = (v, decimals) => {
          if (v == null || !Number.isFinite(v)) return null;
          return decimals === 0 ? Math.round(v) : Number(v).toFixed(decimals);
        };
        const setVal = (el, v, decimals) => {
          if (!el) return;
          const s = fmt(v, decimals);
          if (s != null) el.textContent = s;
        };
        const fmtTime = (ts) => {
          if (!ts || typeof ts !== "string") return null;
          try {
            const d = new Date(ts);
            if (isNaN(d.getTime())) return null;
            const h = d.getHours(), m = d.getMinutes();
            const ampm = h >= 12 ? "pm" : "am";
            const h12 = h % 12 || 12;
            return h12 + ":" + (m < 10 ? "0" : "") + m + ampm;
          } catch (_) { return null; }
        };
        const setHiLo = (hiEl, loEl, hiVal, loVal) => {
          if (hiEl && hiVal != null && Number.isFinite(hiVal)) hiEl.textContent = Math.round(hiVal);
          if (loEl && loVal != null && Number.isFinite(loVal)) loEl.textContent = Math.round(loVal);
        };
        const setHiLoTimes = (hiEl, loEl, hiTs, loTs) => {
          const t1 = fmtTime(hiTs), t2 = fmtTime(loTs);
          if (hiEl && t1) hiEl.textContent = t1;
          if (loEl && t2) loEl.textContent = t2;
        };

        const hum = Number(n.humidity_pct ?? n.outHumidity ?? n.humidity);
        const dew = Number(n.dewpoint_f ?? n.dewpoint ?? n.dewPoint);
        const solar = Number(n.solar_wm2 ?? n.radiation ?? n.solarRadiation);
        const uv = Number(n.uv_index ?? n.UV ?? n.uv);

        setVal(container.querySelector(".hum-val"), hum, 0);
        setVal(container.querySelector(".dew-val"), dew, 1);
        const dewEl = container.querySelector(".dew-val");
        if (dewEl) {
          dewEl.classList.remove("dew-moderate", "dew-high", "dew-very-high", "dew-extreme");
          if (Number.isFinite(dew)) {
            if (dew >= 80) dewEl.classList.add("dew-extreme");
            else if (dew >= 75) dewEl.classList.add("dew-very-high");
            else if (dew >= 70) dewEl.classList.add("dew-high");
            else if (dew >= 65) dewEl.classList.add("dew-moderate");
          }
        }
        setVal(container.querySelector(".solar-val"), solar, 0);
        setVal(container.querySelector(".uv-val"), uv, 1);
        const uvEl = container.querySelector(".uv-val");
        if (uvEl) {
          uvEl.classList.remove("uv-moderate", "uv-high", "uv-very-high", "uv-extreme");
          if (Number.isFinite(uv)) {
            if (uv >= 11) uvEl.classList.add("uv-extreme");
            else if (uv >= 8) uvEl.classList.add("uv-very-high");
            else if (uv >= 6) uvEl.classList.add("uv-high");
            else if (uv >= 4) uvEl.classList.add("uv-moderate");
          }
        }

        const solarDay = ex.solar_wm2?.day || {};
        const uvDay = ex.uv_index?.day || {};

        setHiLo(container.querySelector(".solar-hi"), null, solarDay.hi, solarDay.lo);
        setHiLoTimes(container.querySelector(".solar-hi-time"), null, solarDay.hi_ts, solarDay.lo_ts);
        setVal(container.querySelector(".uv-hi"), uvDay.hi, 1);
        setHiLoTimes(container.querySelector(".uv-hi-time"), null, uvDay.hi_ts, uvDay.lo_ts);
      } finally {
        container._refreshInProgress = false;
      }
    },
    intervalMs: 3000
  };

  if (typeof MODULES !== "undefined") {
    MODULES["humidity"] = module;
  }
})();
