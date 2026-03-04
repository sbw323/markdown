# Refactoring Plan v4: Variable Influent Outer Loop

## Overview

`run_campaign.m` gains an outer loop that slices a long influent source file
(`DYNINFLUENT_ASM3.mat`) into fixed-length tranches, writes each tranche over the
model's influent file (`dryinfluent.mat`), and runs the full experiment matrix
(`main_sim`) per tranche. A new helper function `dynamicInfluent_writer.m` handles
the slice-renormalize-save operation.

## Design Decisions

| Decision | Choice |
|---|---|
| SS recalibration | Re-run per tranche (delete `workspace_steady_state_initial.mat`) |
| `sim_days` coupling | Always equals `tranche_len_days` (single parameter) |
| Master CSV columns | `InfluentCondition` (tranche_idx) + `InfluentSourceStartDay` |
| Source variable name | `ASM3_Influent` inside `DYNINFLUENT_ASM3.mat` |
| Column structure | Identical 21-col (col1=time, cols 2–21 = states) |
| Tranche boundaries | Non-overlapping contiguous blocks of N rows |

---

## File 1 (NEW): `dynamicInfluent_writer.m`

### Type

Function (not script — no `clear all` needed, runs before `benchmarkinit`).

### Signature

```matlab
function info = dynamicInfluent_writer(source_file, tranche_idx, tranche_len_rows, start_row, target_file)
```

### Defaults

| Parameter | Default | Notes |
|---|---|---|
| `source_file` | `'DYNINFLUENT_ASM3.mat'` | Path to long influent |
| `tranche_idx` | *(required)* | 1-based |
| `tranche_len_rows` | `1344` | 14 d × 96 steps/d |
| `start_row` | `1` | 1-based row where first tranche begins |
| `target_file` | `'dryinfluent.mat'` | Model's expected influent path |

### Algorithm

1. `load(source_file)` → workspace variable `ASM3_Influent` (Mx21 matrix).
2. Compute row range:
   - `row_start = start_row + (tranche_idx - 1) * tranche_len_rows`
   - `row_end = row_start + tranche_len_rows - 1`
3. Validate `row_end <= size(ASM3_Influent, 1)` — error if exceeded, reporting
   how many full tranches are available from the given `start_row`.
4. Extract: `tranche = ASM3_Influent(row_start:row_end, :)`.
5. Renormalize time column to start at 0:
   `tranche(:,1) = tranche(:,1) - tranche(1,1)`.
6. Save as the variable `DRYINFLUENT`:
   ```matlab
   DRYINFLUENT = tranche;
   save(target_file, 'DRYINFLUENT');
   ```
7. Return info struct:
   ```matlab
   info.source_file          = source_file;
   info.tranche_idx          = tranche_idx;
   info.row_start            = row_start;
   info.row_end              = row_end;
   info.time_start_original  = ASM3_Influent(row_start, 1);
   info.time_end_original    = ASM3_Influent(row_end, 1);
   info.source_start_day     = ASM3_Influent(row_start, 1);
   ```

### Input Validation

- `source_file` exists and contains variable `ASM3_Influent`.
- `ASM3_Influent` has exactly 21 columns.
- `tranche_idx >= 1`, integer.
- `tranche_len_rows >= 1`, integer.
- `start_row >= 1`, integer.
- Row range does not exceed source matrix bounds.

### Design Note

The function overwrites `target_file` each time. This is intentional —
`benchmarkinit` will load whatever is in `dryinfluent.mat`, so the tranche must
be written before `main_sim` is called.

---

## File 2 (MODIFIED): `run_campaign.m`

### Structural Change

Sections 2–6 wrapped in `for tranche_idx = 1:num_tranches`.

### New Section 1 Parameters

```matlab
% --- Influent source configuration ---
influent_source     = 'DYNINFLUENT_ASM3.mat';   % Long influent file
influent_target     = 'dryinfluent.mat';         % Model's expected influent
tranche_start_day   = 0;                         % Start of first tranche (days)
tranche_len_days    = 14;                        % Length of each tranche = sim_days

% Derived row-space parameters
steps_per_day       = 96;
tranche_len_rows    = tranche_len_days * steps_per_day;   % 1344
start_row           = tranche_start_day * steps_per_day + 1;  % 1-based
```

### Tranche Count Determination (new, after parameter block)

```matlab
tmp = load(influent_source, 'ASM3_Influent');
total_source_rows = size(tmp.ASM3_Influent, 1);
num_tranches = floor((total_source_rows - start_row + 1) / tranche_len_rows);
clear tmp;
fprintf('  Source: %s (%d rows, %d full tranches from row %d)\n', ...
    influent_source, total_source_rows, num_tranches, start_row);
```

### Outer Loop Pseudocode

```matlab
for tranche_idx = 1:num_tranches
    influent_condition = tranche_idx;

    % (a) Write this tranche's influent over dryinfluent.mat
    tranche_info = dynamicInfluent_writer(influent_source, tranche_idx, ...
        tranche_len_rows, start_row, influent_target);
    source_start_day = tranche_info.source_start_day;

    fprintf('  Tranche %d/%d: source rows %d-%d (day %.2f)\n', ...
        tranche_idx, num_tranches, ...
        tranche_info.row_start, tranche_info.row_end, source_start_day);

    % (b) Delete workspace_steady_state_initial.mat to force SS re-run
    if isfile('workspace_steady_state_initial.mat')
        delete('workspace_steady_state_initial.mat');
    end

    % (c) Delete stale sim_state.mat to reset main_sim's iter to 1
    if isfile('sim_state.mat')
        delete('sim_state.mat');
    end

    % (d) Clean slate for per-cycle results (existing Section 2 logic)
    if isfile(cycle_file), delete(cycle_file); end
    ...

    % (e) Save wrapper state (existing Section 3)
    save('campaign_state.mat', 'cycle_file', 'master_file', ...
         'influent_condition', 'reduction_days', ...
         'tranche_idx', 'num_tranches', 'source_start_day', ...
         'tranche_len_days', 'influent_source', 'influent_target', 'start_row');

    % (f) Pass campaign params to main_sim
    sim_days = tranche_len_days;
    save('campaign_params.mat', 'reduction_days', 'sim_days');

    % (g) Run main_sim
    run('main_sim');

    % (h) Restore wrapper state
    load('campaign_state.mat', ...);

    % (i) Accumulate results
    campaign_cycle_results = addvars(campaign_cycle_table, ...
        repmat(influent_condition, h, 1), ...
        repmat(source_start_day, h, 1), ...
        'Before', 1, ...
        'NewVariableNames', {'InfluentCondition', 'InfluentSourceStartDay'});
    ...
end
```

### Resume Logic for the Outer Loop

On entry, check if `campaign_state.mat` exists with a `tranche_idx` field. If so,
resume from that tranche. The inner `main_sim` resume via `sim_state.mat` handles
mid-experiment crashes within a tranche.

### Backward Compatibility

When `DYNINFLUENT_ASM3.mat` is absent, `run_campaign` errors with a clear message.
The old single-pass path is preserved in git history.

### Cleanup (Section 7)

Add `workspace_steady_state_initial.mat` and `sim_state.mat` to the post-campaign
cleanup list.

---

## File 3 (MODIFIED): `main_sim.m`

### Single Change — Load `sim_days` from `campaign_params.mat`

Replace the hardcoded `sim_days = 14` with:

```matlab
sim_days = 14;   % Default for standalone use
if isfile('campaign_params.mat')
    load('campaign_params.mat', 'reduction_days', 'sim_days');
    fprintf('  Loaded reduction_days and sim_days from campaign_params.mat\n');
else
    reduction_days = 1:7;
    fprintf('  No campaign_params.mat found; using defaults\n');
end
```

### Why This Is the Only Change to main_sim.m

- **SS re-run:** `run_campaign` deletes `workspace_steady_state_initial.mat` before
  each tranche, triggering `main_sim`'s existing SS guard.
- **Iter reset:** `run_campaign` deletes `sim_state.mat` before each tranche.
- **Influent loading:** `benchmarkinit` loads whatever is in `dryinfluent.mat`,
  already overwritten by `dynamicInfluent_writer`.

---

## Files with NO Changes

| File | Reason |
|---|---|
| `effluent_data_writer.m` | Operates on sim outputs, tranche-agnostic |
| `generate_KLa_timeseries.m` | KLa generation independent of influent |
| `generate_test_cases.m` | Experiment matrix independent of influent |
| `ssInfluent_writer.m` | Separate use case (percentile-based constant influent) |
| `ssASM3_influent_sampler.m` | Preprocessing step, not in the runtime path |

---

## Implementation Order

1. **`dynamicInfluent_writer.m`** — new, standalone, testable with just a source
   `.mat` file.
2. **`main_sim.m`** — one-line change to load `sim_days` from `campaign_params.mat`.
3. **`run_campaign.m`** — outer loop refactor (depends on both files above).
4. **Integration test** — small source file (e.g., 3 tranches = 4032 rows), reduced
   experiment matrix.

---

## Risk Assessment

| Risk | Mitigation |
|---|---|
| `benchmarkinit` wipes variables after `dynamicInfluent_writer` writes `dryinfluent.mat` | Not a risk — `benchmarkinit` *loads* `dryinfluent.mat`, it doesn't delete it. |
| SS workspace cached from wrong tranche | Eliminated: `run_campaign` deletes `workspace_steady_state_initial.mat` before each tranche. |
| `sim_state.mat` from prior tranche causes iter skip | Eliminated: `run_campaign` deletes `sim_state.mat` before each tranche. |
| Source file too short for requested tranches | `dynamicInfluent_writer` validates bounds and errors with available-tranche count. |
| Partial tranche at end of source file | `floor()` in tranche count calculation silently drops the remainder. |

---

## Key Learnings & Patterns (Carried Forward)

- **MATLAB workspace scoping is the dominant failure mode:** `benchmarkinit` uses
  `clear all`. The generate-persist-wipe-reload pattern remains the established
  solution.
- **`sim()` requires base workspace:** All BSM variables must be pushed via
  `assignin`/`evalin`.
- **Trailing underscore convention** for temp variables pushed to base workspace.
- **File identity check in GENERATE phase:** If working copy is byte-identical to
  reference copy after a GENERATE phase, treat as failure.
- **Non-directive agent prompts produce no-ops:** Agent prompts for GENERATE phases
  require explicit ACTION REQUIRED directive blocks.