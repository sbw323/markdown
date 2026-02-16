You are entering Phase 2A: Refactor Planning.

You already created an architecture and acceptance criteria in Phase 1.
You now have access to the experiment plan and the uploaded Python scripts.

Your job in this phase is NOT to modify code.

Your job is to create a complete and deterministic refactor plan that can be executed in small batches later without re-analysis.

This phase exists to prevent long-running inference failure.
The output of this phase will be treated as a checkpoint specification for Phase 2B.

-----------------------------------
OBJECTIVE
-----------------------------------
Produce a stable "Refactor Execution Map" describing exactly how the existing codebase must change to satisfy the Phase-1 architecture and acceptance criteria.

This must be complete enough that Phase 2B can execute blindly without reinterpreting requirements.

-----------------------------------
RULES
-----------------------------------
1) Do NOT output code patches.
2) Do NOT rewrite files.
3) Do NOT solve problems yet.
4) Identify — don’t implement.

If behavior is unclear, record an assumption contract instead of guessing.

-----------------------------------
REQUIRED OUTPUT
-----------------------------------

## 1) Codebase Inventory
For each file:
- purpose
- entry points
- inputs/outputs
- hidden side effects
- architectural violations

## 2) Requirement Gap Matrix
Table mapping:

Plan Requirement
→ Current Behavior
→ Gap
→ Required Change Type (refactor / isolate / wrap / replace / new module)

## 3) Dependency & Execution Graph
Define:
- execution stages
- file responsibilities
- data flow between stages
- where checkpoint boundaries must exist

## 4) Refactor Execution Map (CRITICAL CHECKPOINT ARTIFACT)

Create a numbered list of atomic tasks.
Each task must include:

Task ID:
Files affected:
Change category: (move | split | wrap | parameterize | add config | add logging | add checkpoint | create module)
Preconditions:
Postconditions:
Verification signal:
Can run independently: (yes/no)

Tasks must be small enough that no task would require more than ~200 lines of output to implement.

## 5) Risk & Ambiguity Register
List anything unclear and define a deterministic assumption so implementation never blocks.

## 6) Phase-2B Execution Instructions
Provide instructions to your future self describing:
- the order tasks must be executed
- which tasks can run in parallel
- when to run tests
- when to stop

-----------------------------------
STOP CONDITION
-----------------------------------
End only when the Refactor Execution Map is fully complete and self-sufficient.

Do NOT begin implementation.
This document will be reused as a persistent checkpoint.
