import numpy as np
import math
from leyp_config import MATERIAL_PROPS, ALPHA, COEFF_DIAMETER, DEGRADATION_PARAMS, map_condition_to_n_start

class VirtualSegment:
    def __init__(self, segment_length):
        self.length = segment_length
        self.n_breaks = 0
        self.break_length = 0.0

    def simulate_breaks(self, intensity):
        num_events = np.random.poisson(intensity * 0.25)
        total_len = 0.0
        
        if num_events > 0:
            for _ in range(num_events):
                raw_len = np.random.uniform(-17.32, 17.32)
                actual_len = max(0.0, raw_len)
                total_len += actual_len
        
        self.n_breaks += num_events
        self.break_length += total_len
        
        return num_events, total_len

class Pipe:
    def __init__(self, attributes):
        self.id = attributes['PipeID']
        self.material = attributes['Material']
        self.diameter = attributes['Diameter']
        self.length = attributes['Length']
        self.cof = float(attributes.get('CoF_Value', 1.0))
        
        self.initial_age = attributes['Age'] 
        self.current_condition = float(attributes['Condition']) 
        
        self.is_lined = (self.material == 'CIPP')
        self.cleaning_count = 0 
        
        # --- NEW: Degradation Control ---
        # Changed from boolean to integer to support multi-year immunity
        self.skip_degradation_years = 0
        
        # Virtual Segments
        seg_len = self.length / 4.0
        self.segments = [VirtualSegment(seg_len) for _ in range(4)]
        
        self.reset_physics_params()
        self.update_leyp_state()
        self.has_failed_in_sim = False 

    def reset_physics_params(self):
        mat_params = MATERIAL_PROPS.get(self.material, MATERIAL_PROPS['Default'])
        self.beta = mat_params['beta']
        self.eta = mat_params['eta']
        self.mat_mult = mat_params['base_mult']

        deg_params = DEGRADATION_PARAMS.get(self.material, DEGRADATION_PARAMS['Default'])
        mu_years = deg_params['ttf_mean']
        sigma_years = deg_params['ttf_std']
        
        phi = math.sqrt(sigma_years**2 + mu_years**2)
        log_sigma = math.sqrt(math.log(phi**2 / mu_years**2))
        log_mu = math.log(mu_years**2 / phi)
        
        self.total_ttf_years = max(10, np.random.lognormal(log_mu, log_sigma))
        self.degradation_rate = math.log(6.0) / self.total_ttf_years

    @property
    def current_ttf(self):
        safe_cond = max(1.001, self.current_condition)
        rul = math.log(safe_cond) / self.degradation_rate
        return max(0.1, rul)

    def predict_ttf(self, hypothetical_cond, material_override=None):
        if material_override and material_override != self.material:
            deg_params = DEGRADATION_PARAMS.get(material_override, DEGRADATION_PARAMS['Default'])
            return deg_params['ttf_mean']
        else:
            safe_cond = max(1.001, hypothetical_cond)
            rul = math.log(safe_cond) / self.degradation_rate
            return max(0.1, rul)

    def update_leyp_state(self):
        self.n_breaks = map_condition_to_n_start(self.current_condition)
        if not hasattr(self, 'initial_n_breaks'):
            self.initial_n_breaks = self.n_breaks

    def reset_breaks(self):
        """
        Resets break history for repairs.
        """
        for seg in self.segments:
            seg.n_breaks = 0
            seg.break_length = 0.0
        self.update_leyp_state()

    def degrade(self, dt=1.0):
        # --- NEW: Multi-Year Skip Logic ---
        if self.skip_degradation_years > 0:
            self.skip_degradation_years -= 1
            # We skip the decay math for this year
            return 

        decay_factor = math.exp(-self.degradation_rate * dt)
        self.current_condition *= decay_factor
        self.current_condition = max(1.0, min(6.0, self.current_condition))
        self.update_leyp_state()

    def calculate_hazard(self, sim_year_idx):
        current_age = self.initial_age + sim_year_idx
        t = max(current_age, 0.1) 
        h0 = (self.beta / self.eta) * ((t / self.eta) ** (self.beta - 1))
        cov_factor = self.mat_mult * np.exp(COEFF_DIAMETER * self.diameter)
        leyp_factor = 1.0 + (ALPHA * self.n_breaks)
        return h0 * cov_factor * leyp_factor

    def simulate_year(self, sim_year_idx):
        intensity = self.calculate_hazard(sim_year_idx)
        total_new_breaks = 0
        total_new_break_len = 0.0
        
        for seg in self.segments:
            n, length = seg.simulate_breaks(intensity)
            total_new_breaks += n
            total_new_break_len += length
            
        if total_new_breaks > 0:
            damage = 0.5 * total_new_breaks
            self.current_condition = max(1.0, self.current_condition - damage)
            
            cumulative_break_len = sum(s.break_length for s in self.segments)
            if cumulative_break_len > (0.5 * self.length):
                self.current_condition = 1.0 
                
            self.update_leyp_state()
            return True
            
        return False