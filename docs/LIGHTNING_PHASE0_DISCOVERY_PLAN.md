# MRW Lightning — Phase 0 Discovery Plan

**Status:** Pre-implementation discovery only. No parser code. No ingestion code.

**Purpose:** Resolve all unknowns required before implementing the .nex parser. Phase 0 must complete successfully before Phase 1 (parser implementation) begins.

**Constraint:** Lightning-PC is strictly read-only. We pull via scp only. No installs, no background jobs, no modifications to NexStorm files. Discovery tasks that require running software on Lightning-PC must be one-off, read-only operations (e.g. listing directories, copying files out). nxutil runs on a Windows machine with access to a .nex file — either Lightning-PC (if nxutil is present and we run a one-off) or a Windows dev box with a copied .nex.

---

## 1. Phase 0 Objectives

1. Confirm the exact .nex file location on Lightning-PC.
2. Confirm how NexStorm rolls over daily files.
3. Confirm that files are truly append-only.
4. Confirm nxutil location and command syntax.
5. Use nxutil on a sample .nex to generate CSV for format discovery.
6. Determine from evidence: 16-byte record layout, timestamp encoding, endianness, bearing field, distance field, strike-type/polarity (if present).
7. Define the minimum sample set for validation.
8. Define the exact evidence required before parser implementation (Go/No-Go criteria).

---

## 2. Discovery Tasks (In Order)

### Task 1: Confirm .nex File Location on Lightning-PC

**Goal:** Verify where NexStorm writes daily .nex files.

**Steps:**
1. SSH to Lightning-PC (or use existing scp/ssh access).
2. List `C:\Program Files (x86)\Astrogenic\NexStormLite\` (or `NexStorm` if Full version).
3. Confirm presence of `YYYYMMDD.nex` files. Note exact path format (forward vs backslash, spaces).
4. Check for alternate locations: NexStorm config, registry, or user AppData. Document any config that specifies archive path.
5. If NexStorm Lite uses a different base path, document it. lightning_inspect_nex.py currently assumes `C:/Program Files (x86)/Astrogenic/NexStormLite`.

**Output:** Documented path(s). Single canonical path for scp pull.

---

### Task 2: Confirm NexStorm Daily File Rollover

**Goal:** Understand when and how a new daily file is created.

**Steps:**
1. Note Lightning-PC timezone (likely America/New_York).
2. On a day with lightning activity, pull the same date's .nex at two times: before midnight and after midnight (local).
3. Compare: does yesterday's file stop growing? Does today's file appear at midnight local?
4. Check file creation timestamps: when was `YYYYMMDD.nex` created? At 00:00:00 local?
5. Document: rollover time (midnight local? UTC?), whether old file is closed or still appended, any overlap.

**Output:** Rollover behavior documented. Critical for incremental ingest (when to switch files).

---

### Task 3: Confirm Append-Only Behavior

**Goal:** Re-validate that .nex files are append-only (no mid-file edits).

**Steps:**
1. Pull the same day's .nex twice, ~5–10 minutes apart (during active lightning if possible).
2. Use `lightning_inspect_nex.py --diff` to compare the two files.
3. Confirm: common prefix equals length of first file; second file has only additional bytes at end.
4. If any mid-file differences appear, document. Append-only is a Phase 1 assumption.

**Output:** Written confirmation: append-only verified, or exception documented.

---

### Task 4: Confirm nxutil Location and Command Syntax

**Goal:** Find nxutil and learn how to run it for CSV export.

**Steps:**
1. Check if nxutil exists in NexStorm install: `C:\Program Files (x86)\Astrogenic\NexStormLite\util\` or similar. WXForum indicates it is "included with NexStorm in the util directory."
2. If not present, download nxutil_v1.1.zip from Astrogenic downloads. Extract to a known location.
3. Run nxutil with help flags: `nxutil.exe -?`, `nxutil.exe /?`, `nxutil.exe --help`, or `nxutil.exe` with no args. Document all output.
4. Identify: input file argument, output file argument, CSV export option (if explicit), any repair/extract mode flags.
5. Document exact command syntax to produce CSV from a .nex file.

**Output:** nxutil path, full command syntax, example invocation.

---

### Task 5: Run nxutil on Sample .nex to Generate CSV

**Goal:** Obtain CSV output for format discovery.

**Steps:**
1. Obtain a .nex file: pull from Lightning-PC via `lightning_inspect_nex.py --pull` (or scp) to wx-core. Copy to a Windows machine that will run nxutil (or run nxutil on Lightning-PC if it has nxutil and we can write CSV to a location we can retrieve).
2. Run nxutil with documented syntax. Produce CSV.
3. Copy CSV to wx-core (e.g. `scratch/lightning_nex/samples/` or `scratch/lightning_nex/nxutil_output/`).
4. Verify CSV: has header row, has data rows, columns are readable.
5. Record: source .nex filename, nxutil version, CSV row count. Ensure CSV row count is plausible (same order of magnitude as expected record count: (file_size - 512) / 16).

**Output:** CSV file in project scratch. Metadata: source .nex, nxutil version, row count.

---

### Task 6: Determine Format from nxutil CSV

**Goal:** Infer 16-byte record layout and field encodings from CSV.

**Steps:**
1. Inspect CSV header: column names. Map to expected fields: timestamp, distance, bearing, type, polarity, etc.
2. Inspect sample rows: data types (integer, float, datetime string).
3. Timestamp: What format does nxutil use? (e.g. `YYYY-MM-DD HH:MM:SS`, Unix epoch, ISO 8601). Timezone?
4. Distance: Column name, units (miles?), range in sample (0–300?).
5. Bearing: Column name, units (degrees 0–360?), range in sample.
6. Strike type / polarity: Present or absent? Column names?
7. Cross-check: Pick 2–3 CSV rows. Manually compute expected byte values for those strikes. Read the corresponding 16-byte records from the .nex file (at offset 512 + row_index * 16). Compare. This validates our interpretation of the layout.
8. Document: byte layout (offsets 0–15), field types, endianness. Produce a layout spec.

**Output:** Format specification document: 16-byte layout, timestamp encoding, endianness, field mapping.

---

### Task 7: Define Minimum Sample Set for Validation

**Goal:** Specify what .nex samples we need to validate the parser.

**Required samples:**
1. **Active day** — One .nex from a day with known lightning activity. Multiple strikes. Used for: full parse test, geo sanity check.
2. **Same-day diff pair** — Two pulls of the same day, minutes apart. Used for: append-only re-check, incremental overlap test (later).
3. **nxutil CSV pair** — The .nex used for Task 5 + its nxutil CSV. Used for: parser output vs nxutil row-by-row comparison.
4. **Edge cases (if available)** — Empty or near-empty file; file spanning rollover. Optional for Phase 1.

**Output:** List of required samples. Checklist: which we have, which we need to collect.

---

### Task 8: Define Go/No-Go Evidence for Parser Implementation

**Goal:** Explicit criteria that must be met before writing the parser.

See Section 5 below.

---

## 3. Required Artifacts to Collect

| Artifact | Source | Purpose |
|----------|--------|---------|
| **.nex path confirmation** | Task 1 | scp pull path |
| **Rollover behavior doc** | Task 2 | Incremental ingest design |
| **Append-only confirmation** | Task 3 | Parser assumptions |
| **nxutil command spec** | Task 4 | Reproducible CSV export |
| **nxutil CSV** | Task 5 | Format discovery |
| **16-byte layout spec** | Task 6 | Parser implementation |
| **Sample set checklist** | Task 7 | Validation readiness |
| **Format spec document** | Task 6 | Canonical reference for parser |

**Storage:**
- `scratch/lightning_nex/` — pulled .nex files
- `scratch/lightning_nex/samples/` — timestamped snapshots, nxutil CSV
- `docs/` — layout spec, rollover doc, Phase 0 findings (this plan + addendum)

---

## 4. Questions to Answer

### 4.1 Location and Access

| # | Question | Answered By |
|---|----------|-------------|
| Q1 | Exact .nex directory path on Lightning-PC? | Task 1 |
| Q2 | NexStorm Lite vs Full — same path? | Task 1 |
| Q3 | Can we scp using the documented path? | Task 1 (verify with test pull) |

### 4.2 File Behavior

| # | Question | Answered By |
|---|----------|-------------|
| Q4 | When does NexStorm create new daily file? (Midnight local? UTC?) | Task 2 |
| Q5 | Does yesterday's file stop growing at rollover? | Task 2 |
| Q6 | Are files strictly append-only? (No mid-file changes?) | Task 3 |

### 4.3 nxutil

| # | Question | Answered By |
|---|----------|-------------|
| Q7 | Where is nxutil? (NexStorm util dir? Separate install?) | Task 4 |
| Q8 | Exact command to export .nex to CSV? | Task 4 |
| Q9 | Does nxutil CSV row count match (size - header) / 16? | Task 5 |

### 4.4 Format

| # | Question | Answered By |
|---|----------|-------------|
| Q10 | 16-byte layout: which bytes are timestamp, distance, bearing? | Task 6 |
| Q11 | Timestamp encoding? (Unix, FILETIME, BCD, custom?) | Task 6 |
| Q12 | Endianness? (Little-endian assumed for Windows) | Task 6 |
| Q13 | Distance field: offset, type (int/float), units? | Task 6 |
| Q14 | Bearing field: offset, type, units? | Task 6 |
| Q15 | Strike type (CG/IC) or polarity in record? | Task 6 |
| Q16 | Header size: 512 bytes confirmed? | Task 6 (cross-check) |

---

## 5. Go / No-Go Criteria for Parser Implementation

**Do NOT begin Phase 1 (parser implementation) until ALL of the following are true.**

### 5.1 Location and Access — GO

- [ ] **NEX_PATH** — Exact .nex path on Lightning-PC documented and verified with successful scp pull.
- [ ] **PULL_TEST** — At least one .nex file successfully pulled to wx-core scratch.

### 5.2 File Behavior — GO

- [ ] **APPEND_ONLY** — Append-only behavior confirmed via diff of two same-day pulls.
- [ ] **ROLLOVER** — Rollover behavior documented (when new file appears; when old stops). Can be approximate for Phase 1 (full-file parse only).

### 5.3 nxutil and CSV — GO

- [ ] **NXUTIL_CMD** — nxutil command syntax documented. Reproducible CSV export possible.
- [ ] **NXUTIL_CSV** — At least one nxutil CSV obtained for a .nex file we have.
- [ ] **CSV_PLausible** — CSV row count is plausible: within 10% of `(file_size - 512) / 16` (or determined header size).

### 5.4 Format Specification — GO

- [ ] **LAYOUT_SPEC** — 16-byte record layout documented: byte offsets for timestamp, distance, bearing.
- [ ] **TIMESTAMP_SPEC** — Timestamp encoding identified. Conversion to UTC documented.
- [ ] **ENDIANNESS** — Endianness confirmed (little-endian or documented otherwise).
- [ ] **CROSS_CHECK** — At least one CSV row cross-checked against raw bytes in .nex. Interpretation validated.

### 5.5 Sample Set — GO

- [ ] **SAMPLE_ACTIVE** — At least one .nex from a day with lightning activity available.
- [ ] **SAMPLE_NXUTIL** — The .nex used for nxutil CSV is retained for parser validation.

### 5.6 No-Go Conditions

If any of the following occur, **stop** and reassess before parser work:

- nxutil cannot produce CSV, or CSV structure is unusable.
- Cross-check fails: our interpretation of bytes does not match nxutil CSV values.
- Append-only is violated (mid-file differences observed).
- .nex path is inaccessible or incorrect and cannot be resolved.
- Format is variable-length or otherwise incompatible with fixed 16-byte assumption.

---

## 6. Phase 0 Completion Checklist

Before declaring Phase 0 complete and proceeding to Phase 1:

1. [ ] All discovery tasks (1–8) completed.
2. [ ] All required artifacts collected and stored.
3. [ ] All questions in Section 4 answered (or explicitly deferred with rationale).
4. [ ] All Go criteria in Section 5 satisfied.
5. [ ] Format specification document written and committed to docs/.
6. [ ] Phase 1 Implementation Plan updated with the resolved layout (or addendum created).

---

## 7. References

- [lightning_pipeline_plan.md](lightning_pipeline_plan.md) — Phase 1 discovery results, .nex structure
- [LIGHTNING_PHASE1_IMPLEMENTATION_PLAN.md](LIGHTNING_PHASE1_IMPLEMENTATION_PLAN.md) — Parser implementation plan (blocked until Phase 0 complete)
- [WXForum: NexStorm Archive Files](https://www.wxforum.net/index.php?topic=691.0) — nxutil in util dir
- [Astrogenic Downloads](https://www.astrogenic.com/?p=downloads) — nxutil_v1.1.zip
- `bin/lightning_inspect_nex.py` — Pull, diff, inspect

---

*Document created 2026-03-14. Phase 0 discovery plan only — no parser, no implementation.*
