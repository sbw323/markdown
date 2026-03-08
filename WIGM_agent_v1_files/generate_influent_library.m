function generate_influent_library(n_samples, seed, output_dir)
%GENERATE_INFLUENT_LIBRARY Generate complete library of LHS-sampled WIGM influent profiles
%
%   generate_influent_library(n_samples, seed, output_dir)
%
%   PURPOSE:
%   Generates a complete library of Latin Hypercube Sampling-based influent
%   profiles using the BSM ASM3 Wastewater Influent Generator Model (WIGM).
%   Each profile is a 728-day timeseries at 15-minute resolution with 10
%   LHS-sampled input parameters. Supports resume functionality for long
%   generation runs.
%
%   ALGORITHM:
%   1. Apply default arguments and validate inputs
%   2. Generate LHS design matrix using generate_influent_lhs
%   3. Create output directory and save configuration
%   4. Check for resume state and initialize log file
%   5. For each sample: run init script, apply overrides, simulate WIGM
%   6. Save each profile as influent_NNN.mat with error resilience
%   7. Update log, checkpoint progress, clean up Simulink models
%
%   INPUTS:
%   n_samples  — (positive integer) Number of LHS samples. Default: 200.
%   seed       — (non-negative integer) RNG seed. Default: 42.
%   output_dir — (char or string) Output directory path.
%                Default: 'influent_library'.
%
%   OUTPUTS:
%   Files written to output_dir:
%     influent_NNN.mat            — Individual profiles (variable: ASM3_Influent)
%     influent_library_config.mat — Generation configuration
%     influent_library_log.csv    — Per-sample metadata log
%     influent_gen_state.mat      — Resume checkpoint (deleted on completion)
%     influent_library_errors.csv — Error log (if errors occur)
%
%   EXAMPLES:
%   % Generate 200-sample library with default settings
%   generate_influent_library();
%
%   % Generate 50-sample library with custom seed and output directory
%   generate_influent_library(50, 123, 'test_library');
%
%   % Resume interrupted generation (automatically detects state file)
%   generate_influent_library(200, 42, 'influent_library');
%
%   Author: Claude Code Assistant
%   Date: March 2026

    % Configuration constants
    WIGM_MODEL = 'ASM3_Influentmodel';
    SIM_DAYS = 728;
    INIT_SCRIPT = 'ASM3_Influent_init';
    EXPECTED_OUTPUT_COLS = 16;

    % Start timing
    generation_start_time = tic;

    % Apply defaults for missing/empty arguments
    if nargin < 1 || isempty(n_samples)
        n_samples = 200;
    end
    if nargin < 2 || isempty(seed)
        seed = 42;
    end
    if nargin < 3 || isempty(output_dir)
        output_dir = 'influent_library';
    end

    % Input validation
    if ~isscalar(n_samples) || ~isnumeric(n_samples) || n_samples <= 0 || n_samples ~= round(n_samples)
        error('generate_influent_library:invalidNSamples', ...
              'n_samples must be a positive integer scalar');
    end

    if ~isscalar(seed) || ~isnumeric(seed) || seed < 0 || seed ~= round(seed)
        error('generate_influent_library:invalidSeed', ...
              'seed must be a non-negative integer scalar');
    end

    if ~ischar(output_dir) && ~isstring(output_dir)
        error('generate_influent_library:invalidOutputDir', ...
              'output_dir must be a char array or string');
    end

    if isempty(output_dir)
        error('generate_influent_library:emptyOutputDir', ...
              'output_dir cannot be empty');
    end

    % Convert string to char for consistency
    if isstring(output_dir)
        output_dir = char(output_dir);
    end

    % Print header banner
    fprintf('\n');
    fprintf('========================================\n');
    fprintf('   WIGM INFLUENT LIBRARY GENERATION\n');
    fprintf('========================================\n');
    fprintf('Samples:     %d\n', n_samples);
    fprintf('RNG seed:    %d\n', seed);
    fprintf('Output dir:  %s\n', output_dir);
    fprintf('Model:       %s\n', WIGM_MODEL);
    fprintf('Sim days:    %d\n', SIM_DAYS);
    fprintf('========================================\n\n');

    % Generate LHS design matrix
    fprintf('Generating LHS design matrix...\n');
    [X_physical, var_info] = generate_influent_lhs(n_samples, seed);

    % Create output directory if it does not exist
    if ~isfolder(output_dir)
        fprintf('Creating output directory: %s\n', output_dir);
        mkdir(output_dir);
    end

    % Save configuration file
    config_file = fullfile(output_dir, 'influent_library_config.mat');
    save(config_file, 'X_physical', 'var_info', 'n_samples', 'seed', ...
         'SIM_DAYS', 'WIGM_MODEL', 'INIT_SCRIPT');
    fprintf('Configuration saved to: %s\n', config_file);

    % Check for resume state
    state_file = fullfile(output_dir, 'influent_gen_state.mat');
    if isfile(state_file)
        fprintf('Resume state file found. Loading...\n');
        state_data = load(state_file, 'start_idx_next');
        start_idx = state_data.start_idx_next;
        fprintf('Resuming from sample %d\n', start_idx);
    else
        start_idx = 1;
        fprintf('Starting fresh generation from sample 1\n');
    end

    % Initialize log file
    log_file = fullfile(output_dir, 'influent_library_log.csv');
    if ~isfile(log_file)
        fprintf('Initializing log file: %s\n', log_file);
        log_fid = fopen(log_file, 'w');
        if log_fid == -1
            error('generate_influent_library:cannotCreateLog', ...
                  'Cannot create log file: %s', log_file);
        end

        % Write CSV header
        fprintf(log_fid, 'SampleIndex,PE,QperPE,aHpercent,Qpermm,LLrain,');
        fprintf(log_fid, 'CODsol_gperPEperd,CODpart_gperPEperd,SNH_gperPEperd,');
        fprintf(log_fid, 'TKN_gperPEperd,SI_cst,OutputRows,OutputCols,Timestamp\n');
        fclose(log_fid);
    else
        fprintf('Log file exists. Will append new entries.\n');
    end

    % Initialize error tracking
    n_errors = 0;
    n_completed = 0;

    % Main per-sample loop
    fprintf('\nStarting sample generation loop...\n');
    for i = start_idx:n_samples
        fprintf('Sample %d/%d ... ', i, n_samples);

        try
            % 5a. Populate base workspace with defaults via init script
            evalin('base', sprintf('run(''%s'')', INIT_SCRIPT));

            % 5b. Override LHS-sampled variables and dependents
            apply_influent_sample(X_physical(i, :), var_info);

            % 5c. Load and configure Simulink model
            evalin('base', sprintf('load_system(''%s'')', WIGM_MODEL));
            evalin('base', sprintf('set_param(''%s'', ''StopTime'', ''%d'')', ...
                   WIGM_MODEL, SIM_DAYS));

            % 5d. Run simulation
            evalin('base', sprintf('sim(''%s'')', WIGM_MODEL));

            % 5e. Extract output from base workspace
            ASM3_Influent = evalin('base', 'ASM3_Influent');

            % Validate dimensions
            [n_rows, n_cols] = size(ASM3_Influent);
            if n_cols ~= EXPECTED_OUTPUT_COLS
                warning('generate_influent_library:unexpectedColumns', ...
                        'Sample %d: Expected %d columns, got %d', ...
                        i, EXPECTED_OUTPUT_COLS, n_cols);
            end

            % 5f. Save output file
            out_filename = sprintf('influent_%03d.mat', i);
            out_filepath = fullfile(output_dir, out_filename);
            save(out_filepath, 'ASM3_Influent');

            fprintf('saved (%d x %d)\n', n_rows, n_cols);

            % 5g. Append to log CSV
            log_fid = fopen(log_file, 'a');
            if log_fid ~= -1
                % Write sample data
                fprintf(log_fid, '%d', i);
                for j = 1:10
                    fprintf(log_fid, ',%.6f', X_physical(i, j));
                end
                fprintf(log_fid, ',%d,%d,%s\n', n_rows, n_cols, ...
                        string(datetime("now", "Format", "yyyy-MM-dd HH:mm:ss")));
                fclose(log_fid);
            else
                warning('generate_influent_library:cannotWriteLog', ...
                        'Cannot write to log file for sample %d', i);
            end

            % 5h. Checkpoint
            start_idx_next = i + 1;
            save(state_file, 'start_idx_next');

            % 5i. Close Simulink model to free memory
            try
                evalin('base', sprintf('bdclose(''%s'')', WIGM_MODEL));
            catch close_error
                warning('generate_influent_library:cannotCloseModel', ...
                        'Cannot close Simulink model for sample %d: %s', ...
                        i, close_error.message);
            end

            n_completed = n_completed + 1;

        catch sample_error
            % Error handling: log error and continue
            fprintf(2, 'ERROR in sample %d: %s\n', i, sample_error.message);
            n_errors = n_errors + 1;

            % Append to error log
            error_log_file = fullfile(output_dir, 'influent_library_errors.csv');
            error_fid = fopen(error_log_file, 'a');
            if error_fid ~= -1
                % Write header if this is the first error
                if n_errors == 1 && ~isfile(error_log_file)
                    fprintf(error_fid, 'SampleIndex,Timestamp,ErrorMessage\n');
                end

                % Write error data (escape any commas in error message)
                error_msg = strrep(sample_error.message, ',', ';');
                fprintf(error_fid, '%d,%s,"%s"\n', i, ...
                        string(datetime("now", "Format", "yyyy-MM-dd HH:mm:ss")), error_msg);
                fclose(error_fid);
            end

            % Try to close Simulink model even after error
            try
                evalin('base', sprintf('bdclose(''%s'')', WIGM_MODEL));
            catch
                % Ignore errors during cleanup
            end
        end
    end

    % Cleanup: delete state file if all samples completed successfully
    if start_idx == 1 && n_completed == n_samples && n_errors == 0
        if isfile(state_file)
            delete(state_file);
            fprintf('State file deleted (generation completed successfully).\n');
        end
    end

    % Print summary
    elapsed_time = toc(generation_start_time);
    fprintf('\n========================================\n');
    fprintf('   GENERATION COMPLETE\n');
    fprintf('========================================\n');
    fprintf('Samples completed: %d/%d\n', n_completed, n_samples);
    fprintf('Errors occurred:   %d\n', n_errors);
    fprintf('Output directory:  %s\n', output_dir);
    fprintf('Elapsed time:      %.1f minutes\n', elapsed_time / 60);
    fprintf('========================================\n\n');

    if n_errors > 0
        fprintf('Warning: %d errors occurred. Check %s for details.\n', ...
                n_errors, fullfile(output_dir, 'influent_library_errors.csv'));
    end

end