# SelfOS 开发指南

Python 实现位于 src/selfos，根目录没有 Python 启动脚本。模块职责、依赖方向和路径规则见[后端结构](backend-architecture.md)。前端模板和浏览器资源拆分由 #30 单独跟踪。

## 安装与运行

在仓库目录安装开发版本：

    python -m pip install -e .
    python -m selfos serve --port 7070

从其他目录启动时，明确指定数据目录：

    python -m selfos serve --root /path/to/my-selfos --port 7070

安装后也可使用 selfos-serve、selfos-knowledge、selfos-harvest 和 selfos-auth。数据目录、模型配置、认证文件和包资源互相独立；本次入口整理没有迁移数据。

## 项目结构

- src/selfos/app：应用编排、任务、CLI 和聊天上下文。
- src/selfos/sources：对话解析、会话分组及工作区发现。
- src/selfos/knowledge：证据、筛选、分类、状态和历史规则。
- src/selfos/storage：原子写入、锁、检查点、备份、恢复和 Markdown。
- src/selfos/providers：模型协议、网络设置和模型审查。
- src/selfos/security：密码、会话和本地恢复。
- src/selfos/web：HTTP 路由和页面生成。
- src/selfos/resources：认证语言资源、空白模板和 digest skill。
- tests：程序回归和集成测试。
- evals：冻结评测、专用适配器和评测启动入口。
- docs：使用说明、设计和页面截图。

dashboard.html 是本地生成页面，已由 Git 忽略。vault 中的知识、检查点和备份保持原有格式。首次启动仅从本地状态生成缺失页面，不扫描对话、不调用模型。

## 知识整理

    python -m selfos knowledge --help
    python -m selfos knowledge --dry-run
    python -m selfos knowledge --workers 1
    python -m selfos knowledge --rebuild
    python -m selfos knowledge --restore-last
    python -m selfos knowledge --restore RUN_ID

显式 --root 决定模型配置位置，--vault 可以独立选择知识库。来源校验、分类、并发、增量整理、停止续跑及恢复逻辑见[整理指南](knowledge-import.md)。

## Harvest 与 staging

    python -m selfos harvest --help
    python -m selfos harvest --days 7
    python -m selfos harvest --dry-run
    python -m selfos harvest --full

Harvest 读取本地对话并生成 digest，也提供评分、页面生成和模型辅助 staging。知识库一键整理和 Harvest 是不同的工作流。手工 Agent 提案仍通过 staging 审核，参考[Agent 接入](agent-integration.md)。

## HTTP 与认证

服务仅绑定 localhost。页面及 API 由认证和本地请求检查保护；认证接口、密码存储及本地恢复见[认证说明](authentication.md)。恢复命令：

    python -m selfos auth reset

知识浏览、来源和设置由 /__knowledge__、/__knowledge_item__、/__knowledge_source__、/__knowledge_settings__ 提供。/__knowledge_stream__ 和 /__harvest_stream__ 使用 SSE；/__knowledge_stop__ 请求协作停止。模型及网络设置见[配置说明](model-settings.md)。

## 验证

    python -m pip install pytest
    python -m pytest -q

测试使用合成对话和临时知识库。冻结文件保持原样，其历史导入名仅存在于 evals/adapters。评测通过以下入口启动：

    python evals/run.py --help

真实模型评测需要显式 --live；参见[评测说明](../evals/README.md)。程序通过率与模型质量分开报告。重构和入口整理不需要全量扫描生产对话。
