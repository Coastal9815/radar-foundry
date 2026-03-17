/**
 * Current Temp module — LOCKED
 * Self-contained module for Master MRW dashboard.
 *
 * Move/remove: set SLOTS[i] = "current-temp" or null; works in any box 1–8; script always loaded.
 *
 * Data: now.json, wind.json, computed_rt.json, extremes.json via pi-wx proxy.
 * Layout: docs/MASTER_MRW_LAYOUT_LOCKED.md
 */
(function () {
  "use strict";

  function calcHeatIndex(tF, rh) {
    if (!Number.isFinite(tF) || !Number.isFinite(rh) || tF < 50) return null;
    const t = tF, r = rh;
    const hi = -42.379 + 2.04901523 * t + 10.14333127 * r - 0.22475541 * t * r - 6.83783e-3 * t * t - 5.481717e-2 * r * r + 1.22874e-3 * t * t * r + 8.5282e-4 * t * r * r - 1.99e-6 * t * t * r * r;
    return Number.isFinite(hi) ? hi : null;
  }

  function calcWindChill(tF, windMph) {
    if (tF > 50 || windMph < 3) return tF;
    return 35.74 + 0.6215 * tF - 35.75 * Math.pow(windMph, 0.16) + 0.4275 * tF * Math.pow(windMph, 0.16);
  }

  const module = {
    render(slotId) {
      return `<div class="tempTile">
            <div class="tempLabel" style="position:absolute;top:9px;left:16px;">Temp</div>
            <div class="tempMain" style="position:absolute;top:48px;left:14px;"><span class="temp-val">--</span><span class="degF"><span class="deg">°</span><span class="f">F</span></span></div>
            <div class="tempLabel heat-chill-lbl" style="position:absolute;top:169px;left:16px;">Heat Index</div>
            <div class="tempMain" style="position:absolute;top:208px;left:14px;"><span class="heat-chill-val">--</span><span class="degF"><span class="deg">°</span><span class="f">F</span></span></div>
            <div class="tempLabel" style="position:absolute;top:329px;left:16px;">THSW</div>
            <div class="tempMain" style="position:absolute;top:362px;left:14px;"><span class="thsw-val">--</span><span class="degF"><span class="deg">°</span><span class="f">F</span></span></div>
            <div class="tempHiLo" style="top:40px;"><span class="tempHiLo-lbl">Hi</span> <span class="temp-hi">--</span></div>
            <div class="tempTime" style="top:56px;"><span class="temp-hi-time">12:55pm</span></div>
            <div class="tempHiLo" style="top:113px;"><span class="tempHiLo-lbl">Lo</span> <span class="temp-lo">--</span></div>
            <div class="tempTime" style="top:144px;"><span class="temp-lo-time">12:55pm</span></div>
            <div class="tempHiLo" style="top:200px;"><span class="tempHiLo-lbl">Hi</span> <span class="heat-hi">--</span></div>
            <div class="tempTime" style="top:216px;"><span class="heat-hi-time">12:55pm</span></div>
            <div class="tempHiLo" style="top:273px;"><span class="tempHiLo-lbl">Lo</span> <span class="heat-lo">--</span></div>
            <div class="tempTime" style="top:304px;"><span class="heat-lo-time">12:55pm</span></div>
            <div class="tempHiLo" style="top:354px;"><span class="tempHiLo-lbl">Hi</span> <span class="thsw-hi">--</span></div>
            <div class="tempTime" style="top:370px;"><span class="thsw-hi-time">12:55pm</span></div>
            <div class="tempHiLo" style="top:417px;"><span class="tempHiLo-lbl">Lo</span> <span class="thsw-lo">--</span></div>
            <div class="tempTime" style="top:448px;"><span class="thsw-lo-time">12:55pm</span></div>
          </div>`;
    },
    mount(container, slotId) {},
    async refresh(container, dataBase) {
      if (container._refreshInProgress) return;
      container._refreshInProgress = true;
      try {
        const tempEl = container.querySelector(".temp-val");
        const heatChillEl = container.querySelector(".heat-chill-val");
        const heatChillLbl = container.querySelector(".heat-chill-lbl");
        const thswEl = container.querySelector(".thsw-val");
        if (!tempEl || !heatChillEl || !thswEl) return;
        const results = await Promise.allSettled([
          fetchJSON(dataBase + "/data/now.json"),
          fetchJSON(dataBase + "/data/wind.json"),
          fetchJSON(dataBase + "/data/computed_rt.json"),
          fetchJSON(dataBase + "/data/extremes.json")
        ]);
        const now = results[0].status === "fulfilled" ? results[0].value : null;
        const wind = results[1].status === "fulfilled" ? results[1].value : null;
        const computed = results[2].status === "fulfilled" ? results[2].value : null;
        const extremes = results[3].status === "fulfilled" ? results[3].value : null;
        const n = (now && now.now) ? now.now : (now || {});
        const w = wind?.wind || wind || {};
        const c = computed?.computed || {};
        const ex = extremes?.extremes || {};
        const temp = Number(n.temp_f ?? n.outTemp);
        const hum = Number(n.humidity_pct ?? n.outHumidity ?? n.humidity);
        const speed = Number(w.speed_mph ?? w.wind_speed_mph ?? w.windSpeed);
        const heatIndex = c.heat_index_f ?? n.heat_index ?? n.heatindex;
        const windChill = c.wind_chill_f ?? n.windchill ?? n.windChill;
        const thsw = c.thsw_f ?? n.thsw ?? n.apparent_temp ?? n.apparentTemp;
        const tempAlertClass = (v) => {
          if (v == null || !Number.isFinite(v)) return "";
          if (v >= 105) return "tempAlert-red";
          if (v >= 100) return "tempAlert-orange";
          if (v >= 95) return "tempAlert-yellow";
          if (v <= 32) return "tempAlert-blue";
          if (v <= 39.9) return "tempAlert-lightblue";
          return "";
        };
        const applyTempAlert = (el, v) => {
          if (!el) return;
          if (v != null && Number.isFinite(v)) {
            el.textContent = Number(v).toFixed(1);
            ["tempAlert-yellow", "tempAlert-orange", "tempAlert-red", "tempAlert-lightblue", "tempAlert-blue"].forEach(c => el.classList.remove(c));
            const cls = tempAlertClass(v);
            if (cls) el.classList.add(cls);
          }
          /* If v invalid, leave display unchanged — avoid flashing -- on transient fetch failures */
        };
        applyTempAlert(tempEl, temp);
        const useHeatIndex = temp >= 50;
        let hiOrWc = useHeatIndex ? heatIndex : windChill;
        if (hiOrWc == null || !Number.isFinite(hiOrWc)) {
          if (useHeatIndex && Number.isFinite(temp) && Number.isFinite(hum)) {
            hiOrWc = calcHeatIndex(temp, hum);
          } else if (!useHeatIndex && Number.isFinite(temp) && Number.isFinite(speed)) {
            hiOrWc = calcWindChill(temp, speed);
          }
        }
        applyTempAlert(heatChillEl, hiOrWc);
        if (heatChillLbl) heatChillLbl.textContent = useHeatIndex ? "Heat Index" : "Wind Chill";
        applyTempAlert(thswEl, thsw);
        const fmtHiLo = (v) => (v != null && Number.isFinite(v)) ? Math.round(v) : "--";
        const fmtTime = (ts) => {
          if (!ts || typeof ts !== "string") return "--";
          try {
            const d = new Date(ts);
            if (isNaN(d.getTime())) return "--";
            const h = d.getHours(), m = d.getMinutes();
            const ampm = h >= 12 ? "pm" : "am";
            const h12 = h % 12 || 12;
            return h12 + ":" + (m < 10 ? "0" : "") + m + ampm;
          } catch (_) { return "--"; }
        };
        const setHiLo = (hiEl, loEl, hiVal, loVal) => {
          if (hiEl && hiVal != null && Number.isFinite(hiVal)) hiEl.textContent = Math.round(hiVal);
          if (loEl && loVal != null && Number.isFinite(loVal)) loEl.textContent = Math.round(loVal);
        };
        const setHiLoTimes = (hiEl, loEl, hiTs, loTs) => {
          const t1 = fmtTime(hiTs), t2 = fmtTime(loTs);
          if (hiEl && t1 !== "--") hiEl.textContent = t1;
          if (loEl && t2 !== "--") loEl.textContent = t2;
        };
        const tDay = ex.temp_f?.day || {};
        const hDay = ex.heat_index_f?.day || {};
        const sDay = ex.thsw_f?.day || {};
        setHiLo(container.querySelector(".temp-hi"), container.querySelector(".temp-lo"), tDay.hi, tDay.lo);
        setHiLo(container.querySelector(".heat-hi"), container.querySelector(".heat-lo"), hDay.hi, hDay.lo);
        setHiLo(container.querySelector(".thsw-hi"), container.querySelector(".thsw-lo"), sDay.hi, sDay.lo);
        setHiLoTimes(container.querySelector(".temp-hi-time"), container.querySelector(".temp-lo-time"), tDay.hi_ts, tDay.lo_ts);
        setHiLoTimes(container.querySelector(".heat-hi-time"), container.querySelector(".heat-lo-time"), hDay.hi_ts, hDay.lo_ts);
        setHiLoTimes(container.querySelector(".thsw-hi-time"), container.querySelector(".thsw-lo-time"), sDay.hi_ts, sDay.lo_ts);
      } finally {
        container._refreshInProgress = false;
      }
    },
    intervalMs: 3000
  };

  if (typeof MODULES !== "undefined") {
    MODULES["current-temp"] = module;
  }
})();
