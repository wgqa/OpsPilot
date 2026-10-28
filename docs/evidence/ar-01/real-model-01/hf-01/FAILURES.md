# Failure and limitation history

No old AR-01/P0 Gold, log, Trace or acceptance has been overwritten. All new
experiments below are free local work; no remote paid failure was reproduced.

| Record | Actual result / treatment |
|---|---|
| runs/01-red.log | New policy constant absent at collection, exit 2. Preimplementation capability RED, not a new security bug. |
| research/baseline-refusal.json | Executed frozen Base's budget code with the actual saved six-tool body. COST_CAP, 0 reservations. Confirms the old correct refusal; code loaded read-only without changing checkout. |
| Initial tokenizer-console inspection | GBK console could not print a Unicode token, UnicodeEncodeError. Retried inspection with PYTHONUTF8=1. Original console output is in the tool transcript, not falsely presented as an archived test log. No source/archive changes. |
| runs/02-green-attempt.log | 24 passed, 38.87s. Console session handle was not retained, so process exit is not separately captured; raw pytest summary retained. Not used as final release gate. |
| runs/03-extended-green.log | 28 passed, 36.88s, captured exit 0. Added request-ID correlation/probe-scope and protocol-negative tests. |
| runs/04-all-experiment-tests.log | 76 passed, 124.97s, exit 0: then-current 28 new + original 48. |
| runs/05-safety-regression.log | 72 passed, 100.39s, exit 0. Fresh S1/S2/S3/approval/HF/TTL subset, not the old P0 result. |
| runs/06-final-experiment-tests.log | 77 passed, 112.49s, exit 0: original 48 + final 29. Added explicit already-billed contract-overrun simulation. |
| runs/07-offline-request-preflight.log | exit 0; ready=true under request contract; paid_authorized=false, requests=0. No SDK/client/network. |

During evidence assembly, writing the derived patch through Windows text I/O
introduced CRLF, flagged by diff --check because *.patch is -text. Re-generated
the patch from exact Git stdout bytes; no test log/Trace/history was edited.
Patch context blank-line prefixes and raw pytest whitespace remain intentionally
excluded from the source/document whitespace gate and are not reported as a
security or runtime test failure.

Negative fixtures deliberately return HTTP 400, drop responses, delay/cancel,
omit/invalidate Usage/finish/Completion ID, report input/output excess or unexpected
reasoning, and modify prepared wire before send. Refusals and preserved reservations
are expected local results, not actual DeepSeek protocol findings.

**Important overrun experiment:** a local fake ignores the requested output limit
and reports the full input/output maxima. The ledger retains USD 0.786432, exceeding
the USD 0.50 configured cap, and blocks all subsequent requests. Passing this test
means detection and truthful recording, **not prevention of that already-incurred
charge**. A client cannot guarantee the bill of a noncompliant vendor by examining
Usage after a nonstreaming response. New readiness relies explicitly on the
documented output/context/mode contract; it is not an unconditional spending cap.
If independent review requires protection even against that vendor violation,
the result must remain HOLD rather than relabel this simulation as cost safety.

The old normalized Ledger's 87 output overruns remain unresolved at the original
raw-wire level. They do not prove the newly corrected HTTP request is respected,
nor prove it is ignored. Header fallback is an opt-in compatibility proposal;
parallel field acceptance and actual backend/fingerprint/Usage still require an
authorized probe. No field is removed and retried after rejection.

Full repository pytest / browser / real paid Provider / P1 / P2 / AR-02: NOT_RUN.
Stage B HOLD, browser STOP and historical deferred safety gates remain unchanged.
