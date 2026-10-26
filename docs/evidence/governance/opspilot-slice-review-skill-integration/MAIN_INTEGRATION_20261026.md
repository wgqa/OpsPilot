# OpsPilot Review Skill：用户授权纳入 main

## 前置核验

- Repo：`wgqa/OpsPilot`；Base `410bc99577866ed5aa351380a713eb4dae52ebbd`。用户本轮明确要求将原候选纳入 main，取代此前仅推送候选分支的停止线；未授权新的业务开发。
- 原 Skill 候选：`81a4184a4c275e957acd4560f99f945c3a9c15d5`，首次集成提交 `6943c10f5effd334ad1ed890f78057f8ebe40a4a`。仅提取原 Skill 和 AGENTS 两行入口，不合并其他历史或产品补丁。
- 实际重读当前总纲、AGENTS 与候选完整 Skill。North Star Blob `1f737712c7a36ceb34433ac09c3fbba3c3305542`；AGENTS 原 Blob `30319000ed0054007e9b7b6b46bf98b1493c8179`，加入原入口后预期 Blob `32c4550`（完整值见 JSON）。
- Skill Git Blob `d405c8d413d633824b279202cc1503dab4cf0b03`；SHA256 `9f95b7bbf2af6c7b1f6bfe56b0171779d1cc28fe52fb539fbf1403a0fd39ea53`。与原候选完全相同，内容没有重写。
- 开始时 tracked/index 干净；717 个未跟踪实验文件保留，不清理、不暂存。用户主目录仍保留其原 HEAD `add47ec83f31fa76b9b6a5782e013311732bc496`，不做全工作树切换或覆盖。

## 实际安装、发现与执行分别核验

1. **安装**：原 Skill 文件和精确 AGENTS 两行入口已写入当前集成工作树，同时只同步这两份指导文件到 `D:/学习/agent新项目`。写前核对两处 AGENTS 均与原始 Blob 相同、目标 Skill 不存在；保留各自换行风格，未覆盖用户未提交修改。主目录的这两项指导变更不在主目录另行暂存或提交，其余文件保持原状。
2. **发现**：使用本机 `codex-cli 0.145.0` 的真实 app-server，依次发送 `initialize`、`initialized`、`skills/list`，指定两个真实 cwd、`forceReload=true`。两个结果均返回 `name=opspilot-slice-review`、`scope=repo`、`enabled=true`，Skill 错误数均为 0。实际响应的目标条目及原响应摘要见 `DISCOVERY_20261026_01.json`。未启动 Thread、Turn 或模型，Provider 调用为 0；没有打开可见命令行窗口，唯一辅助进程退出码 0，已回收。
3. **读取及执行**：本会话实际打开新安装的完整 Skill，执行 A 开工核验；按 C 做本次实施方提交核对和六项交付。总纲、AGENTS、Skill 的两处实际文件读取 hash 均有记录。不会把 `skills/list` 的成功冒充完整执行，也不把实施方提交核对冒充主 Agent 独立验收。
4. **边界**：本轮没有验证桌面 UI 选择器是否已刷新，没有调用另一个模型模拟评审，没有第三方签字或自动 PASS。普通答疑仍按 Skill 原约定不强制长格式，正式规划/范围变更/验收必须使用规定格式。

本轮是指导文件集成，无业务源码、Runtime、Gate、TaskControl、Schema、Gold、历史实验、业务测试或依赖变更。检查 front matter、原候选字节一致性、入口路径、两处实际发现、变更范围和 `git diff --check`；业务 pytest 不重跑，也不引用上一轮结果充当本次新鲜测试。

## 六项交付与停止线

**用户变化：** 当前项目和集成工作树均可直接发现 Skill，不再需要临时从 ZIP 取指令。

**Agent 决策：** 本轮只修正开发指导入口，没有新增业务 Agent 自主性或调用付费模型。

**观察驱动：** 两个真实 cwd 的注册结果均返回 repo/enabled；未声称由此证明以后每次执行必然遵守全部规则。

**新增约束：** AGENTS 明确要求开发会话实际读取；沿用原 Skill 对普通答疑的例外，没有新增业务硬限制。

**简化结果：** 使用原候选文件与入口，North Star 第 8 节继续为权威；未复制第二套协议或新增治理框架。

**证据与停止线：** 两处发现 2/2、实际读取及提交核对有记录，UI 选择器和主 Agent 独立审查未验证；仅提交推送本次指导文件后停止，原阶段 A 仍等待独立验收，不进入阶段 B。

**实施状态：`ACCEPTANCE_CANDIDATE`。** 按用户本轮授权纳入 main 不等于主 Agent 已签 PASS。最终实际提交 SHA 由包含本文件的 Git commit 及推送后的交付回复确定。
