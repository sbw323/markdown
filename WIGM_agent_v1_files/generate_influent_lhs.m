function [X_physical, var_info] = generate_influent_lhs(n_samples, seed)
%GENERATE_INFLUENT_LHS Generate Latin Hypercube Sampling design matrix for WIGM influent variables
%
%   [X_physical, var_info] = generate_influent_lhs(n_samples, seed)
%
%   PURPOSE:
%   Generates an n x 10 Latin Hypercube Sampling design matrix in physical
%   units for the 10 WIGM (Wastewater Influent Generator Model) input
%   variables. Uses maximin criterion for optimal space-filling properties.
%
%   ALGORITHM:
%   1. Validates inputs using arguments block
%   2. Builds variable metadata struct with hardcoded parameter definitions
%   3. Seeds RNG for reproducibility using Mersenne Twister
%   4. Generates unit hypercube using lhsdesign with maximin criterion
%   5. Transforms columns 1-5 (Normal) via inverse normal CDF
%   6. Transforms columns 6-10 (Uniform) via linear scaling
%   7. Clips Normal variables to physical bounds
%   8. Returns design matrix and metadata
%
%   INPUTS:
%   n_samples — (positive integer scalar) Number of LHS samples to generate.
%               Must be >= 1. No default; required argument.
%   seed      — (non-negative integer scalar) RNG seed for reproducible
%               results. Must be >= 0. No default; required argument.
%
%   OUTPUTS:
%   X_physical — (n_samples x 10 double) Design matrix in physical units.
%                Columns correspond to variables in var_info.names order.
%   var_info   — (1x1 struct) Variable metadata with fields:
%     .names         — 1x10 cell array of MATLAB variable names
%     .distributions — 1x10 cell array of distribution types
%     .params        — 1x10 cell array of distribution parameters
%     .units         — 1x10 cell array of unit strings
%
%   EXAMPLES:
%   % Generate 100 samples with seed 42
%   [X, info] = generate_influent_lhs(100, 42);
%
%   % Check reproducibility
%   [X1, ~] = generate_influent_lhs(50, 123);
%   [X2, ~] = generate_influent_lhs(50, 123);
%   isequal(X1, X2)  % Returns true
%
%   VARIABLE DEFINITIONS:
%   Flow factors (Normal distributions):
%     PE (x1000 inhabitants) — mean=80, std=8 (10% CV)
%     QperPE (L/d per PE)    — mean=150, std=15 (10% CV)
%     aHpercent (%)          — mean=75, std=7.5 (10% CV)
%     Qpermm (m3/mm rain)    — mean=1500, std=375 (25% CV)
%     LLrain (mm rain/d)     — mean=3.5, std=0.875 (25% CV)
%
%   Pollutant factors (Uniform distributions):
%     CODsol_gperPEperd   — [19.31, 21.241] g COD/(d PE)
%     CODpart_gperPEperd  — [115.08, 126.588] g COD/(d PE)
%     SNH_gperPEperd      — [5.8565, 6.44215] g N/(d PE)
%     TKN_gperPEperd      — [12.104, 13.3144] g N/(d PE)
%     SI_cst              — [30, 50] g COD/m3
%
%   Author: Claude Code Assistant
%   Date: March 2026

    arguments
        n_samples (1,1) {mustBeInteger, mustBePositive}
        seed (1,1) {mustBeInteger, mustBeNonnegative}
    end

    % Variable metadata - hardcoded constants for reproducibility
    VAR_NAMES = {'PE', 'QperPE', 'aHpercent', 'Qpermm', 'LLrain', ...
                 'CODsol_gperPEperd', 'CODpart_gperPEperd', ...
                 'SNH_gperPEperd', 'TKN_gperPEperd', 'SI_cst'};

    VAR_DISTRIBUTIONS = {'normal', 'normal', 'normal', 'normal', 'normal', ...
                         'uniform', 'uniform', 'uniform', 'uniform', 'uniform'};

    VAR_UNITS = {'x1000 PE', 'L/d per PE', '%', 'm3/mm rain', 'mm rain/d', ...
                 'g COD/(d PE)', 'g COD/(d PE)', 'g N/(d PE)', 'g N/(d PE)', 'g COD/m3'};

    % Distribution parameters
    % Normal: [mean, std]
    NORMAL_PARAMS = {
        [80, 8];         ... % PE: mean=80, std=8 (10% CV)
        [150, 15];       ... % QperPE: mean=150, std=15 (10% CV)
        [75, 7.5];       ... % aHpercent: mean=75, std=7.5 (10% CV)
        [1500, 375];     ... % Qpermm: mean=1500, std=375 (25% CV)
        [3.5, 0.875]     ... % LLrain: mean=3.5, std=0.875 (25% CV)
    };

    % Uniform: [lower_bound, upper_bound]
    UNIFORM_PARAMS = {
        [19.31, 21.241];    ... % CODsol_gperPEperd
        [115.08, 126.588];  ... % CODpart_gperPEperd
        [5.8565, 6.44215];  ... % SNH_gperPEperd
        [12.104, 13.3144];  ... % TKN_gperPEperd
        [30, 50]            ... % SI_cst
    };

    % Combine parameters into single cell array
    VAR_PARAMS = {NORMAL_PARAMS{:}, UNIFORM_PARAMS{:}};

    % LHS generation parameters
    NUM_VARS = 10;
    LHS_CRITERION = 'maximin';
    LHS_ITERATIONS = 100;

    % Physical bounds for clipping Normal distributions
    PE_MIN = eps;           % PE must be positive
    QPERPE_MIN = eps;       % QperPE must be positive
    AHPERCENT_MIN = 0;      % aHpercent minimum
    AHPERCENT_MAX = 100;    % aHpercent maximum
    QPERMM_MIN = eps;       % Qpermm must be positive
    LLRAIN_MIN = eps;       % LLrain must be positive

    % Build var_info struct
    var_info = struct();
    var_info.names = VAR_NAMES;
    var_info.distributions = VAR_DISTRIBUTIONS;
    var_info.params = VAR_PARAMS;
    var_info.units = VAR_UNITS;

    % Set RNG state for reproducibility
    rng(seed, 'twister');

    % Generate unit hypercube using Latin Hypercube Sampling
    fprintf('Generating %d-sample LHS design matrix with seed %d...\n', n_samples, seed);
    X_unit = lhsdesign(n_samples, NUM_VARS, 'criterion', LHS_CRITERION, ...
                       'iterations', LHS_ITERATIONS);

    % Preallocate physical design matrix
    X_physical = zeros(n_samples, NUM_VARS);

    % Transform columns 1-5: Normal distributions via inverse normal CDF
    for col = 1:5
        mu = NORMAL_PARAMS{col}(1);      % mean
        sigma = NORMAL_PARAMS{col}(2);   % standard deviation
        X_physical(:, col) = norminv(X_unit(:, col), mu, sigma);
    end

    % Transform columns 6-10: Uniform distributions via linear scaling
    for col = 6:10
        uniform_idx = col - 5;  % Index into UNIFORM_PARAMS
        lb = UNIFORM_PARAMS{uniform_idx}(1);  % lower bound
        ub = UNIFORM_PARAMS{uniform_idx}(2);  % upper bound
        X_physical(:, col) = X_unit(:, col) * (ub - lb) + lb;
    end

    % Clip Normal distributions to physical bounds
    % Column 1: PE must be positive
    X_physical(:, 1) = max(X_physical(:, 1), PE_MIN);

    % Column 2: QperPE must be positive
    X_physical(:, 2) = max(X_physical(:, 2), QPERPE_MIN);

    % Column 3: aHpercent must be in [0, 100]
    X_physical(:, 3) = max(min(X_physical(:, 3), AHPERCENT_MAX), AHPERCENT_MIN);

    % Column 4: Qpermm must be positive
    X_physical(:, 4) = max(X_physical(:, 4), QPERMM_MIN);

    % Column 5: LLrain must be positive
    X_physical(:, 5) = max(X_physical(:, 5), LLRAIN_MIN);

    fprintf('LHS design matrix generated successfully.\n');
    fprintf('Sample ranges:\n');
    for col = 1:NUM_VARS
        fprintf('  %s: [%.4f, %.4f] %s\n', VAR_NAMES{col}, ...
                min(X_physical(:, col)), max(X_physical(:, col)), VAR_UNITS{col});
    end

end