# SelfOS — 开发文档

> 当前版本: harvest.py v0.5.0 · 更新: 2026-11-10

---

## 项目结构

Python 后端已拆分到可安装的 src/selfos 包。模块边界、依赖方向、资源路径及安装命令见[后端结构](backend-architecture.md)。下面的根目录命令保持兼容，其实现位于包内；前端模板和资源拆分由 #30 单独跟踪。

```
SelfOS/
├── src/selfos/         # app / sources / knowledge / storage / providers / security / web
├── harvest.py          # 兼容入口：调用包内 Harvest CLI
├── knowledge.py        # 兼容入口：调用包内知识整理 CLI
├── serve.py            # 兼容入口：调用包内 HTTP server
├── dashboard.html      # 生成产物（不在 git 中）
├── .env                # API keys（git-ignored）
├── vault/              # 个人知识库（Markdown + Git）
│   ├── PROFILE.md      # 身份、背景、技能
│   ├── NOW.md          # 当前状态、活跃项目
│   ├── GOALS.md        # 目标
│   ├── DECISIONS.md    # 决策日志（append-only）
│   ├── SCORES.md       # 每日 7 维度评分（append-only）
│   ├── 01_Career/      # 职业
│   ├── 02_Work/        # 工作项目
│   ├── 03_Research/    # 研究
│   ├── 04_Health_Fitness/
│   ├── 05_Life/
│   ├── 06_Reviews/
│   ├── 90_Inbox/       # session digest 原始输出（git-ignored）
│   └── 91_Staging/     # AI 生成的待审核更新
├── tests/
│   └── *.py            # 行为回归、模块边界、路径与 HTTP 集成测试
└── docs/
    ├── dev.md          # 本文件
    └── agent-integration.md
```

---

## 核心流程

### 旧版模块追加整理（兼容实现）

以下两节描述旧版模块追加流程。网页和 CLI 的当前默认会话压缩、并发整理与项目归并流程见文末及 docs/knowledge-import.md 的 Configurable knowledge retention。

- 网页的“一键整理知识库”调用 `GET /__knowledge_stream__`，运行 `knowledge.py` 并通过 SSE 显示进度。
- 扫描 Claude Code/Codex 的用户和 AI 文字消息，以及 Codex 迁移目录中的 Claude 历史；跳过工具输出、思考内容和系统上下文。
- 按 12,000 个对话字符分批，不截掉长消息尾部；已完成片段和已有知识条目通过哈希去重。
- 已有知识库上下文按每个模块最多约 4,000 字符提供首尾摘录；这不改变正式文件，也不截断新对话的处理。
- AI 输出限定模块的知识条目；校验来源 ID 后追加，区分 `[user-statement]`、`[assistant-suggestion]`、`[ai-inference]`。
- 每批先备份再写入，失败回滚该批；成功后记录状态，已完成批次保留，重试继续剩余部分。
- `vault/.knowledge_sources.json` 保存来源 ID 对应的原始文件路径、角色、时间和项目。
- `python knowledge.py --restore RUN_ID` 按反向批次恢复，并检查后续改动。备份目录与索引均被 Git 忽略。
- 此流程重新生成 dashboard，评分仍由原有 Harvest 更新。待审核 staging 流程继续独立使用。

新增测试：`python -m pytest tests/test_knowledge.py -q`；全套：`python -m pytest -q`。

### 模型结果校验与自动修复

- 正文必须是非空字符串，去除首尾空白后最多 4,000 字符；过长正文反馈给模型重写，不静默截断。
- 每批模型输入使用 s1、s2 等短来源编号；返回后映射回原始 ID。单个来源字符串、首尾空白和重复来源可以明确规范化；未知来源绝不猜测。
- 类别接受明确别名并统一到 user_fact、assistant_suggestion、inference；缺失类别保守标记为 inference。AI 回复不能因别名转换成为用户陈述。
- 同一条知识的多个无效字段一次报告；重新生成时将具体错误作为 repair_feedback 提供给模型。
- 默认最多尝试 3 次。验证/格式错误、临时超时和可重试 API 错误可重试；鉴权等永久错误不会重复请求。持续失败的批次不会写入，也不会标记为已处理。
- 失败响应与字段错误脱敏保存到 vault/.knowledge_errors/，不提交 Git；进度日志显示诊断位置，不显示原始响应。
- 专项测试：python -m pytest tests/test_knowledge_validation.py -q。

```
harvest.py 运行
  ├── 1. 提取 Claude Code / Codex JSONL 会话（用户消息）
  ├── 2. 过滤噪声 + redact 敏感数据
  ├── 3. 写 session digest → vault/90_Inbox/YYYY-MM-DD-sessions-digest.md
  ├── 4. score_vault(): 从 vault 各模块推断 7 维度评分
  ├── 5. generate_dashboard(): 生成 dashboard.html
  └── 6. auto_generate_staging(): 调用 Claude Haiku，生成 vault/91_Staging/ 文件

serve.py 运行
  ├── 首次启动: 如 dashboard.html 不存在，运行 harvest.py
  ├── GET  /                    → dashboard.html
  ├── GET  /__harvest_stream__  → SSE，实时流 harvest.py stdout
  ├── POST /__harvest__         → 同步运行 harvest.py（备用）
  ├── GET  /__staging__         → 返回 91_Staging/ 文件列表
  ├── POST /__staging__/apply   → 写入 vault + 删除 staging 文件
  └── POST /chat                → 代理到 Claude API（含 vault context）
```

---

## 关键模块

### harvest.py

| 函数 | 作用 |
|------|------|
| `extract_claude_messages()` | 读 `~/.claude/projects/**/*.jsonl`，提取用户消息 |
| `extract_codex_messages()` | 读 `~/.codex/sessions/**/*.jsonl`，提取用户消息 |
| `_is_meaningful(text)` | 过滤噪声：单字确认、系统通知、纯路径、loop 监控提示 |
| `redact(text)` | 抹除 API key、密码、邮箱、手机号等敏感信息 |
| `build_session_digest()` | 按 cwd/project 分组，每组最多 40 条，渲染 Markdown digest |
| `score_vault()` | 读 vault 子目录，调用 `_infer_score()` 推断 1-10 分 |
| `_infer_score(text, dim)` | 基于关键词正/负信号打分，需要 10+ 实质内容行才打分 |
| `generate_dashboard()` | 渲染含 SVG 环形图、折线趋势、双语切换的 HTML dashboard |
| `auto_generate_staging()` | 调用 Claude Haiku API，输出 JSON → 写 91_Staging/ 文件 |
| `_get_api_config(root)` | 读 `.env` 或环境变量，返回 (api_key, base_url) |

### serve.py

| 端点 | 说明 |
|------|------|
| `GET /` | 返回 dashboard.html |
| `GET /__harvest_stream__?full=0\|1` | SSE 流，实时推送 harvest.py stdout 每一行 |
| `POST /__harvest__` | 同步运行 harvest.py，支持 `{full: true}` |
| `GET /__staging__` | 返回 `{files: [{name, target, content}]}` |
| `POST /__staging__/apply` | `{files: ["fname.md"]}` → 写入 vault，删除 staging 文件 |
| `POST /chat` | `{messages: [...]}` → 调用 Claude API，注入 vault context |

`ThreadingMixIn` 保证 SSE 长连接不阻塞其他请求。

---

## 评分维度

```python
SCORE_DIMENSIONS = [
    ("career",   "职业发展", "01_Career"),
    ("work",     "工作/项目", "02_Work"),
    ("health",   "健康体能",  "04_Health_Fitness"),
    ("learning", "学习成长",  "05_Life"),
    ("research", "研究",      "03_Research"),
    ("life",     "生活",      "__life__"),   # 特殊 sentinel：读 NOW+PROFILE+GOALS+05_Life
    ("family",   "家庭",      None),         # 仅从关键词过滤行推断，不读整个目录
]
```

- `score_vault()` 处理 `__life__` sentinel，聚合多个根文件
- 稀疏子目录（< 10 实质内容行）会补充读 `NOW.md`
- `career` 无 01_Career/profile.md 时回退到根 `PROFILE.md`

---

## 评分存储格式 (SCORES.md)

```markdown
- 2026-11-10 | career: 7 | work: 5 | health: 7 | learning: 6 | research: 7 | life: 6 | family: null
```

- **同一天重复运行会替换该行**，不追加
- `null` = 没有足够数据推断分数
- `skip` = 该维度被明确排除

---

## AI Staging 流程

```
harvest.py 末尾
  → auto_generate_staging(vault, digest_path)
  → 读 digest（截断到 8000 chars）+ 4 个关键 vault 文件
  → 调用 claude-haiku-4-5，prompt 要求输出 JSON 数组
  → 每条: { target, type, content }
  → 写入 vault/91_Staging/YYYY-MM-DD-auto-{slug}.md
     frontmatter: type / updated / source: auto-harvest / target

dashboard 加载时
  → JS checkStaging() 调用 GET /__staging__
  → 有文件 → 右上角橙色 "● N 待审核" badge
  → 点击 → 弹窗列出文件（默认全选）
  → "应用选中" → POST /__staging__/apply
  → serve.py 解析 frontmatter → 写入 target → 删除 staging 文件
```

---

## 安全约束

- `.env` 在 `.gitignore` 中，不进 Git
- `vault/90_Inbox/` 在 `.gitignore` 中，digest 内容不进 Git
- `redact()` 在消息进入任何处理前运行
- AI staging 文件标记 `[ai-inference]`，不自动 apply，需用户确认
- `/chat` 端点只注入 vault root files + 最新 digest 前 4000 chars，不发送 90_Inbox 原始内容

---

## 测试

```bash
python -m pytest tests/test_harvest.py -v    # 123 个测试
python -m pytest tests/test_harvest.py -q    # 快速
```

测试覆盖：
- 消息提取与过滤（`_is_meaningful`, `redact`, `_text_from_content`）
- 评分逻辑（`_infer_score`, `score_vault`, `_append_scores` 同天替换）
- Digest 生成与 signal quality
- Vault 结构初始化（`ensure_vault_structure`）
- State 持久化（`load_state` / `save_state`）
- AI staging（mock API，验证写文件 + frontmatter 解析）
- Dashboard HTML 内容验证（staging UI、进度条、双语元素）

---

## 本地开发

```bash
# 启动 server（仅首次无 dashboard 时跑 harvest）
python serve.py

# 强制重新采集全部历史
python harvest.py --full

# 只采集最近 7 天
python harvest.py --days 7

# 预览不写文件
python harvest.py --dry-run
```

访问 `http://localhost:7070`

---

## 已知限制 / 待改进

| 项目 | 状态 | 说明 |
|------|------|------|
| 只读用户消息，不读 AI 回复 | 设计决定 | AI 回复量大、噪声多，暂不提取 |
| 评分是静态 vault 推断，不是实时分析 | 现状 | 每次 harvest 后更新 |
| `/digest` 仍需手动在 Claude Code 运行 | 半自动 | auto_generate_staging 是轻量替代，但不如 /digest 完整 |
| family 维度几乎总是 null | 现状 | 关键词匹配太严格，或 vault 无内容 |
| 单文件 harvest.py（~2100 行） | 技术债 | 可拆分为 extract / score / dashboard / staging 模块 |
| dashboard.html 不在 Git | 设计决定 | 含个人分数，属于个人数据 |
| serve.py 无认证 | 现状 | 仅本地，不暴露公网 |

---

## 下一步方向（未排期）

知识库一键整理现在使用 selfos.app.pipeline：在内存中压缩代码围栏和大块 JSON、过滤临时请求及无关工具输出，按完整项目路径和原始会话分组，默认 3 路 API 并发、串行保存。原始对话文件保持不变。CLI 支持 `python knowledge.py --dry-run`（不调用 API、不写知识库）和 `--workers 1`。

质量修复进一步区分 user_statement、quoted_dialogue、runtime_evidence、机器摘要和代理状态；引用或工具结果不能升级为用户事实。工具失败和日志错误保留为证据。项目卡当前决策最多 8 条，decision_history、lesson_history 和原始来源留在索引；项目级语义归并合并同义表达、过滤临时建议，未变化的语义归并结果也缓存。允许无项目更新的空结果或独立经验。

聊天直接读取索引中的目标、状态、阻塞和下一步；来源哈希与长历史不占当前状态预算。Git 根目录和 worktree common-dir 用于识别仓库，确认过的历史路径可通过 project_aliases 映射，原始路径留在来源元数据。身份映射或输入内容改变后，相应片段可能重新生成一次。修复旧缓存应先在隔离目录重建，再用 install_rebuilt 带事务备份替换；手工经验笔记保留，旧生成结果可从备份恢复。

项目卡片写入 `02_Work/projects/`，经验写入 `05_Life/lessons.md`；来源、内容指纹及合并状态保存在 `.knowledge_pipeline.json`。旧事实文件与旧检查点保留，新项目摘要首次运行需要独立建立缓存。备份位于 `.knowledge_backups/<run-id>/`，使用 `python knowledge.py --restore <run-id>` 恢复；恢复会检查导入后是否有其他修改。崩溃遗留的死进程锁自动回收，未完成事务在下次启动时恢复。

页面停止按钮调用 `POST /__knowledge_stop__`。停止后不再调度新请求；已发请求允许完成并保存，单次 API 等待上限为 90 秒。扫描与分组也检查停止信号。失败会话不缓存，其他会话继续；点击整理可跳过已经缓存的输入。项目状态的未知摘要不能清除已有阻塞，助手完成报告标记为 reported_complete。

当前整理流程的配置与质量标准见 docs/knowledge-import.md 的 Configurable knowledge retention。项目观察独立保存并进入历史视图；个人事实、偏好、项目状态、可复用方法、历史分别保留。当前决策预算由 detail 配置决定，经验没有最终条数目标。

项目归并的候选逐条复核每批最多 20 个；非组长方法可留空正文并引用完整组长，来源由程序合并。格式失败只修复当前批，明确传入数量、ID 白名单与具体错误。修复成功和归并失败均在 .knowledge_errors/ 留存脱敏诊断。knowledge_method_merge.py 对跨批次方法按最多 80 项、48,000 字符比较，完整覆盖候选对，只选择已有正文；未知组长、跨领域分组、缺项或重复拒绝。较大方法池的比较次数会增加，目前归并范围为单个项目。SYNTHESIS_VERSION 12 只更新最终归并缓存，不重放有效会话提取。

GET /__knowledge_run__ 提供同源任务状态，不公开进程或停止标记路径。独立 stdout 读取在断线后仍记录最后保存；等待子进程与读取线程结束后才释放任务锁。页面断线后轮询，刷新后接回，保存期间不能重复启动。


- **周期性自动 harvest**：Windows 计划任务 / cron，每天定时采集
- **vault diff 视图**：staging 弹窗里展示 before/after diff
- **多数据源接入**：日历、GitHub 活动、健康数据（Apple Health export）
- **harvest.py 拆模块**：extract.py / score.py / dashboard.py / staging.py
- **Web UI 编辑 vault**：在 dashboard 里直接编辑 NOW.md / GOALS.md
