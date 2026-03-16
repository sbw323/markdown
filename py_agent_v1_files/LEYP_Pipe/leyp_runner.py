import pandas as pd
import numpy as np
import os
from leyp_config import COLUMN_MAP, ANNUAL_BUDGET, GLOBAL_COST_PER_FT
from leyp_core import Pipe
from leyp_investment import InvestmentManager 

# Hardcoded Global Cost if not in config (Matches Investment Manager default)
DEFAULT_GLOBAL_COST = GLOBAL_COST_PER_FT

def run_simulation(use_mock_data=False, override_input_path=None, output_dir=None, 
                   annual_budget=None, pm_start=None, pm_stop=None, rehab_trigger=None, 
                   budget_split=None, generate_report=False):
    
    # --- A. LOAD DATA ---
    if use_mock_data:
        from leyp_config import REAL_DATA_PATH 
        target_file = REAL_DATA_PATH
    else:
        from leyp_config import REAL_DATA_PATH
        target_file = override_input_path if override_input_path else REAL_DATA_PATH
        
    try:
        raw_df = pd.read_csv(target_file)
    except Exception as e:
        raise FileNotFoundError(f"Could not load input: {e}")

    # --- B. INITIALIZE NETWORK ---
    network = []
    for _, row in raw_df.iterrows():
        pipe_attrs = {}
        for csv_header, internal_key in COLUMN_MAP.items():
            pipe_attrs[internal_key] = row.get(csv_header, None)
            
        # Default CoF to 1.0 if missing (prevents crashes)
        if pipe_attrs.get('CoF_Value') is None:
            pipe_attrs['CoF_Value'] = 1.0
            
        network.append(Pipe(pipe_attrs))

    # --- C. INITIALIZE MANAGER ---
    use_budget = annual_budget if annual_budget is not None else ANNUAL_BUDGET
    
    invest_manager = InvestmentManager(
        budget=use_budget,
        pm_start=pm_start,
        pm_stop=pm_stop,
        rehab_trigger=rehab_trigger,
        budget_split=budget_split,
        risk_cost_per_ft=DEFAULT_GLOBAL_COST
    )
    
    # --- D. MAIN LOOP (100 Years) ---
    results_risk_cost = 0.0
    results_invest_cost = 0.0
    
    # Track Cumulative Failures to avoid double-counting costs for the same pipe
    failed_pipes = set()
    
    for year in range(1, 101):
        # 1. PHYSICS (Degradation)
        # Apply natural aging to all pipes
        for pipe in network: 
            pipe.degrade()
            
        # 2. INVESTMENT (Strategy)
        # Manager spends budget to improve condition (and resets age if replaced)
        # We pass 'year' so replaced pipes get correct negative initial_age
        report = invest_manager.run_year(network, year)
        results_invest_cost += report['Total_Spend']
        
        # 3. RISK (Failures & Breaks)
        for pipe in network:
            # Skip pipes that have already failed and haven't been replaced
            # (If a pipe failed, it sits at 1.0 until Investment Manager fixes it next year)
            if pipe.current_condition <= 1.001 and pipe.id in failed_pipes:
                continue

            # Run Monte Carlo Break Simulation (Virtual Segments)
            # This returns True if ANY breaks occurred
            breaks_occurred = pipe.simulate_year(year)
            
            # CHECK FOR FAILURE
            # Failure can happen if:
            # a) Natural degradation hits 1.0
            # b) Break Length > 50% (Overrides condition to 1.0 inside simulate_year)
            
            if pipe.current_condition <= 1.001:
                if pipe.id not in failed_pipes:
                    # Mark as failed
                    failed_pipes.add(pipe.id)
                    pipe.has_failed_in_sim = True
                    
                    # Calculate Consequence Cost
                    # Cost = Length * CoF * Global_Cost ($500/ft)
                    fail_cost = pipe.length * pipe.cof * DEFAULT_GLOBAL_COST
                    results_risk_cost += fail_cost
                    
            # Note: If pipe is fixed later by Investment Manager, 
            # we should remove it from 'failed_pipes' set.
            # However, since Investment happens BEFORE Risk in the loop,
            # a fixed pipe is already "clean" for this year. 
            # We just need to ensure if a pipe IS fixed, we allow it to fail again in future.
            if pipe.current_condition > 1.5 and pipe.id in failed_pipes:
                failed_pipes.remove(pipe.id)

    # --- E. RETURN VALUES ---
    if generate_report:
        # Create DataFrame from the manager's action log
        action_log_df = pd.DataFrame(invest_manager.action_log)
        return results_invest_cost, results_risk_cost, action_log_df
    else:
        return results_invest_cost, results_risk_cost