We are resuming Phase 2B: Incremental Implementation.

You previously produced a Progress Ledger describing the current execution state.
Treat that ledger as authoritative state memory.

You must reconstruct the implementation state ONLY from the ledger.
Do NOT re-analyze the experiment plan.
Do NOT regenerate the refactor plan.
Do NOT restart from Task 1.1 unless the ledger explicitly says so.

------------------------------------------------------
STATE RESTORATION RULES
------------------------------------------------------
1) Tasks listed under "Completed" are immutable.
   Never modify them unless they are proven blocking.

2) Tasks listed under "In Progress" should be finished first.

3) Tasks listed under "Next" define the next execution targets.

4) Respect dependency ordering from the Phase 2A map:
   Foundation → MATLAB Layer → Verification Gate → Data Layer → Modeling Layer

5) If the ledger shows the pipeline reached the MATLAB verification gate:
   Do NOT continue implementation.
   Return WAIT_FOR_VERIFICATION unless the user explicitly confirms success.

------------------------------------------------------
WHAT YOU MUST DO
------------------------------------------------------
1) Reconstruct execution position
2) Choose the next ≤3 valid tasks
3) Continue implementation using the standard Phase 2B response format

Never repeat already completed patches.

------------------------------------------------------
RESPONSE FORMAT
------------------------------------------------------
Follow the normal Phase 2B structure:

Selected Tasks
Patches
Local Validation
Progress Ledger
Manager Decision

------------------------------------------------------
SPECIAL CASES
------------------------------------------------------
If new files were uploaded:
Incorporate them only if they affect the current or next task.

If the ledger is inconsistent or missing tasks:
Return BLOCKED and explain what state information is required.

------------------------------------------------------
INPUT
------------------------------------------------------
The next message will contain:
- The last Progress Ledger
- Optional new files

Wait for it before continuing.
