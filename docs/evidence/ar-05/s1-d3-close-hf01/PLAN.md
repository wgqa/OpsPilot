# AR-05-S1-D3-CLOSE-HF01

## Scope

定向处理已批准 S1 Plan 的 D3 复核语义与授权收口。范围仅包括旧 Evidence TTL 到期后的新鲜同事实复核、事实变化或 Plan 失效后的旧权限撤销，以及临时来源读取失败后的同一审批恢复。未新增服务、通用 Guard 或状态机。

## Baseline

- Branch: `codex/ar05-s1-d3-close-hf01`
- Base: `3dd622edfb548ba75f9bd2378bbe9604b705678d`
- `origin/main`: `60eee87bfe3cca522011316cb4cd2c0064ad291b`
- `origin/codex/ar05-s1-d3-close-01`: `3dd622edfb548ba75f9bd2378bbe9604b705678d`
- North Star blob: `e36f2f75509738551ac6d4a2de5b4f9cf44a7991`
- AGENTS blob: `f174a6ab7f23f9e6d8b3ef98d455b99a75193143`
- Review Skill blob: `d405c8d413d633824b279202cc1503dab4cf0b03`
- M2-02 Deferred Gates blob: `2536030b5b942bf9e3765e0916607549fa919934`
- S1/D3 implementation brief blob: `7e442e6697094b450e4be3b87cb9e2897cdd6384`
- v1.0 baseline blob: `30e18d7ddbade7cdf7712d035d6fd8488bcb9676`

## Frozen RED

Before the implementation changes, the focused tests returned `4 failed, 1 passed in 5.68s`. The failures demonstrated that fresh, semantically identical facts were blocked after the original Evidence TTL expired, and that blocked/superseded Plans retained AVAILABLE permissions. The raw output is `logs/red-expiry-and-authorization.txt`.

## Intended proof

- Identical fresh facts plus unchanged approved Plan preserve the existing approval and allow one normal D3 repair.
- Changed facts require a replacement Plan and fresh approval, or are BLOCKED; old AVAILABLE permissions cannot execute.
- DISABLED principal / NO_ACTION cannot reach CAS.
- UNKNOWN creates no Repair Intent and leaves the existing approval recoverable; a later successful revalidation can continue the same approval Run.
- Cancellation, supersession, and deterministic BLOCKED revalidation revoke remaining permissions; replay creates no business side effect.
