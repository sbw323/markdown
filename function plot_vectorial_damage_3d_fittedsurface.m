function plot_vectorial_damage_3d_fittedsurface(csv_path)
% PLOT_VECTORIAL_DAMAGE_3D  Three unified 3D figures with a fitted
% polynomial response surface per IQI bin, colored by bin.
%
%   plot_vectorial_damage_3d(csv_path)
%
%   For each of three damage metrics (COD, SNHe, EQI), fits a 2nd-order
%   polynomial surface  Z = f(Duration, Reduction)  to each IQI bin
%   and renders the surfaces in distinct colors.  Scatter points are
%   overlaid with low alpha for context.
%
%   Axes:
%     X — Curtailment duration  (ReducDura, minutes)
%     Y — Aeration reduction factor  (AirReduc, fractional)
%     Z — Damage metric (fractional anomaly from nominal)
%
%   Polynomial model (poly22):
%     Z = b0 + b1*D + b2*R + b3*D^2 + b4*D*R + b5*R^2
%   No Curve Fitting Toolbox required.
%
%   Filters (edit variables below):
%     QE_EDGES             — bin edges for effluent flow Qe
%     NOM_FAILURE_REQUIRED — nominal failure flag filter

    if nargin < 1 || isempty(csv_path)
        csv_path = 'master_parallel_results.csv';
    end

    %% ==== USER-DEFINED FILTERS ====

    QE_EDGES  = [1.0e4, 2.60e4];
    QE_COLNAME = 'Qe';

    NOM_FAILURE_REQUIRED = 0;

    % IQI discrete bin range (must match sampled LHS bounds)
    IQI_LO   = 39800;
    IQI_HI   = 56100;
    N_BINS    = 6;

    % Polynomial order for surface fit
    %   'poly22' : full 2nd order  (6 terms: 1, D, R, D^2, DR, R^2)
    %   'poly33' : full 3rd order  (10 terms)
    POLY_ORDER = 2;

    % Surface evaluation grid density per axis
    GRID_N = 40;

    % Scatter point alpha (low = context only, 0 = hidden)
    SCATTER_ALPHA = 0.15;

    % Surface transparency
    SURF_ALPHA = 0.55;

    % Minimum points required per bin to attempt a fit
    MIN_PTS_FOR_FIT = 10;

    % Fixed colors per bin: blue, green, yellow, orange, red, violet
    BIN_COLORS = [ ...
        0.00  0.45  0.74;   % bin 1 — blue
        0.20  0.72  0.30;   % bin 2 — green
        0.93  0.86  0.20;   % bin 3 — yellow
        0.96  0.55  0.10;   % bin 4 — orange
        0.85  0.15  0.15;   % bin 5 — red
        0.58  0.25  0.70];  % bin 6 — violet
    %% ===============================

    %% ---- IQI bin edges ----
    IQI_BIN_EDGES = linspace(IQI_LO, IQI_HI, N_BINS + 1);

    %% ---- Z-axis metric definitions ----
    z_fields = {'COD_Damage_pct', 'SNHe_Damage_pct', 'EQI_Damage_pct'};
    z_scales = [1/100,            1/100,              1/100          ];
    z_labels = {'\DeltaCOD / COD_{nom}', ...
                '\DeltaSNH_e / SNH_{e,nom}', ...
                '\DeltaEQI / EQI_{nom}'};
    z_titles = {'COD Damage', 'SNH_e Damage', 'EQI Damage'};

    %% ---- 1. Compute damage metrics ----
    fprintf('Computing damage metrics...\n');
    opts.PlotOn = false;
    dmg = calculate_damage_metrics(csv_path, opts);

    %% ---- 2. Read CSV and apply row filter ----
    T = readtable(csv_path);

    if ~ismember(QE_COLNAME, T.Properties.VariableNames)
        error('Column "%s" not found in CSV.', QE_COLNAME);
    end
    if ~isempty(NOM_FAILURE_REQUIRED) && ...
       ~ismember('Failure', T.Properties.VariableNames)
        error('Column "Failure" not found in CSV.');
    end

    NOMINAL_ITER  = [51, 51.5];
    is_nominal    = ismember(T.Iter, NOMINAL_ITER);
    is_whole_iter = (mod(T.Iter, 1) == 0);
    is_experiment = is_whole_iter & ~is_nominal;

    T_nom = T(is_nominal, :);
    T_exp = T(is_experiment, :);

    IQI_exp = T_exp.IQI_new;
    Qe_exp  = T_exp.(QE_COLNAME);

    if numel(IQI_exp) ~= size(dmg, 1)
        error('Row count mismatch: %d vs %d.', numel(IQI_exp), size(dmg, 1));
    end

    %% ---- 2b. Nominal failure mask ----
    nom_failure_ok = true(height(T_exp), 1);

    if ~isempty(NOM_FAILURE_REQUIRED)
        nom_map = containers.Map('KeyType','int32','ValueType','int32');
        for k = 1:height(T_nom)
            cyc = int32(T_nom.CycleIdx(k));
            if ~isKey(nom_map, cyc)
                nom_map(cyc) = k;
            end
        end
        n_no_nom = 0;
        for i = 1:height(T_exp)
            cyc = int32(T_exp.CycleIdx(i));
            if ~isKey(nom_map, cyc)
                nom_failure_ok(i) = false;
                n_no_nom = n_no_nom + 1;
                continue;
            end
            ni = nom_map(cyc);
            nom_failure_ok(i) = (T_nom.Failure(ni) == NOM_FAILURE_REQUIRED);
        end
        n_excluded = sum(~nom_failure_ok);
        fprintf('  Nominal failure filter (require %d): %d of %d pass (%d excluded).\n', ...
                NOM_FAILURE_REQUIRED, sum(nom_failure_ok), height(T_exp), n_excluded);
    end

    %% ---- 3. Assemble vectors & filters ----
    ER    = dmg.EnergyDamage_pct / 100;
    Dur   = dmg.ReducDura;
    Reduc = dmg.AirReduc;
    IQI   = IQI_exp;
    Qe    = Qe_exp;

    % Qe filter
    n_qe = numel(QE_EDGES) - 1;
    in_qe = false(size(Qe));
    for bq = 1:n_qe
        qe_lo = QE_EDGES(bq);
        qe_hi = QE_EDGES(bq + 1);
        if bq < n_qe
            in_qe = in_qe | ((Qe >= qe_lo) & (Qe < qe_hi));
        else
            in_qe = in_qe | ((Qe >= qe_lo) & (Qe <= qe_hi));
        end
    end

    base_valid = ~isnan(ER) & ~isnan(Dur) & ~isnan(Reduc) ...
               & ~isnan(IQI) & ~isnan(Qe) ...
               & (ER > 0) & nom_failure_ok & in_qe;
    for zm = 1:numel(z_fields)
        base_valid = base_valid & ~isnan(dmg.(z_fields{zm}));
    end

    bin_idx = discretize(IQI, IQI_BIN_EDGES, 'IncludedEdge', 'right');

    fprintf('\n--- Summary ---\n');
    fprintf('  Base valid: %d / %d\n', sum(base_valid), numel(base_valid));
    fprintf('  Poly order: %d  |  Grid: %dx%d\n', POLY_ORDER, GRID_N, GRID_N);
    fprintf('\n  IQI bin edges: ');
    fprintf('%.0f  ', IQI_BIN_EDGES);
    fprintf('\n');
    for b = 1:N_BINS
        nb = sum(base_valid & bin_idx == b);
        fprintf('    Bin %d [%.0f, %.0f]: %d pts\n', ...
                b, IQI_BIN_EDGES(b), IQI_BIN_EDGES(b+1), nb);
    end

    %% ---- 4. One figure per Z metric ----
    for zm = 1:numel(z_fields)
        Z_raw = dmg.(z_fields{zm});
        Z     = Z_raw * z_scales(zm);

        figure('Name', z_titles{zm}, 'NumberTitle', 'off', ...
               'Position', [50+60*zm  50+60*zm  960  720]);
        hold on;

        leg_handles = gobjects(N_BINS, 1);
        leg_entries = cell(N_BINS, 1);

        for b = 1:N_BINS
            in_b = base_valid & (bin_idx == b);
            n_b  = sum(in_b);

            leg_entries{b} = sprintf('IQI [%.0f–%.0f] (n=%d)', ...
                                     IQI_BIN_EDGES(b), IQI_BIN_EDGES(b+1), n_b);

            if n_b == 0
                % Invisible placeholder for legend alignment
                leg_handles(b) = scatter3(NaN, NaN, NaN, 1, ...
                                          BIN_COLORS(b,:), 'filled');
                continue;
            end

            % --- Scatter points (low alpha context) ---
            if SCATTER_ALPHA > 0
                scatter3(Dur(in_b), Reduc(in_b), Z(in_b), ...
                         15, 'filled', ...
                         'MarkerFaceColor', BIN_COLORS(b,:), ...
                         'MarkerFaceAlpha', SCATTER_ALPHA, ...
                         'MarkerEdgeColor', 'none');
            end

            % --- Fit polynomial surface ---
            if n_b < MIN_PTS_FOR_FIT
                fprintf('    Bin %d: %d pts < %d minimum — skipping fit.\n', ...
                        b, n_b, MIN_PTS_FOR_FIT);
                leg_handles(b) = scatter3(NaN, NaN, NaN, 1, ...
                                          BIN_COLORS(b,:), 'filled');
                continue;
            end

            d = Dur(in_b);
            r = Reduc(in_b);
            z = Z(in_b);

            % Build design matrix for polynomial of given order
            A = build_poly_design(d, r, POLY_ORDER);
            n_terms = size(A, 2);

            if n_b <= n_terms
                fprintf('    Bin %d: %d pts <= %d terms — underdetermined, skipping.\n', ...
                        b, n_b, n_terms);
                leg_handles(b) = scatter3(NaN, NaN, NaN, 1, ...
                                          BIN_COLORS(b,:), 'filled');
                continue;
            end

            % Least-squares solve
            coeffs = A \ z;

            % Goodness of fit
            z_pred = A * coeffs;
            SS_res = sum((z - z_pred).^2);
            SS_tot = sum((z - mean(z)).^2);
            R2 = 1 - SS_res / max(SS_tot, eps);
            RMSE = sqrt(SS_res / n_b);

            fprintf('    Bin %d [%s]: R²=%.4f  RMSE=%.6f  (%d pts, %d terms)\n', ...
                    b, z_titles{zm}, R2, RMSE, n_b, n_terms);

            % --- Evaluate on meshgrid ---
            d_grid = linspace(min(d), max(d), GRID_N);
            r_grid = linspace(min(r), max(r), GRID_N);
            [Dg, Rg] = meshgrid(d_grid, r_grid);
            A_grid = build_poly_design(Dg(:), Rg(:), POLY_ORDER);
            Zg = reshape(A_grid * coeffs, GRID_N, GRID_N);

            % --- Plot surface ---
            hs = surf(Dg, Rg, Zg, ...
                 'FaceAlpha', SURF_ALPHA, ...
                 'FaceColor', BIN_COLORS(b,:), ...
                 'EdgeColor', 'none');
            leg_handles(b) = hs;
        end

        % --- Origin marker ---
        h_nom = scatter3(0, 0, 0, 200, 'r', 'filled', ...
                 'MarkerFaceAlpha', 0.95, 'MarkerEdgeColor', 'k', ...
                 'LineWidth', 1.5);

        % --- Reference surface: Z = 0 plane ---
        d_range = [min(Dur(base_valid)), max(Dur(base_valid))];
        r_range = [min(Reduc(base_valid)), max(Reduc(base_valid))];
        [Dm, Rm] = meshgrid(linspace(d_range(1), d_range(2), 10), ...
                            linspace(r_range(1), r_range(2), 10));
        surf(Dm, Rm, zeros(size(Dm)), ...
             'FaceAlpha', 0.06, 'FaceColor', [0.5 0.5 0.5], ...
             'EdgeColor', 'none');

        % --- Axis lines through origin ---
        xl = xlim; yl = ylim; zl = zlim;
        plot3(xl, [0 0], [0 0], 'k--', 'LineWidth', 0.5);
        plot3([0 0], yl, [0 0], 'k--', 'LineWidth', 0.5);
        plot3([0 0], [0 0], zl, 'k--', 'LineWidth', 0.5);

        hold off;

        %% ---- Labels & formatting ----
        xlabel('Duration (min)');
        ylabel('Reduction Factor');
        zlabel(z_labels{zm});
        title(sprintf('%s  (poly%d%d surface per IQI bin)', ...
                      z_titles{zm}, POLY_ORDER, POLY_ORDER));
        grid on;
        view([-120 30]);

        % Build legend from surface handles + nominal
        legend([leg_handles; h_nom], ...
               [leg_entries; {'Nominal (0,0,0)'}], ...
               'Location', 'best', 'FontSize', 8);
        set(gca, 'FontSize', 11);

        fprintf('  [%s] Z range: [%.6f, %.6f]\n', ...
                z_titles{zm}, min(Z(base_valid)), max(Z(base_valid)));
    end

    fprintf('\n3 surface-fit figures generated.\n');
end

%% ========================================================================
function A = build_poly_design(x, y, order)
% BUILD_POLY_DESIGN  Construct Vandermonde-style design matrix for a
% bivariate polynomial of the specified order.
%
%   order=1:  1, x, y                                      (3 terms)
%   order=2:  1, x, y, x^2, x*y, y^2                      (6 terms)
%   order=3:  1, x, y, x^2, x*y, y^2, x^3, x^2y, xy^2, y^3 (10 terms)
%
%   Inputs x, y are column vectors (or will be reshaped).

    x = x(:);
    y = y(:);

    switch order
        case 1
            A = [ones(size(x)), x, y];
        case 2
            A = [ones(size(x)), x, y, x.^2, x.*y, y.^2];
        case 3
            A = [ones(size(x)), x, y, x.^2, x.*y, y.^2, ...
                 x.^3, x.^2.*y, x.*y.^2, y.^3];
        otherwise
            error('Polynomial order %d not implemented. Use 1, 2, or 3.', order);
    end
end