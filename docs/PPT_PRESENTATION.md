# Mercury 项目简历 PPT 介绍内容及配图

为你准备了 3 页 PPT 的讲解逻辑、文字大纲以及对应的高清矢量图（SVG代码）。建议将 SVG 代码保存为 `.svg` 文件，直接拖入 PPT 即可保持无限放大不失真。整体配色采用了现代科技感的深色主题，非常适合在技术面试中展示。

---

## 第 1 页：项目概述与痛点解决 (Project Overview)

**设计意图**：第一页需要迅速抓住面试官的眼球，点出传统 Agent 的缺陷，以及 Mercury 是如何通过架构创新解决这个问题的。

### 📄 文字内容 (PPT 大纲)

**标题：Mercury — 基于双循环架构的自我演化智能体**

**1. 行业痛点：Agent 的“阿尔茨海默症”**
- **重复试错**：面对相同任务，传统 Agent 每次都从零开始摸索，无法内化经验。
- **成本高昂**：将所有历史上下文直接塞入 Prompt 会导致 Token 爆炸及注意力稀释。

**2. Mercury 解决方案：自我演化闭环**
- 引入**「执行-提取-合成-验证」**双循环演化管线，让 Agent 自主沉淀高质量避坑技能（Skills）。
- 独创**渐进式技能加载**，外挂 Anthropic 规范标准技能库，降低复杂任务下的 Token 消耗与大模型幻觉。

**3. 项目核心数据**
- 实现涵盖 20 个数据清洗场景（CSV/JSON/Log）的端到端自动化演化评测集。
- 118+ 测试用例保障，演化后长期推理成本显著下降。

### 🖼️ SVG 配图 1 (概念对比图)

*(请将以下代码保存为 `ppt_page1_overview.svg`)*

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 400">
  <defs>
    <linearGradient id="gradRed" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ef4444" />
      <stop offset="100%" stop-color="#b91c1c" />
    </linearGradient>
    <linearGradient id="gradGreen" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#10b981" />
      <stop offset="100%" stop-color="#047857" />
    </linearGradient>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="5" result="blur" />
      <feComposite in="SourceGraphic" in2="blur" operator="over" />
    </filter>
  </defs>

  <rect width="800" height="400" rx="16" fill="transparent" />

  <!-- Title -->
  <text x="400" y="40" font-family="Arial, sans-serif" font-size="20" font-weight="bold" fill="#f8fafc" text-anchor="middle">传统智能体 vs Mercury 自我演化智能体</text>

  <!-- Left Side: Traditional Agent -->
  <rect x="50" y="80" width="300" height="280" rx="12" fill="#1e293b" stroke="#334155" stroke-width="2" />
  <text x="200" y="110" font-family="Arial, sans-serif" font-size="16" font-weight="bold" fill="#ef4444" text-anchor="middle">❌ 传统无状态智能体</text>
  
  <rect x="100" y="140" width="200" height="60" rx="8" fill="url(#gradRed)" opacity="0.8" />
  <text x="200" y="175" font-family="Arial, sans-serif" font-size="14" fill="#ffffff" text-anchor="middle">重复试错</text>

  <rect x="100" y="220" width="200" height="60" rx="8" fill="url(#gradRed)" opacity="0.8" />
  <text x="200" y="255" font-family="Arial, sans-serif" font-size="14" fill="#ffffff" text-anchor="middle">Token 消耗爆炸</text>

  <!-- Right Side: Mercury -->
  <rect x="450" y="80" width="300" height="280" rx="12" fill="#1e293b" stroke="#10b981" stroke-width="2" />
  <text x="600" y="110" font-family="Arial, sans-serif" font-size="16" font-weight="bold" fill="#10b981" text-anchor="middle">✅ Mercury 自我演化管线</text>

  <!-- Mercury Loop -->
  <circle cx="600" cy="210" r="70" fill="none" stroke="#3b82f6" stroke-width="4" stroke-dasharray="8 4" opacity="0.5"/>
  
  <rect x="525" y="145" width="150" height="40" rx="6" fill="#2563eb" filter="url(#glow)" />
  <text x="600" y="170" font-family="Arial, sans-serif" font-size="14" font-weight="bold" fill="#ffffff" text-anchor="middle">1. 执行与轨迹收集</text>

  <rect x="525" y="235" width="150" height="40" rx="6" fill="#8b5cf6" filter="url(#glow)" />
  <text x="600" y="260" font-family="Arial, sans-serif" font-size="14" font-weight="bold" fill="#ffffff" text-anchor="middle">2. 反思与技能合成</text>
  
  <!-- Arrow -->
  <path d="M 675 190 Q 720 210 675 230" fill="none" stroke="#3b82f6" stroke-width="3" marker-end="url(#arrow)" />

  <text x="600" y="320" font-family="Arial, sans-serif" font-size="14" fill="#10b981" text-anchor="middle" font-weight="bold">持久化技能库</text>
  <rect x="480" y="335" width="240" height="6" rx="3" fill="url(#gradGreen)" />
</svg>
```

---

## 第 2 页：核心架构详解 (Dual-Loop Pipeline)

**设计意图**：展示项目的技术深度，让面试官看到一个完整、规范的管线编排。体现对 LangGraph 状态机及大模型流程控制的理解。

### 📄 文字内容 (PPT 大纲)

**标题：四节点双循环演化架构 (Executor-Evaluator-Synthesizer-Verifier)**

**1. 基础执行层 (Loop 1：业务执行)**
- **Executor**：在 Docker 沙盒内执行并调用工具，完整收集每一步的执行轨迹 (Traces)，遇到错误不终止，自动试错。

**2. 认知反思层 (Loop 2：自我演化)**
- **Evaluator (反思器)**：当检测到任务失败或试错轮次过多（≥4轮）时，摄取 Trace 轨迹进行事后诸葛亮分析，提炼通用的“避坑指南”。
- **Synthesizer (合成器)**：将反思结果结构化，生成 Anthropic Agent Skills 格式文件 (`SKILL.md`)，分离触发词 (Frontmatter) 与详情 (Markdown)，支持按需渐进式加载。

**3. 编排与路由控制**
- 基于 **LangGraph StateGraph** 编排整个 DAG 流程，结合 `SqliteSaver` 持久化状态，实现断点恢复和无损 Trace 记录。
- **Fast/Slow 双模调度**：评估/执行使用 Qwen-Plus (大模型保证深度)，轻量调度/预筛切分至 Qwen-Flash (小模型控制成本)。

### 🖼️ SVG 配图 2 (核心架构图)

*(请将以下代码保存为 `ppt_page2_architecture.svg`)*

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 500">
  <defs>
    <linearGradient id="execGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#2563eb" />
      <stop offset="100%" stop-color="#3b82f6" />
    </linearGradient>
    <linearGradient id="evalGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#7c3aed" />
      <stop offset="100%" stop-color="#8b5cf6" />
    </linearGradient>
    <linearGradient id="verifyGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#059669" />
      <stop offset="100%" stop-color="#10b981" />
    </linearGradient>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
    </marker>
  </defs>

  <rect width="900" height="500" rx="16" fill="transparent" />
  <text x="450" y="40" font-family="Arial, sans-serif" font-size="22" font-weight="bold" fill="#f8fafc" text-anchor="middle">Mercury 架构：双循环自我演化</text>

  <!-- Execution Box -->
  <rect x="50" y="150" width="200" height="120" rx="10" fill="url(#execGrad)" opacity="0.9"/>
  <text x="150" y="195" font-family="Arial, sans-serif" font-size="18" font-weight="bold" fill="#ffffff" text-anchor="middle">1. 执行器 (Executor)</text>
  <text x="150" y="225" font-family="Arial, sans-serif" font-size="13" fill="#e2e8f0" text-anchor="middle">执行任务并收集轨迹</text>

  <!-- Evaluator Box -->
  <rect x="350" y="80" width="200" height="100" rx="10" fill="url(#evalGrad)" opacity="0.9"/>
  <text x="450" y="125" font-family="Arial, sans-serif" font-size="18" font-weight="bold" fill="#ffffff" text-anchor="middle">2. 反思器 (Evaluator)</text>
  <text x="450" y="155" font-family="Arial, sans-serif" font-size="13" fill="#e2e8f0" text-anchor="middle">针对失败或高轮次反思</text>

  <!-- Synthesizer Box -->
  <rect x="350" y="240" width="200" height="100" rx="10" fill="url(#evalGrad)" opacity="0.9"/>
  <text x="450" y="285" font-family="Arial, sans-serif" font-size="18" font-weight="bold" fill="#ffffff" text-anchor="middle">3. 合成器 (Synthesizer)</text>
  <text x="450" y="315" font-family="Arial, sans-serif" font-size="13" fill="#e2e8f0" text-anchor="middle">生成标准化 SKILL.md</text>

  <!-- Verifier Box -->
  <rect x="650" y="150" width="200" height="120" rx="10" fill="url(#verifyGrad)" opacity="0.9"/>
  <text x="750" y="195" font-family="Arial, sans-serif" font-size="18" font-weight="bold" fill="#ffffff" text-anchor="middle">4. 验证器 (Verifier)</text>
  <text x="750" y="225" font-family="Arial, sans-serif" font-size="13" fill="#e2e8f0" text-anchor="middle">三维自动化准入门控</text>

  <!-- Database / Library -->
  <rect x="650" y="340" width="200" height="80" rx="8" fill="#1e293b" stroke="#10b981" stroke-width="2"/>
  <text x="750" y="375" font-family="Arial, sans-serif" font-size="16" font-weight="bold" fill="#10b981" text-anchor="middle">已验证技能库 (Library)</text>
  <text x="750" y="400" font-family="Arial, sans-serif" font-size="12" fill="#94a3b8" text-anchor="middle">支持渐进式按需加载</text>

  <!-- Flow Lines -->
  <!-- Exec to Eval -->
  <path d="M 250 180 C 300 180, 300 130, 350 130" fill="none" stroke="#94a3b8" stroke-width="3" stroke-dasharray="5 5" marker-end="url(#arrow)" />
  <text x="300" y="145" font-family="Arial, sans-serif" font-size="12" fill="#94a3b8" transform="rotate(-35 300 145)">执行轨迹</text>

  <!-- Eval to Synth -->
  <path d="M 450 180 L 450 240" fill="none" stroke="#94a3b8" stroke-width="3" marker-end="url(#arrow)" />
  
  <!-- Synth to Verify -->
  <path d="M 550 290 C 600 290, 600 210, 650 210" fill="none" stroke="#94a3b8" stroke-width="3" marker-end="url(#arrow)" />
  <text x="580" y="270" font-family="Arial, sans-serif" font-size="12" fill="#94a3b8" transform="rotate(-40 580 270)">待验证技能</text>

  <!-- Verify to Library -->
  <path d="M 750 270 L 750 340" fill="none" stroke="#10b981" stroke-width="3" marker-end="url(#arrow)" />
  
  <!-- Library back to Exec -->
  <path d="M 650 380 L 150 380 L 150 270" fill="none" stroke="#10b981" stroke-width="3" stroke-dasharray="4 4" marker-end="url(#arrow)" />
  <text x="400" y="370" font-family="Arial, sans-serif" font-size="12" fill="#10b981">使用 Load Skill 复用经验</text>
</svg>
```

---

## 第 3 页：系统可靠性与 3D 准入自动门控 (Engineering & Security)

**设计意图**：体现工程落地能力和对评测严谨性的追求。避免简历陷入“空谈大模型”，突出用确定性代码控制不确定的 LLM 幻觉。

### 📄 文字内容 (PPT 大纲)

**标题：可靠性基石：沙盒安全与三维确定性门控 (3D Gating)**

**1. 抛弃 LLM-as-Judge，采用代码确定性校验**
- **防“自圆其说”**：使用 Python 代码级的断言校验 (`accept()`) 评估结果，绝不允许大模型“既当运动员又当裁判”，确保评估的 100% 置信度。

**2. 严苛的 3D 自动门控机制 (Verifier)**
- **性能门**：成功率 (Pass@1) 必须达标。
- **经济门**：Token 消耗严卡阈值，必须 **≤ 0.85× 基线**，强制要求新技能能压缩推理上下文，降低成本。
- **效率门**：交互轮次 (Turns) 不高于基线水平。
- **抗污染测试**：注入邻近任务验证**泛化性**；注入异类任务执行**反向触发探测 (Anti-trigger)**，一旦误触发立即拦截，防止知识库污染。

**3. 零信任沙盒 (Zero-Trust Sandbox)**
- 针对 AI 动态生成的 Python 代码构建隔离护城河：
- 采用 Docker SDK 构建 `mercury-sandbox`：强制 `network=none` 断网、资源压测 (512M) 与超时阻断、系统降权 (`cap_drop=ALL`)，彻底杜绝副作用与安全逃逸风险。

### 🖼️ SVG 配图 3 (3D Gating 与沙盒机制)

*(请将以下代码保存为 `ppt_page3_gating.svg`)*

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450">
  <defs>
    <linearGradient id="gateGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#f59e0b" />
      <stop offset="100%" stop-color="#ea580c" />
    </linearGradient>
  </defs>

  <rect width="800" height="450" rx="16" fill="transparent" />
  <text x="400" y="40" font-family="Arial, sans-serif" font-size="22" font-weight="bold" fill="#f8fafc" text-anchor="middle">零信任安全沙盒与三维自动化门控</text>

  <!-- Zero Trust Sandbox Section -->
  <rect x="50" y="80" width="300" height="320" rx="12" fill="#1e293b" stroke="#64748b" stroke-width="2" stroke-dasharray="6 6"/>
  <text x="200" y="120" font-family="Arial, sans-serif" font-size="18" font-weight="bold" fill="#cbd5e1" text-anchor="middle">零信任安全沙盒 (Sandbox)</text>
  
  <rect x="80" y="150" width="240" height="50" rx="6" fill="#334155" />
  <text x="200" y="180" font-family="Arial, sans-serif" font-size="14" fill="#ef4444" text-anchor="middle" font-weight="bold">🚫 network=none (切断网络)</text>

  <rect x="80" y="215" width="240" height="50" rx="6" fill="#334155" />
  <text x="200" y="245" font-family="Arial, sans-serif" font-size="14" fill="#f59e0b" text-anchor="middle" font-weight="bold">⚖️ 内存限制 (512M) &amp; 超时阻断</text>

  <rect x="80" y="280" width="240" height="50" rx="6" fill="#334155" />
  <text x="200" y="310" font-family="Arial, sans-serif" font-size="14" fill="#3b82f6" text-anchor="middle" font-weight="bold">🔒 cap_drop=ALL (剥夺特权)</text>
  
  <text x="200" y="375" font-family="Arial, sans-serif" font-size="12" fill="#94a3b8" text-anchor="middle">AI 生成代码在此安全执行</text>

  <!-- Connection line -->
  <path d="M 350 240 L 420 240" fill="none" stroke="#64748b" stroke-width="4" marker-end="url(#arrow)" />

  <!-- 3D Gating System -->
  <rect x="440" y="80" width="300" height="320" rx="12" fill="#1e293b" stroke="#ea580c" stroke-width="2" />
  <text x="590" y="120" font-family="Arial, sans-serif" font-size="18" font-weight="bold" fill="#f97316" text-anchor="middle">三维自动化准入门控 (Verifier)</text>

  <!-- Condition 1 -->
  <rect x="470" y="150" width="240" height="40" rx="20" fill="url(#gateGrad)" opacity="0.9" />
  <circle cx="490" cy="170" r="10" fill="#ffffff" />
  <path d="M 485 170 L 488 174 L 495 166" fill="none" stroke="#ea580c" stroke-width="2" font-weight="bold"/>
  <text x="515" y="175" font-family="Arial, sans-serif" font-size="14" font-weight="bold" fill="#ffffff">1. 成功率 (Pass@1) 达标</text>

  <!-- Condition 2 -->
  <rect x="470" y="205" width="240" height="40" rx="20" fill="url(#gateGrad)" opacity="0.9" />
  <circle cx="490" cy="225" r="10" fill="#ffffff" />
  <path d="M 485 225 L 488 229 L 495 221" fill="none" stroke="#ea580c" stroke-width="2" font-weight="bold"/>
  <text x="515" y="230" font-family="Arial, sans-serif" font-size="14" font-weight="bold" fill="#ffffff">2. Token 消耗 ≤ 0.85× 基准</text>

  <!-- Condition 3 -->
  <rect x="470" y="260" width="240" height="40" rx="20" fill="url(#gateGrad)" opacity="0.9" />
  <circle cx="490" cy="280" r="10" fill="#ffffff" />
  <path d="M 485 280 L 488 284 L 495 276" fill="none" stroke="#ea580c" stroke-width="2" font-weight="bold"/>
  <text x="515" y="285" font-family="Arial, sans-serif" font-size="14" font-weight="bold" fill="#ffffff">3. 交互轮次 ≤ 基准轮次</text>

  <!-- Anti-Trigger section -->
  <rect x="470" y="320" width="240" height="60" rx="6" fill="#0f172a" stroke="#ef4444" stroke-width="1"/>
  <text x="590" y="340" font-family="Arial, sans-serif" font-size="12" fill="#cbd5e1" text-anchor="middle">知识库防污染测试:</text>
  <text x="590" y="365" font-family="Arial, sans-serif" font-size="12" fill="#ef4444" text-anchor="middle" font-weight="bold">同类泛化探测 &amp; 异类反向触发</text>

</svg>
```

---

### 给你的建议：
1. **SVG 文件生成**：只需将代码块复制并粘贴到任意文本编辑器（如记事本），保存为 `xxx.svg` 文件即可，绝大多数现代的幻灯片软件（如 PowerPoint, Keynote）都原生支持拖拽导入 SVG 并作为矢量图操作。
2. **演讲核心**：演讲时，弱化大模型的通用能力，**强化你的工程编排能力**（特别是 Page 2 的断点恢复，以及 Page 3 的代码校验门槛）。这正是大厂考察候选人是否具备“将玩具变为生产力工具”的关键。
