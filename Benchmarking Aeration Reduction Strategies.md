# **Benchmarking Aeration Reduction Strategies: Best Practices for ASM3 Calibration and Pseudo Steady State Dynamic Simulations**

## **Introduction**

The optimization of energy consumption in wastewater treatment plants (WWTPs) represents a critical objective for modern environmental engineering, driven by increasingly stringent effluent quality legislation—such as the European Union Guideline Urban Wastewater Directive 91/271/EEC—and the global imperative to reduce municipal carbon footprints and operational expenditures.1 Within the biological treatment phases of activated sludge processes (ASP), aeration systems typically account for up to sixty percent of the total electrical energy consumed.3 Consequently, intermittent aeration—a process where aerobic and anoxic phases are temporally alternated within a single bioreactor volume—has emerged as a highly effective operational strategy.1 By periodically switching blowers on and off, facilities can achieve simultaneous nitrification and denitrification (SND) without the capital expenditure required for geographically separated tanks or the massive energy drain of internal mixed liquor recirculation pumps.1

To objectively evaluate the efficacy of these non-stationary control strategies across different scales and configurations, the International Water Association (IWA) developed the Benchmark Simulation Model (BSM) platforms, which include BSM1, BSM1\_LT, and BSM2.5 These platforms provide a standardized physical plant layout, standardized influent weather files characterizing dry, rain, and storm events, and standardized performance evaluation criteria, most notably the Effluent Quality Index (EQI) and the Operational Cost Index (OCI).3 Within this benchmarking framework, the mathematical engine predicting the biological behavior of the activated sludge is of paramount importance. While the original BSM1 relied exclusively on the Activated Sludge Model No. 1 (ASM1), subsequent research and advanced control evaluations have increasingly adopted the Activated Sludge Model No. 3 (ASM3).9

The transition to ASM3 resolves several structural and phenomenological deficiencies inherent in ASM1, primarily by shifting from a death-regeneration mechanism to an endogenous respiration concept, and by introducing the explicit modeling of cell-internal storage products.11 This mechanistic shift significantly reduces the direct mathematical coupling between state variables, rendering the model easier to calibrate and vastly more accurate when simulating the dynamic shifting of electron acceptors that characterizes intermittent aeration sequences.11 For researchers and engineers seeking to utilize the ASM3 BSM framework as a testbed for aeration reduction scenarios, rigorous adherence to standardized modeling protocols is mandatory to ensure reproducible and highly accurate results.13

This comprehensive research report serves as an exhaustive guide to these best practices. It details the specific phenomenological shifts in ASM3, reviews foundational literature to guide new researchers, outlines the critical steps for calibrating kinetic and stoichiometric parameters using respirometry, explains the proper execution of sensitivity analyses, and strictly defines the simulation procedures required to achieve the necessary "pseudo steady state" prior to dynamic evaluation, as mandated by the IWA Task Group on Benchmarking of Control Strategies for Wastewater Treatment Plants.7

## **The Benchmark Simulation Framework and Aeration Control**

The concept of a standardized tool for the objective evaluation of control strategies was introduced to overcome the difficulty of comparing algorithms tested on disparate models, varying plant layouts, and inconsistent influent data.5 The BSM platform eliminates these confounding variables by providing a rigid, universally accepted physical and mathematical environment.7

### **Physical Configuration and Evaluation Metrics**

In its default configuration, the Benchmark Simulation Model No. 1 (BSM1) represents a five-compartment biological reactor followed by a secondary settling tank modeled using a ten-layer one-dimensional flux model, such as the Takács clarifier model.14 The initial layout designs the first two compartments as un-aerated (anoxic) zones for denitrification, followed by three continuously aerated zones for carbon oxidation and autotrophic nitrification.15 To adapt this testbed for intermittent aeration reduction studies, researchers modify the continuous aeration in the final compartments, replacing it with a sequential control logic that cycles between aeration intervals and non-aeration intervals.1

The primary objective of testing any aeration reduction strategy within this environment is the minimization of the Operational Cost Index (OCI), which is heavily weighted by aeration energy and pumping energy, while strictly adhering to the Effluent Quality Index (EQI) constraints.1 The EQI is a composite metric that aggregates the effluent loads of total suspended solids, chemical oxygen demand, biochemical oxygen demand, total Kjeldahl nitrogen, and nitrate/nitrite nitrogen into a single performance value.17 Aeration control strategies must balance the energy savings of extending the "air-off" phase against the risk of violating the effluent standards for ammonia and total nitrogen.1

### **Advanced Control Strategies in BSM**

Control algorithms deployed within the BSM framework range from simple rule-based feedback loops to highly complex predictive algorithms. Traditional proportional-integral-derivative (PID) controllers are frequently used to maintain dissolved oxygen (DO) setpoints or to manipulate internal recycle flows based on nitrate concentrations.15 However, when simulating intermittent aeration reduction, the non-stationary nature of the system often requires more sophisticated approaches.

Model Predictive Control (MPC) algorithms utilize the complete ASM3 non-linear mathematical model with a receding time horizon to continuously compute an optimal sequence of blower switching times.1 These predictive systems estimate the future trajectories of the main process variables, ensuring that the necessary amount of oxygen is provided to facilitate complete nitrification without wasting energy on excessive aeration that would otherwise degrade the subsequent denitrification phase by introducing high DO concentrations into the anoxic period.19 Comparing these advanced MPC strategies against traditional rule-based phase lengths is a primary application of the ASM3 BSM testbed.1

## **Mechanistic Advantages of ASM3 in Intermittent Aeration Modeling**

The application of mathematical models to wastewater biological processes relies heavily on Monod-style growth kinetics, electron acceptor switching functions, and complex mass balances.11 To understand why ASM3 is preferred over the original ASM1 for simulating aeration reduction, one must examine the fundamental phenomenological differences between the two model structures.

### **The Shift from Death-Regeneration to Endogenous Respiration**

In ASM1, the decay of heterotrophic and autotrophic biomass is modeled via the "death-regeneration" concept. When microorganisms decay, the model mathematically converts their biomass into slowly biodegradable particulate substrate. This particulate substrate must then undergo extracellular hydrolysis to become readily biodegradable soluble substrate before it can be consumed again by active biomass for new growth.11 This creates a convoluted, circular mathematical dependency where the rates of oxygen consumption and denitrification are heavily dominated by the empirical hydrolysis rate, regardless of which electron acceptor (oxygen or nitrate) is currently present in the system.11

ASM3 abandons this circular logic in favor of the endogenous respiration concept.11 Biomass decay is modeled as a direct oxidative process that consumes oxygen (under aerobic conditions) or nitrate (under anoxic conditions) to produce inert particulate organic material and release energy for cell maintenance.11 This severs the feedback loop of the death-regeneration cycle, significantly reducing the direct mathematical coupling between state variables. Consequently, the parameters in ASM3 exhibit vastly improved identifiability, meaning that an engineer attempting to calibrate the model can adjust a single kinetic parameter without causing unintended, cascading mathematical artifacts throughout the entire system.11

### **The Critical Role of Cell-Internal Storage Products**

Perhaps the most crucial structural enhancement in ASM3 for the purpose of modeling intermittent aeration is the explicit inclusion of cell-internal storage products. ASM3 recognizes that under transient loading conditions or dynamic aeration cycling, heterotrophic organisms do not instantaneously utilize available soluble substrate for cellular growth.12 Instead, they rapidly absorb the readily biodegradable substrate from the mixed liquor and convert it into internal storage polymers, such as polyhydroxyalkanoates (PHA) or glycogen.12 The organisms subsequently utilize these stored reserves for growth and maintenance during periods of external substrate starvation.12

This mechanistic adjustment accurately reflects the true biological dynamics occurring during an intermittent aeration cycle. During the air-off (anoxic) phase, the kinetics of ASM3 ensure that all processes—with the exception of hydrolysis—proceed at a markedly reduced rate compared to the aerobic phase.12 Readily biodegradable chemical oxygen demand (COD) accumulates in the bulk liquid or is slowly converted to storage polymers using nitrate as the electron acceptor.12 When the control strategy switches the blowers back on, the immediate and massive spike in the oxygen uptake rate is driven by the rapid aerobic oxidation of these accumulated storage polymers, a physical phenomenon that ASM1 struggles to replicate accurately without heavy, unrealistic parameter distortion.12 The inclusion of storage products ensures that ASM3 naturally captures the transient shifting of electron acceptors.11

To provide a clear understanding of the structural components managed by the modeler, the following table compares the primary state variables utilized in ASM3 against those in the legacy ASM1 model:

| Component Category | ASM1 State Variable | ASM3 State Variable | Mechanistic Difference / Significance in Aeration Reduction |
| :---- | :---- | :---- | :---- |
| **Readily Biodegradable Substrate** | **![][image1]** | **![][image1]** | In ASM3, ![][image1] is primarily utilized for the creation of internal storage polymers rather than direct immediate growth. |
| **Slowly Biodegradable Substrate** | **![][image2]** | **![][image2]** | ASM3 reduces the dominance of ![][image2] hydrolysis in controlling overall oxygen uptake rates. |
| **Cell-Internal Storage Products** | *Not Modeled* | *![][image3]* | The defining feature of ASM3; crucial for accurately simulating respiration spikes following the transition from anoxic to aerobic phases. |
| **Heterotrophic Biomass** | **![][image4]** | **![][image5]** | ASM3 models heterotrophic decay directly via endogenous respiration, requiring distinct aerobic and anoxic decay parameters. |
| **Autotrophic Biomass** | **![][image6]** | **![][image7]** | Autotrophic decay is also modeled via endogenous respiration; ![][image7] growth dictates the success of intermittent aeration by consuming ammonia. |
| **Inert Particulate Organics** | **![][image8]** | **![][image9]** | ASM3 combines influent inert particulate and decay-produced inert particulate into a simpler framework. |
| **Ammonium Nitrogen** | **![][image10]** | **![][image10]** | The primary tracked effluent constraint; its oxidation rate defines the minimum required length of the aeration phase. |

## **Essential Literature: Guiding Papers for the New Researcher**

For a new investigator approaching the ASM3 Benchmark Simulation Model platform to evaluate aeration reduction, the sheer volume of parameters and procedural requirements can be overwhelming. To establish a rigorous foundation, a researcher must rely on established, peer-reviewed literature that explicitly documents the step-by-step methodologies for model calibration, predictive control, and benchmark evaluation. Based on an exhaustive review of the domain, three highly influential papers serve as the "gold standard" guides for distinct phases of the modeling process.

### **The Calibration Guide: Koch et al. (2000)**

For the fundamental calibration of the ASM3 model itself, the work by Koch et al. (2000), detailing the calibration of ASM3 for Swiss municipal wastewater using AQUASIM, stands as a premier instructional document.12 This paper is essential because it moves beyond theoretical mathematics and provides a detailed, practical methodology for estimating kinetic and stoichiometric parameters using batch, pilot, and full-scale experimental data.12

Koch et al. establish the best practice of utilizing respirometric batch tests to determine primary kinetic parameters for heterotrophic and autotrophic processes.12 Crucially, for researchers focused on intermittent aeration, this paper provides explicit guidance on estimating decay rates under varying electron acceptor conditions, demonstrating mathematically how heterotrophic decay rates drop significantly in the absence of dissolved oxygen.12 The paper also outlines the sensitivity analysis necessary to check which specific model parameters can actually be determined with the aid of available respirometric experiments, preventing the researcher from attempting to calibrate unidentifiable variables.12

### **The Model-Based Evaluation Guide: Salem et al. (2002)**

When the researcher moves from calibrating the raw ASM3 model to utilizing it for the evaluation of operational strategies (such as aeration reduction or nitrogen removal upgrades), the seminal paper by Salem et al. (2002), "Model-based evaluation of a new upgrading concept for N-removal," serves as the ultimate procedural template.11

Salem et al. provide a transparent, step-by-step account of how to set up a full-scale wastewater treatment plant simulation, execute the model calibration procedure methodically, and discuss the critical importance of each sequential step.23 The authors demonstrate how to evaluate the calibrated model via rigorous sensitivity analysis, assessing the influence of both model parameters and influent component concentrations on the final model output.23 Furthermore, Salem et al. showcase how dynamic modeling can substantially reduce scale-up time by allowing for the risk-free computational evaluation of different process alternatives—a concept perfectly aligned with the goals of the BSM framework.11 Their methodology for generating acceptable predictions of effluent concentrations and internal concentration dynamics is a mandatory reference for any rigorous benchmarking study.11

### **The Predictive Control Guide: Chai and Lie (2008)**

For researchers specifically attempting to design and benchmark advanced aeration reduction algorithms, the work by Chai and Lie (2008), "Predictive control of an intermittently aerated activated sludge process," provides the definitive engineering architecture.1

This paper presents the complete integration of model-based optimal control and predictive control applied to a biological wastewater treatment process governed by intermittent aeration.1 Chai and Lie explicitly formulate the optimization problem used with a receding horizon in a nonlinear Model Predictive Control (MPC) setup based directly on the complete ASM3 model.1 They provide a masterclass in establishing the objective function—designing an aeration strategy that minimizes energy consumption induced by the aeration system while maintaining strict adherence to effluent standards.1 By comparing their MPC aeration profile to three traditional rule-based control strategies within a simulated environment, they demonstrate exactly how a new researcher should structure a comparative benchmarking study.1

## **Best Practices for ASM3 Calibration in Aeration Reduction**

To ensure that the simulated responses to dynamic influent and aeration timeseries are phenomenologically valid, the ASM3 model must be rigorously calibrated to the specific wastewater matrix under investigation. "Good Modelling Practice" (GMP), as outlined by the IWA Task Group, dictates a structured, step-by-step approach moving from data reconciliation to the fine-tuning of highly specific biochemical kinetics.14

### **Data Collection, Reconciliation, and Influent Fractionation**

Before attempting to adjust any biokinetic parameters within the mathematical matrix, the modeler must establish a reconciled dataset representing the physical system. Mathematical models are extraordinarily sensitive to the characterization of the incoming wastewater.8 In ASM3, the accurate fractionation of the total Chemical Oxygen Demand (COD) into its constituent parts—inert soluble, readily biodegradable, inert particulate, and slowly biodegradable components—is arguably the most critical step.12

While the original IWA task group suggested that readily biodegradable substrate could potentially be approximated using total soluble COD determined by 0.45 micrometer membrane filtration, rigorous calibration protocols have conclusively demonstrated that this physical separation technique is inadequate for high-fidelity modeling.12 Instead, best practice dictates that the readily biodegradable inlet substrate be estimated through mathematical curve-fitting derived from dynamic respirometry measurements (oxygen utilization rate tests).12 If the influent is incorrectly fractionated, the resulting errors will cascade uncontrollably through the entire sequence of storage polymer creation and subsequent biomass growth, rendering any downstream simulation of aeration optimization entirely meaningless.18

### **Calibrating Endogenous Respiration (Decay Rates)**

In ASM3, decay rates must be estimated for both heterotrophic and autotrophic biomass under both aerobic and anoxic conditions. Best practice requires the execution of batch experiments using mixed liquor sludge obtained directly from the specific treatment plant or pilot facility under investigation.12 Decay rates are generally estimated by tracking the decrease in total COD and the maximal autotrophic respiration rates over an extended period.12

A fundamental biochemical insight when calibrating these parameters for intermittent aeration scenarios is that decay rates are considerably lower under anoxic conditions than under aerobic conditions. Standard batch test calibrations, such as those performed by Koch et al., frequently reveal an aerobic heterotrophic decay rate of approximately 0.30 per day at a standard reference temperature, whereas the corresponding anoxic decay rate drops significantly to approximately 0.10 per day.12 Failing to differentiate these decay rates within the model parameters will result in an artificial overestimation of biomass loss during the non-aerated phases of the intermittent cycle, leading to inaccurate predictions of sludge production and aeration demand upon the resumption of the aerobic phase.12

### **Calibrating Heterotrophic Storage and Growth**

Because ASM3 relies heavily on the internal storage intermediate, the storage yield and the storage rate constant are among the most sensitive parameters in the entire model architecture.12 These parameters are meticulously determined by analyzing the oxygen consumption curve following a sudden, pulsed addition of substrate (such as acetate) in a respirometric batch test. The distinct "tailing-off" phenomenon observed in the respiration curve explicitly maps to the rate at which the internal storage products are being metabolized for growth after the readily biodegradable substrate in the bulk liquid has been fully exhausted.12

Furthermore, for intermittent aeration models simulating alternating nitrification and denitrification, the anoxic yield reduction factor must be accurately calibrated. Denitrification relies heavily on anoxic storage and growth, but the thermodynamic biological efficiency of utilizing nitrate as a terminal electron acceptor is inherently lower than utilizing dissolved oxygen. Experimental calibrations generally establish an anoxic reduction factor of approximately 0.50, which dictates that the anoxic net yield will be roughly thirty percent lower than the corresponding net aerobic yield.12

### **Calibrating Autotrophic Nitrification Kinetics**

Ammonium breakthrough constitutes the primary failure mode during aggressive aeration reduction strategies.1 When blowers are turned off to save energy, the oxidation of incoming ammonia ceases entirely. Thus, the autotrophic maximum growth rate and the saturation constant for ammonium must be fine-tuned to ensure that the model accurately predicts how fast the autotrophic bacteria can process the accumulated ammonia once the aeration resumes.12

These autotrophic parameters exhibit extreme variability across different treatment plants due to specific wastewater toxicity profiles, uncharacterized industrial discharges, or chemical additions within the plant.12 Values for the maximum autotrophic growth rate can range broadly from 0.9 per day to 1.8 per day, or even wider boundaries depending on the specific nitrifying consortia present in the sludge.12 These critical parameters are typically adjusted by systematically comparing simulated ammonium profiles against highly granular dynamic measurements taken during peak diurnal flow events, ensuring the model can handle maximum loading stress.12

To assist the new researcher, the following table summarizes the most critical parameters requiring rigorous calibration when adapting the ASM3 BSM for intermittent aeration studies, derived from the methodologies of Koch et al. and Salem et al.

| Parameter Symbol | Description | Calibration Methodology | Significance in Aeration Reduction Models |
| :---- | :---- | :---- | :---- |
| **![][image11]** | Influent Readily Biodegradable Substrate | Curve fitting from dynamic respirometry (OUR tests), rather than physical filtration. | Dictates the exact amount of substrate available for conversion into internal storage polymers. |
| ![][image12] / ![][image13] | Aerobic / Anoxic Heterotrophic Decay Rate | Long-term batch tests tracking total COD decrease under continuous aeration vs. continuous anoxic conditions. | Prevents overestimation of biomass death during the extended "blower-off" phases of intermittent cycling. |
| ![][image14] | Aerobic Storage Yield | Analysis of the "tailing-off" slope in a respiration test following a substrate pulse. | Defines the efficiency of converting bulk substrate into internal reserves, driving the subsequent oxygen demand. |
| ![][image15] | Anoxic Yield Reduction Factor | Comparative yield analysis between fully aerobic and fully anoxic batch growth tests. | Calibrates the reduced efficiency of denitrification, ensuring accurate nitrate removal predictions. |
| ![][image16] (or ![][image17]) | Maximum Autotrophic Growth Rate | Fitting simulated ammonium trajectories to empirical measurements during peak diurnal loading events. | The most critical parameter for preventing toxic ammonia breakthrough when aeration phases are artificially shortened. |

## **Sensitivity Analysis of Effluent Parameters**

Before finalizing the calibration phase and commencing formal control strategy benchmarking, the execution of a robust Sensitivity Analysis (SA) is considered a mandatory step within the Good Modelling Practice framework.14 Mathematical models of biological systems are inherently over-parameterized; it is impossible to uniquely identify every stoichiometric and kinetic constant from available macroscopic plant data. Sensitivity analysis resolves this by determining precisely which mathematical parameters dictate the largest variance in the final effluent parameters (the EQI) and the aeration costs (the OCI).17

### **Methodologies for Sensitivity Analysis**

Researchers typically employ either Local Sensitivity Analysis (LSA) or Global Sensitivity Analysis (GSA). While LSA—such as the Latin-Hypercube one-factor-at-a-time (LH-OAT) approach—is computationally inexpensive, requiring only a small number of model simulations, it fundamentally fails to capture the non-linear interactions between parameters that frequently occur in complex biological matrices.22

For highly interconnected models like the ASM3 BSM, Global Sensitivity Analysis techniques are vastly superior and strongly recommended.17 A standard industry approach involves running Monte Carlo simulations combined with Standard Regression Coefficients (SRC).17 By introducing defined input uncertainty bounds (e.g., varying all biokinetic parameters and influent fractions by plus or minus twenty percent), thousands of Monte Carlo simulations generate a comprehensive statistical distribution of the predicted EQI and OCI.17 The SRC method is then mathematically applied to the output data to identify which specific input parameters are driving the vast majority of the uncertainty in the results.17

### **Key Sensitive Parameters in Aeration Reduction**

In simulation scenarios where aeration is restricted or intermittently applied, global sensitivity analyses consistently highlight a highly specific subset of parameters that overwhelmingly control the behavior of the BSM testbed:

1. **Nitrification Parameters:** Because the total duration of the aerobic phase is artificially limited by the intermittent control algorithm, the maximum rate at which autotrophs can oxidize ammonium during the brief "air-on" phase becomes the primary system bottleneck.12 Any slight mathematical underestimation of the autotrophic growth rate will lead to catastrophic simulated ammonium breakthrough in the final effluent, drastically inflating the EQI penalty.17  
2. **Denitrification Yields:** The specific denitrification capacity during the "air-off" phase dictates the final nitrate and overall total nitrogen concentrations.12 Parameters governing the anoxic growth of heterotrophs are highly sensitive because they determine whether the nitrate generated during the aeration phase can be fully reduced before the cycle repeats.17  
3. **Oxygen Half-Saturation Coefficients:** In energy optimization and aeration reduction studies, dissolved oxygen levels are intentionally driven down, often hovering near the saturation threshold of the microorganisms to maximize mass transfer efficiency.20 Consequently, the sensitivity of the model to the half-saturation constants for oxygen for both autotrophs and heterotrophs spikes dramatically in these low-DO regimes.20 These constants mathematically dictate exactly how rapidly biological activity drops off as the blower output is curtailed.

By isolating these ten to fifteen highly sensitive kinetic and stoichiometric parameters, researchers can focus their laboratory respirometry and historical data-fitting efforts purely on the factors that will genuinely impact the benchmark results, explicitly ignoring the dozens of other ASM3 parameters that exert negligible influence on the final EQI and OCI.22

## **Executing the STR No. 23 Protocol for Pseudo-Steady State Simulations**

When utilizing the ASM3 BSM framework to test an aeration control strategy, the chronological execution of the simulation is just as critical as the calibration of the model itself. Simulating a complex biological system dynamically from an arbitrary starting point will irreversibly embed transient mathematical artifacts and initialization errors into the final performance metrics. To isolate the genuine performance of the control strategy from the "echo" of these initial conditions, the model must be initialized through a strict, multi-phase chronological protocol.

Chapter 7 of the IWA Scientific and Technical Report (STR) No. 23, "Benchmarking Control Strategies for Wastewater Treatment Plants" (Gerneay, Vanrolleghem, and Copp, 2020), outlines the absolute gold standard for this procedure.5 This rigid protocol is specifically designed to eliminate bias, ensure consistent application of the benchmark, and guarantee that multiple researchers comparing different control algorithms across the globe are starting from an identical phenomenological baseline.7

### **Phase 1: The Initial Steady State Convergence**

The procedure mandated by STR 23 must always commence with a steady-state simulation.7 The purpose of this phase is to bring the massive matrix of differential equations to a stable baseline.

1. **Constant Forcing Functions:** The simulator must be fed a continuous, non-varying influent file. This file is typically constructed based on the flow-weighted averages of the standard BSM dry weather data.7  
2. **Implementation of the Target Strategy:** Crucially, the steady-state simulation must include the exact control strategy the user intends to benchmark.7 Whether testing a simple PID dissolved oxygen controller or a complex MPC aeration algorithm, the logic must be active to ensure the biology adapts to the intended operational conditions.  
3. **Inactivation of Noise:** To facilitate rapid mathematical convergence, all stochastic noise generators inherent in the influent files or the sensor and actuator models must be strictly disabled.7 The use of ideal sensors and actuators must be considered during this specific phase.7 If ideal models are not utilized, the continuous injection of artificial signal variance prevents the ordinary differential equation (ODE) solvers from ever detecting a true mathematical root (where the rate of change of all state variables equals zero), resulting in infinite calculation loops.7  
4. **Duration:** The simulation is run until the state variables stabilize. Depending on the software platform utilized, this is typically achieved either through specialized steady-state solver algorithms or by running a long-duration dynamic solver holding constant inputs for a minimum of one hundred simulated days.7

This steady state procedure ensures a mathematically consistent starting point and explicitly eliminates the influence of arbitrary initial conditions on the generated dynamic output.7

### **Phase 2: Achieving the "Pseudo" Steady State**

While Phase 1 successfully creates a mathematical baseline, a true continuous steady-state is physically and mathematically impossible if the evaluated control strategy relies on non-stationary control actions.7 Because intermittent aeration requires the blowers to continuously cycle on and off, the internal state variables—such as dissolved oxygen, readily biodegradable substrate, and active biomass fractions—will constantly oscillate in response to the changing electron acceptors.7

If a dynamic weather file containing severe diurnal flow variations or storm events is applied immediately after the Phase 1 steady-state convergence, the fully stabilized biomass will be subjected to an unrealistic mathematical shock, irrevocably compromising the integrity of the subsequent performance indices.14 Therefore, STR 23 mandates that the non-steady operation must be used during an intermediate period to transition the system into a "pseudo steady state" before initiating the final dynamic simulations.13

In a pseudo steady state, the instantaneous values of the state variables are constantly in motion, fluctuating wildly minute-by-minute as the blowers engage and disengage. However, their mathematical integration over one complete operating cycle (typically a 24-hour diurnal period) remains perfectly constant from one cycle to the next.14 To achieve this critical acclimatization phase:

1. **Diurnal Forcing:** The model is fed with a dynamic, diurnally varying influent file. This is typically the standard dry weather pattern, repeated sequentially without variation between days.7  
2. **Activation of Non-Stationary Control:** The intermittent aeration sequences are allowed to fully dictate the process dynamics, imposing the cyclical aerobic and anoxic stress on the microbial populations.7  
3. **Duration Requirements:** The simulation must be allowed to run for several weeks. Specifically, established best practice requires running the model using the diurnal pattern for an equivalent of at least three Sludge Retention Times (3 SRTs).14 For a standard nitrogen-removing treatment plant operating with an SRT of 15 to 20 days, this translates to a mandatory 45 to 60 days of dynamic conditioning simulation.14 This extended duration guarantees that the slow-growing autotrophic populations and the gradual accumulation of inert particulate fractions have fully equilibrated to the cyclical forcing of the aeration strategy.14

### **Phase 3: Dynamic Benchmarking and Evaluation**

Only after the pseudo steady state is demonstrably achieved—verified by observing that the diurnal output profiles map perfectly onto themselves day after day without any long-term drift in the baseline concentrations—can the actual benchmarking begin.13

At this precise point, sensor and actuator noise generation is reactivated to simulate real-world hardware imperfections.7 The target dynamic influent time series are then applied. For the BSM1 platform, this typically involves a 14-day sequence incorporating successive dry, rain, and storm events to severely stress the control logic.3 For the extended BSM2 platform, this involves a massive 364-day sequence reflecting seasonal temperature shifts and long-term precipitation trends.33

Only the data generated during this final, fully dynamic phase is integrated to compute the Effluent Quality Index, the Operational Cost Index, and the total aeration energy consumption.5 This strict chronological firewall between the initialization phases and the evaluation phase provides a scientifically rigorous and completely unbiased evaluation of the proposed aeration reduction strategy, allowing for true apples-to-apples comparisons across different research institutions.5

To synthesize the requirements of STR 23 for the new researcher, the following table explicitly details the operational constraints required during each phase of the simulation protocol:

| Protocol Phase | Influent Data Type | Sensor/Actuator Noise | Aeration Control Status | Minimum Duration | Objective |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **Phase 1: Initial Steady State** | Constant (Flow-weighted average) | Disabled (Ideal Models) | Active | \> 100 days or until solver root | Eliminate initial condition bias; converge base ODEs. |
| **Phase 2: Pseudo Steady State** | Dynamic (Repeating diurnal dry weather) | Disabled (Ideal Models) | Active (Intermittent cycling) | \> 3 SRTs (approx. 45-60 days) | Acclimatize biomass to cyclical anoxic/aerobic stress. |
| **Phase 3: Dynamic Benchmarking** | Dynamic (Full dry/rain/storm files) | Enabled (Realistic variance) | Active | 14 days (BSM1) / 364 days (BSM2) | Generate data exclusively for EQI and OCI computation. |

## **Conclusion**

The utilization of the ASM3 Benchmark Simulation Model as a highly controlled testbed for aeration reduction represents a powerful intersection of biochemical process engineering and computational mathematics. Intermittent aeration strategies offer profound operational cost savings and enhanced simultaneous nitrogen removal, but their non-stationary nature poses significant modeling challenges that legacy models struggle to accommodate. By shifting from the ASM1 death-regeneration architecture to the ASM3 endogenous respiration and internal storage product framework, researchers gain a mathematically robust tool that is ideally suited for accurately replicating the rapid transient responses inherent in cyclic aeration phases.

However, the validity of any conclusion drawn from these models—whether evaluating a simple heuristic timer or a highly advanced nonlinear Model Predictive Controller—is intrinsically and permanently linked to the rigor of the underlying methodology. Adherence to Good Modelling Practice is non-negotiable. This requires accurate influent fractionation derived from dynamic respirometry rather than static physical filtration, the targeted global sensitivity analysis and calibration of highly specific autotrophic and heterotrophic parameters, and the disciplined execution of the IWA STR No. 23 pseudo steady state initialization protocol. By strictly following these established best practices, researchers can isolate the true performance of their control strategies from mathematical artifacts, thereby driving the global wastewater industry toward more sustainable, highly energy-efficient operational paradigms.