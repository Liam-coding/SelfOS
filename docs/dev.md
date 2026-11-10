# SelfOS — 开发文档

> 当前版本: harvest.py v0.5.0 · 更新: 2026-11-10

---

## 项目结构

```
SelfOS/
├── harvest.py          # 核心：提取、评分、生成 dashboard、AI staging
├── serve.py            # 本地 HTTP server：dashboard + chat proxy + staging API
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
│   └── test_harvest.py # 123 个单元测试
└── docs/
    ├── dev.md          # 本文件
    └── agent-integration.md
```

---

## 核心流程

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

- **周期性自动 harvest**：Windows 计划任务 / cron，每天定时采集
- **vault diff 视图**：staging 弹窗里展示 before/after diff
- **多数据源接入**：日历、GitHub 活动、健康数据（Apple Health export）
- **harvest.py 拆模块**：extract.py / score.py / dashboard.py / staging.py
- **Web UI 编辑 vault**：在 dashboard 里直接编辑 NOW.md / GOALS.md
