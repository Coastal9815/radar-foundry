/**
 * Air Quality module — PM2.5, PM10 (Davis Air Link), Ozone (AirNow), Smoke (HRRR),
 * Saharan Dust, Pollen (Google/NAB proxy). Box 5 (SLOTS[4]).
 *
 * Data: /api/air/summary (all metrics; PM from pi-wx proxy).
 */
(function () {
  "use strict";

  const module = {
    render(slotId) {
      return `<div class="airQualityTile">
            <div class="airQualityCell airQualityC1" style="position:absolute;left:24px;top:-1px;right:363px;"><span class="airQualityLabel">PM2.5</span><span class="airQualityVal"><span class="pm25-val">--</span></span></div>
            <div class="airQualityCell airQualityC2" style="position:absolute;left:408px;top:-1px;right:24px;"><span class="airQualityLabel">PM10</span><span class="airQualityVal"><span class="pm10-val">--</span></span></div>
            <div class="airQualityCell airQualityC3" style="position:absolute;left:24px;top:161px;right:363px;"><span class="airQualityLabel">Ozone</span><span class="airQualityVal"><span class="ozone-val">--</span><span class="airQualityUnit"> ppb</span></span></div>
            <div class="airQualityCell airQualityC4" style="position:absolute;left:408px;top:161px;right:24px;"><span class="airQualityLabel">Smoke</span><span class="airQualityVal"><span class="smoke-val">--</span></span></div>
            <div class="airQualityCell airQualityC5" style="position:absolute;left:24px;top:318px;right:363px;"><span class="airQualityLabel">Dust</span><span class="airQualityVal"><span class="dust-val">--</span></span></div>
            <div class="airQualityCell airQualityC6" style="position:absolute;left:408px;top:318px;right:24px;"><span class="airQualityLabel pollen-label">Pollen</span><span class="airQualityVal"><span class="pollen-val">--</span></span></div>
          </div>`;
    },
    mount(container, slotId) {},
    async refresh(container, dataBase) {
      if (container._refreshInProgress) return;
      container._refreshInProgress = true;
      const origin = (typeof location !== "undefined" && location.origin) ? location.origin : "";
      try {
        const res = await fetch(origin + "/api/air/summary", { cache: "no-store" });
        const data = res?.ok ? await res.json() : null;

        const setVal = (el, v, decimals) => {
          if (!el) return;
          if (v == null || (typeof v === "string" && v === "") || (typeof v === "number" && !Number.isFinite(v))) {
            el.textContent = "--";
            return;
          }
          if (typeof v === "string") {
            el.textContent = v;
            return;
          }
          el.textContent = decimals === 0 ? Math.round(v) : Number(v).toFixed(decimals);
        };

        const pm25 = data?.pm25;
        const pm10 = data?.pm10;
        const ozone = data?.ozone;
        const smoke = data?.smoke;
        const dust = data?.saharan_dust;
        const pollen = data?.pollen;

        const pm25El = container.querySelector(".pm25-val");
        const pm10El = container.querySelector(".pm10-val");
        setVal(pm25El, pm25, 1);
        setVal(pm10El, pm10, 1);
        const pm25Class = (v) => { if (v == null || !Number.isFinite(v)) return ""; if (v <= 9) return ""; if (v <= 35.4) return "aqi-moderate"; if (v <= 55.4) return "aqi-unhealthy-sens"; if (v <= 125.4) return "aqi-unhealthy"; if (v <= 225.4) return "aqi-very-unhealthy"; return "aqi-hazardous"; };
        const pm10Class = (v) => { if (v == null || !Number.isFinite(v)) return ""; if (v <= 54) return ""; if (v <= 154) return "aqi-moderate"; if (v <= 254) return "aqi-unhealthy-sens"; if (v <= 354) return "aqi-unhealthy"; if (v <= 424) return "aqi-very-unhealthy"; return "aqi-hazardous"; };
        if (pm25El) pm25El.className = "pm25-val " + pm25Class(pm25 != null ? Number(pm25) : null);
        if (pm10El) pm10El.className = "pm10-val " + pm10Class(pm10 != null ? Number(pm10) : null);

        const ozoneVal = ozone?.value != null ? Number(ozone.value) : null;
        const ozoneEl = container.querySelector(".ozone-val");
        setVal(ozoneEl, ozoneVal, 0);
        const ozoneClass = (v) => { if (v == null || !Number.isFinite(v)) return ""; if (v <= 54) return ""; if (v <= 70) return "aqi-moderate"; if (v <= 85) return "aqi-unhealthy-sens"; if (v <= 105) return "aqi-unhealthy"; if (v <= 200) return "aqi-very-unhealthy"; return "aqi-hazardous"; };
        if (ozoneEl) ozoneEl.className = "ozone-val " + ozoneClass(ozoneVal);

        const smokeDisplay = smoke?.level ?? (smoke?.value != null ? `${smoke.value} µg/m³` : null);
        const smokeEl = container.querySelector(".smoke-val");
        setVal(smokeEl, smokeDisplay, null);
        if (smokeEl) smokeEl.style.color = smoke?.color || "";

        const dustDisplay = dust?.level ?? dust?.status ?? null;
        const dustEl = container.querySelector(".dust-val");
        setVal(dustEl, dustDisplay, null);
        if (dustEl) dustEl.style.color = dust?.color || "";

        const pollenDisplay = pollen?.level != null ? pollen.level : null;
        const pollenValEl = container.querySelector(".pollen-val");
        setVal(pollenValEl, pollenDisplay, null);
        const pollenClassMap = { "None": "pollen-none", "Very Low": "pollen-vlow", "Low": "pollen-low", "Low-Moderate": "pollen-lowmod", "Moderate": "pollen-moderate", "High": "pollen-high", "Very High": "pollen-vhigh" };
        if (pollenValEl) {
          pollenValEl.className = "pollen-val " + (pollenClassMap[pollen?.level] || "");
        }
        const pollenLabelEl = container.querySelector(".pollen-label");
        if (pollenLabelEl) pollenLabelEl.textContent = pollen?.primary ? `${pollen.primary} Pollen` : "Pollen";
      } finally {
        container._refreshInProgress = false;
      }
    },
    intervalMs: 60000
  };

  if (typeof MODULES !== "undefined") {
    MODULES["air-quality"] = module;
  }
})();
