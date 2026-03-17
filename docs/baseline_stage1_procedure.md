# Stage 1 Baseline Procedure

**Goal:** Sanity baseline using ~20–30 production runs. Verify metrics look sane before Stage 2.

**Prerequisites:** Instrumentation deployed. MRMS and coordinator running via launchd on weather-core.

---

## 1. Wait for production runs

**Wait time:** 50 minutes

At 2-min cadence, 50 min yields ~25 MRMS runs and ~25 coordinator runs.

---

## 2. Capture log slices

Run on **weather-core**:

```bash
tail -n 500 /tmp/mrms_loop_launchd.log > /tmp/mrms_stage1.log
tail -n 800 /tmp/radar_coordinator_launchd.log > /tmp/coord_stage1.log
```

**Tail sizes:**
- MRMS: 500 lines (~25 runs)
- Coordinator: 800 lines (~25 runs)

---

## 3. Run the report

```bash
cd /Users/scott/wx/radar-foundry
python3 bin/baseline_report.py /tmp/mrms_stage1.log /tmp/coord_stage1.log
```

---

## 4. Review checklist (before sending to ChatGPT)

- [ ] **MRMS count_runs** ≥ 15
- [ ] **count_add_runs + count_skip_runs** = count_runs
- [ ] **add_duration_sec avg** between 30–120 s (not &lt;10 or &gt;300)
- [ ] **skip_duration_sec avg** between 1–15 s (not &gt;30)
- [ ] **freshness_latency_sec avg** between 60–300 s (not negative or &gt;600)
- [ ] **COORD count_runs** ≥ 15
- [ ] **COORD duration_sec avg** between 10–180 s (not &lt;5 or &gt;300)
- [ ] **RADAR KCLX and KJAX** each have ≥10 samples
- [ ] **RADAR duration_sec avg** between 3–120 s per site
- [ ] No empty or negative values in any metric

**If any check fails:** Investigate before proceeding. Do not send to ChatGPT until all pass.

---

## 5. Report format for ChatGPT

Paste the report output with this header:

```
## MRW Stage 1 Sanity Baseline
**Type:** Stage 1 (~25 runs)
**Source:** tail -500 mrms, tail -800 coord
**MRMS sample:** [count_runs from output] runs | **Coordinator sample:** [count_runs from output] runs

[paste full baseline_report.py output]
```
