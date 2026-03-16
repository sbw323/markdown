import numpy as np
import pandas as pd

# ==========================================
# 1. FILE & COLUMN MAPPING
# ==========================================
REAL_DATA_PATH = "/Users/aya/github/LEYP_Pipe/Louisa_LEYP_Input_csv.csv" 
SIMULATION_START_YEAR = 2025

COLUMN_MAP = {
    'id': 'PipeID',
    'age': 'Age',
    'condition': 'Condition',
    'material': 'Material',
    'diameter': 'Diameter',
    'length': 'Length',
    'cof': 'CoF_Value'
}

# ==========================================
# 2. LEYP MODEL PARAMETERS (Failure Physics)
# ==========================================
ALPHA = 0.15 

# Weibull Baseline (unchanged)
MATERIAL_PROPS = {
    'PVC':  {'beta': 1.1, 'eta': 100, 'base_mult': 0.8},
    'DIP':  {'beta': 1.5, 'eta': 80,  'base_mult': 1.0},
    'CP':   {'beta': 1.8, 'eta': 60,  'base_mult': 1.2},
    'CIPP': {'beta': 1.2, 'eta': 50,  'base_mult': 0.9},
    'VCP':  {'beta': 1.0, 'eta': 120, 'base_mult': 0.6},
    'Default': {'beta': 1.3, 'eta': 80, 'base_mult': 1.0}
}
COEFF_DIAMETER = -0.02 

# ==========================================
# 3. DEGRADATION PHYSICS
# ==========================================
DEGRADATION_PARAMS = {
    'PVC':  {'ttf_mean': 85, 'ttf_std': 15},
    'DIP':  {'ttf_mean': 60, 'ttf_std': 20}, 
    'CP':   {'ttf_mean': 50, 'ttf_std': 10},
    'CIPP': {'ttf_mean': 40, 'ttf_std': 10}, 
    'VCP':  {'ttf_mean': 100, 'ttf_std': 25},
    'Default': {'ttf_mean': 60, 'ttf_std': 20}
}

# ==========================================
# 4. INVESTMENT HEURISTICS
# ==========================================

# Annual Budget (Total for both Capital and O&M)
ANNUAL_BUDGET = 50000

# Pipe failure replacement cost
GLOBAL_COST_PER_FT = 500

# Default Budget Allocation
# 80% allocated to Capital (Rehab/Replace), 20% to O&M (PM)
DEFAULT_BUDGET_SPLIT = 0.80 

# Unit Costs (Cost = Base * Diameter_Inches * Length_Feet)
COST_MODELS = {
    'Replacement': {'unit_cost_per_inch_ft': 90.00}, # Open cut / Full replace
    'Lining':      {'unit_cost_per_inch_ft': 70.00},  # CIPP
    'Repair':      {'unit_cost_per_inch_ft': 27.00},  # Spot Repair
    'Cleaning':    {'unit_cost_per_inch_ft': 8.00}    # Jetting/Cleaning
}

# Intervention Triggers (Condition Score Thresholds)
TRIGGERS = {
    'PM_Start': 4.0,   
    'PM_Stop':  2.5,   
    'Rehab':    2.0    
}

# Benefit of Actions
PM_CONDITION_BOOST = .500

# ==========================================
# 5. HELPER FUNCTIONS
# ==========================================
def map_condition_to_n_start(rating):
    if pd.isna(rating): return 0
    rating = float(rating)
    if rating >= 5.5: return 0
    if rating >= 4.5: return 0
    if rating >= 3.5: return 1
    if rating >= 2.5: return 2
    if rating >= 1.5: return 3
    return 5