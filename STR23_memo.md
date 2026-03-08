# **Executing the STR No. 23 Protocol for Pseudo-Steady State Simulations**

When utilizing the ASM3 BSM framework to test an aeration control strategy, the chronological execution of the simulation is just as critical as the calibration of the model itself. Simulating a complex biological system dynamically from an arbitrary starting point will irreversibly embed transient mathematical artifacts and initialization errors into the final performance metrics. To isolate the genuine performance of the control strategy from the "echo" of these initial conditions, the model must be initialized through a strict, multi-phase chronological protocol.

Chapter 7 of the IWA Scientific and Technical Report (STR) No. 23, "Benchmarking Control Strategies for Wastewater Treatment Plants" (Gerneay, Vanrolleghem, and Copp, 2020), outlines the absolute gold standard for this procedure.5 This rigid protocol is specifically designed to eliminate bias, ensure consistent application of the benchmark, and guarantee that multiple researchers comparing different control algorithms across the globe are starting from an identical phenomenological baseline.7

## **Phase 1: The Initial Steady State Convergence**

The procedure mandated by STR 23 must always commence with a steady-state simulation.7 The purpose of this phase is to bring the massive matrix of differential equations to a stable baseline.

1. **Constant Forcing Functions:** The simulator must be fed a continuous, non-varying influent file. This file is typically constructed based on the flow-weighted averages of the standard BSM dry weather data.7  
2. **Implementation of the Target Strategy:** Crucially, the steady-state simulation must include the exact control strategy the user intends to benchmark.7 Whether testing a simple PID dissolved oxygen controller or a complex MPC aeration algorithm, the logic must be active to ensure the biology adapts to the intended operational conditions.  
3. **Inactivation of Noise:** To facilitate rapid mathematical convergence, all stochastic noise generators inherent in the influent files or the sensor and actuator models must be strictly disabled.7 The use of ideal sensors and actuators must be considered during this specific phase.7 If ideal models are not utilized, the continuous injection of artificial signal variance prevents the ordinary differential equation (ODE) solvers from ever detecting a true mathematical root (where the rate of change of all state variables equals zero), resulting in infinite calculation loops.7  
4. **Duration:** The simulation is run until the state variables stabilize. Depending on the software platform utilized, this is typically achieved either through specialized steady-state solver algorithms or by running a long-duration dynamic solver holding constant inputs for a minimum of one hundred simulated days.7

This steady state procedure ensures a mathematically consistent starting point and explicitly eliminates the influence of arbitrary initial conditions on the generated dynamic output.7

## **Phase 2: Achieving the "Pseudo" Steady State**

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