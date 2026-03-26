/* A9P_HEADER_JS_V2 — render-only header: 12h time/date/sunrise/sunset + update dot */
(function(){
  const POLL_MS = 2500;

  function $(id){ return document.getElementById(id); }
  function setText(id, v){
    const el = $(id);
    if (!el) return;
    if (v === undefined || v === null) return;
    const t = String(v);
    if (!t || t === "null" || t === "undefined") return;
    el.textContent = t;
  }

  function setUpdDot(state){
    const el = $("hdr_upd_dot");
    if (!el) return;
    el.classList.remove("updG","updY","updR","updPulse");
    if (state === "OK"){
      el.classList.add("updG","updPulse");   // pulsing green = alive
    } else if (state === "STALE"){
      el.classList.add("updR");              // solid red = stale
    } else {
      el.classList.add("updY","updPulse");   // pulsing yellow = uncertain/error
    }
  }

  async function fetchJSON(url){
    const r = await fetch(url, {cache:"no-store"});
    if (!r.ok) throw new Error(url + " " + r.status);
    return await r.json();
  }

  function fmtTime12(d){
    try{
      return d.toLocaleTimeString([], {hour: "numeric", minute: "2-digit", hour12: true});
    }catch(e){
      let h=d.getHours(), m=d.getMinutes();
      const ap = (h>=12) ? "PM" : "AM";
      h = h%12; if(h===0) h=12;
      return h + ":" + (m<10?"0":"")+m + " " + ap;
    }
  }
  function fmtDateLong(d){
    try{
      return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
    }catch(e){
      return (d.getMonth()+1) + "/" + d.getDate();
    }
  }

  async function poll(){
    // Always update local clock so header never feels frozen
    const now = new Date();
    setText("hdr_time", fmtTime12(now));
    setText("hdr_date", fmtDateLong(now));

    // Sunrise/Sunset from astro.json
    try{
      const aj = await fetchJSON("/data/astro.json?ts=" + Date.now());
      const a = aj && aj.astro ? aj.astro : {};
      if (a.sunrise_str) setText("hdr_sunrise", "Sunrise " + a.sunrise_str);
      if (a.sunset_str)  setText("hdr_sunset",  "Sunset "  + a.sunset_str);
    }catch(e2){
      // sticky
    }

    // Update dot from status_rt.json
    try{
      const sj = await fetchJSON("/data/status_rt.json?ts=" + Date.now());
      const overall = sj && sj.overall ? sj.overall : {};
      const stale = !!overall.is_stale;
      if (stale) setUpdDot("STALE");
      else setUpdDot("OK");
    }catch(e3){
      setUpdDot("WARN");
    }
  }

  setInterval(poll, POLL_MS);
  poll();
})();
