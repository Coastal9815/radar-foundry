/* A9P_TIDE_JSONLY_V1 — Tide wiring (ported from Galaxy14). External JS to avoid editing main HTML. */
(function(){
  if (typeof window.setTextSticky !== "function"){
    window.setTextSticky = function(id, txt){
      try{
        const el = document.getElementById(id);
        if(!el) return;
        const v = String(txt);
        if(el.textContent !== v) el.textContent = v;
      }catch(e){}
    };
  }

  function _fmtHM(total_minutes){
    const hh = Math.floor(total_minutes / 60);
    const mm = total_minutes % 60;
    return hh + ":" + String(mm).padStart(2, "0");
  }

  function _fmtTime12(d){
    if (!d || isNaN(d.getTime())) return "--:--";
    const h = d.getHours();
    const m = String(d.getMinutes()).padStart(2,"0");
    const ap = (h >= 12 ? "pm" : "am");
    const hh = ((h % 12) || 12);
    return hh + ":" + m + ap;
  }

  function parseLocal(ts){
    return new Date(ts.replace(" ", "T"));
  }

  async function refreshTide(){
    try{
      const r = await fetch("/data/tide.json?ts=" + Date.now(), { cache: "no-store" });
      if(!r.ok) throw new Error("HTTP " + r.status);
      const j = await r.json();
      const t = j.tide || {};
      const ev = (t.events_hilo || []).slice();
      if(ev.length < 2) return;

      const now = new Date();

      let prev_i = -1;
      let next_i = -1;
      for(let i=0;i<ev.length;i++){
        const dt = parseLocal(ev[i].t_local);
        if(dt <= now) prev_i = i;
        if(dt > now && next_i < 0){ next_i = i; break; }
      }
      let prev, next, t0, t1;
      if(prev_i < 0 && next_i >= 0){
        const t1c = parseLocal(ev[next_i].t_local);
        const dayMs = 24 * 60 * 60 * 1000;
        let bestPrev = null, bestT0 = null;
        for(let i=0;i<ev.length;i++){
          const dt = parseLocal(ev[i].t_local);
          const t0c = new Date(dt.getTime() - dayMs);
          if(t0c < now && t0c < t1c && (!bestT0 || t0c > bestT0)){
            bestPrev = ev[i];
            bestT0 = t0c;
          }
        }
        if(!bestPrev || !bestT0) return;
        prev = bestPrev;
        next = ev[next_i];
        t0 = bestT0;
        t1 = t1c;
      } else if(prev_i >= 0 && next_i >= 0){
        prev = ev[prev_i];
        next = ev[next_i];
        t0 = parseLocal(prev.t_local);
        t1 = parseLocal(next.t_local);
      } else {
        return;
      }

      const h0 = Number(prev.height_ft);
      const h1 = Number(next.height_ft);
      if(!isFinite(h0) || !isFinite(h1)) return;

      const span = (t1 - t0);
      if(!(span > 0)) return;

      let u = (now - t0) / span;
      if(u < 0) u = 0;
      if(u > 1) u = 1;

      const height = h0 + (h1 - h0) * 0.5 * (1 - Math.cos(Math.PI * u));
      setTextSticky("tide_main_txt", height.toFixed(1));

      const msLeft = Math.max(0, t1 - now);
      const minsLeft = Math.round(msLeft / 60000);
      const hhLeft = Math.floor(minsLeft / 60);
      const mmLeft = minsLeft % 60;
      const dur = hhLeft + ":" + String(mmLeft).padStart(2,"0");

      const type = (next.type === "H") ? "High" : "Low";

      setTextSticky("tide_next_lbl", "Next " + type);
      setTextSticky("tide_next_time", _fmtTime12(t1));
      setTextSticky("tide_next_ht", h1.toFixed(1) + "\x27");

      const next2 = (next_i + 1 < ev.length) ? ev[next_i + 1] : null;
      if(next2){
        const t2 = parseLocal(next2.t_local);
        const h2 = Number(next2.height_ft);
        const type2 = (next2.type === "H") ? "High" : "Low";
        setTextSticky("tide_next2_lbl", "Next " + type2);
        setTextSticky("tide_next2_time", _fmtTime12(t2));
        setTextSticky("tide_next2_ht", (isFinite(h2) ? h2.toFixed(1) : "--") + "\x27");

        if(isFinite(h2)){
          const rng = Math.abs(h2 - h1);
          setTextSticky("tide_range_val", rng.toFixed(1) + "\x27");
        } else {
          setTextSticky("tide_range_val", "--.-\x27");
        }
      } else {
        setTextSticky("tide_next2_lbl", "Next");
        setTextSticky("tide_next2_time", "--:--");
        setTextSticky("tide_next2_ht", "--");
        setTextSticky("tide_range_val", "--.-\x27");
      }
      setTextSticky("tide_range_lbl", "Range");
      setTextSticky("tide_range_sub", "");

      const minsSince = Math.round(Math.max(0, now - t0) / 60000);
      const prevType = (prev.type === "H") ? "High" : "Low";
      setTextSticky("tide_since_lbl", "Since " + prevType);
      setTextSticky("tide_since_val", _fmtHM(minsSince));
      setTextSticky("tide_since_sub", "");

      setTextSticky("tide_time_line", dur);
      setTextSticky("tide_to_line", "To " + type);

      const rising = (prev.type === "L" && next.type === "H");
      setTextSticky("tide_state_txt", rising ? "Rising" : "Falling");
      let ang = 0;
      if(rising){
        ang = 180 + 180 * u;
        if(ang >= 360) ang -= 360;
      } else {
        ang = 180 * u;
      }

      const hand = document.getElementById("tide_hand");
      if(hand) hand.setAttribute("transform", "rotate(" + ang.toFixed(2) + " 180 180)");
    }catch(e){
      // silent by design
    }
  }

  setInterval(refreshTide, 3000);
  refreshTide();
})();
