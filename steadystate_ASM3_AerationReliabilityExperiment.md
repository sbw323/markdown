# ASM3 Aeration Reliability Experiment
## Puesdo Steady-State of Aeration Reduction
### Step 1: Nominal Mode Setup 
Source: `ssASM3_DR_datagen.m`
Instructions: Modify model aeration parameters to nominal treatment mode prior to initializing experiment. Nominal aeration parameters are KLa1 & KLa2 = 0 and KLa3, KLa4 = 240; KLa5 = 110. Increase the Simulink iteration limit in tandem with Q as Q rises (minimum is 200, max is 1000).
### Step 2: Average Influent, Nominal Aeration Model Output
Instructions: Initiate model with nominal aeration KLa parameters and `CONSTINFLUENT.mat` influent parameters and wait for model to converge. Pass the `savestate` command to save the model parameters for the next step. Save the output of the settler to an external file to serve as a baseline.
### Step 3: Average Influent, Experimental Aeration Setup
Instructions: Simulate aeration reduction by modifying model values of KLa3, KLa4, and KLa5 to lower numbers. Maintain `CONSTINFLUENT.mat` influent parameters and intitate model and wait for model to converge. Pass the `savestate` command to save the model parameters for the next step. Save the output of the settler to an external file to serve as a datapoint in the first iteration of the aeration reduction experiment.
### Step 4: Average Influent, Treatment Reliability Mode
Instructions: Reset Aeration parameters to the nominal vector for KLa3, KLa4 and KLa5. Maintain `CONSTINFLUENT.mat` influent parameters and intitate model and wait for model to converge. Save the output of the settler to an external file to serve as a datapoint in the first iteration of the aeration reduction experiment. Pass `benchmarkinit` to clear the workspace for preparation of the next phase of the experiment.

## Extending the Aeration Reliability Experiment
#### Goals
Using the instructions of `Puesdo Steady-State of Aeration Reduction` as a starting point, please generate a plan to extend the plan of the experiment to create a database for model training purposes. The following is a general set of requirements to fulfill to ensure that enough data is produced from the model to cover the entire space of model outputs and inputs.
A pure steady-state solver assumes infinite time at reduced aeration and ignores storage biology.
Instead use a **Pseudo-Dynamic Step-Response Simulation**:
1. Initialize at nominal aeration parameters
2. Apply influent snapshot
3. Reduce aeration
4. Run steady state ODE solver for the new aeration levels
5. Record effluent at end of event
This captures buffering via ASM3 storage compounds and HRT effects
#### Requirements
	- Influent Variability: Use the different vectors of percentiles of the influent water quality parameters developed in `ASM3 Initial Influent Conditions` to initalize the Step 1 of `Puesdo Steady-State Experiment`. 
	- Strict Nominal Model Starting Point: Initialize the model to steady-state using nominal aeration parameters defined in Step 2 of the `Puesdo Steady-State Experiment`.
	- Experimental Aeration: Numerous different reduced aeration profiles need to be paired with all the influent parameter percentiles organized by the influent Q values. Reduce the aeration parameters of KLa 3 to KLa5 to a minimum of 50% of their inital values. 
	- Treatment Recovery: After running the aeration experiment on a chosen influent vector, conclude the cycle with a final steady state simulation with nominal aeration parameters reinstated. Maintain the same influent characteristics chosen at the influent variablility step.
### ASM3 Variable Initial Influent Conditions
Source: `ASM3_Influent`. 21 parameters (col 1 is time vector, columns 2 to 14 are water quality influent parameters, Q vector is column 15 and temperature is column 16; columns 17 to 21 are dummy variables). Additional references for the headers are contained in `stateset.m`, lines 26 to 25. 
#### Goals
To produce a variety of Steady-state “snapshots” to represent the dynamic operating envelope.
Instead of arbitrary diurnal points, sample characteristic influent states:
| Percentile | Meaning          |
| ---------- | ---------------- |
| 10th       | Low load         |
| 25th       | Typical off-peak |
| 50th       | Normal           |
| 75th       | Elevated         |
| 90th       | Peak loading     |
This produces defensible coverage of plant operation.
#### Requirements 
Process influent time vector and calculate percentiles of Q `ASM3_Input(m,15)`, then for each percentile of Q, identify the percentiles for each of the influent parameters. Create matrix of influent parameters to feed to steady state model, matching the format of `CONSTINFLUENT.mat`. Since this will a series of steady state simulations, each entry in the `CONSTINFLUENT.mat` array is the average influent load of each parameter in `ASM3_Input`.
### Data Analysis Requirements
#### Goals 
Ensure that the following data points are calculated along side each output of the model.
#### Model Parameter Requirements
	- Settler Effluent Concentrations.
		* Source: `perf_plant_LT_DR.m` starting on line 80
#### Model Calculated Values Requirements
	- Aeration Energy Use
		* E_red = (E_exp - E_nom)/nom
	- Energy Use Reduction
		* Source: `perf_plant_LT_DR.m` starting on line 184
	-  Settler COD (sCOD)
		* Source: `perf_plant_LT_DR.m` on line 129, equation parameters starting around line 54
	- Effluent Damage Indicies
		* COD_dmg = (COD_exp - COD_nom)/COD_limit 
			** Explanation: The distance of the aeration experiment effluent COD from the nominal effluent COD. Weighted by the COD limit. 
				*** Source: `perf_plant_LT_DR.m` starting on line 28
		* NH4_dmg = (NH4_exp - NH4_nom)/NH4_limit 
			** Explanation: The distance of the aeration experiment effluent NH4 from the nominal effluent NH4. Weighted by the NH4 limit. 
				*** Source: `perf_plant_LT_DR.m` starting on line 28