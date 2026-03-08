function apply_influent_sample(sample_row, var_info)
%APPLY_INFLUENT_SAMPLE Override WIGM variables and dependents in base workspace
%
%   apply_influent_sample(sample_row, var_info)
%
%   PURPOSE:
%   Overrides the 10 LHS-sampled WIGM variables and their dependent variables
%   in the MATLAB base workspace. This function is called AFTER
%   ASM3_Influent_init.m has populated the base workspace with defaults,
%   and BEFORE sim() runs the WIGM Simulink model.
%
%   ALGORITHM:
%   1. Validates inputs (sample_row as 1x10 double, var_info struct)
%   2. Assigns 10 primary variables to base workspace via assignin
%   3. Reads factor1 and factor3 from base workspace via evalin
%   4. Computes and assigns all dependent variables using exact formulas
%      from ASM3_Influent_init.m
%
%   INPUTS:
%   sample_row — (1x10 double) One row of X_physical from generate_influent_lhs.
%                Column order matches var_info.names.
%   var_info   — (1x1 struct) The metadata struct returned by generate_influent_lhs.
%                Must contain field 'names' with 10 MATLAB variable names.
%
%   OUTPUTS:
%   None. All variables are assigned to MATLAB base workspace.
%
%   EXAMPLES:
%   % Generate LHS samples and apply first sample
%   [X, info] = generate_influent_lhs(100, 42);
%   evalin('base', 'run(''ASM3_Influent_init.m'')');
%   apply_influent_sample(X(1,:), info);
%
%   VARIABLE MAPPING (sample_row columns -> var_info.names):
%   Column 1:  PE                 — Population equivalent (x1000 inhabitants)
%   Column 2:  QperPE             — Flow rate per PE (L/d per PE)
%   Column 3:  aHpercent          — Percentage impervious area (%)
%   Column 4:  Qpermm             — Flow rate per mm rain (m3/mm rain)
%   Column 5:  LLrain             — Rain limit (mm rain/d)
%   Column 6:  CODsol_gperPEperd  — Soluble COD load (g COD/(d PE))
%   Column 7:  CODpart_gperPEperd — Particulate COD load (g COD/(d PE))
%   Column 8:  SNH_gperPEperd     — Ammonium load (g N/(d PE))
%   Column 9:  TKN_gperPEperd     — TKN load (g N/(d PE))
%   Column 10: SI_cst             — SI constant (g COD/m3)
%
%   Author: Claude Code Assistant
%   Date: March 2026

    arguments
        sample_row (1,10) double
        var_info (1,1) struct
    end

    % Validate var_info structure
    if ~isfield(var_info, 'names')
        error('apply_influent_sample:invalidVarInfo', ...
              'var_info must be a struct with field ''names''');
    end

    if ~iscell(var_info.names) || length(var_info.names) ~= 10
        error('apply_influent_sample:invalidVarInfoNames', ...
              'var_info.names must be a cell array with 10 entries');
    end

    % Assign the 10 primary variables to base workspace
    for j = 1:10
        assignin('base', var_info.names{j}, sample_row(j));
    end

    % Read factor1 and factor3 from base workspace (set by ASM3_Influent_init.m)
    try
        factor1 = evalin('base', 'factor1');
        factor3 = evalin('base', 'factor3');
    catch ME
        error('apply_influent_sample:factorsNotFound', ...
              'Cannot read factor1 and factor3 from base workspace. Ensure ASM3_Influent_init.m has been run first.\nOriginal error: %s', ...
              ME.message);
    end

    % Read sampled values into local variables for clarity
    PE_val = sample_row(1);          % PE
    QperPE_val = sample_row(2);      % QperPE
    CODsol_val = sample_row(6);      % CODsol_gperPEperd
    CODpart_val = sample_row(7);     % CODpart_gperPEperd
    SNH_val = sample_row(8);         % SNH_gperPEperd
    TKN_val = sample_row(9);         % TKN_gperPEperd
    SI_val = sample_row(10);         % SI_cst

    % Compute and assign dependent variables to base workspace
    % From PE and QperPE
    assignin('base', 'QHHsatmax', QperPE_val * 50);

    % From CODsol_gperPEperd and PE
    assignin('base', 'CODsol_HH_max', 20 * CODsol_val * PE_val);
    assignin('base', 'CODsol_HH_nv', factor1 * 2 * CODsol_val * PE_val);

    % From CODpart_gperPEperd and PE
    assignin('base', 'CODpart_HH_max', 20 * CODpart_val * PE_val);
    assignin('base', 'CODpart_HH_nv', factor1 * CODpart_val * PE_val);

    % From SNH_gperPEperd and PE
    assignin('base', 'SNH_HH_max', 20 * SNH_val * PE_val);
    assignin('base', 'SNH_HH_nv', factor1 * 2 * SNH_val * PE_val);

    % From TKN_gperPEperd and PE
    assignin('base', 'TKN_HH_max', 20 * TKN_val * PE_val);
    assignin('base', 'TKN_HH_nv', factor1 * 1.5 * TKN_val * PE_val);

    % From SI_cst
    assignin('base', 'SI_nv', factor3 * SI_val);
    assignin('base', 'Si_in', SI_val);
    assignin('base', 'SI_max', 100 * SI_val);

end