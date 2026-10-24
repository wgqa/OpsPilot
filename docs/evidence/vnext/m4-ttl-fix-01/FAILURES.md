# M4-TTL-FIX-01 失败与修复记录

所有失败原始输出都保留在 runs/ 下；本文件只记录分类和处理，不覆盖历史日志。

## 有效问题 RED

- M4-PREFLIGHT-01 的有效 RED 是 runs/preflight/red-02-pytest.log 与 TRACE-red-02.jsonl。真实本地 HTTP 和 MCP 查询在 301 秒后成功，但新 Gate 仍按旧 Evidence fetched_at 排除 delivery/receiver。
- 本轮复跑 runs/red-before-fix/preflight-red-03-pytest.log 得到相同 NEED_MORE / S3_EVIDENCE_EXPIRED。该运行发生于源码改动前。
- 冻结的 Run-scoped 测试在实现前以 TypeError 失败：evaluate_s3_gate 尚不接受 run_id。日志为 runs/red-before-fix/ttl-run-scope-red-before-fix.log。

## 无效 RED

第一次预检 red-01 在快照查询未限定 tenant/service 时命中另一条同名 fixture。失败材料 red-01-pytest.log 和 TRACE-red-01.jsonl 原样保留；该次只标记测试准备问题，不作为业务复现。

## 实施期间失败

- green-01：basetemp 父目录未建立，pytest 在测试启动前拒绝路径。
- green-02：系统 Python 环境缺少 MCP SDK，导入失败；后续使用项目虚拟环境。
- green-03：早期修复尚未让 Run B Gate 达到 DIAGNOSED；保留原失败。
- green-04：发现 SQLite 时间字段由 datetime 与字符串相减；统一解析并核验时间类型后修复。
- green-06 至 green-09：既有 S3 测试辅助函数建立了没有可信 Run/Attempt 关联的 Observation；新 Gate 按冻结合同正确拒绝。添加 s3_observation_support.py 让测试夹具持久化合法业务 Attempt/Run 关联。
- green-11：完整性测试调用了连接上下文管理器而非打开后的 SQLite connection；修正测试调用。
- green-14：HF-01 SLA 测试只冻结 S3 时钟，D2 观察/Attempt 使用了不同时间源；测试改为注入同一个确定性时钟。
- green-16：Windows autocrlf 将哈希校验的 Knowledge 文档换行转为 CRLF，导致资产摘要测试失败。随后恢复到 Git 中的规范字节；Knowledge/Skill 文件未纳入本轮提交。
- green-18：全量测试中一个 Worker 恢复用例需要模型配置，即使它替换了模型实现。用仅用于测试的 dummy key/name 和 127.0.0.1:9 base URL 重跑，未接触付费 Provider。

green-07/08/09/12/13/20/21 等每次尝试及对应原始日志都保留；最终收敛结果以 green-15、green-17、green-19、green-21 为准。318 passed + 1 failed、所有 RED 和设置失败均仍可在原日志中复核，没有删改旧 Gold 或历史报告。

## 最终失败状态

最终 TTL 定向 3/3、HF/S3 回归 77/77、S1/S2 安全回归 104/104、全量 pytest 319/319 通过。其余实现过程失败留档，等待主 Agent独立判断证据充分性。
