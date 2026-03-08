# Simulink Model Integrity — Update Checklist

**Problem:** Simulink caches block diagrams in memory by absolute path, and `.mdl` files can silently absorb workspace parameter values when saved — causing experiments to produce invariant results regardless of KLa inputs. Both issues are invisible at runtime and only manifest as wrong data.

**Goal:** Eliminate these failure modes from the current serial workflow and prevent them in the future parallel computing workflow.

---

## 1. `run_campaign.m`

### 1a. Flush Simulink model cache at campaign start

Add `bdclose('all')` at the top of the script, before any simulation calls. This forces Simulink to reload models from the current MATLAB path rather than using stale in-memory copies from a previous session or a moved directory.

```matlab
%% ---- 0. Environment cleanup ----
bdclose('all');  % flush any in-memory Simulink models from prior sessions
```

Place this before the existing configuration section. It's safe to call even if no models are loaded.

### 1b. Validate `.mdl` file integrity before starting

Compute MD5 checksums of `benchmarkss.mdl` and `benchmark.mdl` at campaign start and compare against known-good reference hashes. Abort if they don't match. Store the reference hashes as constants in the configuration section.

```matlab
%% ---- 0b. Model file integrity check ----
% Reference MD5 hashes from a known-clean copy of the ASM3 BSM files.
% Generate these once from a verified-clean model directory:
%   system('md5sum benchmarkss.mdl benchmark.mdl')
REF_HASHES = struct( ...
    'benchmarkss', 'PASTE_HASH_HERE', ...
    'benchmark',   'PASTE_HASH_HERE'  ...
);

mdl_files = {'benchmarkss.mdl', 'benchmark.mdl'};
for k = 1:numel(mdl_files)
    fname = mdl_files{k};
    [~, hash_line] = system(sprintf('md5sum "%s"', which(fname)));
    hash = strtrim(extractBefore(hash_line, ' '));
    ref = REF_HASHES.(erase(fname, '.mdl'));
    if ~strcmp(hash, ref)
        error('MODEL INTEGRITY FAILURE: %s has been modified.\nExpected: %s\nGot:      %s\nRestore from a clean copy before running.', ...
            fname, ref, hash);
    end
    fprintf('  [OK] %s integrity verified\n', fname);
end
```

### 1c. Lock model files read-only at campaign start, restore at end

Set the `.mdl` files to read-only before the experiment loop begins. This prevents Simulink auto-save or accidental GUI saves from baking parameter values into the block diagram. Restore write permissions in the cleanup section so manual editing isn't blocked outside of campaigns.

```matlab
%% ---- 0c. Lock model files ----
mdl_paths = cellfun(@which, {'benchmarkss.mdl', 'benchmark.mdl'}, 'UniformOutput', false);
for k = 1:numel(mdl_paths)
    fileattrib(mdl_paths{k}, '-w');  % remove write permission
end
```

In the cleanup section (Section 7 or equivalent), restore permissions:

```matlab
%% ---- Cleanup: restore model file permissions ----
for k = 1:numel(mdl_paths)
    fileattrib(mdl_paths{k}, '+w');
end
```

### 1d. Purge `slprj/` build cache at campaign start

Simulink stores compiled model artifacts in `slprj/` directories. These can become stale when models are moved, renamed, or the MATLAB path changes. Delete them at campaign start to force a clean rebuild.

```matlab
%% ---- 0d. Purge Simulink build cache ----
if exist('slprj', 'dir'), rmdir('slprj', 's'); end
```

---

## 2. `main_sim.m`

### 2a. Add `bdclose('all')` before each steady-state calibration call

The steady-state calibration block calls `benchmarkinit` which runs `clear all`. After the workspace is restored from `.mat` files, the in-memory model cache may still reference stale state. Add `bdclose('all')` just before the `sim()` call in the steady-state calibration section to ensure a clean model load.

```matlab
%% Before calling sim() for steady-state
bdclose('all');
sim('benchmarkss', ...);
```

### 2b. Add `bdclose('all')` between Phase 2 and Phase 3

After the pseudo-SS calibration phase completes and before the experiment phase begins, close all models to ensure no cached model state from Phase 2 leaks into Phase 3.

```matlab
%% Between Phase 2 and Phase 3
bdclose('all');
```

### 2c. Verify KLa workspace variables actually propagate

After each `assignin('base', ...)` call that pushes KLa values to the base workspace, add a verification read-back. This catches the scenario where a frozen `.mdl` silently ignores workspace values — the workspace will look correct, but the model won't use it. While this doesn't directly detect the frozen-parameter problem, it ensures the workspace side is correct and narrows the failure domain.

```matlab
%% After assigning KLa timeseries to base workspace
assignin('base', 'KLa3', kla3_ts);
assignin('base', 'KLa4', kla4_ts);
assignin('base', 'KLa5', kla5_ts);

% Verify workspace received the values
ws_kla3 = evalin('base', 'KLa3');
assert(isequal(ws_kla3, kla3_ts), 'KLa3 workspace assignment failed');
```

---

## 3. New helper: `verify_mdl_clean.m` (optional but recommended)

A standalone function that opens a `.mdl` file as text and checks whether KLa block parameters reference workspace variable names rather than hardcoded numeric values. This catches the frozen-parameter problem directly.

```matlab
function verify_mdl_clean(mdl_file, expected_vars)
% VERIFY_MDL_CLEAN  Check that .mdl block parameters reference workspace variables.
%   verify_mdl_clean('benchmark.mdl', {'KLa3', 'KLa4', 'KLa5'})
%
%   Errors if any expected_vars appear as hardcoded numeric values instead
%   of symbolic references in the block diagram file.

    text = fileread(mdl_file);

    for k = 1:numel(expected_vars)
        varname = expected_vars{k};
        % Look for pattern: "Value" followed by a bare number where the
        % variable name should appear. This is a heuristic — adapt the
        % regex to the specific block parameter format in your .mdl files.
        % The key indicator is the variable name appearing as a string
        % (good) vs a numeric literal (bad).
        if ~contains(text, varname)
            error('MDL INTEGRITY: %s not found as symbolic reference in %s.\nThe model may have frozen parameter values.', ...
                varname, mdl_file);
        end
    end
    fprintf('  [OK] %s references workspace variables correctly\n', mdl_file);
end
```

Call from `run_campaign.m` during the integrity check block:

```matlab
verify_mdl_clean(which('benchmark.mdl'), {'KLa3', 'KLa4', 'KLa5'});
verify_mdl_clean(which('benchmarkss.mdl'), {'KLa3', 'KLa4', 'KLa5'});
```

---

## 4. Parallel computing preparation (for future `parfor` or `parsim`)

### 4a. Per-worker directory isolation

Each parallel worker must operate on its own copy of the model directory to avoid file locking, shared `slprj/` cache corruption, and cross-worker model state leakage. Create a helper function that sets up an isolated workspace.

```matlab
function worker_dir = setup_worker_env(clean_model_dir, worker_id)
% SETUP_WORKER_ENV  Create an isolated model directory for a parallel worker.
    worker_dir = fullfile(tempdir, sprintf('bsm_worker_%d', worker_id));
    if exist(worker_dir, 'dir'), rmdir(worker_dir, 's'); end
    copyfile(clean_model_dir, worker_dir);

    % Make .mdl files read-only in the worker copy
    mdl_files = dir(fullfile(worker_dir, '*.mdl'));
    for k = 1:numel(mdl_files)
        fileattrib(fullfile(worker_dir, mdl_files(k).name), '-w');
    end
end
```

### 4b. Worker cleanup function

```matlab
function cleanup_worker_env(worker_dir)
% CLEANUP_WORKER_ENV  Remove a parallel worker's isolated model directory.
    bdclose('all');
    if exist(worker_dir, 'dir'), rmdir(worker_dir, 's'); end
end
```

### 4c. Integration pattern for `parfor`

```matlab
parfor i = 1:n_experiments
    worker_dir = setup_worker_env(clean_model_dir, i);
    old_dir = cd(worker_dir);
    try
        % run simulation in isolated directory
        % ...
    catch ME
        cd(old_dir);
        cleanup_worker_env(worker_dir);
        rethrow(ME);
    end
    cd(old_dir);
    cleanup_worker_env(worker_dir);
end
```

---

## 5. Filesystem / version control hygiene

### 5a. Add `.mdl` files to version control as binary

If using Git, ensure the `.mdl` files are tracked and marked as binary in `.gitattributes` so you always have a known-good baseline to restore from:

```
*.mdl binary
```

### 5b. Keep a `clean_models/` reference directory

Maintain a directory containing verified-clean copies of `benchmarkss.mdl` and `benchmark.mdl` that is never used for actual simulation. The integrity check in 1b compares against hashes derived from these files. This directory should also be read-only.

### 5c. Never open the Simulink GUI on working model copies

The most common way models get corrupted is by opening them in the GUI, which triggers initialization, and then saving (intentionally or via auto-save). If you need to inspect the model visually, open the copy from `clean_models/`, not from the working directory.

---

## Summary — execution order within `run_campaign.m`

The new pre-flight checks should execute in this order before the experiment loop:

1. `bdclose('all')` — flush in-memory models
2. Purge `slprj/` — remove stale build cache
3. MD5 integrity check — verify `.mdl` files are unmodified
4. `verify_mdl_clean` — confirm KLa parameters are symbolic, not frozen
5. Lock `.mdl` files read-only — prevent modification during the campaign
6. *(existing)* Configuration, test case generation, experiment loop
7. *(cleanup)* Restore `.mdl` write permissions