/**
 * Moon River Weather alerts — parity with moonriverweather.com /api/alerts (alerts.ts).
 * Renders NWS (GAZ119) + local MRW conditions into the master dashboard threat bar.
 */
(function () {
  "use strict";

  var DATA_BASE = typeof window !== "undefined" && window.MRW_DATA_BASE ? window.MRW_DATA_BASE : "/pi-wx-data";
  var NWS_ALERTS_URL = "https://api.weather.gov/alerts/active?zone=GAZ119";
  var LIGHTNING_URL =
    typeof window !== "undefined" && window.MRW_LIGHTNING_GEOJSON_URL
      ? window.MRW_LIGHTNING_GEOJSON_URL
      : "https://radar.moonriverweather.com/lightning_points_xweather_local.geojson";

  var REFRESH_MS = 60 * 1000;
  var TIMEOUT_MS = 15000;
  var BAR_CYCLE_LEN = 10;
  var CLOSE_RADIUS_KM = 25 * 1.609344;
  var LIGHTNING_CLEAR_AFTER_SEC = 30 * 60;

  var MRW_THRESHOLDS = {
    airPm25: 12,
    /** MRW local wind: same entry as pi-wx threat_strip / Galaxy A9 */
    windAvg10: 15,
    windGustMin: 20,
    rainRate: 0.02,
    uvIndex: 8,
    tideHeightFt: 9.5,
    windGustYellow: 30,
    windGustRed: 40,
    tempHighYellow: 90,
    tempHighRed: 100,
    tempLowYellow: 45,
    tempLowRed: 32,
    heatIndexYellow: 100,
    heatIndexRed: 110,
    thswHighYellow: 105,
    thswHighRed: 115,
    thswLowYellow: 40,
    thswLowRed: 25,
    windChillYellow: 40,
    windChillRed: 30,
  };

  var COND_ORDER = ["AIR", "LIGHTNING", "WIND", "RAIN", "HEAT", "COLD", "TEMP", "APPARENT", "UV", "TIDE"];

  function $(id) {
    return document.getElementById(id);
  }

  function num(v) {
    return typeof v === "number" && !isNaN(v) ? v : undefined;
  }

  function fetchMaybe(url, headers) {
    var c = new AbortController();
    var id = setTimeout(function () {
      c.abort();
    }, TIMEOUT_MS);
    return fetch(url, {
      cache: "no-store",
      credentials: "omit",
      signal: c.signal,
      headers: headers || undefined,
    })
      .then(function (r) {
        clearTimeout(id);
        if (!r.ok) return null;
        return r.json();
      })
      .catch(function () {
        clearTimeout(id);
        return null;
      });
  }

  function fetchNwsAlerts() {
    var headers = {
      Accept: "application/json",
      "User-Agent": "MoonRiverWeather/1.0 (https://moonriverweather.com)",
    };
    function attempt(i) {
      return fetch(NWS_ALERTS_URL, { cache: "no-store", credentials: "omit", headers: headers }).then(function (res) {
        if (res.status === 429 && i < 3) {
          var delay = 1000 * Math.pow(2, i);
          return new Promise(function (r) {
            setTimeout(r, delay);
          }).then(function () {
            return attempt(i + 1);
          });
        }
        return res;
      });
    }
    return attempt(0)
      .then(function (res) {
        return res.ok ? res.json() : null;
      })
      .catch(function () {
        return null;
      });
  }

  function parseTideLocal(ts) {
    var s = String(ts).trim().replace(" ", "T");
    var m = s.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{1,2}):(\d{2})/);
    if (!m) return new Date(NaN);
    var y = m[1],
      mo = m[2],
      d = m[3],
      h = m[4],
      min = m[5];
    var month = parseInt(mo, 10);
    var isDST = month >= 3 && month <= 10;
    var tz = isDST ? "-04:00" : "-05:00";
    return new Date(y + "-" + mo + "-" + d + "T" + String(h).padStart(2, "0") + ":" + min + ":00" + tz);
  }

  function fmtTideTime(d) {
    if (!d || isNaN(d.getTime())) return "--:--";
    return new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    }).format(d);
  }

  function formatExpires(iso) {
    if (!iso) return "";
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return "";
      return d.toLocaleTimeString("en-US", {
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
        timeZone: "America/New_York",
      });
    } catch (e) {
      return "";
    }
  }

  function nwsSeverityRank(s) {
    var map = { Extreme: 4, Severe: 3, Moderate: 2, Minor: 1, Unknown: 0 };
    return map[s] != null ? map[s] : 0;
  }

  function nwsDisplaySeverityRank(alert) {
    var ev = String(alert.event || "").toLowerCase();
    var isWatch = ev.indexOf("watch") !== -1 && ev.indexOf("warning") === -1;
    var raw = nwsSeverityRank(alert.severity);
    if (isWatch) return Math.min(raw, 3);
    return raw;
  }

  function sortNwsAlerts(alerts) {
    var order = ["Tornado", "Tsunami", "Severe Thunderstorm", "Extreme Wind", "Flash Flood", "Tropical", "Blizzard"];
    return alerts.slice().sort(function (a, b) {
      var sev = nwsSeverityRank(b.severity) - nwsSeverityRank(a.severity);
      if (sev !== 0) return sev;
      function idx(x) {
        var i = order.findIndex(function (o) {
          return x.event.indexOf(o) !== -1;
        });
        return i === -1 ? 999 : i;
      }
      return idx(a) - idx(b);
    });
  }

  function getNowBlock(raw) {
    if (!raw || typeof raw !== "object") return {};
    if (raw.now != null && typeof raw.now === "object") return raw.now;
    return raw;
  }

  function buildAlertsPayload(nwsData, airJson, windJson, rainJson, computedJson, nowJson, lightningJson, tideJson) {
    var nwsAlerts = [];
    if (nwsData && nwsData.features) {
      for (var fi = 0; fi < nwsData.features.length; fi++) {
        var f = nwsData.features[fi];
        var p = (f && f.properties) || {};
        nwsAlerts.push({
          event: typeof p.event === "string" ? p.event : "",
          severity: typeof p.severity === "string" ? p.severity : "Unknown",
          headline: typeof p.headline === "string" ? p.headline : typeof p.event === "string" ? p.event : "",
          onset: typeof p.onset === "string" ? p.onset : undefined,
          expires: typeof p.expires === "string" ? p.expires : undefined,
        });
      }
    }
    var sortedNws = sortNwsAlerts(nwsAlerts);

    var airRoot = (airJson && airJson.air) || airJson || {};
    var windRoot = (windJson && windJson.wind) || windJson || {};
    var rainRoot = (rainJson && rainJson.rain) || rainJson || {};
    var compRoot = (computedJson && computedJson.computed) || computedJson || {};
    var nowN = getNowBlock(nowJson);
    var tideRoot = (tideJson && tideJson.tide) || tideJson || {};

    var airPm25 = num(airRoot.pm_2p5_ugm3);
    var nowW = nowN.wind != null && typeof nowN.wind === "object" ? nowN.wind : {};
    function gustPeak(a, b) {
      if (a == null) return b;
      if (b == null) return a;
      return Math.max(a, b);
    }
    var windAvg10 = num(windRoot.avg_10m_mph);
    if (windAvg10 == null) windAvg10 = num(nowW.avg_10m_mph);
    var windMaxGust10m = gustPeak(num(windRoot.max_gust_10m_mph), num(nowW.max_gust_10m_mph));
    /* Max of all reported gusts so proxy/stale wind.json cannot hide a higher now.json gust */
    var windGustNow = gustPeak(gustPeak(num(windRoot.gust_mph), num(nowW.gust_mph)), num(nowN.wind_gust_mph));
    var windSpeedNow = num(windRoot.speed_mph);
    if (windSpeedNow == null) {
      windSpeedNow = num(nowW.speed_mph != null ? nowW.speed_mph : nowW.wind_speed_mph != null ? nowW.wind_speed_mph : nowN.wind_speed_mph);
    }
    /* Match pi-wx threat_strip: peak gust vs 10m max, not 10m max alone when it lags */
    var windGustPeak = gustPeak(windGustNow, windMaxGust10m);
    var rainRate = num(rainRoot.rate_inhr);
    var heatIndex = num(compRoot.heat_index_f);
    var windChill = num(compRoot.wind_chill_f);
    var thsw = num(compRoot.thsw_f);
    var temp = num(nowN.temp_f);
    if (heatIndex == null) heatIndex = num(nowN.heat_index_f);
    if (windChill == null) windChill = num(nowN.wind_chill_f);
    var uvIndex = num(nowN.uv_index);

    var lightningProximity = undefined;
    if (lightningJson && lightningJson.features) {
      var closestClose = undefined;
      for (var li = 0; li < lightningJson.features.length; li++) {
        var lf = lightningJson.features[li];
        var lp = (lf && lf.properties) || {};
        var distKm = num(lp.distance_km);
        var ageSec = num(lp.age_seconds);
        if (distKm == null || ageSec == null || distKm > CLOSE_RADIUS_KM || ageSec > LIGHTNING_CLEAR_AFTER_SEC) continue;
        if (!closestClose || ageSec < closestClose.ageSec) {
          closestClose = { distanceKm: distKm, ageSec: ageSec };
        }
      }
      if (closestClose) {
        lightningProximity = { miles: Math.round(closestClose.distanceKm / 1.609344) };
      }
    }

    var nextHighTideAbove95 = undefined;
    var events = tideRoot.events_hilo || [];
    var now = new Date();
    var in24h = new Date(now.getTime() + 24 * 60 * 60 * 1000);
    for (var ti = 0; ti < events.length; ti++) {
      var ev = events[ti];
      if (ev.type !== "H") continue;
      var h = num(ev.height_ft);
      if (h == null || h <= MRW_THRESHOLDS.tideHeightFt) continue;
      var t = parseTideLocal(ev.t_local || "");
      if (isNaN(t.getTime())) continue;
      if (t >= now && t <= in24h) {
        nextHighTideAbove95 = { time: fmtTideTime(t), heightFt: h };
        break;
      }
    }

    var mrwConditions = [];
    function pushCond(c) {
      mrwConditions.push(c);
    }

    if (airPm25 != null && airPm25 >= MRW_THRESHOLDS.airPm25) {
      pushCond({ type: "AIR", label: "Air quality", value: "PM2.5 " + airPm25 + " µg/m³" });
    }
    if (lightningProximity) {
      pushCond({
        type: "LIGHTNING",
        label: "Lightning Proximity Alert",
        value: lightningProximity.miles + " mi from MRW",
        severity: 4,
      });
    }
    var windWindy =
      (windAvg10 != null && windAvg10 >= MRW_THRESHOLDS.windAvg10) ||
      (windGustPeak != null && windGustPeak >= MRW_THRESHOLDS.windGustMin) ||
      (windSpeedNow != null && windSpeedNow >= MRW_THRESHOLDS.windAvg10);
    if (windWindy) {
      var wsev = 1;
      var g = windGustPeak;
      var a = windAvg10;
      if (g != null && g >= MRW_THRESHOLDS.windGustRed) wsev = 4;
      else if (g != null && g >= MRW_THRESHOLDS.windGustYellow) wsev = 2;
      else if (g != null && g >= MRW_THRESHOLDS.windGustMin) wsev = 2;
      else if (a != null && a >= MRW_THRESHOLDS.windGustRed) wsev = 4;
      else if (a != null && a >= MRW_THRESHOLDS.windGustYellow) wsev = 2;
      else if (windSpeedNow != null && windSpeedNow >= MRW_THRESHOLDS.windGustYellow) wsev = 2;
      else if (windSpeedNow != null && windSpeedNow >= MRW_THRESHOLDS.windAvg10) wsev = 1;
      else wsev = 1;

      var windVal;
      if (g != null && g >= MRW_THRESHOLDS.windGustMin) {
        windVal = Math.round(g) + " mph gusts";
      } else if (a != null) {
        windVal = Math.round(a) + " mph avg (10m)";
      } else if (windSpeedNow != null) {
        windVal = Math.round(windSpeedNow) + " mph sustained";
      } else {
        windVal = Math.round(g || 0) + " mph";
      }
      pushCond({ type: "WIND", label: "Wind", value: windVal, severity: wsev });
    }
    if (rainRate != null && rainRate >= MRW_THRESHOLDS.rainRate) {
      pushCond({ type: "RAIN", label: "Rain", value: rainRate.toFixed(2) + " in/hr" });
    }
    if (heatIndex != null && heatIndex >= MRW_THRESHOLDS.heatIndexYellow) {
      var hsev = heatIndex >= MRW_THRESHOLDS.heatIndexRed ? 4 : 2;
      pushCond({ type: "HEAT", label: "Heat", value: "Heat index " + heatIndex + "°F", severity: hsev });
    }
    if (windChill != null && windChill <= MRW_THRESHOLDS.windChillYellow) {
      var csev = windChill < MRW_THRESHOLDS.windChillRed ? 4 : 2;
      pushCond({ type: "COLD", label: "Cold", value: "Wind chill " + windChill + "°F", severity: csev });
    }
    if (temp != null) {
      if (temp > MRW_THRESHOLDS.tempHighYellow) {
        var tsHi = temp >= MRW_THRESHOLDS.tempHighRed ? 4 : 2;
        pushCond({ type: "TEMP", label: "High temp", value: temp + "°F", severity: tsHi });
      } else if (temp < MRW_THRESHOLDS.tempLowYellow) {
        var tsLo = temp < MRW_THRESHOLDS.tempLowRed ? 4 : 2;
        pushCond({ type: "TEMP", label: "Low temp", value: temp + "°F", severity: tsLo });
      }
    }
    if (thsw != null) {
      if (thsw > MRW_THRESHOLDS.thswHighYellow) {
        var apHi = thsw >= MRW_THRESHOLDS.thswHighRed ? 4 : 2;
        pushCond({ type: "APPARENT", label: "Apparent (THSW)", value: thsw + "°F", severity: apHi });
      } else if (thsw < MRW_THRESHOLDS.thswLowYellow) {
        var apLo = thsw < MRW_THRESHOLDS.thswLowRed ? 4 : 2;
        pushCond({ type: "APPARENT", label: "Apparent (THSW)", value: thsw + "°F", severity: apLo });
      }
    }
    if (uvIndex != null && uvIndex >= MRW_THRESHOLDS.uvIndex) {
      pushCond({ type: "UV", label: "UV", value: "Index " + uvIndex });
    }
    if (nextHighTideAbove95) {
      pushCond({
        type: "TIDE",
        label: "High tide",
        value: nextHighTideAbove95.heightFt.toFixed(1) + " ft at " + nextHighTideAbove95.time,
      });
    }

    mrwConditions.sort(function (a, b) {
      var sevA = a.severity != null ? a.severity : 0;
      var sevB = b.severity != null ? b.severity : 0;
      if (sevB !== sevA) return sevB - sevA;
      return COND_ORDER.indexOf(a.type) - COND_ORDER.indexOf(b.type);
    });

    var nwsLines =
      sortedNws.length > 0
        ? sortedNws.slice(0, 3).map(function (a) {
            var exp = formatExpires(a.expires);
            var text = exp ? a.event + " until " + exp : a.event;
            return { text: text, severity: nwsDisplaySeverityRank(a) };
          })
        : [];

    var mrwLines =
      mrwConditions.length > 0
        ? mrwConditions.slice(0, 3).map(function (c) {
            return c.label + ": " + c.value;
          })
        : [];

    var severity = 0;
    if (sortedNws.length > 0) {
      severity = Math.max(severity, nwsDisplaySeverityRank(sortedNws[0]));
    }
    if (mrwConditions.length > 0) severity = Math.max(severity, 1);
    for (var ci = 0; ci < mrwConditions.length; ci++) {
      if (mrwConditions[ci].severity) severity = Math.max(severity, mrwConditions[ci].severity);
    }
    if (lightningProximity) severity = Math.max(severity, 4);

    var titleAlertType = "default";
    var hasWarning = sortedNws.some(function (a) {
      var ev = a.event.toLowerCase();
      return (
        ev.indexOf("tornado warning") !== -1 ||
        ev.indexOf("severe thunderstorm warning") !== -1 ||
        ev.indexOf("thunderstorm warning") !== -1
      );
    });
    var hasWatch = sortedNws.some(function (a) {
      var ev = a.event.toLowerCase();
      return (
        ev.indexOf("tornado watch") !== -1 ||
        ev.indexOf("severe thunderstorm watch") !== -1 ||
        ev.indexOf("thunderstorm watch") !== -1
      );
    });
    if (hasWarning) titleAlertType = "flash-red";
    else if (hasWatch) titleAlertType = "yellow";

    return {
      nwsLines: nwsLines,
      mrwLines: mrwLines,
      severity: severity,
      hasLightningAlert: !!lightningProximity,
      titleAlertType: titleAlertType,
    };
  }

  function setDotsSeverity(sev) {
    var dots = $("threat_dots");
    if (!dots) return;
    dots.innerHTML =
      '<span class="threatDot"></span><span class="threatDot" style="animation-delay:0.2s"></span><span class="threatDot" style="animation-delay:0.4s"></span>';
    var color = "#94a3b8";
    if (sev >= 4) color = "#dc2626";
    else if (sev >= 3) color = "#d97706";
    else if (sev >= 1) color = "#eab308";
    var spans = dots.querySelectorAll(".threatDot");
    for (var i = 0; i < spans.length; i++) {
      spans[i].style.background = color;
    }
  }

  function renderPayload(data, status) {
    var bar = $("threat_bar");
    var titleEl = $("threat_title");
    var linesEl = $("threat_lines");
    var dots = $("threat_dots");
    if (!linesEl || !bar || !titleEl) return;

    titleEl.textContent = "Weather Alerts";
    titleEl.className = "threatHeading";
    if (data && (data.titleAlertType === "flash-red" || data.hasLightningAlert)) {
      titleEl.classList.add("threatHeading--flash-red");
    } else if (data && data.titleAlertType === "yellow") {
      titleEl.classList.add("threatHeading--yellow");
    } else {
      titleEl.classList.add("threatHeading--default");
    }

    bar.className = "threatBar";
    var sev = data ? data.severity : 0;
    if (sev >= 4) bar.classList.add("threatBar--sev4");
    else if (sev >= 3) bar.classList.add("threatBar--sev3");
    else if (sev >= 2) bar.classList.add("threatBar--sev2");
    else if (sev >= 1) bar.classList.add("threatBar--sev1");

    linesEl.innerHTML = "";

    var hasNws = data && data.nwsLines && data.nwsLines.length > 0;
    var hasLocal = data && data.mrwLines && data.mrwLines.length > 0;
    var noAlerts = status === "success" && data && !hasNws && !hasLocal;

    if (dots) {
      dots.style.display = noAlerts || status === "loading" ? "none" : "flex";
    }

    if (status === "loading" && !data) {
      setDotsSeverity(0);
      var ld = document.createElement("div");
      ld.className = "threatLine";
      ld.textContent = "Loading…";
      linesEl.appendChild(ld);
      return;
    }

    if (status === "error" && !data) {
      var er = document.createElement("div");
      er.className = "threatLine threatLine--warn";
      er.textContent = "Temporarily unavailable";
      linesEl.appendChild(er);
      if (dots) dots.style.display = "none";
      return;
    }

    if (noAlerts) {
      var ac = document.createElement("div");
      ac.className = "threatLine threatLine--allClear";
      ac.textContent = "All Clear";
      linesEl.appendChild(ac);
      return;
    }

    setDotsSeverity(sev);

    if (hasNws) {
      for (var i = 0; i < data.nwsLines.length; i++) {
        var item = data.nwsLines[i];
        var row = document.createElement("div");
        row.className = "threatLine";
        if (item.severity >= 4) row.classList.add("threatLine--nws4");
        else if (item.severity >= 3) row.classList.add("threatLine--nws3");
        else if (item.severity >= 2) row.classList.add("threatLine--nws2");
        else row.classList.add("threatLine--nws0");
        row.textContent = item.text;
        linesEl.appendChild(row);
      }
    }
    if (hasLocal) {
      for (var j = 0; j < data.mrwLines.length; j++) {
        var line = data.mrwLines[j];
        var row2 = document.createElement("div");
        var isLightning = line.indexOf("Lightning Proximity Alert") === 0;
        row2.className = "threatLine " + (isLightning ? "threatLine--mrwLightning" : "threatLine--mrw");
        row2.textContent = "Moon River: " + line;
        linesEl.appendChild(row2);
      }
    } else if (hasNws) {
      var row3 = document.createElement("div");
      row3.className = "threatLine threatLine--mrw";
      row3.textContent = "Moon River: All clear";
      linesEl.appendChild(row3);
    }
  }

  var lastPayload = null;
  var lastStatus = "loading";
  var barCycleTick = 0;
  var barCycleTimer = null;
  var reduceMotion = false;

  function applyBarFlashClass() {
    var bar = $("threat_bar");
    if (!bar || !lastPayload || lastStatus !== "success") return;
    var titleType = lastPayload.titleAlertType || "default";
    var shouldCycle =
      Boolean(lastPayload.hasLightningAlert) || titleType === "flash-red";
    if (!shouldCycle || reduceMotion) {
      bar.classList.remove("threatBar--pulseOn");
      if (reduceMotion && shouldCycle) bar.classList.add("threatBar--pulseReduced");
      else bar.classList.remove("threatBar--pulseReduced");
      return;
    }
    var phase = barCycleTick % BAR_CYCLE_LEN;
    var pulseOn = phase < 5 && phase % 2 === 0;
    bar.classList.toggle("threatBar--pulseOn", pulseOn);
    bar.classList.remove("threatBar--pulseReduced");
  }

  async function loadOnce() {
    var base = DATA_BASE + "/data/";
    var nwsData = await fetchNwsAlerts();
    var airJson = await fetchMaybe(base + "air.json");
    var windJson = await fetchMaybe(base + "wind.json");
    var rainJson = await fetchMaybe(base + "rain.json");
    var computedJson = await fetchMaybe(base + "computed_rt.json");
    var nowJson = await fetchMaybe(base + "now.json");
    var lightningJson = await fetchMaybe(LIGHTNING_URL);
    var tideJson = await fetchMaybe(base + "tide.json");

    var piMissing =
      !airJson && !windJson && !rainJson && !computedJson && !nowJson && !tideJson;
    if (!nwsData && piMissing) {
      lastStatus = "error";
      if (!lastPayload) renderPayload(null, "error");
      applyBarFlashClass();
      return;
    }

    var payload = buildAlertsPayload(
      nwsData,
      airJson,
      windJson,
      rainJson,
      computedJson,
      nowJson,
      lightningJson,
      tideJson
    );
    lastPayload = payload;
    lastStatus = "success";
    renderPayload(payload, "success");
    applyBarFlashClass();
  }

  function start() {
    var mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    reduceMotion = mq.matches;
    if (mq.addEventListener) {
      mq.addEventListener("change", function () {
        reduceMotion = mq.matches;
        applyBarFlashClass();
      });
    } else if (mq.addListener) {
      mq.addListener(function () {
        reduceMotion = mq.matches;
        applyBarFlashClass();
      });
    }

    renderPayload(null, "loading");

    loadOnce().catch(function () {
      lastStatus = "error";
      if (!lastPayload) renderPayload(null, "error");
      applyBarFlashClass();
    });

    setInterval(function () {
      loadOnce().catch(function () {});
    }, REFRESH_MS);

    barCycleTimer = setInterval(function () {
      barCycleTick = (barCycleTick + 1) % BAR_CYCLE_LEN;
      applyBarFlashClass();
    }, 1000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
