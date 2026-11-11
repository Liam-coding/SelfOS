# SelfOS

**Manage your life, the simplest way.**

SelfOS is an open framework for building a personal knowledge and memory system that AI agents can read, update, and reason over. Think of it as the OS layer between you and your AI assistant — your second brain that persists across every conversation.

> "An AI that remembers nothing about you is a stranger. SelfOS turns it into a collaborator."

### One-click personal knowledge / 一键整理个人知识库

![SelfOS knowledge overview and browser](docs/images/selfos-knowledge-dashboard.png)

*Core dashboard with example data / 核心页面，使用示例数据。*

Start with `python serve.py`, then open `http://localhost:7070` and click **Build Knowledge / 一键整理知识库**. SelfOS reads local Claude Code and Codex JSONL conversations, including supported migrated Claude archives, and turns useful discussion into five separate views: **personal facts, preferences, projects, reusable experience, and history**.

The pipeline filters transient requests and runtime chatter, compacts code and bulk data in memory, then organizes session parts with three workers by default. It retains project goals, reasoning, decisions, blockers and next steps. Reusable methods are reviewed and grouped by meaning; there is **no target number of retained records**. Original conversations are never edited.

Choose focus domains and concise, balanced or detailed wording in **Knowledge settings**. Imports write automatically with source references, audit records and backups. Successful session parts are saved as checkpoints; canonical knowledge is replaced only after the complete operation succeeds. A settings change automatically rebuilds against the new policy.

You can click **Stop** at any time. New work stops being scheduled; active requests may finish and save, so stopping is not instantaneous. Wait for the stopped status before shutting down the server. A page refresh or stream disconnect also requests cooperative stopping; the page follows the existing job's saving/stopped status instead of launching another import. Click Build Knowledge again to continue remaining work; unchanged successful checkpoints are reused.

Configure `ANTHROPIC_API_KEY` and optionally `ANTHROPIC_BASE_URL` in `.env`. Organizing and chat send redacted text and relevant context to that configured API; local storage does not mean offline inference. Source file paths stay in `vault/.knowledge_pipeline.json`. Source IDs and evidence checks make records traceable, but AI summaries and model reviews do not independently prove factual accuracy.

启动服务后点击 **一键整理知识库**。系统先过滤临时请求、压缩模型输入，再按会话并发提取，将个人事实、偏好、项目、可复用经验和历史分别保留。关注领域和详细程度可配置，保留数量由内容决定；原始对话不修改。整理过程会调用你配置的 AI API。

整理可随时停止：已成功片段保留为检查点，正在进行的请求可能仍需完成保存；页面显示停止后再关闭服务。刷新或断线也会请求协作停止，页面接回的是当前保存或停止状态；再次点击整理才续跑剩余内容，复用有效检查点。整次操作成功后才安装到正式知识库，并保留来源、备份和撤销能力。

Use the dashboard **Undo last import**, or `python knowledge.py --restore-last`, to restore the last completed operation. `python knowledge.py --restore RUN_ID` restores an older backup. Restoration refuses to overwrite later file edits; restore newer operations first. Manual notes outside managed sections are preserved, including notes on generated project cards.

每次正式写入都有备份。页面可撤销上次整理，CLI 可用 `--restore-last` 或 `--restore RUN_ID` 恢复；后续手工修改会阻止覆盖恢复。自动生成区域以外的手工备注会保留。当前支持本地 JSONL 会话，其他聊天软件的导出格式尚未接入。

See [the import guide](docs/knowledge-import.md) for CLI examples, retention rules, retries and recovery, and [the evaluation guide](evals/README.md) for reproducible quality checks.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**[中文文档 →](#chinese)**

---

## What is this?

Most AI assistants forget you the moment the session ends. SelfOS fixes that by giving your AI a structured, version-controlled knowledge base about your life — your goals, career, health, research, decisions, and context.

Think of it as a **second brain** built for the AI era: a personal knowledge management (PKM) system that your AI can actually read, update, and reason over — not just a note-taking app that sits idle.

- **Git-native**: everything is Markdown + Git. Your life has version history.
- **AI-agnostic**: works with Claude Code, Codex, or any agent that can read files.
- **Local storage**: Markdown stays on your machine. Optional organizing and chat use your configured AI API.
- **Structured but flexible**: opinionated enough to be useful out of the box, open enough to adapt to your life.

> Built for anyone who uses AI daily and wants their assistant to actually know them. Git is optional — your AI agent can manage the vault for you.

---

## How it works

```
You ──→ AI Agent ──→ reads vault/ ──→ understands your context
                  ──→ proposes changes to 91_Staging/
                  ──→ you approve
                  ──→ applies to canonical files
                  ──→ commits to Git
```

The vault is a directory of Markdown files organized by life domain. The AI reads these files at the start of each session and maintains them over time. Manual agent edits use staging approval; the one-click knowledge import writes directly with provenance and recoverable backups.

---

## Vault structure

```
vault/
├── PROFILE.md          # Who you are — identity, background, skills
├── NOW.md              # Current state — priorities, active projects, blockers
├── GOALS.md            # Short and long-term goals
├── DECISIONS.md        # Append-only decision log
│
├── 01_Career/          # Career history, opportunities, criteria
├── 02_Work/            # Active work projects and logs
├── 03_Research/        # Research projects, experiments, papers
├── 04_Health_Fitness/  # Training plans, logs, health data
├── 05_Life/            # Learning, relationships, housing, side projects
├── 06_Reviews/         # Weekly and monthly reviews
├── 07_World_Observer/  # External signals, market intelligence, reading
│
├── 90_Inbox/           # Raw input (git-ignored, treated as sensitive)
├── 91_Staging/         # Proposed changes awaiting approval
├── 98_Archive/         # Historical records
└── 99_Templates/       # Reusable templates
```

---

## Memory system

SelfOS includes a persistent memory layer for AI agents — a set of structured Markdown files the agent reads at session start to recall who you are, your preferences, and your ongoing work.

```
memory/
├── MEMORY.md           # Index of all memory files
├── user-profile.md     # Background, role, goals, preferences
├── feedback.md         # How you like to work with AI
└── project-context.md  # Current project state
```

Memory files use a simple frontmatter schema:

```yaml
---
name: user-profile
description: Background, role, and preferences — read before any advice
metadata:
  type: user  # user | feedback | project | reference
---
```

---

## Getting started

```bash
# 1. Clone
git clone https://github.com/Liam-coding/SelfOS.git && cd SelfOS

# 2. Extract your AI history (installs /digest skill automatically)
python harvest.py

# 3. Open Claude Code and type /digest
claude
```

That's it.

---

## Life Dashboard

Every time you run `python harvest.py`, SelfOS automatically generates a `vault/dashboard.html` — a visual snapshot of your life across 7 dimensions:

| Dimension | What it tracks |
|-----------|---------------|
| Career | Job opportunities, momentum, clarity |
| Work | Active projects, delivery, blockers |
| Health | Training, energy, physical state |
| Learning | Courses, books, skill growth |
| Research | Experiments, progress, publications |
| Life | Balance, wellbeing, side projects |
| Family | Relationships, connection, presence |

Each dimension gets a score (1–10) inferred from your vault content, a color-coded status, and a concrete suggestion for improvement. The dashboard supports **Chinese / English toggle** and shows a 14-day sparkline trend per dimension.

Open it in any browser — no server needed:
```bash
open vault/dashboard.html   # macOS
start vault/dashboard.html  # Windows
```

---

## The staging workflow

Manual agent edits follow a **propose → approve → apply → commit** cycle. One-click knowledge import follows the automatic retention settings described above and writes with source references and backups.

```
1. You give the AI information or ask it to update something
2. AI writes a proposal to vault/91_Staging/YYYY-MM-DD-topic.md
3. You review: "looks good" / "apply" / "change X first"
4. AI applies to canonical files and commits to Git
```

Staging lets you review manual proposals; automatic imports retain an audit trail and restoration support.

---

## Information classification

Every claim in the vault is labeled so you always know how confident to be:

| Label | Meaning |
|-------|---------|
| `confirmed` | You stated it directly, with a source and date |
| `hypothesis` | Unverified — clearly labeled, not treated as fact |
| `ai-inference` | AI interpretation — never promoted to confirmed |
| `historical-decision` | A past choice, preserved even if later superseded |
| `time-series` | Dated measurements (weight, test scores, etc.) |

---

## Supported AI agents

| Agent | Status | Setup |
|-------|--------|-------|
| Claude Code | ✅ Native | Open Claude Code in `vault/` — `CLAUDE.md` auto-loads |
| OpenAI Codex | ✅ Supported | Add system prompt from Step 4 above |
| Any file-reading agent | ✅ Compatible | Point at `PROFILE.md` + `memory/` + `CLAUDE.md` |

See [`docs/agent-integration.md`](docs/agent-integration.md) for detailed setup per agent.

---

## Philosophy

Your AI assistant should know you — not just what you said in the last message, but who you are, what you're working toward, and how you think. SelfOS is the infrastructure layer that makes that possible.

Today it's a pattern. The goal is for it to become the standard OS layer between every person and their AI — a personal context layer that travels with you, works with any agent, and compounds over time. Fork it, build on it, help shape what it becomes.

---

## Contributing

PRs welcome. If you adapt SelfOS to a new AI agent or workflow, open a PR to add it to the supported agents table.

---

## Author

**Liam (Jialei Liu)**
- GitHub: [@Liam-coding](https://github.com/Liam-coding)
- Email: jialei.liu.sh@gmail.com

---

<a name="chinese"></a>

---

# SelfOS — 中文文档

**用最简单的方式管理你的人生**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**[English ↑](#selfos)**

SelfOS 是一个开源框架，用于构建 AI 可读、可更新、可推理的个人知识与记忆系统。把它理解为你和 AI 助手之间的 OS 层——一个跨会话持久存在的第二大脑。

> "对你一无所知的 AI 是陌生人。SelfOS 让它成为真正的协作者。"

---

## 这是什么？

大多数 AI 助手在会话结束后就忘记了你。SelfOS 通过给 AI 一个结构化、版本控制的知识库来解决这个问题——包含你的目标、职业、健康、研究、决策和上下文。

把它理解为 AI 时代的**第二大脑**：一个 AI 真正能读取、更新、推理的个人知识管理（PKM）系统——而不是一个闲置的笔记 app。

- **Git 原生**：一切都是 Markdown + Git，你的人生有版本历史。
- **AI 无关**：支持 Claude Code、Codex 或任何能读文件的 Agent。
- **隐私优先**：完全运行在本地，无云端，无数据库。
- **结构化但灵活**：开箱即用，也可以完全按你的方式定制。

> 适合所有每天使用 AI 的人——让你的 AI 助手真正了解你。Git 是可选的，AI agent 可以直接帮你管理 vault。

---

## 工作原理

```
你 ──→ AI Agent ──→ 读取 vault/ ──→ 理解你的上下文
                 ──→ 提议变更到 91_Staging/
                 ──→ 你审批
                 ──→ 写入正式文件
                 ──→ Git 提交
```

vault 是一组按生活领域组织的 Markdown 文件。AI 在每次会话开始时读取这些文件，并随时间维护它们。手工编辑使用 staging 审批；一键知识整理按配置直接写入，保留来源和可恢复备份。

---

## 快速开始

```bash
# 1. 克隆
git clone https://github.com/Liam-coding/SelfOS.git && cd SelfOS

# 2. 提取 AI 会话历史（自动安装 /digest skill）
python harvest.py

# 3. 打开 Claude Code，输入 /digest
claude
```

就这些。

---

## 人生仪表盘

每次运行 `python harvest.py`，SelfOS 自动生成 `vault/dashboard.html`——7 个维度的人生状态可视化快照：

| 维度 | 追踪内容 |
|------|---------|
| 职业发展 | 职业机会、发展势头、方向清晰度 |
| 工作/项目 | 活跃项目、交付进度、阻塞项 |
| 健康体能 | 训练、精力、身体状态 |
| 学习成长 | 课程、书籍、技能进展 |
| 研究 | 实验、进展、论文发表 |
| 生活 | 平衡感、幸福感、副业项目 |
| 家庭 | 家庭关系、联系频率、存在感 |

每个维度根据 vault 内容自动推断 1-10 分，带颜色状态和具体改进建议。仪表盘支持**中英文切换**，每个维度显示 14 天趋势折线。

用浏览器直接打开，不需要任何服务器：
```bash
start vault/dashboard.html  # Windows
open vault/dashboard.html   # macOS
```

---

## Staging 工作流

手工编辑采用 **提议 → 审批 → 应用 → 提交** 循环。一键知识整理按上面的自动保留配置直接写入，并保存来源和备份。

```
1. 你给 AI 信息，或要求它更新某些内容
2. AI 将提议写入 vault/91_Staging/YYYY-MM-DD-主题.md
3. 你审阅："好的" / "应用" / "先改一下 X"
4. AI 应用到正式文件并 Git 提交
```

Staging 用于审核手工提议；自动整理保留审计记录和恢复能力。

---

## 信息分类

vault 中的每条信息都有标签，让你始终清楚其可信度：

| 标签 | 含义 |
|------|------|
| `confirmed` | 你直接陈述的，有来源和日期 |
| `hypothesis` | 未验证——明确标注，不作为事实处理 |
| `ai-inference` | AI 的推断——不会被提升为 confirmed |
| `historical-decision` | 过去的决定，即使被覆盖也会保留 |
| `time-series` | 有日期的测量数据（体重、考试成绩等） |

---

## 支持的 AI Agent

| Agent | 状态 | 接入方式 |
|-------|------|---------|
| Claude Code | ✅ 原生支持 | 在 `vault/` 下打开 Claude Code，自动加载 `CLAUDE.md` |
| OpenAI Codex | ✅ 支持 | 按第四步添加系统提示 |
| 任意可读文件的 Agent | ✅ 兼容 | 指向 `PROFILE.md` + `memory/` + `CLAUDE.md` |

详细接入说明见 [`docs/agent-integration.md`](docs/agent-integration.md)。

---

## 哲学

你的 AI 助手应该了解你——不只是你上条消息说了什么，而是你是谁、你在追求什么、你怎么思考。SelfOS 是让这一切成为可能的基础设施层。

现在它是一种模式。目标是让它成为每个人和 AI 之间的标准 OS 层——一个随你迁移、兼容任意 Agent、随时间持续积累的个人上下文层。Fork 它，在上面构建，帮助塑造它的未来。

---

## License

MIT — see [LICENSE](LICENSE)
