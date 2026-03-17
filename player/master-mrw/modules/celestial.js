/**
 * Celestial module — sunrise, sunset, day length, moonrise, moonset, phase, next season.
 * Box 6 (SLOTS[5]). LOCKED. Data: /api/celestial/summary.
 */
(function () {
  "use strict";

  const module = {
    render(slotId) {
      return `<div class="celestialTile">
            <div class="celestialCell" style="position:absolute;left:24px;top:9px;right:478px;"><span class="celestialLabel">Sunrise</span><span class="celestialVal sunrise-val">--</span></div>
            <div class="celestialCell" style="position:absolute;left:256px;top:9px;right:256px;text-align:center;"><span class="celestialLabel">Sunset</span><span class="celestialVal sunset-val">--</span></div>
            <div class="celestialCell" style="position:absolute;left:478px;top:9px;right:24px;text-align:right;"><span class="celestialLabel">Length</span><span class="celestialVal day-length-val">--</span></div>
            <div class="celestialCell" style="position:absolute;left:24px;top:161px;right:478px;"><span class="celestialLabel">Moonrise</span><span class="celestialVal moonrise-val">--</span></div>
            <div class="celestialCell" style="position:absolute;left:256px;top:161px;right:256px;text-align:center;"><span class="celestialLabel">Moonset</span><span class="celestialVal moonset-val">--</span></div>
            <div class="celestialCell" style="position:absolute;left:478px;top:161px;right:24px;text-align:right;"><span class="celestialLabel">Phase</span><span class="celestialVal phase-val">--</span></div>
            <div class="celestialCell" style="position:absolute;left:24px;top:318px;right:24px;"><span class="celestialLabel">Next Season</span><span class="celestialVal next-season-val">--</span></div>
          </div>`;
    },
    mount(container, slotId) {},
    async refresh(container, dataBase) {
      if (container._refreshInProgress) return;
      container._refreshInProgress = true;
      const origin = (typeof location !== "undefined" && location.origin) ? location.origin : "";
      try {
        const res = await fetch(origin + "/api/celestial/summary", { cache: "no-store" });
        const data = res?.ok ? await res.json() : null;

        const setVal = (el, v) => {
          if (!el) return;
          el.textContent = (v != null && v !== "") ? String(v) : "--";
        };

        setVal(container.querySelector(".sunrise-val"), data?.sunrise);
        setVal(container.querySelector(".sunset-val"), data?.sunset);
        setVal(container.querySelector(".day-length-val"), data?.day_length);
        setVal(container.querySelector(".moonrise-val"), data?.moonrise);
        setVal(container.querySelector(".moonset-val"), data?.moonset);
        setVal(container.querySelector(".phase-val"), data?.phase);
        setVal(container.querySelector(".next-season-val"), data?.next_season_start);
      } finally {
        container._refreshInProgress = false;
      }
    },
    intervalMs: 300000  // 5 min — celestial data changes slowly
  };

  if (typeof MODULES !== "undefined") {
    MODULES["celestial"] = module;
  }
})();
