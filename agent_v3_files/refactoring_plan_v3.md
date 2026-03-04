# BSM Aeration Experiment — Refactoring Plan v3

**Scope:** Add weekly reduction-day patterns, midnight-wrapping support, active-day-only aeration energy averaging, and propagate the new parameters through the full pipeline.

**Affected files:** `generate_KLa_timeseries.m`, `generate_test_cases.m` (minor), `main_sim.m`, `run_campaign.m`, `effluent_data_writer.m`

**Key architectural decision:** The `reduction_days` pattern is a **campaign-level** parameter, not an experimental factor. Each `run_campaign` invocation specifies a single pattern (e.g., `[1 3 5]`). The 60-experiment grid (`5 × 4 × 3`) remains unchanged. Testing different patterns requires separate `run_campaign` invocations.

---

## 1. New Parameter: `reduction_days`

A row vector of integers from 1–7 representing which days of a 7-day week receive the reduction window. The pattern repeats every 7 days across the full `sim_days` duration.

| Value | Meaning | Active days (14-day sim) |
|-------|---------|--------------------------|
| `[1]` | Weekly, day 1 only | 1, 8 |
| `[1 3 5]` | Mon/Wed/Fri pattern | 1, 3, 5, 8, 10, 12 |
| `[1 2 3 4 5 6 7]` | Daily (current behavior) | 1–14 |
| `[6 7]` | Weekend-only | 6, 7, 13, 14 |

**Convention:** Day indexing is 1-based and aligns with `sim_days` day numbering (day 1 = first simulated day = time 0–1). The mapping from simulation day `d` (1-based) to active status is:

```matlab
week_day = mod(d - 1, 7) + 1;   % maps day 1→1, day 8→1, day 7→7, day 14→7
is_active = ismember(week_day, reduction_days);
```

---

## 2. Changes by File

### 2.1 `generate_KLa_timeseries.m`

**A. New parameter — `reduction_days`**

Add a 6th positional argument after `sim_days`:

```matlab
function KLa_ts = generate_KLa_timeseries(nominal_KLa, reduction_frac, ...
    duration_hrs, start_hour, sim_days, reduction_days)
```

Default value (backward-compatible): `[1 2 3 4 5 6 7]` (daily — preserves current behavior for all existing callers).

Add input validation:

- Must be a non-empty row or column vector of integers in `[1, 7]`.
- No duplicates (use `unique` to sanitize or error).

**B. Remove midnight-wrap error — implement wrapping logic**

Replace the current error block:

```matlab
% REMOVE THIS:
if num_reduction_steps > 0 && (step_start + num_reduction_steps) > STEPS_PER_DAY
    error('KLa:windowWrapsMidnight', ...);
end
```

With wrap-aware index computation inside the day loop. When the window extends past step 95 (end of day), the overflow indices wrap to the beginning of the *same* calendar day (steps 0–95), **not** into the next day. This models a reduction window like 22:00–02:00 where the aeration reduction spans midnight within a single daily pattern.

Implementation approach — replace the inner loop body:

```matlab
for day_idx = 0 : sim_days - 1
    % Check if this day is active
    week_day = mod(day_idx, 7) + 1;  % 1-based day-of-week
    if ~ismember(week_day, reduction_days)
        continue;  % skip non-reduction days
    end

    day_offset = day_idx * STEPS_PER_DAY;

    % Generate within-day step indices (0-based), wrapping via mod
    within_day_steps = mod(step_start + (0 : num_reduction_steps - 1), STEPS_PER_DAY);

    % Convert to 1-based MATLAB indices within the full timeseries
    abs_indices = day_offset + within_day_steps + 1;

    KLa_col(abs_indices) = KLa_reduced;
end
```

The `mod(..., STEPS_PER_DAY)` handles wrapping automatically: if `step_start = 88` and `num_reduction_steps = 16` (4 hours), the indices become `[88 89 90 91 92 93 94 95 0 1 2 3 4 5 6 7]`, which correctly wraps to the start of the same day.

**C. Update docstring**

Add documentation for the new `reduction_days` parameter, the midnight-wrap behavior, and updated examples.

---

### 2.2 `generate_test_cases.m`

**Minimal changes.** Since `reduction_days` is now a campaign-level parameter (not an experimental factor), the test case grid stays at `5 × 4 × 3 = 60` rows. The `ndgrid` enumeration and table schema are unchanged.

**A. Accept `reduction_days` as a pass-through argument**

Update the function signature to accept and store the campaign's reduction-day pattern so it's available in the test_cases table for downstream use:

```matlab
function T = generate_test_cases(reduction_days)
    if nargin < 1
        reduction_days = [1 2 3 4 5 6 7];  % backward-compatible default
    end
```

**B. Add `reduction_days_label()` helper function**

Add as a local function at the end of the file:

```matlab
function label = reduction_days_label(days_vec)
    label = "d" + strjoin(string(sort(days_vec)), "_");
end
% Examples: [1 2 3 4 5 6 7] → "d1_2_3_4_5_6_7"
%           [1]             → "d1"
%           [1 3 5]         → "d1_3_5"
```

**C. Add campaign-level columns to the output table**

Append `ReductionDays` (cell) and `ReductionDaysLabel` (string) as uniform columns — every row carries the same value since it's a campaign-level setting:

```matlab
rd_cell  = repmat({reduction_days}, NUM_EXPERIMENTS, 1);
rd_label = repmat(reduction_days_label(reduction_days), NUM_EXPERIMENTS, 1);

T = table(experiment_id, rf_col, dh_col, sh_col, rd_cell, rd_label, ...
          'VariableNames', {'ExperimentID', 'ReductionFrac', 'DurationHrs', ...
                            'StartHour', 'ReductionDays', 'ReductionDaysLabel'});
```

This keeps the pattern accessible per-row for `main_sim` extraction without changing the grid logic.

---

### 2.3 `main_sim.m`

**A. Extract `reduction_days` from `test_cases` in Step A**

```matlab
% Inside the while loop, Step A:
reduction_days = test_cases.ReductionDays{iter};   % cell indexing
rd_label       = test_cases.ReductionDaysLabel(iter);
```

**B. Pass `reduction_days` to `generate_KLa_timeseries` in Step B**

```matlab
KLa3_ts = generate_KLa_timeseries(240, reduction_frac, duration_hrs, start_hour, sim_days, reduction_days);
KLa4_ts = generate_KLa_timeseries(240, reduction_frac, duration_hrs, start_hour, sim_days, reduction_days);
KLa5_ts = generate_KLa_timeseries(114, reduction_frac, duration_hrs, start_hour, sim_days, reduction_days);
```

**C. Persist `reduction_days` and `rd_label` across workspace wipes**

Add to the KLa `.mat` save or create a dedicated `experiment_params.mat`:

```matlab
save('experiment_params.mat', 'reduction_days', 'rd_label');
```

And reload in Step D:

```matlab
load('experiment_params.mat', 'reduction_days', 'rd_label');
```

Add `'experiment_params.mat'` to the cleanup list in Section 9.

**D. Pass `rd_label` and `reduction_days` to `effluent_data_writer` calls (Steps E & F)**

Add both name-value arguments (see §2.4 below) — the label for file naming and the vector for AE filtering:

```matlab
effluent_data_writer(t, settler, base_output_dir, ...
    ...,  % existing args
    ReductionDaysLabel=rd_label, ...
    ReductionDays=reduction_days(:), ...   % column vector
    SummaryFile=output_file);
```

**E. Update fprintf diagnostics**

```matlab
fprintf('  Experiment params: reduction=%.2f, duration=%dh, start=%d:00, days=%s\n', ...
        reduction_frac, duration_hrs, start_hour, rd_label);
```

---

### 2.4 `effluent_data_writer.m`

**A. New name-value arguments**

Add to the `arguments` block:

```matlab
options.ReductionDaysLabel (1,1) string   = "d1_2_3_4_5_6_7"
options.ReductionDays      (:,1) double   = (1:7)'   % active days vector
```

Both the label (for filenames/CSV) and the actual vector (for AE calculation) are needed.

**B. Update summary row — add column for reduction pattern**

Insert `ReductionDaysLabel` into the summary table after `Start Time`:

```matlab
summary_row = table( ...
    options.IterationLabel, ...
    options.KLa(1), options.KLa(2), options.KLa(3), ...
    options.ReductionDaysLabel, ...   % ← NEW
    eff.SOe, ... );

'VariableNames', { ...
    'Iter', 'Air Reduc %', 'Reduc Dura', 'Start Time', ...
    'ReductionDaysPattern', ...       % ← NEW
    'SOe', ... }
```

**C. Update settler CSV filename to encode the reduction pattern**

Replace:

```matlab
filename = sprintf('settler_data_iter_%.1f.csv', options.IterationLabel);
```

With:

```matlab
filename = sprintf('settler_data_iter_%.1f_%s.csv', ...
    options.IterationLabel, options.ReductionDaysLabel);
```

Example filenames:
- `settler_data_iter_1.0_d1_2_3_4_5_6_7.csv` (daily)
- `settler_data_iter_3.5_d1.csv` (weekly, experiment phase)

**D. Update subfolder naming (optional)**

Currently the subfolder is just the iteration label. Could incorporate the pattern:

```matlab
subfolder = fullfile(base_output_dir, ...
    sprintf('%s_%s', num2str(options.IterationLabel), options.ReductionDaysLabel));
```

This keeps outputs from different pattern configurations separated even if iteration labels overlap across campaign runs.

**E. Active-day-only aeration energy averaging (NEW REQUIREMENT)**

The current aeration energy calculation integrates over the entire evaluation window and normalizes by `totalt`. When the reduction pattern is not daily (e.g., `[1 3 5]`), this contaminates the average with nominal-only days where no experiment is running, diluting the measured effect.

**Goal:** Compute average aeration energy using *only* the timesteps that fall on active reduction days.

**Implementation approach — build an active-day mask:**

```matlab
if calc_aeration
    % Build a logical mask identifying timesteps on active reduction days.
    % time_window contains fractional-day timestamps; floor gives the
    % 0-based day index for each timestep.
    %
    % For the data partition (startindex:stopindex-1), use the first
    % N = stopindex-1-startindex+1 timestamps.
    partition_time = time_window(1:end-1);  % matches sp rows
    day_indices = floor(partition_time);     % 0-based day number
    week_days = mod(day_indices, 7) + 1;    % 1-based day-of-week

    active_mask = ismember(week_days, options.ReductionDays);

    % If no active days fall in the window, report NaN
    if ~any(active_mask)
        ae_orig_per_day = NaN;
        ae_upd_per_day  = NaN;
    else
        % --- Slice KLa vectors and dt to active timesteps only ---
        dt_active = dt(active_mask);
        totalt_active = sum(dt_active);

        kla1_act = kla1vec(active_mask);
        kla2_act = kla2vec(active_mask);
        kla3_act = kla3vec(active_mask);
        kla4_act = kla4vec(active_mask);
        kla5_act = kla5vec(active_mask);

        % --- Original BSM1 (quadratic) — active days only ---
        V = options.VOL;
        ae1_orig = 0.0007*(V(1)/1333)*(kla1_act.^2) + 0.3267*(V(1)/1333)*kla1_act;
        ae2_orig = 0.0007*(V(2)/1333)*(kla2_act.^2) + 0.3267*(V(2)/1333)*kla2_act;
        ae3_orig = 0.0007*(V(3)/1333)*(kla3_act.^2) + 0.3267*(V(3)/1333)*kla3_act;
        ae4_orig = 0.0007*(V(4)/1333)*(kla4_act.^2) + 0.3267*(V(4)/1333)*kla4_act;
        ae5_orig = 0.0007*(V(5)/1333)*(kla5_act.^2) + 0.3267*(V(5)/1333)*kla5_act;

        ae_vec_orig = 24 * (ae1_orig + ae2_orig + ae3_orig + ae4_orig + ae5_orig);
        ae_orig_per_day = sum(ae_vec_orig .* dt_active) / totalt_active;

        % --- Updated BSM1/BSM2 (OTR) — active days only ---
        S = options.SOSAT;
        otr1 = S(1)*V(1)*kla1_act;
        otr2 = S(2)*V(2)*kla2_act;
        otr3 = S(3)*V(3)*kla3_act;
        otr4 = S(4)*V(4)*kla4_act;
        otr5 = S(5)*V(5)*kla5_act;

        ae_vec_upd = (otr1 + otr2 + otr3 + otr4 + otr5) / (1.8 * 1000);
        ae_upd_per_day = sum(ae_vec_upd .* dt_active) / totalt_active;
    end
end
```

**Key behavior:**
- When `ReductionDays = [1 2 3 4 5 6 7]` (daily/default), the mask is all-true and the calculation is identical to the current code — backward compatible.
- When `ReductionDays = [1]` on a 14-day sim with evaluation window days 1–7, only ~1/7 of timesteps contribute. The average reflects the actual aeration energy on experiment days, not the blend of experiment + nominal days.
- The effluent concentration averages (flow-weighted) remain computed over the *full* evaluation window. Only the aeration energy metric is filtered, since it's the metric that would be misleading if nominal days were included.

**F. Summary row additions for transparency (optional)**

Consider adding columns for the number of active days in the window and total window days, so downstream analysis can verify the filtering:

```matlab
n_active_days = sum(active_mask);   % active timesteps (approximate)
% Or more precisely:
n_active_calendar_days = numel(unique(day_indices(active_mask)));
n_total_calendar_days  = numel(unique(day_indices));
```

This is optional but useful for QA.

---

### 2.5 `run_campaign.m`

**A. Accept a single `reduction_days` pattern as a user argument**

The pattern is a campaign-level setting. Each `run_campaign` invocation tests one pattern across all 60 experiments. Different patterns require separate runs.

```matlab
%% ---- 1. Configuration ----
% Reduction-day pattern for this campaign run.
% Vector of integers 1–7 specifying which days of a 7-day week are active.
% Examples:
%   [1 2 3 4 5 6 7]  — daily (default, matches original behavior)
%   [1]               — weekly (day 1 and day 8 of a 14-day sim)
%   [1 3 5]           — alternating (Mon/Wed/Fri pattern)
%   [6 7]             — weekend-only
reduction_days = [1 2 3 4 5 6 7];
```

**B. Pass to `main_sim` via `.mat` file**

Since `main_sim` is a script, pass the pattern through `campaign_params.mat`:

```matlab
save('campaign_params.mat', 'reduction_days');
```

Then in `main_sim`, load before calling `generate_test_cases`:

```matlab
if isfile('campaign_params.mat')
    load('campaign_params.mat', 'reduction_days');
else
    reduction_days = 1:7;  % default
end
test_cases = generate_test_cases(reduction_days);
```

**C. Tag master CSV with the pattern**

The `master_results.csv` filename (or an added column) should distinguish between campaign runs with different patterns. Options:

1. **Filename approach:** `master_results_d1_3_5.csv` — each pattern gets its own file.
2. **Column approach:** Keep a single `master_results.csv` and rely on the `ReductionDaysPattern` column added by `effluent_data_writer`.

**Recommendation:** Use the column approach (simpler, already handled by §2.4B). The `InfluentCondition` + `ReductionDaysPattern` columns together uniquely identify each campaign configuration.

**D. Add `campaign_params.mat` to save/cleanup lists**

Add to the Section 3 save and Section 7 cleanup. Also add to the `campaign_state.mat` variables so it survives the `main_sim` workspace wipe:

```matlab
save('campaign_state.mat', 'cycle_file', 'master_file', ...
     'influent_condition', 'reduction_days');
```

**E. Update console output**

```matlab
rd_label = "d" + strjoin(string(sort(reduction_days)), "_");
fprintf('  Reduction-day pattern: %s\n', rd_label);
```

---

## 3. Campaign Execution Model

Since `reduction_days` is a campaign-level parameter, the experiment grid remains fixed at 60 cases per campaign run. Different patterns are tested by launching separate `run_campaign` instances:

| Campaign Run | Pattern | Experiments | Master CSV rows |
|-------------|---------|-------------|-----------------|
| Run 1 | `[1 2 3 4 5 6 7]` (daily) | 60 | 60 |
| Run 2 | `[1]` (weekly) | 60 | 60 appended |
| Run 3 | `[1 3 5]` (alternating) | 60 | 60 appended |

Each run appends to `master_results.csv`. The `ReductionDaysPattern` column distinguishes rows from different pattern configurations. Runtime per campaign run is unchanged from current (~60 experiments × ~1.5 min each).

---

## 4. Implementation Order (Sprint Sequence)

Each sprint should be independently testable.

### Sprint 1 — `generate_KLa_timeseries.m` (core logic)

1. Add `reduction_days` parameter with default `[1:7]`.
2. Replace midnight-wrap error with `mod`-based wrapping.
3. Integrate `reduction_days` day-skip logic into the day loop.
4. Add input validation for the new parameter.
5. Update docstring with new parameter, wrapping behavior, and examples.
6. **Test:** Unit tests for midnight wrap (e.g., `start_hour=22, duration=4`), weekly pattern (`[1]` on 14-day sim → only days 1,8 active), daily pattern matches old output exactly.

### Sprint 2 — `generate_test_cases.m` (pass-through wiring)

1. Add `reduction_days` input argument (vector, default `1:7`).
2. Add `reduction_days_label()` local helper function.
3. Add `ReductionDays` (cell) and `ReductionDaysLabel` (string) columns — uniform across all rows (campaign-level).
4. **Test:** Verify 60-row output is unchanged when called with no arguments. Verify columns are populated correctly when called with `[1 3 5]`.

### Sprint 3 — `effluent_data_writer.m` (output labeling + AE filtering)

1. Add `ReductionDaysLabel` and `ReductionDays` name-value arguments.
2. Insert `ReductionDaysPattern` column into summary row.
3. Update settler CSV filename to include the pattern label.
4. Optionally update subfolder naming.
5. **Implement active-day-only AE averaging:** Build a logical mask from `ReductionDays` and `floor(time)` day indices. Filter KLa vectors and `dt` to active timesteps before computing both BSM energy methods. Normalize by `totalt_active` (sum of dt on active days only) instead of `totalt`.
6. **Test:** Verify that with `ReductionDays=[1:7]`, AE output is identical to current code. Verify that with `ReductionDays=[1]` on a 7-day window, only ~1/7 of timesteps contribute. Verify steady-state mode still returns NaN for AE. Verify edge case where no active days fall in the evaluation window → NaN.

### Sprint 4 — `main_sim.m` (orchestration wiring)

1. Load `campaign_params.mat` if present; extract `reduction_days` vector. Fall back to `1:7`.
2. Pass `reduction_days` to `generate_test_cases`.
3. Extract `reduction_days` and `rd_label` from test_cases in Step A (uniform across rows but keeps extraction pattern consistent).
4. Pass `reduction_days` to all three `generate_KLa_timeseries` calls in Step B.
5. Persist `reduction_days` and `rd_label` in `experiment_params.mat` across workspace wipes.
6. Pass both `ReductionDaysLabel` and `ReductionDays` to both `effluent_data_writer` calls (Phase 2 and Phase 3).
7. Update fprintf diagnostics to include pattern label.
8. Add `experiment_params.mat` and `campaign_params.mat` to cleanup list.
9. **Test:** Dry-run first 2 iterations with `reduction_days=[1]`, verify KLa timeseries has reductions only on days 1 and 8, verify output filenames include `_d1`, verify AE is computed over active days only.

### Sprint 5 — `run_campaign.m` (user interface)

1. Add `reduction_days` configuration variable (single vector, default `1:7`).
2. Save `campaign_params.mat` before calling `main_sim`.
3. Add `reduction_days` to `campaign_state.mat` save/reload.
4. Add `campaign_params.mat` to cleanup lists.
5. Update console output to display the pattern label.
6. Update documentation header with usage examples for different patterns.
7. **Test:** End-to-end single-pass with `[1 3 5]` on a reduced grid. Verify `master_results.csv` contains the pattern column. Run a second campaign with `[1]` and verify rows append correctly with distinct pattern labels.

---

## 5. Backward Compatibility

All changes use defaults that reproduce current behavior:

| Parameter | Default | Effect |
|-----------|---------|--------|
| `reduction_days` in `generate_KLa_timeseries` | `[1 2 3 4 5 6 7]` | Applies reduction every day (same as current) |
| `reduction_days` in `generate_test_cases` | `1:7` | Produces same 60-row table with uniform daily pattern |
| `ReductionDaysLabel` in `effluent_data_writer` | `"d1_2_3_4_5_6_7"` | Appended to filenames but functionally inert |
| `ReductionDays` in `effluent_data_writer` | `(1:7)'` | Active-day mask is all-true → AE calc identical to current |
| `campaign_params.mat` absence in `main_sim` | Falls back to `1:7` | No-arg `run_campaign` still works |

---

## 6. Risks & Open Questions

1. **Midnight wrap semantics (RESOLVED):** Overflow wraps within the same day slot. A 22:00–02:00 window on day 3 applies the reduced KLa to steps 88–95 and 0–7 of day 3's 96-step block. No spill into day 4.

2. **AE filtering edge case — evaluation window vs. active days:** The current evaluation windows are `StartTime=1, StopTime=7` (Phase 2) and `StartTime=1, StopTime=2` (Phase 3). With a weekly pattern like `[1]`, the Phase 3 window (days 1–2) contains exactly 1 active day. This is valid but the per-day average is computed from a small sample. Consider whether the evaluation windows should be widened for sparse patterns, or whether this is acceptable given the pseudo-steady-state conditioning.

3. **AE filtering — `floor(time)` alignment with day boundaries:** The BSM time vector starts at 0.0 (midnight of day 1). `floor(0.0) = 0`, `floor(0.999) = 0`, `floor(1.0) = 1`, so day 0 in the time vector corresponds to "day 1" in the `reduction_days` convention. The mapping `week_day = mod(floor(t), 7) + 1` must be verified to align correctly with the day indexing used by `generate_KLa_timeseries` (`day_idx = 0 : sim_days-1`, where `day_idx=0` → `week_day=1`). Both use the same `mod(..., 7) + 1` formula, so they should align, but this is a critical correctness check for Sprint 3 testing.

4. **Master CSV appending across patterns:** When multiple `run_campaign` runs append to the same `master_results.csv`, the `ReductionDaysPattern` column is a string while the other columns are numeric. The `writetable` append mode handles mixed types correctly, but verify that `readmatrix` (used in `run_campaign` Section 6) doesn't silently drop the string column. May need to switch to `readtable` for the accumulation step.

5. **`generate_test_cases` as function vs. config-driven:** Currently the parameter vectors (reduction fracs, durations, start hours) are hard-coded. The new `reduction_days` argument opens the door to making all vectors configurable. Consider whether to generalize now or keep it scoped to the new parameter only.
