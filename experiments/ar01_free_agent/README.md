# AR-01 isolated standard Agent candidate

Local/free experiment only. Nothing in the product imports this directory.
`agent.py` builds installed `langchain.agents.create_agent()` with the existing six
MCP tools. Its middleware handles existing Attempt/Observation/Context audit and
bounded safe delivery. There is no new investigation planner or fault router.

`simulation.py` contains the deterministic test model. Its business branches are
test fixtures, not candidate policy. `harness.py` prepares real local HTTP facts,
clones independent A/B SQLite initial states, invokes unchanged S3 strategy A
methods and the candidate, and evaluates the frozen cases offline.

## Run from the repository root

Use a separate Python environment with the repository's `requirements.lock.txt`.
The actual validation environment reused the existing `.venv-stageb`; no package
was installed or upgraded for AR-01.

```powershell
python -m venv .venv-ar01
.venv-ar01/Scripts/python.exe -m pip install -r requirements.lock.txt
.venv-ar01/Scripts/python.exe -m experiments.ar01_free_agent --output experiments/ar01_free_agent/.artifacts/local-01
.venv-ar01/Scripts/python.exe -m pytest experiments/ar01_free_agent/tests -q --basetemp=C:/Temp/opspilot_ar01_review_01
```

The output directory must be new: existing evidence is never overwritten. Each
case creates its own seed/A/B DB, real HTTP preparation record, protocol/model
Trace and local result. SQLite files stay local and are ignored by Git. MCP child
processes and local HTTP servers close through context managers. The CLI constructs
only LocalModel; it has no live Provider flag or key loader.

## Scope of the comparison

- Exactly six tool definitions obtained from the existing MCP `tools/list`.
- The B native BaseTool serializer removes only display `title` metadata. The
  middleware passes the original A specs to `bind_tools`, and the runner compares
  actual bound model schemas byte-for-byte (canonical JSON).
- A uses unchanged S3Nodes strategy A investigate/execute/gate/next_step; it omits
  the production report/Diagnosis writer. A's Prompt is not rewritten for B.
- B uses the standard message/tool loop and a smaller system instruction. It
  requests parallel calls disabled; if a model violates that setting, native B
  batch execution is serialized. A instead reconsiders unexecuted proposals.
- Only fresh initial Task/Run cases are claimed equivalent (8/6). B's experiment
  `limit` argument also caps cumulative usage at 8/6 by default; this adapter does
  not claim CONT-UX lifecycle 24/18 allocation across multiple Runs is equivalent.
- Re-entering the same Run counts persisted failed/reserved/unknown attempts.
  Continuity accepts only an unchanged history returned by this same Candidate
  instance, revalidating current sources before dispatch. Restarted/cross-Run
  history needs a future trusted integration and is rejected explicitly.
- The experiment controls invocation time (60 s); it does not run the production
  Worker active-time heartbeat or Checkpoint recovery. Experimental Runs remain
  local RUNNING records, not product-completion or recovery claims.

Output has `EXPERIMENT_ONLY_NO_BUSINESS_RECEIPT` authority. Existing support checks
reject unsupported typed processing claims and structured fake Receipt fields.
Free text remains untrusted model output and is not proof of factual accuracy.
No business Gate/approval/write API is exposed by the candidate.

Review `docs/evidence/ar-01/` for Gold, parity differences, actual attempts,
limitations, and a separately proposed (not authorized) real-model trial.
