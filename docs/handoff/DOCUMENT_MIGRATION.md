# 将本包同步到现有 Windows 本地项目（重要）

**用户本地目录可能是** `D:\学习\agent新项目`，但模型当前**没有权限直接访问或修改你的 D: 盘**，因此本 ZIP 是交付给用户/Luna 的候选同步包，**不是对已存在 README/TASKS/AGENTS 的实际写入证明**。

## 合并流程（不要盲目覆盖）

1. Luna 先读取现有 `README.md`、`TASKS.md`、`AGENTS.md` 和项目 Git 状态；另存备份或新建分支 `docs/opspilot-v1-baseline`。
2. 将本包中的 `docs/baseline/v1.0-implementation-baseline.md`、`docs/reviews/*`、`docs/handoff/*` 原样加入项目；保留旧评审文档为历史，不再作为开发合同。
3. 将本包 `README.md/TASKS.md/AGENTS.md` **与项目现有文件合并**，保留对真实环境、现有代码、历史任务和安全限制仍有效的事实；删去“第二 Skill 属于 P0”“D1 早在某日完成”等过时说法。
4. 项目中必须只有一个 v1.0 有效设计入口；README/TASKS/AGENTS 都链接它，旧候选文档标记 archived。
5. 核对 D1 首次执行前 Git 状态、三份合并结果及链接；用户/主 Agent 审查后再提交。不要未经许可删除用户本地历史文件。
6. 设计冻结基线只作为文件已发布；实际开发/运行测试需要后续 Luna 证据。

## 最小可验证检查（Luna 执行）

- `git status`：没有误删旧资源；
- `README.md`、`TASKS.md`、`AGENTS.md` 均只指向 `docs/baseline/v1.0-implementation-baseline.md`；
- R5 已归档，并且 v0.3 经批准源 SHA256 `3c2cbddc5cac2c38360275750fa0de8e13da5ea3fcd2a2db355d97e82189b832`；
- 不能把 `docs/reviews/v0.3-approved-source.md` 当另一个有效开发需求；
- D1 日程按**实际**开始编码和实测来登记，而不是沿用原 10/17—23 假定进度。
