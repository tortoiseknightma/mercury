# 架构

Mercury 内部架构技术文档。

Mercury 是一个**自我演化的技能合成 Agent**：在 LangGraph 上跑数据清洗任务，把执行轨迹喂给评估器反思、合成出 Anthropic Agent Skills 规范的 `SKILL.md`，再经过隔离 Docker 沙箱内的三维门控验证，只让真正提升性能的技能进库。本文档按系统模块自顶向下展开 —— 想看高层叙事见 `README.md`，想看里程碑进度见 `ROADMAP.md`，想看面试故事线见 `docs/RESUME.md`。

---

## 系统概览

```
                     CLI (mercury {run, bench, evolve, report, reset})
                                    |
                       LangGraph StateGraph (graph.py::build_app)
        ┌───────────┬────────────┬────────────┬────────────┐
     执行层      反思层      合成层       验证层      技能库
                                                  |
                                                  ▼
                               Docker 沙箱（network=none + cap_drop=ALL）
                                  |          |          |
                              python_repl  read/write  load_skill / submit
```

四个 LangGraph 节点（`executor` / `evaluator` / `synthesizer` / `verifier`）通过单一 `AgentState` TypedDict 通信，每个字段都有唯一的 writer 节点；`graph.py::build_app(mode)` 是唯一入口，按运行模式（`baseline` | `evolve` | `evolved`）拼出对应的有向图。CLI（`cli.py`）、评测管线（`eval/runner.py`）、单元测试都共享同一个 `build_app` 工厂 —— 不在三处分别 wiring。

---

## 双循环架构

Mercury 的核心是一个嵌套的双循环：内层 executor 自循环负责"解题"，外层 evolve 链路负责"反思 → 合成 → 验证"。

```
                       ┌──────────┐ done=False (loop)
                       │ executor │◀─────┐
                       └────┬─────┘      │
                            │ done=True  │
        baseline / evolved  │            │
        ─────────────────  END           │
                            │ should_evaluate(state)
        evolve              ▼
                       ┌──────────┐ should_synthesize=False
                       │evaluator │──────────────────────▶ END
                       └────┬─────┘
                            │ should_synthesize=True
                            ▼
                       ┌─────────────┐ skill name 非法 / 重复
                       │ synthesizer │──────────────────▶ END
                       └────┬────────┘
                            │ SKILL.md 写入成功
                            ▼
                       ┌──────────┐
                       │ verifier │──────────────────▶ END
                       └────┬─────┘
                            │
                  verified ─┴─ rejected
                  (frontmatter      (移到 _rejected/
                   翻 status:        + rejection.json
                   verified)         归档)
```

三种模式共用 executor 自循环；`baseline` 与 `evolved` 在 done 后直奔 END，`evolve` 才会进入 evaluator → synthesizer → verifier 链路。模式之间的差别**只在合成路径**，执行层完全相同。

**`add_conditional_edges` 必须传显式 mapping 字典**：`add_conditional_edges(from, fn, {return_value: to})`。否则 LangGraph 会把 routing 函数返回的字符串当成字面节点名，静默路由到不存在的节点。`graph.py:90-101` 三处条件路由都遵守这个约定。

`recursion_limit=64`（vs LangGraph 默认 25）：每次 executor 自循环消耗一次递归名额，12 max_steps × (1 LLM 轮 + 1 工具轮) = 24 已经爆默认上限，所以在 `app.invoke(..., config={"recursion_limit": 64})` 显式抬高。

---

## AgentState

LangGraph 在节点之间路由的是单一的 `TypedDict`（`state.py::AgentState`）。每个字段都有**唯一的 writer 节点**，任意节点可读：

| 字段 | Writer | 类型 | 用途 |
|---|---|---|---|
| `task_id`、`task`、`workspace_dir`、`expected_acceptance` | caller（CLI / runner） | str | 任务身份；一次性写入 |
| `messages` | executor | `list[BaseMessage]`（`add_messages` reducer） | LangGraph 自动 append，**不要覆盖** |
| `skill_manifest` | caller | `list[{name, description}]` | 注入 system prompt 的渐进披露列表 |
| `loaded_skill_bodies` | （仅记录） | `dict[str, str]` | `load_skill` 调用记录，路由不读 |
| `trace` | executor | `TraceCard`（in-place mutate） | 步骤、token、turns 的累积容器 |
| `proposed_skill` | evaluator | `Optional[ProposedSkill]` | 路由开关：决定是否进 synthesizer |
| `done` | executor | `bool` | 路由开关：内循环是否终止 |
| `consecutive_no_tool` | executor | `int` | 卡死探测器（连续 3 次纯文本 → done） |
| `synthesized_skill_path` | synthesizer | `Optional[str]` | 路由开关：决定是否进 verifier |
| `verification_outcome` | verifier | `Optional[dict]` | 序列化的 `VerificationOutcome` |

### TraceCard schema

```
TraceCard = {
    task_id, task_description, mode, skills_loaded[],
    steps: list[TraceStep],
    final_output_path, success,
    total_tokens, total_turns,    # turns 只算 tool=='llm' 的步骤
    timestamp,
}

TraceStep = {
    step_id, tool, args, output,
    error, duration_ms,
    tokens_in, tokens_out,
}
```

`append_step` 是 `total_turns` 的唯一变更入口，**只在 `step["tool"] == "llm"` 时 +1**。这是计费相关的关键指标，不能与 `len(steps)`（同时计 LLM 轮数和每个工具调用）混用 —— Day 2 早期版本就因此把 turns 蹭成 step 计数，校准过的 `baseline_metrics` 全数失真。

---

## 执行层（executor）

`nodes/executor.py::make_executor_node` 是工厂函数，闭包 `(llm, tools, max_steps)` 构造一个 LangGraph 节点。每次调用对应**一次 LLM call + 内联执行所有 tool_calls + 路由决策**，循环由 `graph.py::_route_after_executor_evolve` 控制。

### 三个退出条件

executor 自循环在以下任一条件触发时设 `done=True`：

| 条件 | 触发位置 | 含义 |
|---|---|---|
| `submit` 返回 `passed=True` | tool 执行后 `json.loads(result_str)` 检测 | 任务通过验收，写入 `trace.success=True` |
| `total_turns >= max_steps` | 节点末尾硬封顶 | 默认 12 turns 用完仍未 submit |
| 连续 3 次纯文本响应 | `consecutive_no_tool >= 3` | 模型在"说话"而不是"做事"，认定为卡死 |

`consecutive_no_tool` 在任何 `tool_calls` 非空时复位为 0。这条规则看似简单，但是 Day 2 调试 Qwen-Plus 时发现的关键 corner case —— 否则模型死循环吐推理文本时会一直消耗 turns 直到爆 max_steps。

### System Prompt 构造

executor 在第一轮（`messages` 为空时）注入 system prompt + initial human task message。`SYSTEM_PROMPT_TEMPLATE` 模板声明：

- 5 个工具的签名与边界（沙箱限制 / 网络隔离 / submit 验收语义）
- 已 verified 技能清单（仅 `(name, description)` 对，body 按需加载）
- max_steps 硬上限
- 推荐工作流 4 步（read → transform → write → submit）

manifest 在 `baseline` / `evolve` 模式恒为空 `[]`；只有 `evolved` 模式会注入 `scan_manifest(status="verified")` 的结果。这是渐进披露的"启动期"半边 —— 完整 body 只在 agent 主动 `load_skill(name)` 时才读入上下文。

### Tool 分发与序列化契约

每个 tool 的返回值必须是 **JSON 字符串**。executor 在分发时：

1. 把字符串 result 直接 append 为 `ToolMessage`（LangChain 的固定形态）。
2. **额外**对 `submit` 的结果调 `json.loads()` 检测 `passed` 字段。

这意味着所有 `tools.py` 的 wrapper 都必须 `json.dumps(...)` —— Day 2 在 fakelm 测试里发现一个回 dict 的 stub 直接打挂了路由。

---

## 反思层（evaluator）

`nodes/evaluator.py` 在 `evolve` 模式下、executor done 后被 `should_evaluate(state)` 门控触发：

```python
def should_evaluate(state):
    if not state.trace.success:
        return True                    # 失败必反思（教训也是经验）
    return state.trace.total_turns >= 4  # 成功且 ≥ 4 turns 才反思
```

`MIN_TURNS_FOR_REFLECTION = 4` 是软阈值，校准自 Day 5 实测：Qwen-Plus 在简单任务上常 3 turns 解完，没有 headroom 让评估器找到"非平凡 SOP"，跳过这些 case 节省 token。

### 两段式过滤

evaluator 实际是 **flash 预筛 + plus 反思** 的两段流水线：

1. **Flash 预筛**：用 `qwen-flash` 跑一句话过滤 prompt——"这个 trace 有没有出现错误，或者超过 4 轮？是答 YES 否答 NO"。NO 直接返回 `should_synthesize=False`，省下后续完整反思的几千 token。
2. **Plus 反思**：通过 flash 才进入完整结构化反思，用 `evaluator_model`（默认 `qwen-plus`，温度 0.3）。

这个组合在 Day 6 实测下来把 evaluator 端的 token 消耗降了约 40%。

### `bind_tools` 而非 `with_structured_output`

evaluator 期望的输出是 `ProposedSkillSchema`（pydantic）。教科书做法是 `llm.with_structured_output(schema, method="function_calling", strict=True)`，但这条路在 Qwen 上**走不通** —— `with_structured_output` 内部会设 `tool_choice="required"`，与 Qwen 的 thinking 模式冲突，调用直接抛错。

绕路：定义一个名为 `emit_skill_proposal` 的 no-op `StructuredTool`，把 `ProposedSkillSchema` 作为它的 `args_schema`，然后 `llm.bind_tools([emit_skill_proposal])`。响应里读 `response.tool_calls[0].args` 就能拿到结构化 dict。**两条恢复路径**保证健壮性：

- 模型没回 tool_call → 把 `response.content` 当 JSON 解析（兜底纯文本回退）
- 解析失败 → 返回 `{should_synthesize: False, _error: ...}` 优雅降级，不抛异常

这个 workaround 是 Day 3 写成的、Day 4-7 一直保留 —— 切换到任何 OpenAI 兼容厂商前都得重新评估这条路径。

### ProposedSkill 字段

```python
class ProposedSkillSchema(BaseModel):
    should_synthesize: bool                # 触发开关
    skill_name: Optional[str]              # kebab-case, ≤ 4 词
    trigger_description: Optional[str]     # 一句话："When ... use this skill before ..."
    failure_patterns: list[str]            # trace 里的弯路
    successful_subroutines: list[str]      # 最终奏效的步骤
    instructions_md: Optional[str]         # SKILL.md body，含 ## When to use / ## Steps / ## Pitfalls
```

`should_synthesize=False` 时其余字段空。

---

## 合成层（synthesizer）

`nodes/synthesizer.py` 是**纯 I/O，无 LLM 调用**。职责单一：把 evaluator 的 proposal 转成磁盘上的 `SKILL.md`。

### 名字净化

`_sanitise_name(raw)` 把任意输入压成安全 kebab-case 目录名：

1. 小写 + 去首尾空白
2. 空白 / 下划线 → `-`
3. 删掉非 `[a-z0-9-]` 字符
4. 折叠连续 `-`、剪首尾 `-`
5. 截断到 64 字符；垃圾输入（如 `"$$$"`）兜底为字面 `"skill"`

之后再用正则 `^[a-z0-9][a-z0-9-]{0,63}$` 验证，不通过返回 `None`（路由进 END）。

### 幂等性

写 `SKILL.md` 前检查目录是否已存在；存在直接返回 `None`，**绝不覆盖**。这意味着同一任务在 evolve 模式下重复跑不会反复改写已存在的技能。`_rejected/` 下的归档不算重复（loader 跳过 `_` 前缀），所以一个被拒过的技能名仍能在新一轮被重新合成。

### Frontmatter 写入

写出的 `SKILL.md` 是 YAML frontmatter + markdown body 双段结构（Anthropic Agent Skills 规范）：

```yaml
---
name: csv-mixed-line-endings           # kebab-case，≤ 64 字符；与目录名严格相等
description: When ... use this skill   # 一句话；shown in manifest
version: 1
applies_to: [csv]                       # 该技能针对的任务组
status: pending | verified | rejected   # 只有 verified 进 manifest
source_task: csv-005                    # 哪个任务触发的合成
baseline_metrics:                       # 触发时的"无技能"开销 —— 验证器用它当门槛
  tokens: 16269
  turns: 8
---

## When to use
...

## Steps
...

## Pitfalls
...
```

`baseline_metrics` 是 trace 里 `total_tokens` / `total_turns` 的快照，**evolve 模式下 manifest 为空时录得**，所以是真正的"无技能开销"——这是验证器三轴门控的比较基准。

---

## 验证层（verifier）

`nodes/verifier.py` 是 Day 4 的核心。**任意合成的技能默认 `status: pending`，必须经验证器三轴门控才翻 `verified` 入库**。验证器是 Mercury 与"把任意 LLM 反思直接固化"的根本区别。

### 三维门控（`gate_decision`，纯函数）

| 检查 | 违反时判决 |
|---|---|
| `source.success` | reject —— 技能反而打挂了原任务 |
| `source.tokens > 0.85 × baseline_tokens` | reject —— token 退化 |
| `source.turns > baseline_turns` | reject —— turn 退化 |
| `neighbour ≠ None ∧ ¬neighbour.success` | reject —— 打挂同组邻居 |
| `anti ≠ None ∧ anti.loaded_skill` | reject —— trigger 太宽（误触发跨组任务） |
| 否则 | **verified** |

source 三轴必须**同时满足**（success ∧ tokens ≤ 0.85× ∧ turns ≤）。neighbour 只查 success（不缓存邻居 baseline，全跑会让 verifier 成本翻倍）。anti-trigger 只查 `load_skill(<this>)` 是否被调用 ——**跨组任务本身不需要通过**，关心的只有"description 是否够具体不会误吸跨域任务"。

### 0.85× ratio 的设计意图

这个比例在 `CLAUDE.md` 标注为"load-bearing"，未经 ROADMAP 更新不允许放宽。它的工程含义：

- 加载一个 skill 本身就要消耗一次 `load_skill` LLM 轮 + body 进上下文（约 500–1500 tokens）。
- 0.85× 意味着 skill 必须**在 source 任务上至少省下 15% token**才值得入库；否则等于"加了一层壁纸还多花了油漆"。
- Day 4 早期 9 任务集上这条门槛**结构性卡死**——Qwen-Plus baseline 普遍 3-4 turns / 4-7K tokens，留给 skill 的预算覆盖不住一次 load_skill 的成本。两个自然合成的 skill 都因此被拒。
- Day 6 把任务集扩到 16 后，更难的任务（csv-005 的混合换行 / json-002 的嵌套展平）baseline 升到 8+ turns / 12K+ tokens，0.85× 才有可达性 —— 自然产出 2 个 verified skill。

### Anti-trigger 的归位

Day 4 实测两次自然拒绝（`dirty-csv-whitespace-cleanup` / `csv-quoted-number-cleanup`），异组探针（json-001）都 `loaded_skill=False`。这反向印证 evaluator + synthesizer 链上游产生的 description 质量过关 —— `bind_tools` workaround 没有牺牲结构化输出的精度。

### 探针 runner（`run_task_with_manifest`）

每个探针（source / neighbour / anti）独立完成：

1. 从任务 fixture 准备一份**全新 workspace**。
2. 起一个**独立 DockerSandbox**（一次性，无 checkpointer）。
3. 编译一个一次性图（仅 `executor → END`，跳过 evolve 节点）。
4. 注入 `manifest = [{name: skill_name, description: skill_desc}]`，候选技能是模型唯一能看到的。
5. 跑完后扫 trace 找 `load_skill(name=skill_name)` 步骤，填入 `RunMetrics.loaded_skill`。

**探针强制使用 `build_llm("executor")`** —— `baseline_metrics` 是用 executor 模型测得的，换模型会让 0.85× 失去比较意义。这条在 `verifier.py:215` 写明且 CLAUDE.md 反复强调。

### 拒绝归档

被拒技能不删，移到 `<library>/_rejected/<name>__<iso-ts>/` 并写一份 `rejection.json`（含完整 `VerificationOutcome` —— 三个 `RunMetrics` + 判决原因）。ISO 时间戳的 `:` 替换为 `-`，保证 Windows 文件系统安全。

`scan_manifest()` 跳过 `_` 与 `.` 前缀目录，所以 `_rejected/` 永远不会再回到 manifest。

### "Skill Regression" 现象（Day 6 主动诊断）

Day 6 全量 16 任务评测下，evolved 模式 Pass@1 反而比 baseline 低 6.25 pp（93.75% → 87.50%）。诊断结论：

- `csv-mixed-line-endings`（applies_to=csv）通过 verifier 三轴 + csv-001 邻居 + json-001 反触发探针。
- 但 csv-002（whitespace 边界，与换行无关）在 evolved 模式下**自发调用了 csv-mixed-line-endings**，从 6 turns / 12K token 暴涨到 15 turns / 58K token，最后失败。
- 根因：**1 邻居采样不足以保证整组泛化**。
- 这反而是验证器必要性的反向证据 —— 没有验证器全部直入 manifest，回归会更严重；现有验证器拦掉了"明显有害"的（D4 两次 token regression），但放过了"在邻居上无害但在远亲上有害"的。
- 改进方向已写入 `ROADMAP.md`：(a) verifier 用 ALL same-group 任务做泛化验证；(b) per-skill ablation 报表标注哪些 skill 在哪些任务被加载。

---

## Docker 沙箱

`sandbox/docker_sandbox.py::DockerSandbox`。LLM 生成的 Python 默认是恶意的，沙箱的存在就是把"可能泄露数据 / 越权 / fork-bomb / 无限循环"的爆炸半径关进盒子。

### 容器参数

| 参数 | 取值 | 抵御的威胁 |
|---|---|---|
| `image` | `mercury-sandbox:latest` | 自建镜像（`scripts/sandbox.Dockerfile`）：`python:3.11-slim` + pandas / numpy / lxml / bs4 / chardet / regex / dateutil 全预装。**容器 `network=none` 不能 pip install**，所以必须自带全部依赖 |
| `command` | `["sleep", "infinity"]` | 容器长生命周期；每段代码通过 `put_archive` 注入 + `exec_run` 执行。**一容器一任务 ≈ 一容器一 snippet 的 200× 便宜** |
| `network_mode` | `none` | 出站数据外泄 + 入站 RCE |
| `mem_limit` | `512m` | 内存炸 / DoS |
| `nano_cpus` | `1×10⁹`（1 CPU） | CPU 抢占 |
| `cap_drop` | `ALL` | Linux capabilities 提权 |
| `security_opt` | `no-new-privileges:true` | setuid 逃逸 |
| `pids_limit` | `128` | fork-bomb |
| `working_dir` | `/workspace` | workspace 通过 bind-mount 挂入；相对路径解析到这里 |
| `volumes` | `host_workspace:/workspace:rw` | 输出文件落盘到 host，给 `accept()` 读 |
| GNU `timeout` 包装 | `--signal=KILL <SANDBOX_TIMEOUT_SECONDS>`（默认 30s） | 单段 wallclock 上限；exit code 124/137 → `timed_out=True` |

`docker.from_env()` 跟随用户的 Docker context，所以 Windows Docker Desktop / Mac / 原生 Linux 都能跑。Docker SDK 的 `dockerfile=` 参数即使在 Windows 上也要 POSIX 路径（`Path.as_posix()`）。

### 生命周期

```python
with DockerSandbox(workspace) as sbx:
    # __enter__ → start() → containers.run(detach=True, ...)
    sbx.run("import pandas; ...")  # exec_run + timeout 包装
    sbx.run("...")
# __exit__ → stop() → kill() + remove(force=True)
```

`stop()` 一律先 `kill()` 再 `remove(force=True)`，并吞掉 `APIError` / `NotFound` —— 即使遇到残留的僵尸容器也不会让 wrapper 崩溃。

代码注入用 `put_archive`：把 Python 片段写到内存 tar buffer，再 PUT 到容器的 `/tmp/snippet_<uuid>.py`，避免 `exec_run` 直接传命令时的 shell 引号 / 多行转义陷阱。

---

## 工具栈（5 个）

`tools.py::build_tools(workspace, sandbox, skill_loader, on_submit) → ToolBundle` 在每次 run 时构造，闭包当次 run 的 workspace / sandbox / loader / submit 钩子。返回 5 个 `StructuredTool`：

| 工具 | 用途 | 入参 → 出参 |
|---|---|---|
| `python_repl` | 在沙箱执行 Python | `code: str → {exit_code, stdout, stderr, elapsed_ms, timed_out}` |
| `read_file` | 读 workspace 文件（UTF-8 文本或 hex preview） | `path, max_bytes=4096 → {content / content_hex, encoding, bytes}` |
| `write_file` | 写 UTF-8 文本到 workspace（自动建父目录） | `path, content → {ok, bytes}` |
| `load_skill` | 读已 verified 技能完整 body（仅 `evolved` 模式有意义） | `name → {name, body}` 或 `{error}` |
| `submit` | 触发 host 端 `accept(workspace)` 验收 | `output_path, note → {passed, reason, output_path}` |

**全部 tool 输出统一 4 KB 截断**（`MAX_OUTPUT_BYTES = 4096`），否则一次失败 stderr 就能把上下文打爆。多字节字符截断时用 `errors="ignore"` 容错，避免半个 UTF-8 编码点导致 `ToolMessage` 解析失败。

`read_file` / `write_file` 拒绝路径穿越 —— `(workspace / path).resolve()` 后检查是否仍在 `workspace.resolve()` 之下。

---

## 渐进披露技能加载

`skills/loader.py` 实现 Anthropic Agent Skills 规范里"启动只看名+描述、按需才读 body"的两阶段加载。

| 函数 | 职责 |
|---|---|
| `parse_skill_file(path)` | 拆 frontmatter / body，pydantic 验证 |
| `write_skill_file(path, fm, body)` | 圆环安全：`parse ∘ write = id` |
| `scan_manifest(library_dir, status="verified")` | 列 frontmatter；默认只读 verified；跳过 `_` 前缀；坏 frontmatter 不崩只跳过 |
| `load_full(name)` | 按需读完整 body（`load_skill` 工具的后端） |
| `manifest_to_dicts(...)` | 压成 `[{name, description}]`，注入 system prompt |

只有 `cli.py`（`evolved` 模式）和 `verifier.py`（构造候选 skill 单技能 manifest）会调 `scan_manifest`；其他节点都从 `AgentState.skill_manifest` 读已注入的列表。

---

## 评测管线

`eval/runner.py` + `eval/metrics.py` + `eval/plots.py` 三层。

```
runner.run_one_task(task, mode, run_idx)
    → 准备 workspace + sandbox + 编译图 + 初始 state
    → 一次 invoke
    → 返回 TaskResult dataclass

runner.run_bench(mode, task_ids?, progress_cb?)
    → 顺序遍历任务（不并行 —— Docker 启动竞争 + DashScope 限流让小集合并行无收益）
    → 返回 BenchResult { mode, timestamp, tasks: [TaskResult, ...] }

runner.save_bench(result)  → results/metrics_<mode>.json
runner.load_bench(path)    → BenchResult

metrics.compute(BenchResult)
    → BenchMetrics { n, pass_at_1, avg_tokens, avg_turns, by_group: {...} }

metrics.normalized_gain(p_before, p_after)
    → (p_after - p_before) / (1 - p_before)        if p_before < 1
    → 0.0                                          if p_before == 1   (clamp)

metrics.compare(baseline, evolved) → ComparisonMetrics
    { baseline, evolved, pass_delta, normalized_gain,
      tokens_ratio (= evolved/baseline; <1 = improvement),
      turns_ratio  (= evolved/baseline; <1 = improvement) }

plots.render_all(baseline, evolved, out_dir)
    → results/plots/{pass_at_1, tokens_per_task, tokens_radar}.png
```

`progress_cb(idx, total, task, result_or_None)` 接口让 CLI 进度展示与测试 stub 共用一个回调，每个任务前后各回一次（前者 result=None）。

`plot_tokens_radar` 在任务数 < 3 时自动降级到 `plot_tokens_per_task` —— 极坐标只 1-2 个轴会退化到无意义。

### Normalized Gain

报告里的核心指标：

```
g = (P_after - P_before) / (1 - P_before)         # P_before < 1
g = 0.0                                           # P_before == 1   (无 headroom 封顶)
```

它把 Pass@1 改进按"还有多少 headroom"重新缩放。0.6 → 0.8（g = 0.5）是比 0.0 → 0.2（g = 0.2）更难的成就，即使 raw delta 一样。Day 6 实测 g = -1.00 的数学含义：headroom = 1 - 0.9375 = 0.0625（一个失败任务 xml-002），evolved 退到 14/16 = 损失 1 个，正好等于全部 headroom 的反方向。

---

## 任务集

`eval/tasks/<group>/<id>/` 三件套：

```
<group>/<id>/
├── task.py     # TASK = register(Task(...))，定义 accept(workspace) -> (bool, str)
├── input.*     # 输入文件，run 时复制进 workspace
└── expected.*  # 标注答案，**只在 host 端**，永不暴露给 agent
```

**host / sandbox 分离是硬规则**：agent 看不到 `expected.*`。验收永远是确定性 Python 函数比对 workspace 输出与 expected ——**禁用 LLM-as-Judge**，因为那会创造一个反馈回路：评估器可以给自己的错误反思打高分。

任务自发现：`_autodiscover()` 在第一次调 `all_tasks()` / `get_task()` 时遍历子包，import 每个 `task.py`，模块顶层的 `register(Task(...))` 自动注册到 `_REGISTRY`。

### 当前 16 任务 6 组

| 组 | n | 示例 |
|---|---|---|
| `csv` | 5 | BOM + `;` + 欧式小数；脏空白；引号数字；UTF-16 LE；混合换行 |
| `json` | 2 | flat-array → CSV；嵌套展平点列名 |
| `log` | 2 | nginx combined-format；多行 Python traceback |
| `multi` | 2 | 跨文件 JOIN（含 GBK 编码） |
| `pipeline` | 3 | 链式转换 + Z-score 归一化 |
| `xml` | 2 | XML → CSV（含故意损坏的修复任务） |

---

## 模型路由 / 配置 / 提示缓存

`config.py::load_config()` 集中读 `.env`（`load_dotenv` 幂等）。所有 dataclass `frozen=True`，每次调 `load_config()` 重读 —— 测试可以单独改 env。

### 三角色 model dispatch

`build_llm(role)`（`llm.py`）按角色路由模型：

| 角色 | env 覆盖 | 默认 fallback |
|---|---|---|
| `executor` | `EXECUTOR_MODEL` | `QWEN_PLUS_MODEL`（`"qwen-plus"`） |
| `evaluator` | `EVALUATOR_MODEL` | `QWEN_PLUS_MODEL` |
| `flash` | `FLASH_MODEL` | `QWEN_FLASH_MODEL`（`"qwen-flash"`） |

温度同样按角色分（`EXECUTOR_TEMPERATURE=0.0`、`EVALUATOR_TEMPERATURE=0.3`、flash 强制 0.0）。

**典型配置**：把 `EXECUTOR_MODEL=qwen-flash` 让执行轨迹更长 → evaluator 有更多反思素材；保留 `EVALUATOR_MODEL=qwen-plus` 走聪明反思。

**verifier 探针固定使用 executor 模型** —— `baseline_metrics` 是在 executor 模型下测得的，换模型会让 0.85× token 预算失去比较意义。这条规则写死在 `verifier.py::run_task_with_manifest` 第 215 行。

### 全局 prompt cache

`llm.py` import 时立即注册 LangChain 全局 SQLite 缓存：

```python
set_llm_cache(SQLiteCache(database_path=str(RESULTS_DIR / "prompt_cache.db")))
```

相同 `(model, messages, params)` 元组直接命中本地 sqlite，**不重复计费**。缓存命中仍走 tenacity 重试装饰器（首次成功就退出）。要强制重跑，删掉 `results/prompt_cache.db` 即可 —— verifier 每次探针的 `uuid` thread_id 与缓存键无关（缓存按内容寻址而非身份寻址）。

### 重试

`invoke_with_retry(llm, messages)` 用 tenacity 包装：4 次尝试，2-20s 指数退避。底层 `ChatOpenAI` 的 `max_retries=0` —— 把重试策略集中到一处，避免双层退避导致 worst-case 延迟爆炸。

---

## 模式语义对照

`graph.py::build_app(mode=...)` 拼出三种 DAG。三者共用执行层，差异只在 done 之后：

| mode | 路径 | 用途 |
|---|---|---|
| `baseline` | `executor → END` | 测无技能基线，产出 `baseline_metrics` |
| `evolve` | `executor → evaluator → (synthesizer → verifier) → END` | 反思 + 合成 + 验证一条龙 |
| `evolved` | `executor → END`，但启动时注入 verified 技能 manifest | 测有技能性能，与 baseline 对比 |

注意 `evolve` 与 `evolved` 的语义区别：前者是"做完再反思"，后者是"用着已有技能解题"。CLI 命令分别是 `mercury evolve` 和 `mercury bench --mode evolved`。

---

## CLI

`cli.py`（typer）暴露 6 个子命令：

| 命令 | 用途 |
|---|---|
| `mercury run --task X --mode {baseline,evolve,evolved}` | 单任务调试，打印 run summary 表 |
| `mercury list-tasks` | 列出所有 16 任务（id / group / 描述前 90 字符） |
| `mercury bench --mode {baseline,evolve,evolved} [--tasks X,Y]` | 跑评测，写 `results/metrics_<mode>.json` |
| `mercury evolve [--task X \| --tasks X,Y]` | 等价于 `bench --mode evolve`，单任务时复用 run summary UX |
| `mercury report` | 读 `metrics_baseline.json` + `metrics_evolved.json` 出对比表 + 3 张 PNG |
| `mercury reset` | 清空 `skills/library/*`（保留 `.gitkeep`）+ 删 `results/state.db` |

**Windows quirk**：CLI 入口强制 `sys.stdout.reconfigure("utf-8")`（cp936 / gbk 默认会让 rich 渲染的 `✓` 炸掉）；同时 `os.environ.setdefault("PYTHONIOENCODING", "utf-8")` 让子进程也走 UTF-8。

---

## 数据持久化

| 路径 | 用途 |
|---|---|
| `results/state.db` | LangGraph SqliteSaver checkpointer。caller MUST `conn.close()`（`build_app` 把 conn 一并返回正是为此） |
| `results/prompt_cache.db` | LangChain 全局 SQLite prompt 缓存。`mercury reset` **不**碰这个 —— 故意保留以加速调试 |
| `results/traces/<task>__<mode>__<idx>.jsonl` | 每次 run 一个 JSONL trace；header 行 + 一行一 step；`load_trace` 反序列化 |
| `results/workspaces/<task>__<mode>_<idx>/` | 每次 run 一个隔离 workspace；下次 run 同任务会先 rmtree 再重建 |
| `results/metrics_<mode>.json` | `mercury bench` 的产出，`mercury report` 的输入 |
| `results/plots/{pass_at_1,tokens_per_task,tokens_radar}.png` | 3 张评测图 |
| `src/mercury/skills/library/<name>/SKILL.md` | verified 技能本体 |
| `src/mercury/skills/library/_rejected/<name>__<ts>/` | 拒绝归档 + `rejection.json` |

---

## 测试矩阵

| 文件 | 类型 | 需 Docker | 需真实 LLM |
|---|---|---|---|
| `test_state.py`（3） | 纯函数 | 否 | 否 |
| `test_executor.py`（5） | scripted LLM | 否 | 否 |
| `test_tasks.py`（~64） | 参数化 | 否 | 否 |
| `test_loader.py`（7） | tmp_path I/O | 否 | 否 |
| `test_synthesizer.py`(8) | tmp_path I/O | 否 | 否 |
| `test_evaluator.py`(~9) | stub LLM | 否 | 否 |
| `test_verifier.py`（22） | stub runner | 否 | 否 |
| `test_metrics.py`（9） | 纯函数 | 否 | 否 |
| `test_plots.py`（6） | tmp_path PNG | 否 | 否 |
| `test_config.py`（6） | env mocking | 否 | 否 |
| `test_sandbox.py` | 集成 | **是** | 否 |
| `test_tools_e2e.py` | 集成 | **是** | 否 |
| `test_llm.py` | API smoke | 否 | **是** |

**139 离线测试**对应前 10 个文件。CI 无 Docker / API key 时用 `--ignore` 跳过最后 3 个。

`tests/test_llm.py` 顶部需手工 `load_dotenv()` —— pytest 不自动加载 `.env`，跟 CLI / runner 行为不同。

---

## 头号实测结果

| 指标 | baseline | evolved | Δ |
|---|---|---|---|
| Pass@1 | 93.75%（15/16） | 87.50%（14/16） | −6.25% · g = −1.00 |
| avg tokens / task | 16 049 | 19 026 | ×1.185 |
| avg turns / task | 5.56 | 6.06 | ×1.090 |
| 自然产出 verified skills | — | 2（`csv-mixed-line-endings`、`json-nested-flatten-csv`） | — |
| 自然拒绝（含归档） | — | 多个（含 token regression / turn regression / 过宽 trigger 三种原因） | — |

evolved 模式 Pass@1 反而下降 6.25 pp，是项目最有趣的结果：一个通过单技能三轴门控的 skill 仍能通过同组 sibling 任务上的误触发拖低整体性能 —— 验证器的 1 邻居采样不足以捕捉这个，**而退化本身就是验证器机制必要性的反向证据**。完整工程叙事见 `docs/BENCHMARK_SUMMARY.md` 与 `docs/RESUME.md`。

---

## 运维提示

- `mercury reset` 清 `skills/library/*`（保留 `.gitkeep`）+ 删 `results/state.db`，**不**动 `results/prompt_cache.db` 与 `results/traces/`（这两个故意保留以加速复现 + 调试）。
- LangGraph `SqliteSaver` 在 `results/state.db`。caller（CLI / runner）**必须** `conn.close()` —— `build_app` 把 conn 一并返回正是为此。
- Windows quirk：CLI 设 `sys.stdout.reconfigure("utf-8")`，因为默认 GBK / cp936 会把 rich 输出与非 ASCII 任务描述弄炸。
- uv 在 `>=3.11,<3.13` 区间内会选 Python 3.12.13，这是预期行为，**不要**强制 3.11。
- `langgraph-checkpoint-sqlite` 在 langgraph-0.2 之后是独立包，必须保留在 `pyproject.toml` —— `langgraph` 主包已经分家。
- Docker SDK 的 `dockerfile=` 即使在 Windows 上也要 POSIX 路径（`scripts/pull_docker_image.py` 用 `Path.as_posix()`）。

---

## 依赖

| 包 | 用途 |
|---|---|
| `langgraph` + `langgraph-checkpoint-sqlite` | 状态图 + sqlite checkpointer（独立包，post-0.2） |
| `langchain-openai` | OpenAI-Compat 客户端（DashScope / Qwen 接入） |
| `langchain-community` | `SQLiteCache` 提供全局 prompt 缓存 |
| `pydantic` v2 | 结构化数据（`BaseModel` 给 LLM 看的 schema、`SkillFrontmatter` 落盘 schema） |
| `tenacity` | LLM 调用退避重试 |
| `docker` | Docker SDK 起 / 停 / exec / put_archive |
| `pandas` / `numpy` / `lxml` / `bs4` / `chardet` | **沙箱镜像**预装，不在 host runtime 直接用 |
| `typer` + `rich` | CLI + 表格渲染 |
| `matplotlib` | 评测图（`Agg` 后端，无显示器也能跑） |
| `pyyaml` | SKILL.md frontmatter 解析 / 写出 |
| `python-dotenv` | `.env` 加载（host 与测试都用） |
| `pytest` | 测试框架；`test_llm.py` 顶部手工 `load_dotenv()` |
