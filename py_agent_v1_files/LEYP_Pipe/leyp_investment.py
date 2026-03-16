import pandas as pd
import numpy as np
import math
from leyp_config import COST_MODELS, TRIGGERS, PM_CONDITION_BOOST, DEFAULT_BUDGET_SPLIT, GLOBAL_COST_PER_FT

class InvestmentManager:
    def __init__(self, budget, pm_start=None, pm_stop=None, rehab_trigger=None, 
                 budget_split=None, risk_cost_per_ft=GLOBAL_COST_PER_FT):
        self.total_budget = budget
        self.split_ratio = budget_split if budget_split is not None else DEFAULT_BUDGET_SPLIT
        self.risk_cost_per_ft = GLOBAL_COST_PER_FT
        
        self.rehab_limit = self.total_budget * self.split_ratio
        self.pm_limit = self.total_budget * (1.0 - self.split_ratio)
        
        self.rehab_spend = 0.0
        self.pm_spend = 0.0
        
        self.pm_start = pm_start if pm_start is not None else TRIGGERS['PM_Start']
        self.pm_stop = pm_stop if pm_stop is not None else TRIGGERS['PM_Stop']
        self.rehab_trigger = rehab_trigger if rehab_trigger is not None else TRIGGERS['Rehab']
        
        self.action_log = []

    def calculate_cost(self, pipe, action_type):
        rate = COST_MODELS[action_type]['unit_cost_per_inch_ft']
        # Note: Keeps existing logic (ignoring diameter) as requested
        return rate * pipe.length

    def get_annualized_risk(self, pipe, ttf_years):
        total_consequence = pipe.cof * pipe.length * self.risk_cost_per_ft
        return total_consequence / ttf_years

    def assess_needs(self, network, current_year):
        rehab_candidates = []
        pm_candidates = []
        
        for pipe in network:
            cond = pipe.current_condition
            
            # 1. REHAB ANALYSIS
            if cond <= self.rehab_trigger:
                cumulative_break_len = sum(s.break_length for s in pipe.segments)
                if cumulative_break_len >= pipe.length*0.67 or pipe.is_lined:
                    action = 'Replacement'
                    target_mat = 'PVC'
                else:
                    action = 'Lining'
                    target_mat = 'CIPP'
                
                cost = self.calculate_cost(pipe, action)
                current_risk = self.get_annualized_risk(pipe, pipe.current_ttf)
                future_ttf = pipe.predict_ttf(6.0, material_override=target_mat)
                future_risk = self.get_annualized_risk(pipe, future_ttf)
                
                benefit = max(0, current_risk - future_risk)
                priority = benefit / max(cost, 1.0)
                
                rehab_candidates.append({
                    'pipe': pipe, 'action': action, 'cost': cost, 'priority': priority
                })
            
            # 2. PM ANALYSIS
            elif self.pm_stop < cond <= self.pm_start:
                if pipe.n_breaks > 1: 
                    action = 'Repair'
                    cost = self.calculate_cost(pipe, action)
                    
                    # Repair Benefit: Boost Condition (Extend TTF)
                    current_risk = self.get_annualized_risk(pipe, pipe.current_ttf)
                    future_cond = min(6.0, cond + PM_CONDITION_BOOST)
                    future_ttf = pipe.predict_ttf(future_cond)
                    future_risk = self.get_annualized_risk(pipe, future_ttf)
                    
                    benefit = max(0, current_risk - future_risk)
                    priority = benefit / max(cost, 1.0)
                    
                else: 
                    action = 'Cleaning'
                    cost = self.calculate_cost(pipe, action)
                    
                    # --- NEW STRATEGY: Hybrid Benefit (Boost + Immunity) ---
                    DURATION = 1.0
                    HALF_BOOST = 0.0 * PM_CONDITION_BOOST
                    
                    # Scenario A: Do Nothing (Degrade for 5 years)
                    decay_factor = math.exp(-pipe.degradation_rate * DURATION)
                    degraded_cond = max(1.0, cond * decay_factor)
                    risk_future_neglected = self.get_annualized_risk(pipe, pipe.predict_ttf(degraded_cond))
                    
                    # Scenario B: Clean (Boost Condition + Maintain for 5 years)
                    # 1. Apply Boost
                    boosted_cond = min(6.0, cond + HALF_BOOST)
                    # 2. Assume boosted condition is maintained (Immunity)
                    risk_cleaned = self.get_annualized_risk(pipe, pipe.predict_ttf(boosted_cond))
                    
                    # Benefit is the difference between Neglect and Cleaned state
                    benefit = max(0, risk_future_neglected - risk_cleaned)
                    priority = benefit / max(cost, 1.0)
                
                pm_candidates.append({
                    'pipe': pipe, 'action': action, 'cost': cost, 'priority': priority
                })
                
        return rehab_candidates, pm_candidates

    def run_year(self, network, current_year):
        self.rehab_spend = 0.0
        self.pm_spend = 0.0
        
        rehab_list, pm_list = self.assess_needs(network, current_year)
        
        rehab_list.sort(key=lambda x: x['priority'], reverse=True)
        pm_list.sort(key=lambda x: x['priority'], reverse=True)
        
        executed_count = {'Replacement': 0, 'Lining': 0, 'Repair': 0, 'Cleaning': 0}
        
        for plan in rehab_list:
            if self.rehab_spend + plan['cost'] <= self.rehab_limit:
                self.execute_action(plan, current_year)
                self.rehab_spend += plan['cost']
                executed_count[plan['action']] += 1
            else: continue 

        for plan in pm_list:
            if self.pm_spend + plan['cost'] <= self.pm_limit:
                self.execute_action(plan, current_year)
                self.pm_spend += plan['cost']
                executed_count[plan['action']] += 1
            else: continue

        return {
            'Year': current_year,
            'Total_Spend': self.rehab_spend + self.pm_spend,
            'Rehab_Spend': self.rehab_spend,
            'PM_Spend': self.pm_spend,
            'PM_Count': executed_count['Repair'] + executed_count['Cleaning'],
            'Rehab_Count': executed_count['Replacement'] + executed_count['Lining']
        }

    def execute_action(self, plan, current_year):
        pipe = plan['pipe']
        action = plan['action']
        
        log_entry = {
            'Year': current_year,
            'PipeID': pipe.id,
            'Action': action,
            'Cost': plan['cost'],
            'Priority_Score': plan['priority'],
            'Condition_Before': pipe.current_condition
        }
        self.action_log.append(log_entry)
        
        if action == 'Replacement':
            pipe.material = 'PVC'
            pipe.current_condition = 6.0
            pipe.initial_age = -current_year 
            pipe.is_lined = False
            pipe.reset_physics_params()
            pipe.reset_breaks() 
            
        elif action == 'Lining':
            pipe.material = 'CIPP'
            pipe.current_condition = 4.0
            pipe.initial_age = -current_year
            pipe.is_lined = True
            pipe.reset_physics_params()
            pipe.reset_breaks() 
            
        elif action == 'Repair':
            new_cond = pipe.current_condition + PM_CONDITION_BOOST
            pipe.current_condition = min(6.0, new_cond)
            pipe.reset_breaks()
            
        elif action == 'Cleaning':
            # --- NEW: Grant 5 years immunity + Half Boost ---
            pipe.skip_degradation_years = 1
            
            # Apply Half Boost
            new_cond = pipe.current_condition + (0.0 * PM_CONDITION_BOOST)
            pipe.current_condition = min(6.0, new_cond)
            
        pipe.update_leyp_state()