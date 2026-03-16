# LEYP-Pipe Refactoring Plan: Sewer → Water CIP Optimizer

**Date**: March 15, 2026
**Scope**: Refactor the existing sewer CIP optimization package into a water main replacement planning tool
**Estimated effort**: ~16 working hours (2 focused days)
**Decision**: Refactor existing code — not a rewrite

---

## Executive summary

The existing sewer CIP optimizer is built on LEYP-family physics (Weibull hazard, Poisson break simulation on virtual sub-segments, LEYP feedback parameter) and NSGA-II multi-objective optimization. The water model is a *simplification* of the sewer model: one intervention type (replacement) instead of four, two optimizer genes instead of five, and no condition improvement until replacement. The simulation loop, hazard engine, sub-segment break model, and optimizer wrapper transfer directly. The investment logic needs the most surgery but becomes substantially smaller.

The sub-segment model is the most valuable reusable component. It directly supports the proposed point-break accumulation and segment-level failure threshold, which produces three distinct cost streams (planned CIP, emergency repair, emergency replacement) for the optimizer to minimize.

---

## Model differences: Sewer vs. Water

| Aspect | Current sewer model | Target water model |
|---|---|---|
| Intervention types | 4 (Replacement, Lining, Repair, Cleaning) | 1 (Replacement only) |
| Condition recovery | Repair boosts +0.5, cleaning grants immunity | None until replacement |
| Optimizer genes | 5 (budget, PM start/stop, rehab trigger, split) | 2 (budget, rehab trigger) |
| Optimizer constraints | 1 (PM_stop < PM_start) | 0 |
| Budget allocation | Dual pool (capital + O&M with split ratio) | Single pool (capital only) |
| Break cost model | No per-break cost; failure = CoF × length × $500/ft | Per-break emergency repair cost + failure = emergency replacement at penalty rate |
| Sub-segment failure | Cumulative break *length* > 50% of pipe → fail | Point-break *count* on any segment > threshold → fail |
| Condition initialization | Direct from CSV condition score | Interpolated from age ÷ standard useful life |
| Break history initialization | Mapped from condition score (0–5 breaks) | Uniform random draw scaled by age |
| Materials | PVC, DIP, CP, CIPP, VCP | CI, DIP, AC, PVC, PCCP, CU, HDPE, Steel |
| Primary outputs | Pareto front + action plan | Pareto front + action plan + validation curve (% breaks avoided) |

---

## Module-by-module reuse assessment

| Module | Reuse | Action | Key changes |
|---|---|---|---|
| `leyp_config.py` | 70% | Modify | Swap material tables, delete PM/cleaning params, add standard life tables and emergency cost params |
| `leyp_core.py` | 60% | Modify | Rework Pipe.__init__ for age-based condition + break seeding. Simplify VirtualSegment to point-break counts. Remove degradation skip logic |
| `leyp_investment.py` | 25% | Rewrite as `ReplacementManager` | Delete 100+ lines of PM/cleaning/repair logic. Keep risk-based prioritization. Add emergency replacement pathway |
| `leyp_runner.py` | 75% | Modify | Three-cost-stream accounting. Add validation curve generation. Remove PM phase from loop |
| `leyp_optimizer.py` | 80% | Modify | 2 genes, 0 constraints, updated cost accounting. Add validation curve to outputs |
| `leyp_preprocessor.py` | 90% | Minor | Adjust default segment length. Otherwise unchanged |
| `leyp_orchestrator.py` | 0% | Delete | No strategy combinations to enumerate |
| `optimizer_config.yaml` | 60% | Modify | 2-gene bounds, water budget ranges, new economic params |

---

## Three-cost-stream model

The optimizer minimizes two objectives derived from three cost streams:

```
Objective 1 (Investment Cost)  = Σ planned CIP replacement spend
Objective 2 (Risk Cost)        = Σ emergency repair costs + Σ emergency replacement costs
```

The economic logic:

- **Planned CIP replacement**: Proactive, budget-constrained, at standard unit cost. Resets pipe to new condition. This is the only thing the decision-maker controls.
- **Emergency repair cost**: Incurred per point-break event on pipes that haven't yet failed. Represents dig-and-patch reactive maintenance. Unavoidable for any pipe still in service — the optimizer reduces this by replacing high-break-rate pipes before they accumulate events.
- **Emergency replacement cost**: Triggered when any sub-segment exceeds the point-break threshold. Significantly more expensive than planned CIP (3–5× multiplier). Represents the penalty for failure to proactively replace.

The ratio between CIP unit cost and emergency replacement unit cost is the primary economic lever. A higher penalty ratio gives the optimizer stronger incentive to replace proactively.

---

## Sub-segment mechanics (refactored)

Each pipe has N virtual sub-segments (default 4). Each segment tracks a cumulative point-break count. Each year:

1. Pipe-level hazard intensity is calculated from Weibull baseline × material covariate × LEYP feedback
2. Each segment draws Poisson-distributed break events at intensity proportional to its length
3. Each new break event adds a per-break emergency repair cost to the risk accumulator
4. If any segment's cumulative count reaches the threshold, the pipe is declared failed and emergency-replaced at penalty cost
5. Break events also degrade condition (no recovery possible) — this feeds back into the LEYP factor for future years

The segment-level failure threshold creates a physically realistic model where a localized weak spot (corroded joint, bedding failure) can kill a pipe even if the overall pipe-level statistics look moderate. This produces better risk differentiation on the validation curve.

---

## Implementation phases

### Phase 1 — Strip and simplify (morning, ~4 hours)

**Goal**: Get the existing loop running with replacement-only logic. Proves the architecture works before changing physics.

**Task 1.1 — `leyp_config.py`** (~45 min)

Delete:
- `COST_MODELS` entries for Lining, Repair, Cleaning
- `TRIGGERS['PM_Start']`, `TRIGGERS['PM_Stop']`
- `PM_CONDITION_BOOST`
- `DEFAULT_BUDGET_SPLIT`

Add:
```python
# Water material standard useful lives (AWWA/EPA industry data)
STANDARD_LIFE = {
    'CI':    {'base_life': 100, 'min_life': 75,  'max_life': 120},
    'DIP':   {'base_life': 100, 'min_life': 80,  'max_life': 110},
    'AC':    {'base_life': 75,  'min_life': 50,  'max_life': 90},
    'PVC':   {'base_life': 110, 'min_life': 90,  'max_life': 130},
    'PCCP':  {'base_life': 75,  'min_life': 50,  'max_life': 100},
    'CU':    {'base_life': 70,  'min_life': 50,  'max_life': 80},
    'HDPE':  {'base_life': 100, 'min_life': 80,  'max_life': 120},
    'Steel': {'base_life': 60,  'min_life': 40,  'max_life': 80},
    'Default': {'base_life': 80, 'min_life': 60, 'max_life': 100}
}

# Update MATERIAL_PROPS with water-appropriate Weibull parameters
MATERIAL_PROPS = {
    'CI':    {'beta': 1.8, 'eta': 90,  'base_mult': 1.2},
    'DIP':   {'beta': 1.5, 'eta': 95,  'base_mult': 1.0},
    'AC':    {'beta': 2.0, 'eta': 65,  'base_mult': 1.5},
    'PVC':   {'beta': 1.1, 'eta': 110, 'base_mult': 0.7},
    'PCCP':  {'beta': 2.2, 'eta': 70,  'base_mult': 1.3},
    'CU':    {'beta': 1.6, 'eta': 65,  'base_mult': 1.1},
    'HDPE':  {'beta': 1.0, 'eta': 100, 'base_mult': 0.6},
    'Steel': {'beta': 2.0, 'eta': 55,  'base_mult': 1.4},
    'Default': {'beta': 1.3, 'eta': 80, 'base_mult': 1.0}
}

# Sub-segment configuration
N_SEGMENTS_PER_PIPE = 4
SEGMENT_BREAK_THRESHOLD = 3

# Cost parameters
CIP_REPLACEMENT_COST_PER_INCH_FT = 120.00
EMERGENCY_REPAIR_COST_PER_BREAK = 5000.00
EMERGENCY_REPLACEMENT_COST_PER_FT = 800.00
DEFAULT_REPLACEMENT_MATERIAL = 'HDPE'
```

**Task 1.2 — `leyp_investment.py` → `water_replacement.py`** (~1.5 hours)

Create a new file replacing the entire `InvestmentManager`. Core structure:

```python
class ReplacementManager:
    def __init__(self, budget, rehab_trigger, cip_cost_rate, replacement_material):
        self.budget = budget
        self.rehab_trigger = rehab_trigger
        self.cip_cost_rate = cip_cost_rate
        self.replacement_material = replacement_material
        self.action_log = []
        self.annual_spend = 0.0

    def calculate_cost(self, pipe):
        return self.cip_cost_rate * pipe.diameter * pipe.length

    def get_annualized_risk(self, pipe):
        return (pipe.cof * pipe.length * GLOBAL_COST_PER_FT) / pipe.current_ttf

    def run_year(self, network, current_year):
        self.annual_spend = 0.0
        candidates = [
            pipe for pipe in network 
            if pipe.current_condition <= self.rehab_trigger
        ]
        ranked = []
        for pipe in candidates:
            cost = self.calculate_cost(pipe)
            risk = self.get_annualized_risk(pipe)
            ranked.append({'pipe': pipe, 'cost': cost, 'priority': risk / max(cost, 1.0)})
        
        ranked.sort(key=lambda x: x['priority'], reverse=True)
        count = 0
        for plan in ranked:
            if self.annual_spend + plan['cost'] <= self.budget:
                self.execute_replacement(plan, current_year)
                self.annual_spend += plan['cost']
                count += 1
        
        return {'Year': current_year, 'Spend': self.annual_spend, 'Count': count}

    def execute_replacement(self, plan, current_year):
        pipe = plan['pipe']
        self.action_log.append({
            'Year': current_year, 'PipeID': pipe.id,
            'Action': 'CIP_Replacement', 'Cost': plan['cost'],
            'Priority': plan['priority'], 'Condition_Before': pipe.current_condition
        })
        pipe.material = self.replacement_material
        pipe.current_condition = 6.0
        pipe.initial_age = -current_year
        pipe.is_lined = False
        pipe.reset_physics_params()
        pipe.reset_breaks()
```

**Task 1.3 — `leyp_optimizer.py`** (~45 min)

Reduce problem definition:
- `n_var=2` (budget, rehab_trigger)
- `n_obj=2` (investment cost, risk cost)
- `n_ieq_constr=0`
- Remove PM start/stop and split ratio from gene unpacking
- Update results DataFrame columns
- Update Pareto visualization

**Task 1.4 — Smoke test** (~1 hour)

Run the simplified pipeline on the existing sewer dataset (materials won't match but the loop should execute). Verify:
- 100-year loop completes without errors
- Optimizer converges within 40 generations
- Pareto front has plausible shape
- Action log is populated

This confirms the architecture is intact before changing physics.

---

### Phase 2 — Rework initialization physics (afternoon, ~4 hours)

**Goal**: Implement age-based condition interpolation, break seeding, and the point-break sub-segment model.

**Task 2.1 — `leyp_core.py` VirtualSegment refactor** (~45 min)

Replace break-length tracking with point-break counting:

```python
class VirtualSegment:
    def __init__(self, segment_length):
        self.length = segment_length
        self.n_point_breaks = 0

    def simulate_breaks(self, intensity):
        num_events = np.random.poisson(intensity * self.length / 1000.0)
        self.n_point_breaks += num_events
        return num_events

    def has_failed(self, threshold):
        return self.n_point_breaks >= threshold
```

**Task 2.2 — `leyp_core.py` Pipe.__init__ refactor** (~1.5 hours)

New initialization sequence:
1. Load attributes from CSV
2. Look up standard useful life for material
3. Compute life fraction = age / base_life (clamped to [0, 1])
4. Interpolate initial condition: `6.0 × (1 - fraction) + 1.0 × fraction`
5. Seed initial break count from uniform distribution scaled by life fraction
6. Sample lognormal TTF from material degradation params
7. Initialize N sub-segments with proportional lengths

```python
def __init__(self, attributes):
    # ... existing attribute loading ...
    
    # Condition interpolation from age vs. standard life
    std_life = STANDARD_LIFE.get(self.material, STANDARD_LIFE['Default'])
    life_fraction = min(1.0, max(0.0, self.initial_age / std_life['base_life']))
    self.current_condition = max(1.0, 6.0 - (5.0 * life_fraction))
    
    # Break history seeding (uniform distribution)
    max_expected_breaks = max(0, int(life_fraction * 6))
    seeded_breaks = np.random.randint(0, max_expected_breaks + 1) if max_expected_breaks > 0 else 0
    
    # Distribute seeded breaks across sub-segments
    seg_len = self.length / N_SEGMENTS_PER_PIPE
    self.segments = [VirtualSegment(seg_len) for _ in range(N_SEGMENTS_PER_PIPE)]
    for _ in range(seeded_breaks):
        target_seg = np.random.randint(0, N_SEGMENTS_PER_PIPE)
        self.segments[target_seg].n_point_breaks += 1
    
    self.n_breaks = seeded_breaks
    self.initial_n_breaks = seeded_breaks
    
    # Physics setup (unchanged)
    self.reset_physics_params()
    self.skip_degradation_years = 0  # DELETE THIS LINE (carry-over from sewer)
    self.has_failed_in_sim = False
```

**Task 2.3 — `leyp_core.py` degrade() and simulate_year() refactor** (~1 hour)

Simplify `degrade()`:
```python
def degrade(self, dt=1.0):
    decay_factor = math.exp(-self.degradation_rate * dt)
    self.current_condition *= decay_factor
    self.current_condition = max(1.0, min(6.0, self.current_condition))
    self.update_leyp_state()
```

Refactor `simulate_year()` to return structured cost information:
```python
def simulate_year(self, sim_year_idx, repair_cost_per_break, segment_threshold):
    intensity = self.calculate_hazard(sim_year_idx)
    year_breaks = 0
    year_repair_cost = 0.0
    pipe_failed = False
    
    for seg in self.segments:
        new_breaks = seg.simulate_breaks(intensity)
        year_breaks += new_breaks
        year_repair_cost += new_breaks * repair_cost_per_break
        
        if seg.has_failed(segment_threshold):
            pipe_failed = True
    
    if year_breaks > 0:
        damage = 0.3 * year_breaks
        self.current_condition = max(1.0, self.current_condition - damage)
        self.update_leyp_state()
    
    return {
        'breaks': year_breaks,
        'repair_cost': year_repair_cost,
        'failed': pipe_failed
    }
```

**Task 2.4 — Delete dead code** (~30 min)

Remove from `leyp_core.py`:
- `skip_degradation_years` attribute and all references
- The `break_length` tracking in VirtualSegment
- The break-length-based failure check (replaced by point-break threshold)
- The negative-to-positive uniform distribution for break lengths

---

### Phase 3 — Runner and three-cost-stream accounting (Day 2 morning, ~4 hours)

**Goal**: Wire the refactored physics into the simulation loop and produce all three output types.

**Task 3.1 — `leyp_runner.py` main loop refactor** (~2 hours)

```python
def run_simulation(use_mock_data=False, override_input_path=None,
                   annual_budget=None, rehab_trigger=None, generate_report=False):
    
    # A. Load data (unchanged)
    # B. Initialize network (uses new Pipe.__init__)
    
    # C. Initialize manager
    manager = ReplacementManager(
        budget=annual_budget or ANNUAL_BUDGET,
        rehab_trigger=rehab_trigger or TRIGGERS['Rehab'],
        cip_cost_rate=CIP_REPLACEMENT_COST_PER_INCH_FT,
        replacement_material=DEFAULT_REPLACEMENT_MATERIAL
    )
    
    # D. Main loop — three cost accumulators
    results_cip_cost = 0.0
    results_repair_cost = 0.0
    results_emergency_cost = 0.0
    emergency_replaced = set()
    
    for year in range(1, 101):
        # Phase 1: Degrade
        for pipe in network:
            pipe.degrade()
        
        # Phase 2: Planned CIP replacement (budget-constrained)
        report = manager.run_year(network, year)
        results_cip_cost += report['Spend']
        
        # Clear emergency status for CIP-replaced pipes
        for pipe in network:
            if pipe.current_condition > 5.0 and pipe.id in emergency_replaced:
                emergency_replaced.discard(pipe.id)
        
        # Phase 3: Break simulation + emergency costs
        for pipe in network:
            if pipe.id in emergency_replaced:
                continue
            
            result = pipe.simulate_year(
                year,
                EMERGENCY_REPAIR_COST_PER_BREAK,
                SEGMENT_BREAK_THRESHOLD
            )
            
            results_repair_cost += result['repair_cost']
            
            if result['failed'] and pipe.id not in emergency_replaced:
                emergency_replaced.add(pipe.id)
                emg_cost = pipe.length * EMERGENCY_REPLACEMENT_COST_PER_FT
                results_emergency_cost += emg_cost
                
                # Force replacement at penalty cost
                pipe.material = DEFAULT_REPLACEMENT_MATERIAL
                pipe.current_condition = 6.0
                pipe.initial_age = -year
                pipe.reset_physics_params()
                pipe.reset_breaks()
                
                if generate_report:
                    manager.action_log.append({
                        'Year': year, 'PipeID': pipe.id,
                        'Action': 'Emergency_Replacement',
                        'Cost': emg_cost, 'Priority': 0,
                        'Condition_Before': 1.0
                    })
    
    # E. Return
    if generate_report:
        action_log_df = pd.DataFrame(manager.action_log)
        return results_cip_cost, results_repair_cost, results_emergency_cost, action_log_df
    else:
        return results_cip_cost, results_repair_cost + results_emergency_cost
```

Note: The optimizer receives 2 values `(investment_cost, risk_cost)` where `risk_cost = repair + emergency`. The report mode returns all three separately for detailed analysis.

**Task 3.2 — Validation curve generator** (~1.5 hours)

New function, either in the runner or a separate `water_validation.py`:

```python
def generate_validation_curve(network_snapshot, sim_years=100):
    """
    Generates the '% breaks avoided vs. % pipes replaced' curve.
    Run on a snapshot of the network BEFORE any investment is applied
    (i.e., the no-action baseline).
    
    Returns: (pct_replaced_by_number, pct_breaks_avoided,
              pct_replaced_by_length, pct_breaks_avoided_by_length)
    """
    pipe_data = []
    for pipe in network_snapshot:
        predicted_annual = sum(
            pipe.calculate_hazard(yr) for yr in range(sim_years)
        ) / sim_years
        pipe_data.append({
            'pipe_id': pipe.id,
            'predicted_annual_breaks': predicted_annual,
            'length': pipe.length
        })
    
    # Sort by descending predicted break rate
    pipe_data.sort(key=lambda x: x['predicted_annual_breaks'], reverse=True)
    
    total_breaks = sum(p['predicted_annual_breaks'] for p in pipe_data)
    total_length = sum(p['length'] for p in pipe_data)
    n = len(pipe_data)
    
    # By number of pipes
    pct_replaced_n, pct_avoided_n = [], []
    cum = 0.0
    for i, p in enumerate(pipe_data):
        cum += p['predicted_annual_breaks']
        pct_replaced_n.append(100.0 * (i + 1) / n)
        pct_avoided_n.append(100.0 * cum / total_breaks)
    
    # By length of pipes (re-sort by break rate per length)
    pipe_data.sort(key=lambda x: x['predicted_annual_breaks'] / max(x['length'], 1.0), reverse=True)
    pct_replaced_l, pct_avoided_l = [], []
    cum_len, cum_breaks = 0.0, 0.0
    for p in pipe_data:
        cum_len += p['length']
        cum_breaks += p['predicted_annual_breaks']
        pct_replaced_l.append(100.0 * cum_len / total_length)
        pct_avoided_l.append(100.0 * cum_breaks / total_breaks)
    
    return pct_replaced_n, pct_avoided_n, pct_replaced_l, pct_avoided_l
```

**Task 3.3 — Integrate validation curve into optimizer output** (~30 min)

After the "victory lap" re-run, generate and save the validation curve as a second chart alongside the Pareto cost curve.

---

### Phase 4 — Polish, test, and calibrate (Day 2 afternoon, ~4 hours)

**Task 4.1 — Update `optimizer_config.yaml`** (~30 min)

```yaml
genes:
  budget:
    min: 10000
    max: 2000000
  rehab_trigger:
    min: 1.0
    max: 3.5

algorithm:
  pop_size: 50
  n_offsprings: 15
  n_gen: 40
  seed: 1027895609238

economic:
  cip_cost_per_inch_ft: 120.00
  emergency_repair_per_break: 5000.00
  emergency_replacement_per_ft: 800.00
  segment_break_threshold: 3
```

**Task 4.2 — End-to-end test on water dataset** (~1.5 hours)

Run full optimization. Verify:
- Pareto front shows the expected U-shaped total cost curve
- Validation curve separates from the random diagonal (the model is identifying high-risk pipes)
- Action plan has plausible year-by-year replacement volumes
- Emergency replacements decrease as CIP budget increases across the Pareto front
- Cost streams sum correctly

**Task 4.3 — Sensitivity calibration** (~1.5 hours)

Test sensitivity to key parameters:
- `SEGMENT_BREAK_THRESHOLD`: Lower values (2) make pipes fail faster → more emergency costs → optimizer pushes toward higher budgets. Higher values (5) are more forgiving.
- `EMERGENCY_REPLACEMENT_COST_PER_FT` / `CIP_REPLACEMENT_COST_PER_INCH_FT` ratio: This ratio determines how much the optimizer "cares" about preventing emergencies. Test at 3×, 5×, and 8× ratios.
- Break seeding distribution: If the validation curve hugs the diagonal, the seeding isn't differentiating risk enough — increase the max_expected_breaks multiplier or switch to a Poisson draw.

**Task 4.4 — Update README** (~30 min)

Update the existing README to document the water model, new cost streams, and changed configuration parameters.

---

## Files to create/modify/delete

| File | Action | Phase |
|---|---|---|
| `leyp_config.py` | Modify | 1 |
| `leyp_core.py` | Modify | 2 |
| `leyp_investment.py` | Delete | 1 |
| `water_replacement.py` | Create (replaces investment) | 1 |
| `leyp_runner.py` | Modify | 3 |
| `leyp_optimizer.py` | Modify | 1, 3 |
| `leyp_preprocessor.py` | Minor modify | 1 |
| `leyp_orchestrator.py` | Delete | 1 |
| `optimizer_config.yaml` | Modify | 4 |
| `water_validation.py` | Create (optional, can be in runner) | 3 |
| `README.md` | Modify | 4 |

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Break seeding doesn't differentiate risk | Medium | High — flat validation curve | Make seeding distribution configurable (uniform / Poisson / age-weighted). Tune after first run. |
| Emergency cost ratio too low → optimizer ignores proactive replacement | Low | Medium | Test at 3×, 5×, 8× ratios in Phase 4 calibration |
| Weibull parameters miscalibrated for water materials | Medium | Medium | Start with AWWA literature values, treat as tunable. Consider adding a calibration mode later if break records become available. |
| 100-year horizon too long for meaningful planning | Low | Low | Horizon is standard for water infrastructure. Outputs are actionable at the 5–20 year range within the plan. |
| Stochastic variability across runs | Medium | Low | Optimizer uses fixed seed. For final deliverables, run 3–5 seeds and average. |

---

## Definition of done

- [ ] Full optimization completes in under 30 minutes on the test dataset
- [ ] Pareto front CSV with investment cost, risk cost, total cost, and 2 gene values per solution
- [ ] Pareto cost curve PNG matching the format of the sewer version (investment, risk, total, optimum marker)
- [ ] Validation curve PNG (% breaks avoided vs. % pipes replaced, by number and by length) with random diagonal
- [ ] Optimal action plan CSV with year, pipe ID, action type, cost, priority, condition before
- [ ] Emergency replacements are logged in the action plan with distinct action type
- [ ] All PM/cleaning/repair/budget-split code removed — no dead code paths
- [ ] README updated with water model documentation
