We are revisiting Phase 2A (Refactor Planning Checkpoint).

The previous Refactor Execution Map is now incomplete because the experiment depends on MATLAB model behavior that has not yet been incorporated.

I will now provide the MATLAB code used by the simulation model.

Your job is to UPDATE the existing Refactor Plan — not replace it — so that the Python pipeline correctly interfaces with the real MATLAB behavior instead of assumptions or placeholders.

-------------------------------------------------------
CRITICAL RULE
-------------------------------------------------------
Preserve all existing Task IDs and structure whenever possible.
Only modify or extend tasks that are affected by MATLAB behavior.

Do NOT redesign the architecture.
Do NOT restart the planning process.
Do NOT begin implementation.

You are performing a surgical augmentation of the plan.

-------------------------------------------------------
OBJECTIVE
-------------------------------------------------------
Incorporate the real MATLAB workflow into the pipeline design so that:

• MatlabAdapter responsibilities become accurate
• Scenario generation produces valid inputs for MATLAB
• Runner produces correct .mat artifacts
• ETL reflects actual MATLAB output structure
• Risk metrics reference real output variables
• Surrogate + optimizer operate on real data fields

-------------------------------------------------------
WHAT YOU MUST PRODUCE
-------------------------------------------------------

1) MATLAB Interface Analysis
After I provide the code, identify:
- required inputs
- produced outputs
- file formats (.mat structures, variable names, dimensions)
- execution sequence
- side effects (workspace assumptions, global variables, paths)

2) Impacted Tasks
List which existing Task IDs must change and why.

3) Task Modifications
For each affected task provide:

Task ID:
What changes:
New preconditions:
New postconditions:
New verification signal:

4) New Tasks (only if unavoidable)
If MATLAB introduces behavior not represented in the plan,
append new tasks using decimal extensions:
Example: Task 2.3a, 3.1b, etc.

5) Updated Pipeline Diagram (text description)
Show the new data flow including MATLAB artifacts.

6) Updated Stop & Check Gate
Define precisely what artifact the user must confirm before real MATLAB runs.

-------------------------------------------------------
STOP CONDITION
-------------------------------------------------------
End when the Refactor Execution Map is updated and fully consistent with the MATLAB model.

Do NOT implement code yet.
Wait for the MATLAB files.
