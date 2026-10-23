# M4-03-HF-01 RED 与失败记录

所有运行日志都按原样保留在 `runs/`，包括工具启动问题、RED 和首次全量失败。

| 日志 | 结果 | 说明 |
|---|---|---|
| `red-01-pytest.log` | 5 setup errors | pytest 默认 `%TEMP%` 目录无法枚举，Windows 返回 `PermissionError`；测试函数没有执行。 |
| `red-02-pytest.log` | 5 setup errors | 同一默认临时目录问题再次出现。后续所有 pytest 都显式指定本轮 `--basetemp`。 |
| `red-03-pytest.log` | 10 failed, 4 passed | 基线代码复现 Scope/Grant 版本不参与 Evidence 当前性、撤权后诊断仍 CURRENT、Web 资源端点仍 200、缺失 Principal/Policy/Grant 未拒绝，以及未实现历史审计身份接口。另有一项 credential mismatch 测试值违反凭证外键。 |
| `red-04-pytest.log` | 11 failed, 4 passed | 冻结用例的补充 RED：复现 scope/policy 变更后旧 Evidence 仍 DIAGNOSED，SLA 跨界后旧 WAIT 仍 CURRENT，以及资源授权和历史审计问题。credential mismatch 的测试夹具外键错误一并留档。 |
| `green-focused-01-pytest.log` | 4 failed, 11 passed | 实施早期测试迭代：授权版本更新尚未在独立连接提交、凭证夹具选值与当前环境相同，以及新交接测试误调用 S3 模块成员。已修正测试夹具/事务边界；不是最终运行结果。 |
| `green-focused-02-pytest.log` | 15 passed | 修复后的早期定向通过记录；之后增加了 Web、三种 MCP 工具、历史权限和 SLA 新鲜 Run 用例。 |
| `full-01-pytest.log` | 291 passed, 1 failed | 新增 SLA 测试使用 `queue_age_seconds=299`，fixture 准备耗时可能使被冻结初始时间已越过边界。修复为确定性设置 `accepted_at=now−299s`，并同步 transport response digest。 |
| `sla-deterministic-01-pytest.log` | 1 passed | 确定性时钟复现补跑。 |
| `full-02-pytest.log` | 292 passed | 全量最终复跑。 |

最终 S3 与 S1/S2 定向结果也分别保留在 `s3-final-01-pytest.log`（50 passed）和 `s1-s2-security-01-pytest.log`（104 passed）。没有删除或覆盖失败记录，也没有把文档或夹具失败宣称成产品 PASS。
