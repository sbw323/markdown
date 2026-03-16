import pandas as pd
import yaml
import os
import itertools
import time
from leyp_config import COLUMN_MAP

# Import logic from our modules
from leyp_strategy_applicator import load_strategies, apply_strategy_logic
from leyp_preprocessor import preprocess_network
from leyp_runner import run_simulation

# Configuration File for the Orchestrator
ORCH_CONFIG_FILE = "/Users/aya/github/LEYP_Pipe/orchestrator_config.yaml"

def load_orch_config():
    if not os.path.exists(ORCH_CONFIG_FILE):
        raise FileNotFoundError(f"Missing config file: {ORCH_CONFIG_FILE}")
    with open(ORCH_CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f)

def run_orchestrator():
    print("=== LEYP Simulation Orchestrator ===")
    
    # 1. Load Configurations
    config = load_orch_config()
    strategies = load_strategies()
    
    raw_input_path = config['master_input_file']
    base_output_dir = config['output_base_dir']
    
    # NEW: Load Simulation Settings
    sim_settings = config.get('simulation_settings', {})
    budget_override = sim_settings.get('annual_budget', 500000)
    skip_seg = sim_settings.get('skip_segmentation', False)
    
    print(f"Global Settings: Budget=${budget_override:,.0f}/yr | Segmentation={'OFF' if skip_seg else 'ON'}")

    # 2. Load Master Data
    print(f"Loading Master Dataset: {raw_input_path}")
    try:
        master_df = pd.read_csv(raw_input_path)
    except FileNotFoundError:
        print(f"CRITICAL ERROR: Input file '{raw_input_path}' not found.")
        return

    # 3. Define Combinations
    pm_options = list(strategies['Maintenance'].keys())
    rehab_options = list(strategies['Rehabilitation'].keys())
    
    combinations = []
    if config.get('run_mode') == 'ALL':
        combinations = list(itertools.product(pm_options, rehab_options))
    else:
        specs = config.get('specific_combinations', [])
        for spec in specs:
            combinations.append((spec['pm'], spec['rehab']))
            
    print(f"Prepared {len(combinations)} scenarios to execute.\n")
    time.sleep(1)

    # 4. Main Execution Loop
    for i, (pm_name, rehab_name) in enumerate(combinations):
        scenario_label = f"{pm_name}__vs__{rehab_name}"
        print(f"--- Running Scenario {i+1}/{len(combinations)}: {scenario_label} ---")
        
        # Define Paths
        scenario_output_dir = os.path.join(base_output_dir, pm_name, rehab_name)
        os.makedirs(scenario_output_dir, exist_ok=True)
        
        temp_input_csv = "temp_scenario_input.csv"
        temp_opt_csv = "temp_scenario_opt.csv"

        # --- STEP A: STRATEGY APPLICATOR ---
        df_temp = master_df.copy()
        df_temp.rename(columns=COLUMN_MAP, inplace=True)
        
        try:
            df_temp, _ = apply_strategy_logic(df_temp, strategies, pm_name, rehab_name)
        except Exception as e:
             print(f"  [Error] Strategy Application failed: {e}")
             continue

        reverse_map = {v: k for k, v in COLUMN_MAP.items()}
        df_temp.rename(columns=reverse_map, inplace=True)
        df_temp.to_csv(temp_input_csv, index=False)

        # --- STEP B: PREPROCESSOR ---
        try:
            preprocess_network(
                input_path=temp_input_csv, 
                output_path=temp_opt_csv,
                skip_segmentation=skip_seg # NEW: Pass flag
            )
        except Exception as e:
            print(f"  [Error] Preprocessor failed: {e}")
            continue

        # --- STEP C: RUNNER ---
        try:
            run_simulation(
                use_mock_data=False, 
                override_input_path=temp_opt_csv, 
                output_dir=scenario_output_dir,
                annual_budget=budget_override # NEW: Pass budget
            )
            print(f"  [Success] Results saved to: {scenario_output_dir}")
        except Exception as e:
            print(f"  [Error] Simulation failed: {e}")

        # Cleanup
        if os.path.exists(temp_input_csv): os.remove(temp_input_csv)
        if os.path.exists(temp_opt_csv): os.remove(temp_opt_csv)
        
        print("") 

    print("=== Batch Run Complete ===")
    print(f"All results stored in: {base_output_dir}")

if __name__ == "__main__":
    run_orchestrator()