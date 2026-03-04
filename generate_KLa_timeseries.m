function KLa_ts = generate_KLa_timeseries(nominal_KLa, reduction_frac, duration_hrs, start_hour, sim_days)
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
%       nominal_KLa    – Scalar (double). Baseline KLa value for the tank
%                        under nominal (unreduced) operation.
%                        Typical BSM1 values: 240 (tanks 3 & 4), 114 (tank 5).
%
%       reduction_frac – Scalar (double) in (0, 1]. Fraction of nominal_KLa
%                        applied during each daily reduction window.
%                        Example: 0.70 means the KLa is reduced to 70% of
%                        nominal (i.e. a 30% reduction).
%                        Expected experiment set: [0.90, 0.80, 0.70, 0.60, 0.50].
%
%       duration_hrs   – Scalar (integer-valued double). Length of the daily
%                        reduction window in whole hours.  Each hour equals
%                        4 timesteps at 15-min resolution.
%                        Valid range: 1–4 hours (4–16 timesteps).
%
%       start_hour     – Scalar (double). Clock hour (0–23) at which the
%                        reduction window begins each day.
%                        Expected experiment set: 8 (08:00), 12 (12:00), 16 (16:00).
%                        Mapped to within-day step index as:
%                            step = round(start_hour * 96 / 24)
%                        Correspondence:  8 → step 32,  12 → step 48,  16 → step 64.
%
%       sim_days       – Scalar (positive integer-valued double). Total
%                        simulation length in days.  Determines the number
%                        of rows: sim_days * 96.
%                        Must match the length of the influent timeseries
%                        used by the Simulink model (14 for DRYINFLUENT).
%
%   OUTPUT
%       KLa_ts – (sim_days*96) × 2 double matrix.
%                Column 1: Time in fractional days, starting at 0 and
%                          incrementing by 1/96 (i.e. 0, 1/96, 2/96, ...).
%                Column 2: KLa value at each timestep.
%                          = nominal_KLa          outside the reduction window
%                          = nominal_KLa * reduction_frac   inside the window
%
%   DAILY PATTERN
%       The reduction window is applied identically on every simulated day.
%       Within each 24-hour cycle (96 steps indexed 0–95):
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
%       % Result: 1344×2 matrix.  Nominal KLa = 240 everywhere except
%       %         steps 48–55 of each day, where KLa = 168.
%
%       % Tank 5: 50% reduction for 1 hour starting at 8 AM
%       KLa5_ts = generate_KLa_timeseries(114, 0.50, 1, 8, 14);
%       % Result: 1344×2 matrix.  Nominal KLa = 114 everywhere except
%       %         steps 32–35 of each day, where KLa = 57.
%
%   See also: generate_test_cases, main_sim, effluent_data_writer

% ---- Implementation below this line ----

end
