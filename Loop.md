We will now build the complete pipeline. To prevent deviation and ensure adherence to the strict guardrails, you must operate via a Checkpoint Generation Loop.

EXECUTION PROTOCOL & RE-UPDATING FEATURES:

You will act as a state machine working through a strict Checklist of phases.

You will only generate the code required for the CURRENT active Checkpoint and then STOP.

At the end of your response, you will insert a hard [CHECKPOINT WAITING] prompt, asking me to review the code or execution results.

Re-updating/Rollback Function: If I reply with an error message, a bug, or a deviation warning (e.g., using forbidden terms, missing variables, or hallucinating Python physics), you must NOT advance to the next Checkpoint. You will carefully analyze the error against the guardrails, regenerate the corrected code for the current Checkpoint, and wait for approval again.

You will only advance to the next Checkpoint when I explicitly state "Checkpoint Approved. Proceed."

THE DEVELOPMENT CHECKLIST:

[ ] Checkpoint 1: MATLAB Influent & Data Generation Scripts. Generate the MATLAB .m scripts that process ASM3_Input, create CONSTINFLUENT.mat using the Q-percentiles, and execute the 4-phase Dynamic Step-Response workflow (Nominal Setup, Nominal Run savestate, Experimental Run for duration t savestate, Recovery benchmarkinit). Ensure parameters are dynamically configurable.

[ ] Checkpoint 2: Python CRUD Orchestration Pipeline. Generate the Python script that uses subprocess or matlab.engine to iterate through the experimental parameter grid (Influent percentiles, reduced KLa profiles, event durations) and orchestrates the MATLAB scripts. Parse the raw outputs into a structured database (e.g., Pandas DataFrame).

[ ] Checkpoint 3: Python Data Analysis Engine. Generate the Python module that processes the database to calculate E_saved, E_red, COD_dmg, NH4_dmg, MTBF_red return periods, and the Effluent Risk Indicator. Append these derived metrics as new columns to the database.

[ ] Checkpoint 4: Python ML Surrogate Model. Generate the Python code to train, validate, and save an ML surrogate model (Random Forest/XGBoost) mapping the operational inputs to the Risk and Energy Savings outputs.

[ ] Checkpoint 5: Python NSGA-II Optimizer. Generate the Python script implementing NSGA-II (e.g., using pymoo) that purely queries the surrogate model to calculate the optimal Pareto front of the cost + risk curve. Extract the final operational policy mapping.

ACTION REQUIRED:
Acknowledge these loop rules and output your internal checklist status. Then, immediately output the highly-commented code strictly for Checkpoint 1. Remind me that physics are isolated to this MATLAB script, print [CHECKPOINT WAITING], and pause for my feedback.