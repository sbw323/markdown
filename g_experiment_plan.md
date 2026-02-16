### **Phase 1: Initialization & Operating Envelope Definition**

*Objective: Establish the mathematical baseline and define the representative operating envelope of the wastewater treatment plant.*

* **Step 1: Compute Nominal Steady State**
* **Action:** Configure the ASM3 model in your simulation environment with nominal continuous influent flow, standard composition, and the baseline aeration rate (kLa_nom). Run the ODE solver until the system reaches steady state (dx/dt ~ 0).
* **Output:** Save the complete biological state vector (concentrations of autotrophs, heterotrophs, dissolved oxygen, storage products, etc.) and nominal effluent (C_nom). **Crucial:** This saved state acts as the universal t=0 initial condition for all dynamic perturbations.

* **Step 2: Sample Structured Influent Conditions**
* **Action:** Analyze historical plant influent time-series data (e.g., Flow, COD, TKN, Alkalinity). Calculate the statistical percentiles representing different loading regimes.
* **Output:** Extract 5 specific influent "snapshot" vectors corresponding to the **10th (Low), 25th (Off-peak), 50th (Normal), 75th (Elevated), and 90th (Peak)** percentiles.

### **Phase 2: Pseudo-Dynamic Simulation & Database Generation**

*Objective: Systematically simulate the plant’s response to aeration curtailment to capture biological buffering and Hydraulic Retention Time (HRT) effects.*

* **Step 3: Perform Pseudo-Dynamic Aeration Step Tests**
* **Action:** Define an experimental grid spanning the 5 Influent States, a range of Aeration Reductions (kLa_red, e.g., 10% to 100% reduction), and Event Durations (t, e.g., 15 mins to 4 hours). Script a batch process to iterate through every combination:
1. Initialize the ODE solver using the **saved nominal state vector** from Step 1.
2. Apply the chosen Influent State snapshot.
3. Drop the aeration to kLa_red.
4. Run the dynamic simulation *strictly* for duration t.
5. Record the final effluent concentrations (C_eff) at exactly time t.

* **Output:** A raw tabular dataset mapping the inputs `[Influent State, kLa_red, t]` to the resulting output `[C_eff]`.

### **Phase 3: Data Processing & Risk Formulation**

*Objective: Translate raw concentration data into bounded performance, financial, and probabilistic risk metrics.*

* **Step 4: Compute Normalized Degradation Index (δ)**
* **Action:** For every row in the dataset, calculate the degradation relative to regulatory compliance: δ=(C_eff−C_nom)/C_limit) (using regulatory limits for key pollutants like Ammonia or Total Nitrogen).
* **Validation:** Ensure the metric behaves as designed: < 0 is an improvement, 0-1 is compliant degradation, and >= 1 is a permit violation.

* **Step 5: Associate with Energy Savings**
* **Action:** Compute the specific energy offset for every scenario using: E_saved = (kLa_nom - kLa_red) * t.

* **Step 6: Build Probabilistic Risk Model**
* **Action:**
1. Define P(t): the probability distribution of event durations (derived from power grid Mean Time Between Failures [MTBF] or historical demand-response signals).
2. Define C(δ): a consequence penalty function (e.g., scales aggressively as δ -> 1 and applies a massive penalty for δ >= 1 ).
3. Calculate Expected Risk: Risk = P(t) x C(δ) for every row.

* **Output:** An enriched, master dataset containing all operational inputs, resulting degradation indices, energy savings, and expected risk.

### **Phase 4: Machine Learning & Optimization Engine**

*Objective: Decouple the optimization algorithm from the computationally heavy ASM3 ODE solver to enable rapid multi-objective optimization.*

* **Step 7: Train Surrogate Model**
* **Action:** Split the processed master dataset into training and testing sets. Train a Machine Learning regressor (Random Forest or XGBoost are highly recommended as they handle the non-linear "cliffs" of permit violations well).
* **Features (Inputs):** Influent Percentile, kLa_red, duration t.
* **Targets (Outputs):**  and Expected Risk (or predict δ directly and calculate Risk algebraically).

* **Output:** A fast, deployable ML surrogate model validated with a high R^2 score against the ASM3 dataset.

* **Step 8: Run NSGA-II Optimization**
* **Action:** Formulate the constrained optimization problem using an evolutionary algorithm framework.
* **Decision Variable: kla_red** 
* **Objective:** Maximize E_saved 
* **Constraint:** Risk <= Risk_target (where Risk_target is an acceptable probability of violation defined by plant management).

* **Output:** Generate a Pareto front for each of the 5 influent states, showing the maximum permissible energy savings achievable without breaching allowable reliability risk.

### **Phase 5: Policy Extraction & Documentation**

*Objective: Convert the optimized math into a tangible, deployable operational asset.*

* **Step 9: Extract Operational Control Policy**
* **Action:** From the Pareto front, isolate the maximum allowable kLa_red for every specific Influent State that keeps the system just below the Risk_target.
* **Output:** A definitive mapping function or lookup table: `Influent State (Percentile) -> Maximum Allowed Aeration Reduction`. This modular ruleset will serve as the direct setpoint policy for future LSTM-based predictive control.

* **Step 10: Document Assumptions (Section 6 Requirement)**
* **Action:** As explicitly required by Section 6 of the framework, formally document the **Instantaneous Recovery Assumption** in your project logs. Acknowledge that this proof-of-concept represents an "optimistic bound" and outline a future validation phase utilizing continuous, multi-day dynamic ASM3 simulations to assess true biological recovery tails.