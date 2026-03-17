/**
 * Rain (Current) module — Today, Rain Rate, Storm Rain, Days Since Rain.
 * LOCKED. Do not change layout without explicit approval.
 *
 * MOVE: Set SLOTS[newIndex] = "rain-current", SLOTS[oldIndex] = null.
 * REMOVE: Set SLOTS[i] = null.
 * ADD BACK: Set SLOTS[i] = "rain-current".
 *
 * Data: rain.json, now.json via pi-wx proxy. today_in, rate_inhr, storm_in.
 * Days Since: 0 if today_in > 0.001, else from storm_last_end_at.
 */
(function () {
  "use strict";

  const module = {
    render(slotId) {
      /* Explicit X/Y — from flex: row left 16, right 16, gap 18; label left 16; value left 474 (16+18+maxLabel); digit cluster right 116; " at right 96; " in/hr" at right 16 */
      return `<div class="rainTile">
            <div class="rainLabel" style="position:absolute;bottom:405px;left:16px;line-height:1;">Rain Today</div>
            <div class="rainVal" style="position:absolute;top:-1px;left:404px;right:186px;text-align:right;"><span class="today-val">--</span><span class="rainUnit rainUnitInch">"</span></div>
            <div class="rainLabel" style="position:absolute;bottom:275px;left:16px;line-height:1;">Rain Rate</div>
            <div class="rainVal" style="position:absolute;top:129px;left:404px;right:186px;text-align:right;"><span class="rate-val">--</span></div>
            <div class="rainUnit rainUnitInHr" style="position:absolute;top:144px;right:16px;line-height:1;text-align:right;">in<br>hr</div>
            <div class="rainLabel" style="position:absolute;bottom:155px;left:16px;line-height:1;">Storm Rain</div>
            <div class="rainVal" style="position:absolute;bottom:155px;left:404px;right:186px;text-align:right;"><span class="storm-val">--</span><span class="rainUnit rainUnitInch">"</span></div>
            <div class="rainLabel" style="position:absolute;bottom:23px;left:16px;line-height:1;">Days Since Rain</div>
            <div class="rainVal" style="position:absolute;bottom:22px;left:404px;right:186px;text-align:right;"><span class="days-val">--</span></div>
          </div>`;
    },
    mount(container, slotId) {},
    async refresh(container, dataBase) {
      if (container._refreshInProgress) return;
      container._refreshInProgress = true;
      try {
        const results = await Promise.allSettled([
          fetchJSON(dataBase + "/data/rain.json"),
          fetchJSON(dataBase + "/data/now.json")
        ]);
        const rain = results[0].status === "fulfilled" ? results[0].value : null;
        const now = results[1].status === "fulfilled" ? results[1].value : null;
        const r = (rain && rain.rain) ? rain.rain : (rain && typeof rain === "object" ? rain : {});
        const n = (now && now.now) ? now.now : (now || {});

        const fmtIn = (v) => {
          if (v == null || !Number.isFinite(v)) return null;
          return Number(v).toFixed(2);
        };
        const fmtRate = (v) => {
          if (v == null || !Number.isFinite(v)) return null;
          return Number(v).toFixed(2);
        };
        const setVal = (el, s) => {
          if (!el) return;
          el.textContent = s != null ? s : "--";
        };

        const today = r.today_in ?? r.rain_today ?? r.rain_today_in ?? n.rain_today ?? n.rain_today_in;
        const rate = r.rate_inhr ?? r.rain_rate_in ?? r.rainRate ?? r.rain_rate ?? n.rain_rate_inhr ?? n.rainRate;
        const storm = r.storm_in ?? r.storm_rain_in ?? r.stormRain ?? r.storm_rain ?? n.storm_rain_in ?? n.stormRain;
        let days = r.days_since_rain ?? r.daySinceRain ?? r.day_since_rain ?? n.days_since_rain ?? n.daySinceRain;
        const todayIn = Number(r.today_in ?? r.rain_today ?? r.rain_today_in ?? n.rain_today ?? n.rain_today_in ?? 0);
        if (todayIn > 0.001) {
          days = 0; // rained today
        } else if (days == null && r.storm_last_end_at != null) {
          const endTs = Number(r.storm_last_end_at);
          if (Number.isFinite(endTs)) days = Math.floor((Date.now() / 1000 - endTs) / 86400);
        }

        setVal(container.querySelector(".today-val"), fmtIn(today));
        setVal(container.querySelector(".rate-val"), fmtRate(rate));
        setVal(container.querySelector(".storm-val"), fmtIn(storm));
        setVal(container.querySelector(".days-val"), (days != null && Number.isFinite(days)) ? Math.round(days) : "--");
      } finally {
        container._refreshInProgress = false;
      }
    },
    intervalMs: 3000
  };

  if (typeof MODULES !== "undefined") {
    MODULES["rain-current"] = module;
  }
})();
