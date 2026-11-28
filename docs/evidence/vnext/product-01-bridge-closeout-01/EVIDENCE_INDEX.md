# EVIDENCE_INDEX

代码/业务 Trace 在本目录。完整原始测试输出保存在本地私有目录 `.private-evidence/product-01-bridge-closeout-01/`，不提交到公开候选。

| 私有文件 | 用途 | SHA-256 |
|---|---|---|
| `red2-20261107-034026-bf44c4f0.log` | outcome count RED | `6CC7922A1A9C61A976E1ABB5B853A8BC122E32A6B68CC23972C5A287EE901F76` |
| `green2-20261107-034423-e73dace5.log` | outcome count GREEN | `35D7F5ED2A7B8C28F72856524ACABFAF8B7EBBFCCFCFB86ACCD8027179654184` |
| `cli-reset-green-994ada599929466eb82958fc731313eb.log` | CLI reset regression GREEN | `9E9E89E80722E2CBF2E652416689BED02A62819A5678E3B707836242CD4DE7F4` |
| `focused-suite-final-327950edd4ae4aaeb375243f9579835d.log` | 77 项聚焦 Python | `C9B6295525FF8A01AE56AE76DBC438F48187F58CAE9524318801D72D96C206FB` |
| `full-pytest-5a5ef1848cff4378b5ca48d079f6173a.log` | 一次全量 pytest，最终 741/757 | `8D0BDC5A1A9C61A976E1ABB5B853A8BC122E32A6B68CC23972C5A287EE901F76` |
| `frontend-suite-20261107-034701-6179df65.log` | 前端测试 29 pass / 1 skip | `E40FA32E9016276F326BCB3808676541BA0A37D7FC6949B079D6133D8E15D64D` |
| `typecheck-20261107-034812-06dfd261.log` | TypeScript | `459CFB6F20A7A6A25F32A4D97EE30125EAB7A03E11C6431A76AC3E0F116A124B` |
| `build-20261107-034812-39ec9340.log` | 前端 build | `FD48F5242B7E70120B4082BF620F1A553F27EA4AC498F710D50A042001D4C426` |
| `eslint-20261107-034812-0edd17b5.log` | 变更文件 ESLint | `03F21F7520DDEA2EA2C0578207FC8EBC5E7E430235798E09CABFBE5448F9EEBE` |

`focused-final-15dd61df12fd404d88351c19a57d177e.log`、`wp3-s1s2-20261107-035102-5ff925e0.log`、`green-20261107-034247-1156792a.log` 等较早 RED/GREEN 与 API Trace 也保留在同一私有目录。npm 安装尝试、环境检查和首次失败日志同样保留，未覆盖。

本次 full pytest 在隔离 detached worktree 执行；测试追加改动留在该 worktree 的两份历史 C1 Trace 中，未合并回当前候选。该测试 worktree 被保留，没有清理。

## 实际命令

聚焦 Python：

```powershell
python -m pytest tests/test_product_01_bridge_closeout_01.py tests/test_product_01_final_bridge_01.py tests/test_ar05_s1_session_bridge_01.py tests/test_ar05_s2_assistant_handoff_01.py tests/test_d3_actions.py tests/test_ar02_runtime.py tests/test_ar02_assistant.py tests/test_ar02_smoke_provider_factory.py tests/test_ar02_ar03_integration_01.py -vv -s --basetemp <unique-private-basetemp>
```

完整 pytest（在独立 detached test worktree）：

```powershell
python -m pytest -vv -s -o faulthandler_timeout=120 --basetemp <unique-private-basetemp>
```

前端命令：

```powershell
npm test
npm run typecheck
npm run build
npx eslint src/App.vue src/assistant-entry.ts test/assistant-entry.test.ts
```

完整 pytest 的完整实际日志及 SHA-256 在上表。占位目录指向私有临时目录，公开仓库不存放运行态 DB、完整全量日志或密钥。\n