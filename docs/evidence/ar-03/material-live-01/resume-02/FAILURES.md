# Failures and stops

## Preserved RED

- The first project-venv run of the new focused tests produced 7 expected RED failures: the outcome classifier did not yet exist, the new experiment ID was not supported by the budget schema, and the exact RESUME-02 one-shot gate did not exist. Raw output is preserved in the private evidence directory.
- During expanded regression, a history hash comparison initially failed because the expected SHA was uppercase while `hashlib.hexdigest()` is lowercase. The expected literal was normalized to lowercase; no historical claim was modified.
- A later new negative test found that an answer with a mismatched source ID could be labelled as “completion without persisted answer”. The classification precedence was corrected so any non-empty unverified delivery remains `UNVERIFIED_NONMODEL_ANSWER`.

## Environment-only failure

An initial test command used the global Python interpreter, which did not have the project `langchain` dependency. That run is preserved and is not counted as a product test. All subsequent commands used `D:\学习\agent新项目\.venv\Scripts\python.exe`.

## Preflight iteration

The first formal preflight ran before the implementation was committed and stopped with `WORKTREE_OR_INDEX_NOT_CLEAN`. The configured shared environment and model settings were then verified using presence-only checks. No one-shot claim was created and no paid request or live MCP call was sent during that attempt. A clean-worktree preflight is still required before claim creation.

No Provider retry, claim reuse, budget change, Gold change, or historical ledger change occurred.
