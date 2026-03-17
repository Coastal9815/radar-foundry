/**
 * Rain Accumulation module — Monthly to Date, Monthly % of Norm, Year to Date, Year % of Norm, Yearly Deficit/Excess.
 * Box 4 (SLOTS[3]). Includes Drought Status bar (US Drought Monitor, Chatham County GA).
 *
 * Data: rain.json, rain_norms.json from pi-wx; drought from /drought-data/chatham.json (proxied USDM API).
 */
(function () {
  "use strict";

  // Default norms: Savannah Hilton Head Intl Airport (GHCND:USW00003822), 1991–2020. Override via rain_norms.json from pi-wx.
  const DEFAULT_MONTH_NORMS_IN = [3.28, 2.80, 3.50, 3.39, 3.62, 6.65, 5.75, 5.46, 4.35, 3.72, 2.39, 3.21];
  const DEFAULT_YEAR_NORM_IN = 48.12;

  const DROUGHT_CATEGORIES = [
    { id: "Normal", short: "Normal", full: "Normal" },
    { id: "D0", short: "D0", full: "Abnormally Dry" },
    { id: "D1", short: "D1", full: "Moderate Drought" },
    { id: "D2", short: "D2", full: "Severe Drought" },
    { id: "D3", short: "D3", full: "Extreme Drought" },
    { id: "D4", short: "D4", full: "Exceptional Drought" }
  ];
  const DROUGHT_COLORS = ["#4ade80", "#bef264", "#facc15", "#fb923c", "#ef4444", "#a855f7"];

  const module = {
    render(slotId) {
      return `<div class="rainAccumTile">
            <div class="rainAccumCol rainAccumColLeft">
              <div class="rainAccumLabel" style="position:absolute;top:6px;left:16px;right:350px;text-align:center;">Month</div>
              <div class="rainAccumVal" style="position:absolute;top:56px;left:16px;right:350px;text-align:center;"><span class="month-val">--</span><span class="rainAccumUnit">"</span></div>
              <div class="rainAccumLabel" style="position:absolute;top:166px;left:16px;right:350px;text-align:center;">% of Norm:</div>
              <div class="rainAccumVal" style="position:absolute;top:221px;left:16px;right:350px;text-align:center;"><span class="month-pct-val">--</span><span class="rainAccumUnit rainAccumUnitPct">%</span></div>
            </div>
            <div class="rainAccumCol rainAccumColRight">
              <div class="rainAccumLabel" style="position:absolute;top:6px;left:350px;right:16px;text-align:center;">Year</div>
              <div class="rainAccumVal" style="position:absolute;top:56px;left:350px;right:16px;text-align:center;"><span class="year-val">--</span><span class="rainAccumUnit">"</span></div>
              <div class="rainAccumLabel" style="position:absolute;top:166px;left:350px;right:16px;text-align:center;">% of Norm:</div>
              <div class="rainAccumVal" style="position:absolute;top:221px;left:350px;right:16px;text-align:center;"><span class="year-pct-val">--</span><span class="rainAccumUnit rainAccumUnitPct">%</span></div>
            </div>
            <div class="rainAccumBottom">
              <div class="rainAccumDeficit">
                <div class="rainAccumLabel deficit-label-wrap"><span class="deficit-label">Year Deficit</span></div>
                <div class="rainAccumVal deficit-val-wrap"><span class="deficit-val">--</span><span class="rainAccumUnit rainAccumUnitDeficit">"</span></div>
              </div>
              <div class="rainAccumDrought">
                <div class="rainAccumLabel drought-label">Drought Status</div>
                <div class="droughtBarWrap">
                  <div class="droughtBarArrow"></div>
                  <div class="droughtBar">
                    ${DROUGHT_CATEGORIES.map((c, i) => `<div class="droughtSeg" data-idx="${i}" style="background:${DROUGHT_COLORS[i]}"></div>`).join("")}
                  </div>
                  <div class="droughtBarLabels">
                    ${DROUGHT_CATEGORIES.map((c, i) => `<span class="droughtSegLbl" data-idx="${i}">${c.short}</span>`).join("")}
                  </div>
                </div>
                <div class="droughtStatusText"><span class="drought-status-val">--</span></div>
              </div>
            </div>
          </div>`;
    },
    mount(container, slotId) {},
    async refresh(container, dataBase) {
      if (container._refreshInProgress) return;
      container._refreshInProgress = true;
      const origin = (typeof location !== "undefined" && location.origin) ? location.origin : "";
      try {
        const [rainRes, normsRes, droughtRes] = await Promise.allSettled([
          fetch(dataBase + "/data/rain.json").then(r => r.ok ? r.json() : null),
          fetch(dataBase + "/data/rain_norms.json").then(r => r.ok ? r.json() : null),
          fetch(origin + "/drought-data/chatham.json").then(r => r.ok ? r.json() : null)
        ]);
        const rain = rainRes.status === "fulfilled" ? rainRes.value : null;
        const norms = normsRes.status === "fulfilled" ? normsRes.value : null;
        const r = (rain && rain.rain) ? rain.rain : (rain && typeof rain === "object" ? rain : {});

        const monthNorms = (norms && Array.isArray(norms.month_norm_in))
          ? norms.month_norm_in : DEFAULT_MONTH_NORMS_IN;
        const yearNorm = norms?.year_norm_in ?? DEFAULT_YEAR_NORM_IN;

        const monthIn = Number(r.month_in ?? r.month_rain_in ?? 0);
        const yearIn = Number(r.year_in ?? r.year_rain_in ?? 0);

        // Use America/New_York (EST/EDT) — source of truth for all MRW weather
        const tz = "America/New_York";
        const fmt = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" });
        const parts = Object.fromEntries(fmt.formatToParts(new Date()).map((p) => [p.type, p.value]));
        const year = parseInt(parts.year, 10);
        const monthIdx = parseInt(parts.month, 10) - 1;
        const monthNorm = monthNorms[monthIdx];
        const daysElapsed = parseInt(parts.day, 10);
        const daysInMonth = new Date(year, monthIdx + 1, 0).getDate();

        // Expected to date = sum of full months Jan..(current-1) + partial current month
        let expectedToDate = 0;
        for (let m = 0; m < monthIdx; m++) expectedToDate += Number(monthNorms[m]) || 0;
        expectedToDate += (monthNorm > 0 && daysInMonth > 0)
          ? (monthNorm / daysInMonth) * daysElapsed : 0;
        expectedToDate = expectedToDate > 0 ? expectedToDate : null;

        // Deficit/Excess: actual - expected. Negative = deficit, positive = excess
        const deficitExcess = (Number.isFinite(yearIn) && Number.isFinite(expectedToDate))
          ? yearIn - expectedToDate : null;

        const fmtIn = (v) => (v != null && Number.isFinite(v)) ? Number(v).toFixed(2) : null;
        const fmtPct = (v) => (v != null && Number.isFinite(v)) ? String(Math.round(v)) : null;
        const fmtDeficit = (v) => {
          if (v == null || !Number.isFinite(v)) return null;
          const n = Number(v);
          if (n >= 0) return (n === 0 ? "0.00" : "+" + n.toFixed(2));
          return n.toFixed(2);
        };
        const setVal = (el, s) => { if (el) el.textContent = s != null ? s : "--"; };

        // Monthly % of Norm: expected to date = (monthNorm / daysInMonth) * daysElapsed; pct = actual / expected * 100
        const expectedMonthToDate = (monthNorm > 0 && daysInMonth > 0)
          ? (monthNorm / daysInMonth) * daysElapsed : null;
        const monthPct = (expectedMonthToDate > 0 && Number.isFinite(monthIn))
          ? (monthIn / expectedMonthToDate) * 100 : null;
        const yearPct = (expectedToDate > 0 && Number.isFinite(yearIn)) ? (yearIn / expectedToDate) * 100 : null;

        setVal(container.querySelector(".month-val"), fmtIn(monthIn));
        setVal(container.querySelector(".month-pct-val"), fmtPct(monthPct));
        setVal(container.querySelector(".year-val"), fmtIn(yearIn));
        setVal(container.querySelector(".year-pct-val"), fmtPct(yearPct));
        setVal(container.querySelector(".deficit-val"), fmtDeficit(deficitExcess));
        const deficitLbl = container.querySelector(".deficit-label");
        if (deficitLbl && deficitExcess != null) {
          deficitLbl.textContent = deficitExcess >= 0.01 ? "Year Excess" : "Year Deficit";
        }

        // Drought: parse USDM CountyStatistics response, pick highest category with >0
        let droughtIdx = 0;
        const droughtData = droughtRes?.status === "fulfilled" ? droughtRes.value : null;
        if (droughtData && Array.isArray(droughtData) && droughtData.length > 0) {
          const latest = droughtData[0];
          const pct = (k) => (typeof latest[k] === "number" ? latest[k] : parseFloat(latest[k]) || 0);
          const d4 = pct("d4"), d3 = pct("d3"), d2 = pct("d2"), d1 = pct("d1"), d0 = pct("d0");
          if (d4 > 0) droughtIdx = 5;
          else if (d3 > 0) droughtIdx = 4;
          else if (d2 > 0) droughtIdx = 3;
          else if (d1 > 0) droughtIdx = 2;
          else if (d0 > 0) droughtIdx = 1;
        }
        const cat = DROUGHT_CATEGORIES[droughtIdx];
        const arrow = container.querySelector(".droughtBarArrow");
        if (arrow) {
          arrow.style.left = `${(droughtIdx + 0.5) * (100 / 6)}%`;
          arrow.style.transform = "translateX(-50%)";
        }
        const statusEl = container.querySelector(".drought-status-val");
        if (statusEl) statusEl.textContent = droughtData ? `${cat.full} (${cat.short})` : "--";
      } finally {
        container._refreshInProgress = false;
      }
    },
    intervalMs: 60000
  };

  if (typeof MODULES !== "undefined") {
    MODULES["rain-accumulation"] = module;
  }
})();
