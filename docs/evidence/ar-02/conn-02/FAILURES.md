# AR-02-CONN-02 失败及修复记录

## 1. 首次离线日志编码失真

运行 00-offline-first.log 时，PowerShell 重定向 Python 的非 ASCII stdout 后将冻结中文输入显示为替代字符。实际源码字面值经 ASCII 转义读取为 \u8bf7\u53ea\u56de\u590d\uff1aOK，MockTransport 捕获仍为程序内 JSON 内容；此日志不作为有效请求体证据，也没有任何外部请求。修正方式是程序直接写 UTF-8 文件，stdout 使用 ASCII 安全 JSON 转义。该原始失败日志及退出码保留。

## 2. 旧离线证明因发送器源码更新失效

预发送状态分类与单发 CAS 收口修改后，早先生成的 proof 的 sender 源码 SHA 已过期，程序按设计拒绝用该 proof；04-final-offline-preflight.log 的 PREFLIGHT_PROOF_ALREADY_EXISTS/退出码 2 不是 Provider 调用。旧 proof 移至 runs 留存，最终源代码重新通过离线 MockTransport 生成 PREFLIGHT.json。保留旧日志和 proof，不用它授权发送。

## 3. 定向测试迭代

- 早期接线与请求体：10 passed（runs/01-focused-tests.log）。
- 单发状态初步修正：10 passed（runs/03-focused-tests.log）。
- 当前最终候选代码：14 passed（runs/09-final-focused-tests.log）。
- 其中包含实际 ChatOpenAI/HTTPX MockTransport 线协议检查、精确 body、请求身份与美元预留 SQLite 持久化、重复账本拒绝、CAS 单一发送权、未知出站状态重放拒绝及峰值费用估算。
- 没有在测试或预检中调用付费 Provider；没有修改历史 CONN-01、P1 账本或生产代码。

所有失败与补充运行按原文件保留；尚无真实 Provider 结果。后续若唯一真实请求失败或结果未知，追加原始状态，不重试。
