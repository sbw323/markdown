unction KLa_ts = generate_KLa_timeseries(nominal_KLa, reduction_frac, duration_hrs, start_hour, sim_days)
%GENERATE_KLA_TIMESERIES  Build a daily-repeating KLa reduction timeseries for Simulink.
%
%   Produces a two-column [time, KLa] matrix at 15-minute resolution
%   (96 steps/day) suitable for a Simulink From Workspace block configured
%   for zero-order hold interpolation. The timeseries represents a single
%   tank's KLa profile in which the nominal aeration rate is reduced by a
%   fixed fraction during a contiguous window each day, with the nominal
%   rate maintained at all other times.
%
%   The output length matches the BSM1 DRYINFLUENT timeseries convention:
%   sim_days * 96 rows.  For the standard 14-day dry-weather file this
%   yields 1344 rows.
%
%   KLa_ts = generate_KLa_timeseries(nominal_KLa, reduction_frac, ...
%       duration_hrs, start_hour, sim_days)
%
%   REQUIRED INPUTS
%       nominal_KLa    - Scalar (double). Baseline KLa value for the tank
%                        under nominal (unreduced) operation.
%                        Typical BSM1 values: 240 (tanks 3 & 4), 114 (tank 5).
%
%       reduction_frac - Scalar (double) in (0, 1]. Fraction of nominal_KLa
%                        applied during each daily reduction window.
%                        Example: 0.70 means the KLa is reduced to 70% of
%                        nominal (i.e. a 30% reduction).
%                        Expected experiment set: [0.90, 0.80, 0.70, 0.60, 0.50].
%
%       duration_hrs   - Scalar (integer-valued double). Length of the daily
%                        reduction window in whole hours.  Each hour equals
%                        4 timesteps at 15-min resolution.
%                        Valid range: 0-24 hours (0-96 timesteps).
%                        A value of 0 produces an all-nominal timeseries.
%
%       start_hour     - Scalar (double). Clock hour (0-23) at which the
%                        reduction window begins each day.
%                        Expected experiment set: 8 (08:00), 12 (12:00), 16 (16:00).
%                        Mapped to within-day step index as:
%                            step = round(start_hour * 96 / 24)
%                        Correspondence:  8 -> step 32,  12 -> step 48,  16 -> step 64.
%                        Note: fractional hours not on the 15-min grid are
%                        quantised to the nearest step via round().
%
%       sim_days       - Scalar (positive integer-valued double). Total
%                        simulation length in days.  Determines the number
%                        of rows: sim_days * 96.
%                        Must match the length of the influent timeseries
%                        used by the Simulink model (14 for DRYINFLUENT).
%
%   OUTPUT
%       KLa_ts - (sim_days*96) x 2 double matrix.
%                Column 1: Time in fractional days, starting at 0 and
%                          incrementing by 1/96 (i.e. 0, 1/96, 2/96, ...).
%                Column 2: KLa value at each timestep.
%                          = nominal_KLa          outside the reduction window
%                          = nominal_KLa * reduction_frac   inside the window
%
%   DAILY PATTERN
%       The reduction window is applied identically on every simulated day.
%       Within each 24-hour cycle (96 steps indexed 0-95):
%
%         step_start = round(start_hour * 96 / 24)
%         step_end   = step_start + duration_hrs * 4 - 1
%
%       All steps from step_start through step_end (inclusive) receive the
%       reduced KLa.  All other steps retain the nominal value.
%
%       The maximum window (start_hour=16, duration_hrs=4) ends at step 79
%       (20:00), so no midnight-wrap logic is required for the defined
%       experiment set.
%
%   PERSISTENCE (caller responsibility)
%       This function returns the timeseries matrix but does NOT save it to
%       disk.  The caller is responsible for persisting the output to a .mat
%       file (e.g. KLa3_timeseries.mat) so that it survives workspace wipes
%       caused by benchmarkinit's 'clear all'.  Typical caller pattern:
%
%           KLa3_ts = generate_KLa_timeseries(240, 0.70, 2, 12, 14);
%           save('KLa3_timeseries.mat', 'KLa3_ts');
%
%   EXAMPLE
%       % Tank 3: 30% reduction for 2 hours starting at noon, 14-day sim
%       KLa3_ts = generate_KLa_timeseries(240, 0.70, 2, 12, 14);
%       % Result: 1344x2 matrix.  Nominal KLa = 240 everywhere except
%       %         steps 48-55 of each day, where KLa = 168.
%
%       % Tank 5: 50% reduction for 1 hour starting at 8 AM
%       KLa5_ts = generate_KLa_timeseries(114, 0.50, 1, 8, 14);
%       % Result: 1344x2 matrix.  Nominal KLa = 114 everywhere except
%       %         steps 32-35 of each day, where KLa = 57.
%
%   Author:  BSM Aeration Agent
%   Date:    2026-03-01
%
%   See also: generate_test_cases, main_sim, effluent_data_writer

% ---- Named constants ----
STEPS_PER_DAY = 96;          % 15-min resolution: 24*60/15 = 96
HOURS_PER_DAY = 24;

% ---- Input validation ----
if ~isscalar(nominal_KLa) || ~isnumeric(nominal_KLa) || nominal_KLa <= 0
    error('KLa:invalidNominal', ...
        'nominal_KLa must be a positive scalar. Got: %g', nominal_KLa);
end

if ~isscalar(reduction_frac) || ~isnumeric(reduction_frac) || ...
        reduction_frac <= 0 || reduction_frac > 1
    error('KLa:invalidReductionFrac', ...
        'reduction_frac must be in (0, 1]. Got: %g', reduction_frac);
end

if ~isscalar(duration_hrs) || ~isnumeric(duration_hrs) || ...
        duration_hrs < 0 || mod(duration_hrs, 1) ~= 0 || duration_hrs > HOURS_PER_DAY
    error('KLa:invalidDuration', ...
        'duration_hrs must be a non-negative integer in [0, %d]. Got: %g', ...
        HOURS_PER_DAY, duration_hrs);
end

if ~isscalar(start_hour) || ~isnumeric(start_hour) || ...
        start_hour < 0 || start_hour > 23
    error('KLa:invalidStartHour', ...
        'start_hour must be in [0, 23]. Got: %g', start_hour);
end

if ~isscalar(sim_days) || ~isnumeric(sim_days) || ...
        sim_days < 1 || mod(sim_days, 1) ~= 0
    error('KLa:invalidSimDays', ...
        'sim_days must be a positive integer. Got: %g', sim_days);
end

% Compute within-day step range and check for midnight wrap
step_start = round(start_hour * STEPS_PER_DAY / HOURS_PER_DAY);  % 0-based
num_reduction_steps = duration_hrs * 4;  % each hour = 4 steps at 15-min resolution

if num_reduction_steps > 0 && (step_start + num_reduction_steps) > STEPS_PER_DAY
    error('KLa:windowWrapsMidnight', ...
        'Reduction window wraps past midnight: start step %d + %d steps = %d (> %d).', ...
        step_start, num_reduction_steps, step_start + num_reduction_steps, STEPS_PER_DAY);
end

% ---- Build time column using integer-step method to avoid FP drift ----
total_steps = sim_days * STEPS_PER_DAY;
time_col = (0 : total_steps - 1)' / STEPS_PER_DAY;

% ---- Build KLa column ----
% Preallocate to nominal value
KLa_col = repmat(nominal_KLa, total_steps, 1);

% Apply daily reduction windows (skip loop entirely if duration is zero)
if num_reduction_steps > 0
    KLa_reduced = nominal_KLa * reduction_frac;

    for day_idx = 0 : sim_days - 1
        % day_offset is the 0-based index of the first step of this day
        day_offset = day_idx * STEPS_PER_DAY;

        % Convert to 1-based MATLAB indices
        idx_start = day_offset + step_start + 1;
        idx_end   = idx_start + num_reduction_steps - 1;

        KLa_col(idx_start : idx_end) = KLa_reduced;
    end
end

% ---- Assemble output ----
KLa_ts = [time_col, KLa_col];

end
