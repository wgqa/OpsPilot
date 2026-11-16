# E10-H Readiness Report

**Result:** offline integration evidence ready for independent review; first Live remains unauthorized and unverified.
**Candidate base:** `335346c3c96b06e3de65c70c1096eb5ae1961a6b`
**Gold status:** not scored. The frozen `execution_constraint` still caps any result at `PARTIAL`.

## What was executed

- Initialized a new isolated `.runtime/user-demo-r2-e10h-readiness-02` from the existing `r2-e07-queued` S3 fixture only after verifying that the directory did not exist. The earlier `-01` iteration is retained separately and is not the final trace source.
- Ran the normal FastAPI app and single Worker in-process with the explicit Fixture Model; `assistant_runtime_enabled=False`.
- Created two independent source Sessions/Tasks via formal Assistant order API. Each Semantic Memory went through the candidate API and project APPROVER confirmation. B was revoked through the existing formal revoke API before the target request.
- Submitted the original E10-H frozen input to fresh target Sessions and observed current target-Task Delivery/Receiver MCP results.
- Verified A was present in each ON model wire, tagged as project context rather than a fact; B and its conflicting content were absent. The Context Manifest excluded B as `SEMANTIC_MEMORY_REVOKED`.
- Ran a separate source-digest invalidation variant. The row remained ACTIVE but its source was not current; Context excluded it as `SEMANTIC_MEMORY_SOURCE_INVALID`, and it did not appear in target model messages.
- Ran a taskless, no-memory/no-current-observation control through the formal Assistant message API. No TaskBinding, Memory or MCP read was available; the Fixture response explicitly left the current status unknown and the Run succeeded.
- Compared Memory ON and OFF under the same frozen prompt and synthetic queued profile. Both arms used the same tool schemas and MCP tool names, matched on the business fact projection and returned identical Fixture answers. ON estimated Semantic Memory context was 279 tokens; OFF was 0. Fixture Usage metadata was 45 input / 15 output tokens per arm and is not Provider usage.

## Evidence counts

Final named Runtime trace (`user-demo-r2-e10h-readiness-02`): **7 successful Runs** (3 source, 3 bound targets, 1 taskless control), **13 Fixture Model calls**, **6 local read-only MCP calls**, **228 Fixture-reported tokens** (160 input / 68 output), **0 real Provider sends**, **0 Runtime Grant rows**, **0 Spend rows**, and **0 protected business writes**. Provider token and cost totals are `NOT_APPLICABLE` because no Provider was called. The complete IDs, events, calls, model wires, manifests and source observations are in `E10_OFFLINE_TRACE.json`.

The detailed test result is one E10 test passing in a temporary isolated DB and again in the new named Runtime; **29/29** AR04B, M303 Semantic Memory and selected C01-B2-A Personal Memory tests passed. See `E10_TEST_LOG.txt`.

## What this does and does not establish

Established: the existing Semantic Memory candidate/confirmation/revocation lifecycle, tenant/project scope, Context selection/exclusion, actual model wire, current MCP Observation, Task/Event identity, taskless no-evidence behavior, and empty-Grant offline execution work together for this synthetic case.

Not established: real-model comprehension, useful behavioral benefit from A, statistical ON/OFF effect, browser/UI behavior, real Live startup/Preflight, Provider pricing/usage, or formal E10 score. Fixture calls and fixture usage are not real model evidence. The ON/OFF arms have distinct Task/Run IDs and observation timestamps; this is a matched integration contrast, not a controlled model-quality experiment.

## Remaining items

- Main Agent should independently inspect the source, generated Trace and preserved Gold ceiling.
- A later Live test needs separate explicit case/cost authorization, fresh price and local Grant preflight, one frozen input submission, no retry on UNKNOWN, and independent M1–M6 scoring.
- The prepared runtime was not started with the normal PowerShell Live launcher. Its successful offline TestClient run is not a Live preflight result.
- The existing AR04B fixture `JourneyFixtureModel` preselects the receiver tools. Do not claim the model autonomously chose them.
- The prior `user-demo-r2-e10h-readiness-01` iteration remains preserved as a separate synthetic offline runtime; the final extended trace and report use `-02`.

No production code, frozen evaluation files, E09 data, external business state or Grant was changed.
