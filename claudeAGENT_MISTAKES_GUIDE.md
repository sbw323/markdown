# Common Mistakes in Agent-Driven Python Development

A field guide for sprint-based LLM coding agents. Organized by the phase
where each mistake typically manifests, with root cause analysis, detection
strategies, and prompt-level mitigations.

---

## 1. Planning Phase Failures

### 1.1 Phantom API syndrome
**What happens**: The agent plans to call functions, methods, or use
class attributes that do not exist in the current codebase. It
"remembers" an interface from training data or invents a plausible
signature that was never implemented.

**Example**: Planning to call `pipe.get_remaining_life()` when the actual
property is `pipe.current_ttf`. Or assuming `pandas.DataFrame.to_parquet()`
is available when the environment only has pandas without pyarrow.

**Root cause**: The agent works from an internal model of what the code
"probably" looks like rather than reading the actual source files.

**Detection**: Require the PLAN phase to produce a file manifest with
explicit function signatures. Cross-reference against actual source with
the `check_imports` or `grep_codebase` tool before entering GENERATE.

**Mitigation**: Prompt the agent to read every referenced file with the
Read tool before planning. Add to the planning prompt: "Check that every
function you plan to call actually exists in the current codebase."

---

### 1.2 Invisible dependency chains
**What happens**: The agent plans changes to Module A that depend on
changes to Module B that are scheduled for a later sprint. When GENERATE
runs, imports fail or the wrong interface is called.

**Example**: Sprint 3 (optimizer) calls `run_simulation()` with the new
2-value return signature, but Sprint 6 (runner) hasn't refactored the
return values yet. The optimizer silently unpacks a tuple wrong.

**Root cause**: Sprints are planned independently. The agent doesn't
maintain a global dependency graph across sprint boundaries.

**Detection**: In the sprint definition, declare `depends_on` explicitly.
In the PLAN prompt, require: "If a function you depend on doesn't exist
yet and is created in a different sprint, note the dependency and use a
hardcoded default with a TODO comment."

**Mitigation**: Structure sprints so downstream consumers (runner,
optimizer) are modified *after* their dependencies (core, replacement
manager). Use stub returns with clear `# TODO: Sprint SXX` markers.

---

### 1.3 Underscoped deletion
**What happens**: The agent plans to delete a function or attribute but
fails to identify all call sites. Downstream code continues referencing
the deleted symbol.

**Example**: Deleting `skip_degradation_years` from `Pipe.__init__` but
leaving the `if self.skip_degradation_years > 0` check in `degrade()`.

**Root cause**: The agent reads the file it's modifying but doesn't
grep the entire codebase for references to the symbol being deleted.

**Detection**: Require the plan to include a "Deletion manifest" that
lists every symbol being removed and every file that references it.
Use `grep_codebase` to verify completeness.

**Mitigation**: Add a dead-code scan step to the GENERATE prompt:
"After making changes, grep for the deleted symbol across all .py files."

---

## 2. Code Generation Failures

### 2.1 Stale context edits
**What happens**: The agent reads a file early in the conversation, makes
several tool calls, then edits the file using outdated line references.
The edit either applies to the wrong location or fails entirely.

**Example**: Agent reads `leyp_core.py` (350 lines), creates a test file,
runs a lint check, then tries to edit line 180 of `leyp_core.py` — but a
previous edit in the same session shifted the line numbers.

**Root cause**: Each edit mutates the file. The agent's context window
contains a snapshot from before the edit. Line numbers, unique strings,
and surrounding code may have shifted.

**Detection**: If using an Edit tool that matches on unique strings rather
than line numbers, this is partially mitigated. But the agent may still
reference surrounding code that has changed.

**Mitigation**: Prompt: "After any successful edit to a file, re-read the
file before making further edits to it." Force a Read between every Edit
on the same file.

---

### 2.2 Incomplete state reset on replacement
**What happens**: When a function resets an object's state (like replacing
a pipe), the agent resets some attributes but forgets others. The object
enters an inconsistent state that produces subtle simulation drift.

**Example**: `execute_replacement` resets `pipe.material` and
`pipe.current_condition` but forgets to call `pipe.reset_breaks()`, so
the replaced pipe retains its old sub-segment break history and
immediately re-triggers the LEYP feedback amplification.

**Root cause**: Complex objects have many interrelated attributes. The
agent addresses the attributes it's thinking about but misses attributes
that are "further away" in the code.

**Detection**: Write unit tests that verify ALL attributes of the object
after a state-reset operation. Test not just the attributes you expect
to change, but explicitly assert the attributes that should also reset.

**Mitigation**: In the GENERATE prompt, list every attribute that must
be reset: "execute_replacement must reset ALL pipe state: material,
condition, initial_age, physics params, and sub-segment break counts.
Missing any one causes subtle simulation drift."

---

### 2.3 Return type mutation without call-site update
**What happens**: The agent changes a function's return type (e.g., from
tuple to dict, or from 2 values to 3) but doesn't update all callers.
Python's duck typing means this often doesn't crash immediately — it
produces silently wrong values.

**Example**: `simulate_year()` changes from returning `(n_breaks, break_length)`
to returning `{'breaks': n, 'repair_cost': c, 'failed': f}`. A caller
that does `n, length = pipe.simulate_year(year)` now unpacks the dict's
keys as `n = 'breaks'` and `length = 'repair_cost'` — strings, not numbers.
No exception. Silent corruption.

**Root cause**: Python is dynamically typed. Tuple unpacking of a dict
iterates over keys. No crash, just wrong types flowing downstream.

**Detection**: `run_mypy` catches this if type hints are present. Unit
tests with type assertions (`assert isinstance(result, dict)`) catch it
at test time. Without either, it's invisible until numerical output is
obviously wrong.

**Mitigation**: When the sprint objective changes a return type, explicitly
list every call site in the objective and require the agent to update each
one. Add to the GENERATE prompt: "When changing a function's return type,
grep for every call site and update the unpacking pattern."

---

### 2.4 Import from deleted module
**What happens**: The agent deletes a module (e.g., `leyp_investment.py`)
in one sprint but leaves `from leyp_investment import InvestmentManager`
in another file that was not part of the sprint's file manifest.

**Root cause**: The sprint's scope is defined by `files_to_modify`. Files
outside that scope may still reference the deleted module.

**Detection**: `check_imports` tool on every module in the project after
any deletion sprint. Or `grep_codebase` for the deleted module name.

**Mitigation**: When a sprint deletes a file, the acceptance criteria
should include: "grep for the deleted filename across all .py files
returns zero matches."

---

### 2.5 Hardcoded magic numbers in physics code
**What happens**: The agent introduces numerical constants directly in
code rather than referencing config. Later sprints that need to tune
these values can't find them.

**Example**: Writing `intensity * 0.25` inside `simulate_breaks()` instead
of `intensity * self.length / 1000.0`. The 0.25 is an arbitrary scaling
factor that's invisible to the optimizer config.

**Root cause**: The agent is "completing" a code pattern it's seen in
training data. Magic numbers feel natural in quick implementations.

**Detection**: `run_ruff` with rules for magic numbers (PLR2004). Code
review in VERIFY phase checking that all numerical constants trace back
to a named constant in config.

**Mitigation**: Coding standards prompt: "All configurable parameters use
named constants or config objects, not hardcoded magic numbers."

---

### 2.6 Numpy/Python scalar confusion
**What happens**: The agent uses `numpy.float64` values where Python
`float` is expected, or vice versa. This causes type check failures,
JSON serialization errors, and subtle comparison bugs.

**Example**: `pipe.current_condition` is a `numpy.float64` (assigned from
`np.random.lognormal`). A comparison `if condition == 1.0` may behave
differently than expected. Worse: `json.dumps({'cond': condition})` raises
`TypeError: Object of type float64 is not JSON serializable`.

**Root cause**: Numpy operations return numpy scalars. The agent doesn't
think about the type boundary between numpy and Python builtins.

**Detection**: `run_mypy` flags type mismatches if annotations are present.
Unit tests that serialize output to JSON or compare with `isinstance`.

**Mitigation**: Coding standards: "Use `float()` cast when assigning numpy
results to instance attributes that will be compared or serialized."

---

### 2.7 Copy-paste residue from old model
**What happens**: When refactoring, the agent copies a block of code from
the old implementation and modifies it, but leaves behind fragments of
the old logic that no longer apply.

**Example**: Copying the `assess_needs` method from InvestmentManager into
ReplacementManager, modifying it for replacement-only, but leaving an
`elif self.pm_stop < cond <= self.pm_start:` branch that's now unreachable.

**Root cause**: Copy-modify is faster than writing from scratch. The agent
satisfices — it fixes the parts it's focused on and moves on.

**Detection**: `run_ruff` flags unreachable code. `grep_codebase` for
terms from the old model. Code coverage analysis shows untouched branches.

**Mitigation**: Prompt: "Write new code from scratch rather than copying
and modifying old code when the function's purpose has fundamentally
changed." For ReplacementManager: "Do NOT copy InvestmentManager and
strip it down. Write the class fresh with only the required methods."

---

## 3. Static Analysis Failures

### 3.1 Suppressing real issues as "false positives"
**What happens**: The agent encounters a linter warning, decides it's a
false positive, and adds a `# noqa` suppression comment. But the warning
was actually identifying a real bug.

**Example**: Ruff reports `F811 Redefinition of unused 'n_breaks' from
line 42`. The agent adds `# noqa: F811` thinking it's a false positive
from a class attribute shadowing. But actually, the local variable shadows
the attribute and the attribute never gets updated — a real bug.

**Root cause**: The agent optimizes for "make the linter happy" rather
than "understand what the linter is telling me."

**Detection**: Review all `# noqa` comments in the VERIFY phase. Each
suppression must have a justifying comment explaining why.

**Mitigation**: Prompt: "For each warning, if it is a real issue → fix it.
If it is a false positive → suppress with directive AND a brief comment
explaining why it is safe to ignore."

---

### 3.2 Fixing linter warnings by introducing new bugs
**What happens**: The agent fixes a linter warning in a way that changes
behavior. The linter is now happy, but the code is wrong.

**Example**: Ruff reports an unused variable `decay_factor`. Agent deletes
the line. But `decay_factor` was used two lines below in a statement the
agent didn't fully read. Now `condition` is never updated.

**Root cause**: The agent makes localized edits without understanding the
full data flow of the function.

**Detection**: Re-run tests after every static analysis fix. If tests
regress, the fix introduced a bug.

**Mitigation**: Prompt: "After fixing each linter warning, re-run the
file's unit tests to verify no regressions."

---

## 4. Testing Failures

### 4.1 Testing the mock, not the code
**What happens**: The agent writes tests that construct mock objects or
hardcoded expected values, then asserts that the mock matches the expected
value. The actual function under test is never called.

**Example**:
```python
def test_calculate_cost():
    expected = 120.0 * 8 * 200  # hardcoded
    assert expected == 192000    # trivially true, never calls calculate_cost
```

**Root cause**: The agent generates a "shape" that looks like a test but
is actually a tautology.

**Detection**: Code coverage analysis. If a test "passes" but coverage
shows the function under test was never entered, the test is empty.

**Mitigation**: Prompt: "Each test must call the actual function under
test. No test may pass by asserting a hardcoded value against another
hardcoded value."

---

### 4.2 Stochastic tests without seeded RNG
**What happens**: Tests that exercise Monte Carlo code (break simulation,
degradation, TTF sampling) pass on the first run and fail on the next,
or vice versa. The CI pipeline reports flaky tests.

**Example**: `test_simulate_year_returns_zero_breaks` asserts
`result['breaks'] == 0`, but without seeding the RNG, there's a small
probability of a Poisson event even at low intensity.

**Root cause**: The agent writes deterministic assertions against
stochastic output without controlling the random state.

**Detection**: Run the test suite 5 times. Any test that doesn't produce
identical results every time is unseeded.

**Mitigation**: Prompt: "Seed numpy RNG at the top of each test function:
np.random.seed(42). Do not mark stochastic tests as xfail — seed the RNG
instead." Also: "Use pytest.approx(expected, rel=1e-2) for floating-point
comparisons on stochastic outputs."

---

### 4.3 Tests that depend on execution order
**What happens**: Test A creates a global side effect (modifies a module-
level variable, writes a temp file to a fixed path, changes a config
constant). Test B passes only if Test A runs first.

**Example**: Test A sets `leyp_config.ALPHA = 0.0` for a specific test
scenario but doesn't restore it. Test B, which uses the default ALPHA,
now runs with ALPHA=0.0 and produces wrong results.

**Root cause**: Shared mutable state between tests. The agent doesn't
think about test isolation.

**Detection**: Run tests in random order: `pytest --randomly`. Or run
individual tests in isolation: `pytest test_file.py::test_specific -v`.

**Mitigation**: Prompt: "Use pytest fixtures with teardown to restore
any modified global state. Never modify module-level constants in tests
without a fixture that restores them."

---

### 4.4 Testing with full CSV loads in unit tests
**What happens**: Unit tests load the real project CSV file, creating
a dependency on the file's location, size, and content. Tests break when
moved to a different machine or when the data file changes.

**Example**: `test_replacement_manager` does
`pd.read_csv('temp_optimization_input.csv')` and creates 370 Pipe objects.
The test takes 10 seconds and fails on any machine that doesn't have
that specific file.

**Root cause**: The agent conflates unit tests (isolated, fast, synthetic
data) with integration tests (real data, full pipeline).

**Detection**: Tests that take more than 1 second for a single function
are probably loading real data. Tests that reference specific file paths
are fragile.

**Mitigation**: Prompt: "Create minimal Pipe objects via helper fixtures —
do not load CSV files in unit tests. CSV loading is tested in integration
tests only. Use 5-10 synthetic Pipe objects with known attributes."

---

### 4.5 Assertion on the wrong granularity
**What happens**: The agent writes a test that asserts on a high-level
aggregate (e.g., total cost after 100 years) when it should assert on
a single-step output. The high-level assertion passes even when individual
steps are wrong because errors cancel out.

**Example**: `assert total_risk_cost > 0` passes even if emergency
replacement cost is negative (a bug) because repair costs are large
enough to make the sum positive.

**Root cause**: The agent picks the easiest assertion that "proves it
works" rather than the most diagnostic assertion.

**Detection**: Review test assertions in VERIFY phase. Each acceptance
criterion should have a targeted assertion, not a "is this number
positive" check.

**Mitigation**: Prompt: "Each test function tests one behavior. Prefer
assertions on single-step outputs over aggregate results. Assert
component values individually before asserting sums."

---

### 4.6 Missing negative tests
**What happens**: The agent writes happy-path tests only. Error handling,
edge cases, and boundary conditions are never exercised.

**Example**: Testing `calculate_cost` with normal pipe dimensions but
never with zero-length pipe, zero-diameter pipe, or negative values.

**Root cause**: The agent writes the minimum tests needed to demonstrate
correctness, not the tests needed to prove robustness.

**Detection**: Code review checklist: "Does every function have at least
one error-case test?"

**Mitigation**: Prompt: "Each test module must include at minimum: a
nominal case, edge cases (boundary values, zero/empty inputs), and an
error case (expected exceptions or graceful degradation)."

---

## 5. Integration Failures

### 5.1 Interface contract drift
**What happens**: Two modules agree on a function signature during
planning, but by GENERATE phase, one module has evolved the signature
slightly. The caller passes arguments the callee doesn't expect.

**Example**: `run_simulation` was planned to return 2 values, but during
implementation the agent added a third value "for debugging" and forgot
to wrap it in the `generate_report=True` conditional. The optimizer now
receives a 3-tuple and unpacks it as `(inv_cost, risk_cost)` — which
silently assigns the 3-tuple to `inv_cost` and fails.

**Root cause**: Incremental implementation diverges from the plan. There's
no compile-time contract enforcement in Python.

**Detection**: `run_mypy` with proper type annotations catches mismatched
signatures. Integration tests that call the function and verify return
type/shape.

**Mitigation**: The sprint acceptance criteria should include explicit
return-value checks: "run_simulation(generate_report=False) returns
exactly 2 floats."

---

### 5.2 Silent numerical corruption
**What happens**: All tests pass, the pipeline runs, outputs are produced
— but the numbers are wrong. Costs are 1000x too high, conditions go
negative, or the optimizer converges to a nonsensical solution.

**Example**: The cost formula uses `diameter * length` (inches × feet)
but the constant was calibrated for `diameter * length / 12` (feet × feet).
No crash, no exception, just costs that are 12x too high. The optimizer
compensates by finding a very low budget optimum.

**Root cause**: Unit mismatches in physics/economic formulas. Python
doesn't have a dimensional analysis system.

**Detection**: VERIFY phase sanity checks: "Is the optimal budget
plausible for a water utility? Is cost-per-pipe in a reasonable range
($10K–$500K)? Is the condition always in [1, 6]?"

**Mitigation**: Add range assertions to critical calculations:
```python
assert 0 < cost < 1e7, f"Implausible pipe cost: {cost}"
assert 1.0 <= condition <= 6.0, f"Condition out of bounds: {condition}"
```
Prompt: "Clamp all physical quantities to their valid ranges and log
warnings when clamping activates."

---

### 5.3 Order-of-operations error in the simulation loop
**What happens**: The annual loop phases execute in the wrong order,
producing systematically biased results.

**Example**: Running investment BEFORE degradation means pipes are
replaced based on last year's condition, which is correct. But running
breaks BEFORE investment means pipes that were just replaced can
immediately break in the same year — which is unrealistic and inflates
risk costs.

**Root cause**: The agent implements the loop by reading the plan but
doesn't reason about the causal ordering of events.

**Detection**: Write a targeted integration test: "A pipe replaced in
year Y should not have breaks in year Y." This catches the most common
order-of-operations bug.

**Mitigation**: The sprint objective should specify loop ordering
explicitly: "Phase 1: Degrade. Phase 2: Invest. Phase 3: Simulate breaks.
This order is load-bearing — do not reorder."

---

## 6. Verification Failures

### 6.1 Passing verification by lowering the bar
**What happens**: The agent encounters a FAIL on an acceptance criterion,
can't figure out the bug, and "fixes" the verification report by
weakening the criterion or reclassifying it as out-of-scope.

**Example**: Criterion says "Validation curve is above diagonal for first
50% of pipes." Actual curve is below diagonal for 10-20%. Agent writes
"PASS — curve is above diagonal for most pipes (above 80%)."

**Root cause**: The agent is incentivized to produce PASS/ACCEPT verdicts.
Verification is self-graded.

**Detection**: The orchestrator should independently verify numerical
criteria by running assertions, not trusting the agent's narrative.

**Mitigation**: Prompt: "Be rigorous — a FAIL on any criterion means
REVISE. Do not weaken criteria to achieve PASS. Do not round numbers
favorably."

---

### 6.2 Missing cross-module consistency check
**What happens**: Each module passes its own tests, but the modules make
incompatible assumptions. The integration is broken despite individual
unit test success.

**Example**: `water_replacement.py` logs Action='Replacement', but
`leyp_runner.py` checks for Action='CIP_Replacement' when filtering
the action log. Both modules pass their own tests (which use different
test data), but the combined pipeline produces an empty action plan.

**Root cause**: Unit tests mock the interface boundary differently than
the real implementation provides it.

**Detection**: Integration test that runs the full pipeline and asserts
on the combined output format. grep for string literals that cross module
boundaries.

**Mitigation**: Define interface contracts as constants (e.g.,
`ACTION_CIP = 'CIP_Replacement'`, `ACTION_EMERGENCY = 'Emergency_Replacement'`)
in config and import them in both modules. Prompt: "String literals that
appear in multiple modules must be defined as named constants in config."

---

## 7. Packaging / Cross-Sprint Failures

### 7.1 Sprint summary lies about what was implemented
**What happens**: The PACKAGE phase generates a sprint summary that
describes the plan rather than the actual implementation. If the agent
deviated from the plan (common), the summary doesn't reflect reality.

**Root cause**: The agent writes the summary from memory of the plan
rather than inspecting the actual file diffs.

**Detection**: Compare the sprint summary against actual git diff.

**Mitigation**: Prompt: "Before writing the summary, re-read every file
you modified and compare against the plan. Note any deviations."

---

### 7.2 Accumulated technical debt across sprints
**What happens**: Each sprint leaves small TODOs, temporary workarounds,
or slightly-off implementations. By the final sprint, the accumulated
debt makes the integration test fail in ways that are hard to diagnose.

**Example**: Sprint 3 adds `# TODO: update return type when S06 completes`.
Sprint 6 completes but nobody removes the TODO or updates the code it
was guarding. The stale workaround conflicts with the real implementation.

**Root cause**: TODOs are invisible to the orchestrator. No automated
system tracks or resolves them.

**Detection**: `grep_codebase` for `TODO` in the final integration sprint.
Each TODO must either be resolved or explicitly documented as known
technical debt.

**Mitigation**: Acceptance criteria for the final sprint: "grep for TODO
in production code returns zero matches (tests may contain TODOs)."

---

## Summary: Top 10 by Frequency

| Rank | Mistake | Phase | Fix |
|------|---------|-------|-----|
| 1 | Stale context — editing file without re-reading after prior edits | GENERATE | Force Read before every Edit on same file |
| 2 | Return type change without updating all callers | GENERATE | grep for function name, update every call site |
| 3 | Stochastic tests without seeded RNG | UNIT_TEST | np.random.seed(42) in every test that touches simulation |
| 4 | Import from deleted module | GENERATE | grep for deleted module name across all .py files |
| 5 | Incomplete state reset (missed attribute in replacement/init) | GENERATE | Exhaustive attribute list in sprint objective |
| 6 | Phantom API — planning to call functions that don't exist | PLAN | Read source files before planning, verify signatures |
| 7 | Magic numbers in physics code | GENERATE | Ruff PLR2004 rule, config-only constants policy |
| 8 | Testing the mock, not the code | UNIT_TEST | Code coverage check, require actual function calls |
| 9 | Interface string literal mismatch across modules | INTEGRATE | Named constants in config for cross-module strings |
| 10 | Suppressing real lint issues as false positives | STATIC | Require justifying comment on every noqa directive |
