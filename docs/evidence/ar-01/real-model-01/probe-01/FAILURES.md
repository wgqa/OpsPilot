# Actual failure retained

One real request was sent and returned HTTP 200. The Provider returned
finish_reason=length with completion_tokens=512. Existing MeteredModel rejected
this unfinished completion as INCOMPLETE_OR_INVALID_COMPLETION; entry exit=2.

Usage was present/consistent and settled; the result is neither a network failure
nor unknown billing. The preserved generic runner status says
STOPPED_WITH_FAILURE_OR_UNKNOWN; ANALYSIS/REPORT narrow it to known truncated
output. Do not overwrite the original runner output to make it look successful.

No retry, output-limit increase, Prompt/tool/context edits or parameter removal
followed. No deterministic model or fallback answer replaces the real result.
No second billed endpoint was used to query balance, model list or invoice.

This one request does not identify the cause of historical nominal-512 overruns,
does not prove general vendor compliance, and does not release the five-pair P1.
Any later attempt must have a new authorization and its own immutable evidence.
