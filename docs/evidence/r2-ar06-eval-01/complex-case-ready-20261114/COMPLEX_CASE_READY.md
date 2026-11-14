# R2-AR06 Complex Case Live Readiness

**Date:** 2026-11-14
**Status:** ACCEPTANCE_CANDIDATE — offline readiness evidence only; E03-D and E11-D are not approved for Live by this preparation.

## Baseline and evidence boundary

- Repository/worktree: D:\OpsPilot-LIVE-02-FIX-01-HF02
- Base: codex/r2-ar06-holdout-ready-01@0fc26da0ea08309977460e44f5ff60fcae1adb9b
- Candidate branch: codex/r2-ar06-complex-case-ready-01
- No new Worktree was created. Existing LIVE-02 databases, Checkpoints, Grants, Spend rows, and prior traces were not changed.
- The worktree was clean at the Base. Current uncommitted changes are this report and the two command/test logs beside it.
- PROJECT_NORTH_STAR.md blob 43dabda468506717c6956e676dfad4304c4f38e6; AGENTS.md blob 807b928686a4dd2cac7b15b3c354b9943c93c910; .agents/skills/opspilot-slice-review/SKILL.md blob d405c8d413d633824b279202cc1503dab4cf0b03. All three were read from the Base checkout.
- Frozen contracts were not modified: CASES.json SHA-256 c1acd3fa789befa733aa96bf3a49b08357ff071f3b627b4c40319882e2805cf8; RUBRIC.json 859985480169b04824a96a97db3031c312a68abbb550be3a96ffa6cbe5040944; EVAL_PROTOCOL.md 22c0677121a2106fa529c4a5c245ca557ad5d7ea8ed01d3660bc4171d77e12c7.
- Frozen contract Git blobs at Base: CASES.json c3f5190fa7193e89d36a3e54f5489577d0c0b033; RUBRIC.json 71e8f975e50b2883c1ea96c785a66fbd3207606d; EVAL_PROTOCOL.md be2969c409b13966cd2c6222445974710e02422f.
- Inspected source Git blobs at Base: Start-UserDemo.ps1 cd756082db7a7ed372e88987b3171f571b559864; runtime_admin.py d89a1e240060e910f5a80c1b09e89fea590e637b; run_r2_ar06_case.py 74e3f91a91e55cd1e059102682d6cc413ba7817c; initialize_demo.py f2fce512bc437b94151feaa0a4b4dfc470cae35a; worker.py d4492da74202291490c2e753c2c7d9e3921a06ee; investigator.py 68fa0fe6632fca30426667e54a137e9f9373f812; assistant.py ad483250200ce59a1ed19d5f52b29acde9be8f55; config.py 29728b47c826b4620d7ccca3052c8b63f9365c44; domain/d2.py 20fd4b2c47e6fc7581bc135d6e5a8e7ea093ddbb; assistant_runtime_grant.py fe148f656cbbc183e45af4cd722ab2c05d13909c; assistant_mcp.py 4b61b8a7cb9c37ac21adb2b1cb779045e95fc49e; assistant_knowledge.py 160746699969637ffd545069f9ba1e6dbce3b721; knowledge_assets.py 062fa4b084ccf392368f269d6a6e90919e791f0b; scoped_protocol_comparison.py 1f8e3c6cf09b8ccd4369b3e91b60aaf4a5820675; assistant-access.json 1b641d7d9f1ffd6c8c8de7eddbede9cd5e3c4d00; async-callback/manifest.json ba68013d54d08621a120e091ff0bf7f27b7e34c4; web/app.py 2b8bbc8b2f64b527a7219a53e27e8388974a33ff.
- Inspected regression Git blobs at Base: test_ar03_02_scoped_protocol_comparison.py be66b83d464ffcdf4b59904cf12bb8c60d953699; test_m2_02_s2_diagnosis.py 37b0e96b1dac5c77bd386f8f3f91f4027965db23; test_ar05_s2_assistant_handoff_01.py c91f2077b1d9ae6a7285d5843c83cb03944fbf8d.
- No Provider request, Runtime Grant, controlled handoff submit, external business write, or browser automation occurred.

## E11-D — S2 403 investigation and controlled handoff

### Frozen case and current implementation

Gold requires a trusted S2 TaskBinding, a current HTTP 403 Probe, matching current DENY / SCOPE_INSUFFICIENT facts for that Probe's exact request ID, a DiagnosisReceipt, and a frozen handoff draft. A local HandoffReceipt is expected only after the user explicitly submits the draft. Scope/Grant/Policy must remain unchanged.

The existing synthetic S2 fixture is present. Start-UserDemo.ps1 with Profile S2 selects orders-demo-s2 and integration-s2-a; initialize_demo.py seeds the missing-scope condition. The Investigator schema supports autonomous tool_choice=auto; after a same-Run 403 it exposes get_scope_authz_facts for the Probe's returned request ID. opspilot/domain/d2.py bounds an Investigator Task to 8 model attempts and 6 MCP attempts.

### Historical NotImplementedError: fixture defect, plus a separate current Live blocker

The prior E11 traces record CHAT_READONLY Runs run-623b25e6-6b38-4f92-9d68-dde111ccee5c and run-d1bd6cca-b195-4ebc-880a-cac17eda6a6b as FAILED with ASSISTANT_STOP:NotImplementedError, no persisted Provider response, and zero Provider HTTP requests. The historical test's _AssistantAnswerModel implemented _generate but not bind_tools, while the Assistant middleware calls bind_tools. That explains this specific failure as a Fixture Model defect; it does not show a production ChatOpenAI bind-tools failure. The separate successful Fixture Investigator Run was run-4adfb6a7-66ab-4b4a-b13e-1d12724104aa for Task task-2acc6820-8214-4b4a-b13e-1d12724104aa. The preserved source artifacts are runs/E11_S2_ASSISTANT_FIXTURE_FAILURE_ATTEMPT_1.json, runs/E11_S2_ASSISTANT_FIXTURE_FAILURE.json, and runs/E11_S2_HANDOFF_TRACE_CAPTURE.json under docs/evidence/r2-ar06-eval-01.

The separate INVESTIGATE path did complete in the historical fixture trace. It called probe_endpoint and get_scope_authz_facts under the same Run and same request ID (31f39c711a107873), producing the current S2 denial evidence and draft. The later historical submit created only a local pending-review handoff; Scope remained unchanged. This is historical Fixture evidence, not a new Live result.

The present Live startup cannot safely execute that Investigator path:

- opspilot/web/worker.py::_process_run_inner and opspilot/investigator.py::run_investigation require require_legacy_provider_authorization().
- Start-UserDemo.ps1 in Live mode forces OPSPILOT_LEGACY_PROVIDER_ENABLED=0. Its Runtime Grant explicitly covers ASSISTANT_V1; the Investigator still constructs ChatOpenAI directly and does not bind to that Grant/Spend ledger.
- Therefore setting up the ordinary Assistant Grant or starting Live does not authorize or cost-bound an S2 Investigator request. Enabling the legacy switch would bypass the required durable Runtime Grant path. No configuration-only Live workaround is acceptable.
- The existing R2 Runner does not include E11-D. Its prepare --case-id E11-D probe exits 2 at argument validation; no Runtime directory was created.
- The task card does not authorize a controlled handoff submit. Even after the read-only model path is made cost-bounded and authorized, full Gold completion must stop at the frozen draft until the user explicitly submits it in the authenticated UI/API.

Minimum follow-up: a separately approved implementation must route the Investigator Provider dispatch through the existing durable Runtime Grant/send ledger, preserving the existing legacy deny-by-default boundary. Add E11 to the existing Runner only if needed for exact frozen input and trace export. A separate user authorization is required for the E11 Live Provider budget. A separate explicit user action is required for /api/tasks/{task_id}/handoff/submit; that action only creates the local pending-review receipt, not a Scope grant.

E11 budget: no RuntimeGrant-enforced USD ceiling exists on the current Investigator route. It has an 8-call Task limit and max_tokens=512 / 30-second timeout / zero retries, but it lacks RuntimeGrant reservations and settlement. Those are not a spend cap. Do not issue an E11 Grant against the current path or count illustrative token-based arithmetic as a hard limit.

## E03-D — protocol upgrade and Skill

### Frozen case and current project scope

Gold freezes a fresh Session with no TaskBinding and authorized_project = orders-async-demo. The exact frozen user question is in CASES.json. Required output includes sourced v1/v2 differences, configuration implications, compatibility risks, and a useful engineering checklist; the actual deployed version must remain unverified.

There is a real document relationship, but no demonstrated authorization alias:

- knowledge/async-callback/manifest.json contains callback-retry-contract v1.0.0 and callback-retry-contract-v2 v2.0.0, with source identifiers under local:orders-async-demo/...
- opspilot/domain/knowledge_assets.py maps service_id == orders-async-demo to those protocol assets for the Task-scoped Investigator Knowledge path.
- The ordinary Assistant's no-Task knowledge path instead reads the project grant in knowledge/assistant-access.json. Its only active SUPPORT project for tenant-a is project_id = orders-callback, with the callback retry v1/v2 document IDs allowed.
- assistant_knowledge.select_scope() accepts only an authorized project_id; the orders-async-demo service/source name is not an explicit project alias. The registry is loaded from the checkout-wide file, so adding a grant there would broaden access across runtimes rather than isolate the change to one evaluation Runtime.
- The existing scoped comparison regression returns project_id=orders-callback. It proves the documents are usable under that grant, but it is not an exact E03 execution. The current Runner also rejects E03-D at argument validation and creates no Runtime.

Blocker: do not silently replace the frozen orders-async-demo project value with orders-callback. Main Agent/project owner must decide whether Gold means a project ID or a service/source ID. If the Gold value is a project ID, its SUPPORT grant and exact document allow-list require an explicitly approved, properly isolated authorization solution. No policy file or Gold was changed here.

Minimum follow-up: resolve the project namespace and grant contract first. Then use a new Runtime and exact E03-D.user_turns[0], with no TaskBinding, no deployment-version assertion, and the optional Skill left to the model. A single isolated Live Runtime Grant needs separate explicit user approval; recommend no more than USD 0.05 for the first Run, with no automatic retry or added case.

### Provider configuration and proposed E03 budget

The local .env was inspected without printing its secret values. Required configuration is present: model deepseek-flash, host api.deepseek.com, price version DEEPSEEK_FLASH_PEAK_2026-11-14, input rate 300,000 and output rate 1,200,000 micro-USD per million tokens. The API key was present but never displayed. No evaluation Runtime/Grant was created and no Live preflight was run against a new DB.

The current DeepSeek official pricing page (https://api-docs.deepseek.com/quick_start/pricing/) lists peak rates of USD 0.30/M uncached input tokens and USD 1.20/M output tokens for deepseek-flash. The repository's ordinary Runtime Admin reserves against 12,000 input / 2,048 output tokens; at these configured peak rates the per-request reserve is USD 0.006058. This is an application reservation, not an invoice. USD 0.05 is a proposed per-case application pool ceiling only; actual request count depends on model/tool choices and pool headroom and is not a fixed one-request guarantee.

No truthful Live run command exists for E03 on this Base: the current Runner rejects the case ID, and the project's authorization does not match the Gold project. Once those decisions are resolved and the separate Live approval is granted, the existing isolation/start/preflight commands are:

    $RuntimeName = 'user-demo-r2-e03d-live01'
    .\scripts\user-demo\Initialize-UserDemo.ps1 -RuntimeName $RuntimeName
    # Configure a new per-case Grant only after separate explicit user authorization.
    python .\scripts\user-demo\runtime_admin.py preflight --runtime-name $RuntimeName
    .\scripts\user-demo\Start-UserDemo.ps1 -Profile S1 -Mode Live -RuntimeName $RuntimeName

This command block only prepares and starts an isolated runtime. It does not submit the frozen question. The existing Runner must first support E03 or an approved formal API runbook must be provided; do not use a different project or substitute question.

## Offline validation

- Corrected targeted run: 17 passed in 5.58s — 15 tests/test_ar03_02_scoped_protocol_comparison.py cases, plus the S2 401/404/stale-policy Gate test and the S2 evidence-dependent tool-schema test. All used pytest's unique isolated temp directory under this Worktree's .runtime; no User Demo Runtime was initialized.
- The first pytest attempt used the Windows default Temp root and failed during tmp_path setup: 1 test not requiring tmp_path passed, 16 setup errors reported PermissionError enumerating pytest-of-tu me manques. Re-running with an explicit fresh .runtime pytest temp directory passed all 17; this was not a product failure.
- run_r2_ar06_case.py prepare --case-id E03-D ... and ... E11-D ... both exited 2 with invalid choice; neither created a Runtime. Exact output is in RUNNER_SCOPE_PROBES.txt.
- Full model/tool loop, formal User Demo API/Worker/Vue preflight, live readiness, real Provider requests, actual Provider Usage/Spend, and controlled handoff were NOT_RUN.
- This round ran 0 real Provider requests, 0 external business writes, 0 handoff submits, created 0 Runtime Grants, and created 0 Worktrees.

## E04-H / E08-H / E09-D / E10-H remaining initial-state needs

- E04-H: isolated Knowledge fixture with conflicting v1/v2 retry documents (or explicit document absence), frozen user assertions, valid digest manifest and narrowly scoped authorization. Do not add those documents to global production Knowledge access.
- E08-H: existing r2-e08-processed-decoy profile supplies target PROCESSED and a distinct QUEUED decoy Event. Gold also requires historical QUEUED state; a fresh Session still lacks a traceable historical Message identity/source/time. Main Agent must resolve/freeze that history representation before claiming exact fidelity.
- E09-D: Gold does not freeze the long config/log attachment or exact multi-turn sequence needed to trigger and inspect Summary. Freeze those materials/turns before any real run; do not borrow AR-04 test-generated text as the Gold input.
- E10-H: fresh target Session and source Session need one valid method Memory plus a separate revoked/source-invalid conflicting Memory with verifiable source lineage. Do not fabricate these rows or use prior runs as an exact holdout initial state.

## Diff and stop line

This candidate adds only this readiness report and two offline command/test logs. No production code, schema, dependency, grant policy, project access registry, frozen Gold/Rubric, or historical evidence changed. Stop here for Main Agent review; do not start E03/E11 Live or another case from this branch.
