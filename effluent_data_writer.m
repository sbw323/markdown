% effluent_data_writer.m
function [summary_row, filepath] = effluent_data_writer(t, settler, base_output_dir, options)
% EFFLUENT_DATA_WRITER  Extract effluent data and write reliability summary to CSV.
%
%   Operates in two modes controlled by the TimeSeries flag:
%     false (default) – Steady-state: extracts the last row of settler.
%     true            – Time-series:  computes flow-weighted average
%                       concentrations and aeration energy over the
%                       specified time window using BSM protocol indexing.
%
%   [summary_row, filepath] = effluent_data_writer(t, settler, base_output_dir)
%   [summary_row, filepath] = effluent_data_writer(t, settler, base_output_dir, Name=Value)
%
%   REQUIRED INPUTS
%       t               – Simulation time vector (from Simulink workspace).
%       settler         – Simulation output matrix (no time column).
%       base_output_dir – Root output folder (string or char).
%
%   OPTIONAL NAME-VALUE ARGUMENTS
%       TimeSeries      – Logical flag. false = steady-state, true = flow-weighted
%                         average over [StartTime, StopTime] (default false).
%       StartTime       – Beginning of the export window (default -Inf).
%       StopTime        – End of the export window (default Inf).
%       IterationLabel  – Scalar label for subfolder/filename (default NaN -> StartTime).
%       KLa             – 1x3 vector [KLa3, KLa4, KLa5] (default [NaN NaN NaN]).
%                         Used as metadata in the summary row, not for calculation.
%       SNH_limit       – Ammonia effluent limit, mg/L (default 4.0).
%       COD_limit       – COD effluent limit, mg/L (default 100.0).
%       SummaryFile     – Path to the appended reliability summary CSV
%                         (default '' -> no summary row written).
%
%   AERATION ENERGY ARGUMENTS (TimeSeries mode only):
%       kla1in .. kla5in – Column vectors of KLa values per reactor, from
%                          Simulink "To Workspace" blocks.  Each vector must
%                          have the same number of rows as t.  Pass all five
%                          to enable aeration energy calculation; omit any
%                          to skip.  (Default: [] for each -> skip.)
%
%                          BSM workspace convention:
%                            kla1in, kla2in = anoxic tanks (typically 0)
%                            kla3in, kla4in, kla5in = aerated tanks
%
%       SOSAT            – 1x5 vector [SOSAT1..SOSAT5], O2 saturation
%                          concentrations per reactor (default [8 8 8 8 8]).
%       VOL              – 1x5 vector [VOL1..VOL5], reactor volumes in m3
%                          (default [1000 1000 1333 1333 1333]).
%
%   SRT ARGUMENTS:
%       reac1 .. reac5   – Reactor output matrices from Simulink "To Workspace"
%                          blocks (reac1..reac5).  Each must have the same
%                          number of rows as t.  Column 13 = TSS (g TSS/m3).
%                          Pass all five to enable SRT calculation; omit any
%                          to skip.  (Default: [] for each -> skip.)
%
%       A_settler        – Settler plan area in m2 (default 1500).
%       z_layer          – Height of each settler layer in m (default 0.4).
%
%   SRT FORMULA (BSM / ASM3):
%       fr_COD_SS = 4/3   (hardcoded; COD-to-TSS conversion factor)
%       TSS_as = sum_k( reac_k(:,13) * VOL(k) )             k = 1..5
%       TSS_sc = sum_j( settler(:, TSS_sc_j) * z * A )      j = 1..10
%       psi_e  = settler(:, TSS_sc_10) * settler(:, Q_e)    (effluent flux)
%       psi_w  = settler(:, TSS_sc_1)  * settler(:, Q_w)    (wastage flux)
%       SRT    = (TSS_as + TSS_sc) / (psi_e + psi_w)        [days]
%
%       Settler TSS layer columns (0-based 41..50 -> 1-based 42..51)
%         NOTE: The settler matrix stores layers in REVERSE physical order:
%           col 42 = layer 10 (top/effluent), col 51 = layer 1 (bottom/waste).
%         col_TSS_sc is defined as 51:-1:42 so that index k = physical layer k.
%       Q_w column (0-based 20 -> 1-based 21)
%       Reactor TSS column: 13 (1-based)
%
%   AERATION ENERGY METHODS (both computed when inputs are available):
%       Original BSM1 (quadratic power-to-KLa relationship):
%         AE_i = 0.0007*(VOL_i/1333)*(KLa_i^2) + 0.3267*(VOL_i/1333)*KLa_i
%         AE_total = 24 * sum(AE_1..5)
%         Integrated: sum(AE_total(t) * dt), normalized per day
%
%       Updated BSM1 / BSM2 (oxygen transfer rate):
%         OTR_i = SOSAT_i * VOL_i * KLa_i(t)
%         AE_total = sum(OTR_1..5) / (1.8 * 1000)
%         Integrated: sum(AE_total(t) * dt), normalized per day
%
%       Ref: perf_plant.m from the BSM evaluation toolbox.
%
%   OUTPUTS
%       summary_row – Table (1 row) of the computed effluent summary.
%       filepath    – Full path of the detailed settler data CSV.
%
%   TIME-SERIES INDEXING (BSM Protocol):
%       startindex = max(find(t <= StartTime))
%       stopindex  = min(find(t >= StopTime))
%       settlerpart = settler(startindex : stopindex-1, :)
%       timevector  = t(startindex:stopindex)    % called 'dt' in this code
%       dt          = diff(timevector)
%       totalt      = time(end) - time(1)

arguments
    t               (:,1) double
    settler         (:,:) double
    base_output_dir (1,1) string
    options.TimeSeries     (1,1) logical  = false
    options.StartTime      (1,1) double   = -Inf
    options.StopTime       (1,1) double   =  Inf
    options.IterationLabel (1,1) double   = NaN
    options.KLa            (1,3) double   = [NaN NaN NaN]
    options.SNH_limit      (1,1) double   = 4.0
    options.COD_limit      (1,1) double   = 100.0
    options.SummaryFile    (1,1) string   = ""
    options.kla1in         (:,1) double   = double.empty(0,1)
    options.kla2in         (:,1) double   = double.empty(0,1)
    options.kla3in         (:,1) double   = double.empty(0,1)
    options.kla4in         (:,1) double   = double.empty(0,1)
    options.kla5in         (:,1) double   = double.empty(0,1)
    options.SOSAT          (1,5) double   = [8 8 8 8 8]
    options.VOL            (1,5) double   = [1000 1000 1333 1333 1333]
    options.reac1          (:,:) double   = double.empty(0,0)
    options.reac2          (:,:) double   = double.empty(0,0)
    options.reac3          (:,:) double   = double.empty(0,0)
    options.reac4          (:,:) double   = double.empty(0,0)
    options.reac5          (:,:) double   = double.empty(0,0)
    options.A_settler      (1,1) double   = 1500
    options.z_layer        (1,1) double   = 0.4
    options.ReductionDaysLabel (1,1) string = "d1_2_3_4_5_6_7"
    options.ReductionDays  (:,1) double   = (1:7)'
end

if isnan(options.IterationLabel)
    options.IterationLabel = options.StartTime;
end

% Check if aeration energy inputs are available.
% All five KLa vectors must be provided (non-empty) to compute energy.
calc_aeration = ~isempty(options.kla1in) && ~isempty(options.kla2in) && ...
                ~isempty(options.kla3in) && ~isempty(options.kla4in) && ...
                ~isempty(options.kla5in);

% Check if SRT inputs are available.
% All five reactor matrices must be provided (non-empty) to compute SRT.
calc_srt = ~isempty(options.reac1) && ~isempty(options.reac2) && ...
           ~isempty(options.reac3) && ~isempty(options.reac4) && ...
           ~isempty(options.reac5);

% If scalar KLa values were passed (constant open-loop), expand to match t.
% If two-column timeseries [time, KLa], extract the value column.
% This mirrors the BSM perf_plant changeScalarToVector convention.
n_t = numel(t);
if calc_aeration
    options.kla1in = expand_scalar_kla(options.kla1in, n_t);
    options.kla2in = expand_scalar_kla(options.kla2in, n_t);
    options.kla3in = expand_scalar_kla(options.kla3in, n_t);
    options.kla4in = expand_scalar_kla(options.kla4in, n_t);
    options.kla5in = expand_scalar_kla(options.kla5in, n_t);
end

%% ---- Column Map (BSM / ASM3 settler output — no time column) ----
col = struct( ...
    'SOe',  22, 'SIe',  23, 'SSe',  24, ...
    'SNHe', 25, 'SN2e', 26, 'SNOe', 27, 'SALKe',28, ...
    'XIe',  29, 'XSe',  30, 'XBHe', 31, 'XSTOe',32, ...
    'XBAe', 33, 'TSSe', 34, 'Qe',   35, ...
    'Qw',   21);     % wastage flow (0-based col 20)

% Settler TSS per layer: 10 layers, bottom (1) to top (10).
% 0-based cols 41..50 -> 1-based cols 42..51.
% IMPORTANT: The settler matrix stores layers in REVERSE order:
%   col 42 = layer 10 (top / effluent, low TSS)
%   col 51 = layer 1  (bottom / waste, high TSS)
% We reverse the vector so that col_TSS_sc(k) corresponds to
% physical layer k, matching BSM convention:
%   col_TSS_sc(1)  = col 51 = bottom layer (waste)
%   col_TSS_sc(10) = col 42 = top layer (effluent)
col_TSS_sc = 51:-1:42;   % TSS_sc_1 .. TSS_sc_10 (physical layer order)

% Reactor TSS column (1-based).  Column 13 in each reacN output matrix.
REAC_COL_TSS = 13;

conc_fields = {'SOe','SIe','SSe','SNHe','SN2e','SNOe','SALKe', ...
               'XIe','XSe','XBHe','XSTOe','XBAe','TSSe'};

all_col_idx = [col.SOe, col.SIe, col.SSe, col.SNHe, col.SN2e, ...
               col.SNOe, col.SALKe, col.XIe, col.XSe, col.XBHe, ...
               col.XSTOe, col.XBAe, col.TSSe, col.Qe];
col_headers = [{'Time'}, conc_fields, {'Qe'}];

%% ---- Compute Effluent Concentrations ----
if options.TimeSeries
    % ============================================================
    %  BSM-protocol indexing (matches original evaluation scripts)
    % ============================================================
    startindex = find(t <= options.StartTime, 1, 'last');
    stopindex  = find(t >= options.StopTime,  1, 'first');

    if isempty(startindex) || isempty(stopindex) || startindex >= stopindex
        warning('effluent_data_writer:noData', ...
            'Cannot build valid window [%.2f, %.2f] from time vector range [%.2f, %.2f].', ...
            options.StartTime, options.StopTime, min(t), max(t));
        summary_row = table();
        filepath    = "";
        return
    end

    % BSM indexing convention
    time_window = t(startindex:stopindex);
    dt          = diff(time_window);                          % N intervals (= perf_plant "timevector")
    totalt      = time_window(end) - time_window(1);          % BSM totalt
    sp          = settler(startindex:(stopindex - 1), :);     % N data rows

    % Flow volume per interval: Qe(i) * dt(i)
    Qe_vol  = sp(:, col.Qe) .* dt;
    total_Q = sum(Qe_vol);

    % Flow-weighted average concentrations: sum(C * Qe * dt) / sum(Qe * dt)
    eff = struct();
    for k = 1:numel(conc_fields)
        f = conc_fields{k};
        eff.(f) = sum(sp(:, col.(f)) .* Qe_vol) / total_Q;
    end

    % Time-averaged flow rate: total_volume / totalt
    eff.Qe = total_Q / totalt;

    % ============================================================
    %  SRT Calculation (BSM / ASM3)
    %
    %  SRT = (TSS_as + TSS_sc) / (psi_e + psi_w)
    %
    %  TSS_as  = total suspended solids mass in activated sludge reactors
    %          = sum_k( reac_k(:,13) * VOL(k) )    k = 1..5
    %
    %  TSS_sc  = total suspended solids mass in settler column
    %          = sum_j( settler(:, TSS_j) * z_layer * A_settler )  j = 1..10
    %
    %  psi_e   = effluent solids flux  = TSS_sc_10 * Q_e
    %  psi_w   = wastage solids flux   = TSS_sc_1  * Q_w
    %
    %  Instantaneous SRT is computed at each timestep, then
    %  time-averaged over the evaluation window.
    % ============================================================
    if calc_srt
        V = options.VOL;

        % Slice reactor data to evaluation window
        r1 = options.reac1(startindex:(stopindex - 1), REAC_COL_TSS);
        r2 = options.reac2(startindex:(stopindex - 1), REAC_COL_TSS);
        r3 = options.reac3(startindex:(stopindex - 1), REAC_COL_TSS);
        r4 = options.reac4(startindex:(stopindex - 1), REAC_COL_TSS);
        r5 = options.reac5(startindex:(stopindex - 1), REAC_COL_TSS);

        % TSS_as: total solids mass in activated sludge [g TSS]
        TSS_as = r1*V(1) + r2*V(2) + r3*V(3) + r4*V(4) + r5*V(5);

        % TSS_sc: total solids mass in settler column [g TSS]
        %   10 layers, each with height z_layer and plan area A_settler
        TSS_sc_layers = sp(:, col_TSS_sc);              % Nx10 matrix
        TSS_sc = sum(TSS_sc_layers, 2) * options.z_layer * options.A_settler;

        % Solids fluxes out of the system [g TSS / day]
        %   psi_e: effluent (top layer = layer 10, column index 10)
        %   psi_w: wastage  (bottom layer = layer 1, column index 1)
        psi_e = sp(:, col_TSS_sc(10)) .* sp(:, col.Qe);
        psi_w = sp(:, col_TSS_sc(1))  .* sp(:, col.Qw);

        % Instantaneous SRT at each timestep [days]
        SRT_inst = (TSS_as + TSS_sc) ./ (psi_e + psi_w);

        % Time-averaged SRT over evaluation window
        SRT_d = sum(SRT_inst .* dt) / totalt;

    else
        SRT_d = NaN;
    end

    % ============================================================
    %  Aeration Energy (both BSM methods — see perf_plant.m)
    %
    %  KLa vectors are sliced to match the data partition using
    %  the same startindex:stopindex-1 range as the settler data.
    %  Integration weights are dt = diff(t(startindex:stopindex)),
    %  which is equivalent to perf_plant's "timevector" variable.
    %
    %  ACTIVE-DAY FILTERING:  When reduction_days is not daily
    %  (e.g. [1 3 5]), nominal-only days would dilute the measured
    %  AE effect.  We build a logical mask from the partition
    %  timestamps using the same day mapping as generate_KLa_timeseries
    %  (mod(day_idx, 7) + 1) and integrate only over active days.
    %  Effluent concentrations (above) remain computed over the
    %  FULL evaluation window — only AE is filtered.
    % ============================================================

    if calc_aeration
        % Slice each KLa vector to the evaluation window
        kla1vec = options.kla1in(startindex:(stopindex - 1));
        kla2vec = options.kla2in(startindex:(stopindex - 1));
        kla3vec = options.kla3in(startindex:(stopindex - 1));
        kla4vec = options.kla4in(startindex:(stopindex - 1));
        kla5vec = options.kla5in(startindex:(stopindex - 1));

        % Build active-day mask from partition timestamps.
        % day_indices uses floor(time) to get 0-based day numbers,
        % matching generate_KLa_timeseries's day_idx (0-based).
        % week_days uses mod(..., 7) + 1 for 1-based day-of-week,
        % matching generate_KLa_timeseries's week_day mapping.
        partition_time = time_window(1:end-1);          % matches sp rows
        day_indices    = floor(partition_time);          % 0-based day number
        week_days      = mod(day_indices, 7) + 1;       % 1-based day-of-week
        active_mask    = ismember(week_days, options.ReductionDays);

        % If no active days fall in the evaluation window, report NaN
        if ~any(active_mask)
            ae_orig_per_day = NaN;
            ae_upd_per_day  = NaN;
        else
            % Filter KLa vectors and dt weights to active-day timesteps
            dt_active     = dt(active_mask);
            totalt_active = sum(dt_active);

            kla1_act = kla1vec(active_mask);
            kla2_act = kla2vec(active_mask);
            kla3_act = kla3vec(active_mask);
            kla4_act = kla4vec(active_mask);
            kla5_act = kla5vec(active_mask);

            % --- Original BSM1: quadratic power-to-KLa relationship ---
            %   AE_i = 0.0007*(VOL_i/1333)*(KLa_i^2) + 0.3267*(VOL_i/1333)*KLa_i
            %   Total instantaneous AE = 24 * sum(AE_1..5)
            V = options.VOL;
            ae1_orig = 0.0007*(V(1)/1333)*(kla1_act.*kla1_act) + 0.3267*(V(1)/1333)*kla1_act;
            ae2_orig = 0.0007*(V(2)/1333)*(kla2_act.*kla2_act) + 0.3267*(V(2)/1333)*kla2_act;
            ae3_orig = 0.0007*(V(3)/1333)*(kla3_act.*kla3_act) + 0.3267*(V(3)/1333)*kla3_act;
            ae4_orig = 0.0007*(V(4)/1333)*(kla4_act.*kla4_act) + 0.3267*(V(4)/1333)*kla4_act;
            ae5_orig = 0.0007*(V(5)/1333)*(kla5_act.*kla5_act) + 0.3267*(V(5)/1333)*kla5_act;

            ae_vec_orig     = 24 * (ae1_orig + ae2_orig + ae3_orig + ae4_orig + ae5_orig);
            ae_orig_per_day = sum(ae_vec_orig .* dt_active) / totalt_active;

            % --- Updated BSM1 / BSM2: oxygen transfer rate method ---
            %   OTR_i = SOSAT_i * VOL_i * KLa_i(t)
            %   Total instantaneous AE = sum(OTR_1..5) / (1.8 * 1000)
            S = options.SOSAT;
            otr1 = S(1) * V(1) * kla1_act;
            otr2 = S(2) * V(2) * kla2_act;
            otr3 = S(3) * V(3) * kla3_act;
            otr4 = S(4) * V(4) * kla4_act;
            otr5 = S(5) * V(5) * kla5_act;

            ae_vec_upd     = (otr1 + otr2 + otr3 + otr4 + otr5) / (1.8 * 1000);
            ae_upd_per_day = sum(ae_vec_upd .* dt_active) / totalt_active;
        end
    else
        ae_orig_per_day = NaN;
        ae_upd_per_day  = NaN;
    end

    % Detail table: time + data for the windowed partition
    detail_time  = time_window(1:end-1);
    detail_slice = [detail_time, sp(:, all_col_idx)];

else
    % ============================================================
    %  Steady-state: extract last row directly
    % ============================================================
    eff = struct();
    for k = 1:numel(conc_fields)
        f = conc_fields{k};
        eff.(f) = settler(end, col.(f));
    end
    eff.Qe = settler(end, col.Qe);

    % No aeration energy in steady-state mode
    ae_orig_per_day = NaN;
    ae_upd_per_day  = NaN;

    % SRT from last row (steady-state snapshot)
    if calc_srt
        V = options.VOL;

        TSS_as = options.reac1(end, REAC_COL_TSS)*V(1) + ...
                 options.reac2(end, REAC_COL_TSS)*V(2) + ...
                 options.reac3(end, REAC_COL_TSS)*V(3) + ...
                 options.reac4(end, REAC_COL_TSS)*V(4) + ...
                 options.reac5(end, REAC_COL_TSS)*V(5);

        TSS_sc = sum(settler(end, col_TSS_sc)) * options.z_layer * options.A_settler;

        psi_e = settler(end, col_TSS_sc(10)) * settler(end, col.Qe);
        psi_w = settler(end, col_TSS_sc(1))  * settler(end, col.Qw);

        SRT_d = (TSS_as + TSS_sc) / (psi_e + psi_w);
    else
        SRT_d = NaN;
    end

    % Detail table: time + last row
    detail_slice = [t(end), settler(end, all_col_idx)];
end

%% ---- COD & Failure Flag ----
COD = eff.SIe + eff.SSe + eff.XIe + eff.XSe + eff.XBHe + eff.XBAe + eff.XSTOe;
failure = double((eff.SNHe > options.SNH_limit) || (COD > options.COD_limit));

%% ---- Build Summary Row ----
summary_row = table( ...
    options.IterationLabel, ...
    options.KLa(1), options.KLa(2), options.KLa(3), ...
    options.ReductionDaysLabel, ...
    eff.SOe, eff.SIe, eff.SSe, eff.SNHe, eff.SN2e, eff.SNOe, eff.SALKe, ...
    eff.XIe, eff.XSe, eff.XBHe, eff.XSTOe, eff.XBAe, eff.TSSe, eff.Qe, ...
    COD, failure, ae_orig_per_day, ae_upd_per_day, SRT_d, ...
    'VariableNames', { ...
        'Iter', 'Air Reduc %', 'Reduc Dura', 'Start Time', ...
        'ReductionDaysPattern', ...
        'SOe', 'SIe', 'SSe', 'SNHe', 'SN2e', 'SNOe', 'SALKe', ...
        'XIe', 'XSe', 'XBHe', 'XSTOe', 'XBAe', 'TSSe', 'Qe', ...
        'COD', 'Failure', 'AE_orig_kWhd', 'AE_new_kWhd', 'SRT_d'});

%% ---- Write Detailed Settler CSV ----
detail_table = array2table(detail_slice, 'VariableNames', col_headers);

subfolder = fullfile(base_output_dir, num2str(options.IterationLabel));
if ~exist(subfolder, 'dir'), mkdir(subfolder); end

filename = sprintf('settler_data_iter_%.1f_%s.csv', ...
    options.IterationLabel, options.ReductionDaysLabel);
filepath = fullfile(subfolder, filename);
writetable(detail_table, filepath);
fprintf('  Detail CSV written: %s\n', filepath);

%% ---- Append to Reliability Summary CSV (optional) ----
if strlength(options.SummaryFile) > 0
    if ~isfile(options.SummaryFile)
        writetable(summary_row, options.SummaryFile);
        fprintf('  Summary file created: %s\n', options.SummaryFile);
    else
        writetable(summary_row, options.SummaryFile, 'WriteMode', 'append');
        fprintf('  Summary row appended to: %s\n', options.SummaryFile);
    end
end

end

function v = expand_scalar_kla(v, n)
% EXPAND_SCALAR_KLA  Normalize KLa input to a column vector of length n.
%   Handles all BSM workspace formats:
%     empty       -> zeros(n,1)    (non-aerated reactor, not provided)
%     scalar      -> repmat(v,n,1) (constant open-loop KLa)
%     Nx2 matrix  -> v(:,2)        (From Workspace timeseries [time, KLa])
%     Nx1 vector  -> v             (already correct format)
    if isempty(v)
        v = zeros(n, 1);
    elseif isscalar(v)
        v = repmat(v, n, 1);
    elseif size(v, 2) == 2
        % From Workspace timeseries format: col1=time, col2=KLa value
        v = v(:, 2);
    end
end