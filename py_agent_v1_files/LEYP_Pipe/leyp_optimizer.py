import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import os
import time
import yaml
from pymoo.core.problem import ElementwiseProblem
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.optimize import minimize
from pymoo.termination import get_termination
from pymoo.operators.sampling.rnd import FloatRandomSampling
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM

from leyp_runner import run_simulation
from leyp_preprocessor import preprocess_network

CONFIG_FILE = "optimizer_config.yaml"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"Missing config file: {CONFIG_FILE}")
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f)

class LEYP_Problem(ElementwiseProblem):
    def __init__(self, config, input_file_path):
        genes = config['genes']
        
        super().__init__(
            n_var=5,             # Budget, PM_Start, PM_Stop, Rehab, Split
            n_obj=2,             # Cost, Risk
            n_ieq_constr=1,      # Constraint: PM_Start > PM_Stop
            xl=np.array([
                genes['budget']['min'], 
                genes['pm_start']['min'], 
                genes['pm_stop']['min'], 
                genes['rehab_trigger']['min'],
                genes['budget_split']['min']
            ]),
            xu=np.array([
                genes['budget']['max'], 
                genes['pm_start']['max'], 
                genes['pm_stop']['max'], 
                genes['rehab_trigger']['max'],
                genes['budget_split']['max']
            ])
        )
        self.input_file = input_file_path

    def _evaluate(self, x, out, *args, **kwargs):
        # Unpack 5 Genes
        budget, pm_start, pm_stop, rehab_trigger, split = x[0], x[1], x[2], x[3], x[4]
        
        # Constraint: PM_Stop < PM_Start
        g1 = pm_stop - pm_start + 0.1 
        
        try:
            # Standard optimization run (generate_report=False by default)
            inv_cost, risk_cost = run_simulation(
                use_mock_data=False,
                override_input_path=self.input_file,
                annual_budget=budget,
                pm_start=pm_start,
                pm_stop=pm_stop,
                rehab_trigger=rehab_trigger,
                budget_split=split
            )
        except Exception as e:
            print(f"[Optimizer Error] {e}")
            inv_cost, risk_cost = 1e9, 1e9
        
        out["F"] = [inv_cost, risk_cost]
        out["G"] = [g1]

def run_optimization():
    print("=== LEYP Genetic Optimizer (NSGA-II) ===")
    config = load_config()
    raw_input = config['master_input_file']
    output_dir = config['output_base_dir']
    skip_seg = config.get('skip_segmentation', False)
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Preprocessing
    optimized_input_path = "temp_optimization_input.csv"
    try:
        preprocess_network(input_path=raw_input, output_path=optimized_input_path, skip_segmentation=skip_seg)
    except Exception as e:
        print(f"Data Prep Error: {e}")
        return

    # Algorithm Setup
    alg = config['algorithm']
    algorithm = NSGA2(
        pop_size=alg['pop_size'],
        n_offsprings=alg['n_offsprings'],
        sampling=FloatRandomSampling(),
        crossover=SBX(prob=0.9, eta=15),
        mutation=PM(prob=0.2, eta=20),
        eliminate_duplicates=True
    )
    termination = get_termination("n_gen", alg['n_gen'])
    
    print(f"Starting Evolution ({alg['n_gen']} gens)...")
    res = minimize(LEYP_Problem(config, optimized_input_path), algorithm, termination, seed=alg['seed'], verbose=True)
    
    # Results Processing
    cols = ["Investment_Cost", "Risk_Cost"]
    df = pd.DataFrame(res.F, columns=cols)
    df["Budget"] = res.X[:, 0]
    df["PM_Start"] = res.X[:, 1]
    df["PM_Stop"] = res.X[:, 2]
    df["Rehab_Trigger"] = res.X[:, 3]
    df["Split_Ratio"] = res.X[:, 4] 
    
    df["Total_Cost"] = df["Investment_Cost"] + df["Risk_Cost"]
    
    results_path = os.path.join(output_dir, "nsga2_results.csv")
    df.to_csv(results_path, index=False)
    print(f"Optimization results saved to {results_path}")
    
    # --- VICTORY LAP: Generate Detailed Schedule for Best Strategy ---
    print("\n--- Generating Optimal Action Plan ---")
    
    # 1. Identify Best Strategy
    best_idx = df["Total_Cost"].idxmin()
    best = df.loc[best_idx]
    
    print(f"Best Strategy Found: Total Cost ${best['Total_Cost']:,.0f}")
    print(f"Parameters: Budget=${best['Budget']:,.0f} | PM {best['PM_Start']:.2f}-{best['PM_Stop']:.2f} | Split {best['Split_Ratio']:.2%}")
    
    # 2. Re-Run Simulation with Logging Enabled
    try:
        _, _, action_log_df = run_simulation(
            use_mock_data=False,
            override_input_path=optimized_input_path,
            annual_budget=best["Budget"],
            pm_start=best["PM_Start"],
            pm_stop=best["PM_Stop"],
            rehab_trigger=best["Rehab_Trigger"],
            budget_split=best["Split_Ratio"],
            generate_report=True # <--- TRIGGERS THE REPORT
        )
        
        # 3. Save the Schedule
        schedule_path = os.path.join(output_dir, "Optimal_Action_Plan.csv")
        action_log_df.to_csv(schedule_path, index=False)
        print(f"Detailed Action Plan saved to: {schedule_path}")
        
    except Exception as e:
        print(f"Error generating action plan: {e}")

    # Visualization
    plt.figure(figsize=(10, 6))
    df.sort_values("Investment_Cost", inplace=True)
    
    plt.plot(df["Investment_Cost"], df["Investment_Cost"], 'b--', alpha=0.5, label="Investment")
    plt.plot(df["Investment_Cost"], df["Risk_Cost"], 'r--', alpha=0.5, label="Risk")
    plt.plot(df["Investment_Cost"], df["Total_Cost"], 'k-', linewidth=2, label="Total Cost")
    
    plt.scatter(best["Investment_Cost"], best["Total_Cost"], c='g', s=150, zorder=5, label="Optimum")
    
    plt.title(f"Optimal Strategy\nBudget: ${best['Budget']:,.0f} | Split: {best['Split_Ratio']:.0%} Rehab")
    plt.xlabel("Investment ($)")
    plt.ylabel("Total Cost ($)")
    plt.legend()
    plt.grid(True)
    plt.savefig(os.path.join(output_dir, "optimization_curve.png"))
    print("Done.")

if __name__ == "__main__":
    run_optimization()