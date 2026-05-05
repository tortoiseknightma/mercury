# **现代多模态与Harness Engineering驱动下的智能体架构设计与项目蓝图**

在2026年的前沿人工智能工程领域，大型语言模型（LLM）与视觉语言模型（VLM）的核心开发焦点已经发生了一次深刻的范式转移。行业的核心瓶颈已不再是基础模型本身的推理能力，而是如何构建稳定、可控且具备自我修正能力的执行环境与交互标准1。对于具备深度学习、三维高斯泼溅（3DGS）点云压缩压缩背景，且已经掌握LangGraph等多智能体编排框架的算法研究人员而言3，在暑期实习前从零开始构建一个兼具前瞻性与工程落地价值的Agent项目，是展示系统级架构设计能力的绝佳契机。

当前计算资源配置为一台80GB显存的高端GPU（如A100或H100）配合充足的LLM API资源，这在工程实现上消除了本地多模态解析与庞大上下文处理的硬件壁垒。这种充裕的算力允许开发者直接部署当前最先进的纯视觉解析管道（如OmniParser V2），或者在本地运行高度复杂的内存蒸馏与轨迹分析沙盒，而无需妥协于云端API的延迟与隐私限制4。为了在一周左右的工作量内交付一个具有高度可量化效果的生产级项目，架构选型必须摒弃从头训练基础模型的思路，转而采用成熟的“模型+脚手架（Harness）”组合范式。

本研究报告将深度剖析当前Agent开发领域的两大核心技术方向：其一是代表最新架构理念的Harness Engineering与Agent Skills范式；其二是基于纯视觉大模型（Pure-Vision VLM）的图形用户界面（GUI）智能体。针对这两个方向，本报告将提供详细的底层逻辑分析、契合三维与多模态背景的具体项目应用场景构思、成熟的技术栈选型方案，以及一套严谨的、可量化的系统性能评估指标体系。

## **第一核心方向：Harness Engineering与Agent Skills范式架构**

在2024年至2026年期间，AI工程界对模型上下文的控制经历了一场从“提示词工程（Prompt Engineering）”到“上下文工程（Context Engineering）”，最终演进为“Harness Engineering（脚手架工程/约束工程）”的三阶段范式跃迁7。如果说提示词工程解决的是“如何提问”，上下文工程解决的是“提供什么背景信息”，那么Harness Engineering解决的则是“系统如何可靠地运行”1。

Harness Engineering的核心哲学可以被概括为公式：Agent \= Model \+ Harness11。在一个成熟的智能体系统中，除了模型本身的权重之外，所有决定系统稳定交付的组件——包括上下文交付管道、工具接口、规划伪影（Artifacts）、状态机持久化、运行时沙盒、以及拦截错误并强制自我修正的中间件——都属于Harness的范畴11。这种设计的核心在于，不再试图通过自然语言提示来“请求”模型不犯错，而是通过底层的架构设计和代码层面的静态检查（Linters）来“机械地限制”模型无法打破系统边界8。

在Harness Engineering的生态中，由Anthropic首创并开源的“Agent Skills（智能体技能）”范式已成为注入程序化知识的行业绝对标准13。传统的方法倾向于将所有工具的描述和使用规范全部塞入庞大的系统提示词中，这不仅会引发“上下文腐烂（Context Rot）”，还会显著增加Token成本并降低模型的注意力聚焦11。Agent Skills范式通过“渐进式披露（Progressive Disclosure）”机制优雅地解决了这一问题15。

从物理结构上看，一个Agent Skill仅仅是一个标准化的文件目录，其中必须包含一个带有YAML前言（Frontmatter）和Markdown主体指令的SKILL.md文件，并可选择性地附带可执行脚本（scripts/）和参考文档（references/）16。在智能体启动时，Harness层仅仅将所有可用技能的name（名称）和description（触发描述）加载到初始上下文中。只有当智能体的推理循环判定当前任务与某个技能的触发描述高度吻合时，Harness才会动态地将该技能库中的完整指令和附带脚本当作外部工具加载到活动内存中16。这种设计将智能体从一个“无所不知但容易遗忘的单体”转变为一个“能够根据需要动态查阅参考手册的通用处理器”13。

以下表格系统性地对比了Agent开发范式的演进特征，清晰展现了Harness Engineering的代际优势：

| 范式演进阶段 | 核心驱动层 | 解决方案特征 | 故障处理机制 | 适用任务复杂度 |
| :---- | :---- | :---- | :---- | :---- |
| **第一代：Prompt Engineering** (2024) | 文本指令优化 | 依赖少样本提示（Few-shot）和思维链（CoT），将所有规则硬编码在系统提示词中。 | 盲目重试，容易陷入死循环。 | 单轮问答、简单的文本生成与格式转换。 |
| **第二代：Context Engineering** (2025) | 检索与状态聚合 | 引入RAG、向量数据库和简单的API工具调用，模型开始获取外部知识。 | 依赖异常捕获，将报错信息作为字符串重新喂给模型。 | 浅层逻辑的数据查询、具有有限深度的对话助手。 |
| **第三代：Harness Engineering** (2026) | 系统环境与约束架构 | 将Agent Skills、模型上下文协议（MCP）、状态图（StateGraph）和强制代码检查器结合。 | 拦截器（Middleware）阻断非法操作，要求提供修复计划，持久化记忆跨会话纠错。 | 长周期、需要多步骤规划的软件工程与专业系统操作任务。 |

基于上述理论框架，以下构思了两个完全符合Harness Engineering最新范式，且工作量在一周左右、效果高度可量化的项目方案，供简历丰富之用。

### **方案 1A：基于轨迹分析的自治技能合成与自我进化智能体 (Self-Evolving Skill Synthesis Agent)**

**场景构思与设计逻辑：** 尽管Agent Skills标准提供了一种极佳的能力扩展机制，但目前绝大多数的SKILL.md文件仍需要人类工程师（Harness Engineers）手动编写和维护，这不仅耗时，还容易产生人类与大模型之间的认知错位（人类认为清晰的指令，模型可能无法准确遵循）19。本方案提出构建一个“元脚手架（Meta-Harness）”项目，使智能体能够通过观察自己的执行轨迹（Traces），自动提取成功经验或失败教训，进而自主编写、验证并持久化新的SKILL.md包，实现系统能力的闭环自我进化21。

**系统架构与执行流：** 该项目架构采用“执行者-批评者（Actor-Critic）”或双循环控制结构，完全建立在LangGraph的状态机编排之上22：

1. **内部执行循环（The Execution Loop）：** 由一个基础编码智能体构成。当给定一个具有挑战性的任务（例如，清理一个极其脏乱的CSV数据集并进行异常值检测），该智能体会利用现有的通用工具进行尝试25。Harness层会详细记录所有生成的代码、API调用耗时、终端报错信息以及修正过程的轨迹日志（JSONL格式）24。  
2. **反思与合成引擎（The Synthesis Engine）：** 任务完成后（无论成败），一个专门的“反思智能体”会接管轨迹日志。它被赋予的核心任务是寻找模式：如果发现执行智能体在处理某种特定的数据结构时反复犯错并多次重试，反思引擎将自动抽象出一套标准操作程序（SOP）28。随后，它会在系统的skills/目录下自动生成一个符合Anthropic规范的SKILL.md文件，包含精确的触发条件（YAML Frontmatter）和避免踩坑的具体指令17。  
3. **确定性验证门控（Deterministic Verification Gate）：** 新生成的技能不会立即生效。Harness环境会自动在一个隔离的Docker沙盒中启动回归测试，要求执行智能体在仅加载新技能的情况下重做类似任务24。只有当新技能显著降低了Token消耗、减少了工具调用轮数（Turns），并且测试用例100%通过时，该技能才会被正式合并到主技能库中24。

**技术栈映射：**

* **状态管理与编排：** LangGraph (Python)。利用其StateGraph定义多智能体协作图，利用MemorySaver检查点机制（Checkpointers）在生成技能和验证技能之间维持图的持久化状态32。  
* **沙盒与工具层：** 采用Docker SDK构建隔离的执行环境，确保自动生成的代码不会对宿主机造成破坏。  
* **大模型API：** 利用充足的云端API资源（如GPT-4o或Claude 3.5 Sonnet）作为核心推理引擎。

**量化效果证明：** 该项目的核心亮点在于其“自我提升”效果可以用极其直观的工程指标来量化，非常适合在简历中展示数据24。通过构建一个包含10个特定领域任务（如复杂的数据格式转换）的小型测试集，开发者可以对比智能体在“零预置技能（Zero-Shot）”与“经过五轮自我进化后生成了对应技能（Self-Synthesized Skills）”两种状态下的表现。 核心量化指标包括：

* **Token使用率下降百分比（Token Optimization）：** 量化具有针对性SOP的技能库如何减少智能体盲目重试带来的冗余Token消耗35。  
* **一次性通过率（Pass@1 Rate）：** 对比自我演进前后的任务一次性成功率37。根据SkillsBench的评估基准，优秀的技能库能将平均通过率提升16个百分点以上39。

### **方案 1B：基于MCP与LangGraph的企业级数据中枢智能体 (MCP-Driven Enterprise Data Router)**

**场景构思与设计逻辑：** 随着模型上下文协议（Model Context Protocol, MCP）在2025年至2026年期间被广泛采纳，它被誉为AI时代的“USB-C接口”41。MCP将智能体的“大脑（推理逻辑）”与“双手（工具与数据源）”彻底解耦：它提供了一种标准化的客户端-服务器架构，使得LLM可以无缝连接到本地文件系统、PostgreSQL数据库、GitHub仓库或外部SaaS平台，而无需编写任何定制化的API集成代码14。本方案建议基于MCP构建一个高度安全且被严格约束的企业级数据路由器。

传统的数据查询智能体往往存在严重的设计缺陷：它们倾向于生成低效的SQL语句将海量数据拉取到内存中，然后再试图利用Python甚至LLM自身的上下文去处理这些数据，这在大规模工程中是灾难性的45。本项目的逻辑在于，将MCP作为底层数据访问管道，同时利用Harness层的中间件和Agent Skills来“强制约束”智能体的数据处理策略，迫使其像资深数据工程师一样，将计算下推（Push-down compute）到数据库层45。

**系统架构与执行流：**

1. **基础设施层（MCP Servers）：** 在80GB的GPU服务器或本地环境中，一键部署三个开源MCP服务器实例：一个用于连接本地的模拟企业数据库（如PostgreSQL MCP），一个用于读取代码仓库（GitHub MCP），一个用于访问本地的日志文件（File System MCP）43。  
2. **约束与控制平面（The Harness Control Plane）：** 使用LangGraph构建智能体的决策图。在这里，开发者需要设计拦截器中间件（Middleware hooks）。当LLM通过MCP发起数据请求前，中间件会校验其查询逻辑47。  
3. **平台感知型技能池（Platform-Aware Skills）：** 编写对应的SKILL.md文件。例如，编写一个名为database-optimization-skill的库，在指令中明确规定：“当需要统计分析时，严禁使用SELECT *，必须使用原生SQL的聚合函数（如GROUP BY），仅将最终统计结果返回给上下文”45。通过渐进式披露机制，这些强制性规范会在检测到数据库操作时被激活嵌入。

**量化效果证明：**

在简历中，这种架构体现了对生产级AI系统深刻的理解。可量化的指标包括：

* **上下文负载优化（Context Payload Reduction）：** 记录通过聚合计算下推和MCP资源管理，系统的平均交互Payload大小减少了多少兆字节（MB），这直接关联到延迟（Latency）和Token开销36。  
* **工具调用准确率（Tool Selection Accuracy）：** 在一个包含20个查询任务的测试集中，测量智能体选择正确MCP工具并传递合法JSON Schema参数的成功率35。

## **第二核心方向：基于纯视觉交互的图形用户界面智能体 (Pure-Vision GUI Agent)**

如果说Harness Engineering旨在解决API和代码层面的深度逻辑问题，那么GUI智能体则是赋予AI“数字躯体”，使其能够像人类一样操作任意软件界面的关键。在过去，GUI自动化的主流技术栈依赖于提取网页的文档对象模型（DOM）树或操作系统的无障碍树（Accessibility Trees）51。这种方式在现代工程中暴露出极其脆弱的短板：一旦网页的CSS类名变更、DOM结构混淆，或者面对完全通过Canvas渲染的应用、远程桌面协议以及专业的三维建模软件时，DOM树便会完全失效或根本不存在52。

到2026年，行业技术栈已经决定性地转向了“纯视觉对齐（Pure-Vision Grounding）”范式6。在此范式下，智能体不再依赖底层的代码结构，而是直接读取屏幕的像素级截图。然而，通用多模态大模型（如GPT-4V或普通的开源VLM）在直接输出高分辨率屏幕上微小图标的精确坐标时，存在严重的“空间幻觉”和精度不足问题5。

为弥补这一鸿沟，微软研究院开源的 **OmniParser V2** 成为了当前最成熟、最受瞩目的屏幕解析技术栈55。它并不是一个端到端的决策模型，而是一个专门负责“视觉解析与数字化”的轻量级感知引擎。OmniParser V2采用了极其精妙的级联架构：

1. **交互区域检测模块（Interactable Region Detection）：** 基于微调的YOLOv8模型，专门用于在屏幕截图中找出所有具备交互可能性的区域（如按钮、文本框、滑动条、图标），并为它们绘制边界框（Bounding Box）和分配数字ID4。  
2. **功能语义描述模块（Functional Semantic Captioning）：** 基于轻量级的Florence-2基础模型，对上述YOLOv8裁剪出来的每一个小图像块进行语义描述（例如识别出一个软盘图标，并描述为“保存按钮”）4。

通过这一管道，OmniParser V2将原始的屏幕像素转换成了对大模型极度友好的“结构化表达”：一张覆盖了数字ID的标注图，以及一份包含所有ID对应语义的JSON字典6。此时，后台的推理LLM只需阅读JSON和带有ID的截图，输出简单的JSON指令（如 {"action": "click", "target\_id": 42}），即可由底层的执行脚本计算出ID 42的中心坐标并完成点击23。

开发者拥有一台80GB显存的GPU，这是执行此方向项目的巨大护城河。80GB的显存足以在本地以极低的延迟并发运行OmniParser V2的解析端服务，甚至还可以同时承载一个开源的VLM（如Qwen2.5-VL-7B/72B）作为规划模型，实现完全本地化、隐私安全且超低延迟的“感知-决策-执行”闭环58。

### **方案 2A：三维设计软件的自动化视觉操作专家 (Autonomous 3D Software Operator)**

**场景构思与设计逻辑：** 结合开发者在简历3中体现的“三维高斯泼溅（3DGS）”和“智能点云压缩”的深厚学术背景，构建一个能够自主操作复杂三维专业软件（如Blender、MeshLab或CloudCompare）的视觉智能体，是一个极具个性化且极具技术深度的方向。

专业的3D建模和渲染软件是纯视觉GUI研究的终极测试场。这类软件通常具有极高的分辨率（4K起步）、密集的浮动面板、海量的无文字图标（Icon-only toolbars）以及极深的菜单层级60。一般的DOM抓取技术在此类OpenGL或底层C++渲染的UI面前完全无效60。本项目旨在构建一个视觉管家，它能够接收自然语言指令（例如：“导入桌面上的点云模型文件，执行一次基于统计的异常点去除滤波，将网格面数减半，然后导出为压缩的PLY格式”），并完全通过视觉识别和鼠标点击来自动操作MeshLab或Blender完成这一系列复杂的管道任务63。

**系统架构与执行流：**

1. **感知与解析层（Perception Engine）：** 利用80GB GPU的算力优势，在本地通过Docker部署OmniParser V2和OmniTool服务5。环境运行时捕获当前Windows或Linux屏幕的截图，并将其送入OmniParser进行解析5。对于高分辨率下的微小图标，YOLOv8的高清检测能力配合Florence-2的语义解释，能够精准标记出诸如“Decimate（减面）”或“Export（导出）”等工具图标55。  
2. **空间聚焦与缩放机制（Visual Test-Time Scaling）：** 考虑到三维软件UI的复杂性，在Harness中实现一种称为“RegionFocus（区域聚焦）”的测试时缩放技术62。当规划模型面对过度拥挤的界面（例如Blender的属性面板），对某个目标ID的信心度较低时，系统会自动框选该区域，截取局部高分辨率图像再次送入OmniParser进行二次细粒度解析，以显著降低幻觉并提高点击精度66。  
3. **编排与状态流（Stateful Orchestration）：** 依然采用LangGraph构建循环状态机23。状态节点定义为：\[获取屏幕\] \-\> \[OmniParser解析\] \-\> \-\> \[PyAutoGUI/pywin32执行键鼠操作\] \-\> \[判断是否完成\]23。为了防止操作失控，LangGraph的边（Edges）上必须设置最大循环次数阈值（如max\_steps=15）。

**量化效果证明：** 针对此类专业环境的GUI评估，必须参考学术界最新的 **ScreenSpot-Pro** 基准测试方法，该基准专门针对高分辨率、复杂专业软件界面（包括AutoCAD、Photoshop、Blender等）的识别与操作60。

* **视觉对齐精度（Grounding Accuracy / Pass@1）：** 记录智能体在10个设定的三维软件操作任务中，第一次点击就能准确命中目标UI元素的概率。在专业软件上，常规VLM的准确率不到20%，而结合OmniParser V2与缩放机制的系统有望将此指标提升至40%至50%区间60。  
* **端到端任务完成率（End-to-End Task Success Rate）：** 衡量智能体无需人为干预，完整走完“导入-处理-导出”等多步骤工作流的成功率68。

### **方案 2B：具有自愈能力的跨平台UI自动化测试智能体 (Self-Healing UI QA Agent)**

**场景构思与设计逻辑：** 在现代软件工程中，质量保证（QA）和UI自动化测试是维护成本极高的环节。传统的Selenium或Cypress测试脚本严重依赖于CSS选择器和Xpath70。只要前端开发人员重构了页面布局或更改了类名（这在现代React/Vue等前端框架中极为常见），自动化脚本就会瞬间崩溃，需要耗费大量人力进行维护更新71。

本项目旨在利用视觉智能体彻底颠覆这一痛点，构建一个不需要关心底层代码，纯粹依靠“看”来验证软件逻辑的自愈型QA自动化系统。开发者只需提供自然语言形式的用户故事（User Story，例如：“在登录界面输入格式错误的邮箱，点击提交后，验证屏幕上方是否出现红色的'邮箱格式错误'提示框”）70。智能体将自主导航、填写表单并进行视觉断言（Visual Assertions）。

**系统架构与执行流：**

1. **需求转化与路径规划（Planning Node）：** 接收自然语言的测试需求，将其拆解为原子级的动作序列（例如：1.定位输入框并聚焦；2.键入错误字符串；3.识别提交按钮并点击；4.观察结果）70。  
2. **视觉交互闭环（Vision-Action Loop）：** 每次动作前，捕获屏幕并调用本地部署的OmniParser V2解析出所有UI元素的ID。LLM规划器根据测试序列的当前步骤，选择相应的ID并输出具体的执行动作（Click、Type、Scroll等）23。  
3. **视觉断言引擎（Visual Assertion Engine）：** 当所有操作步骤执行完毕后，执行最终的验证环节。此时不依赖传统的DOM树比对，而是将包含结果界面的截图直接发送给大语言视觉模型（VLM）。VLM作为视觉裁判（Visual Judge），通过纯粹的视觉推理来评估屏幕上的视觉状态（例如颜色的变化、弹出框的样式）是否符合测试预期的成功标准11。

**量化效果证明：**

这是在企业级实习面试中极具说服力的一项数据展示：

* **系统抗毁性/自愈率（Resiliency / Recovery Rate）：** 设置对照组实验。编写一个传统的Selenium脚本和一个基于OmniParser的视觉智能体脚本来执行相同的登录流程。随后，在前端代码中故意修改所有相关的CSS类名和DOM结构层级。传统脚本的通过率将暴跌至0%，而视觉智能体由于直接理解“登录”按钮的视觉语义，其成功执行率（Task Completion Rate）应依然保持在极高的水平（预期90%以上）12。  
* **动作延迟开销（Latency per Action）：** 由于OmniParser V2优化了图像切片的大小，其推理延迟比上一代下降了60%5。利用80GB GPU全本地化推理，记录执行一次动作的端到端延迟（从截图到执行鼠标点击），展现极致的性能优化36。

## **严谨的智能体评估与度量体系 (Agent Evaluation & Metrics Framework)**

对于一份目标是算法和Agent方向暑期实习的简历，仅仅描述“做了一个什么系统”是远远不够的。在2026年的工业界，如何科学、严谨地评估一个Agent系统，其重要性甚至等同于开发Agent本身74。大多数初学者常犯的错误是仅仅统计一个单一的“成功/失败”结果。然而，企业级开发要求将评估分为**轨迹指标（Trajectory Metrics）**和**结果指标（Outcome Metrics）**两个维度75。

本项目的评估设计将全面遵循业界前沿的 **Agent GPA (Goal, Plan, Action)** 评估框架，确保所有的优化都有数据支撑76。

### **1. 行为与执行层指标 (Action Layer Metrics)**

* **工具调用准确率 (Tool Correctness):** 这是评估Harness有效性最直接的底层指标。它衡量在所有模型发起的工具（或Agent Skills、MCP端点）调用中，传递的参数完全符合预设JSON Schema定义的比例35。通过Harness工程中的中间件强校验，这一指标应逼近100%。  
  ![][image1]  
* **步骤效率与Token消耗 (Step Efficiency & Token Usage):** 一个没有良好Harness约束的智能体往往会在错误中反复徘徊（即陷入无效的推理-行动死循环），消耗惊人的Token和时间35。通过记录从任务开始到结束的总推理步数（Turns/Steps）以及消耗的总Token数量，可以直观地反映出渐进式披露的Skills库如何有效地缩小了模型的搜索空间并提高了执行效率50。

### **2. 规划与目标层指标 (Plan & Goal Layer Metrics)**

* **归一化收益评估 (Normalized Gain \- ![][image2]):** 借鉴学术界 *SkillsBench* 论文的严谨评估方法37。为了证明“构建Agent Skills库”或“实施Harness约束”这一架构设计的有效性，需要测量系统在引入这些设计前后的通过率变化。  
  ![][image3]  
  其中，![][image4]代表在给定测试集上的Pass@1一次性成功率37。这一公式科学地反映了系统优化向着完美性能（100%）逼近的比例，避免了基数不同带来的评估偏差39。  
* **任务端到端完成率 (Task Completion Rate):** 无论是GUI自动点击还是数据库查询，这是最终的商业价值指标。衡量智能体能够在无需人工介入（Escalation Rate \= 0%）的情况下独立完成复杂多步任务的百分比68。对于生产级智能体，该指标的工业基准基线通常设定在85%以上34。

在简历中，建议以Markdown表格的精炼形式展现优化前后的对比数据。例如，可以构建类似下表的性能对比矩阵：

| 评估维度 | 指标名称 (Metric) | Baseline (纯大模型提示词驱动) | Optimized (LangGraph Harness / OmniParser驱动) | 提升幅度 |
| :---- | :---- | :---- | :---- | :---- |
| **底层执行** | 工具调用准确率 | 62.4% (频繁出现参数幻觉) | **98.5%** (受制于JSON Schema与沙盒检验) | \+36.1% |
| **系统效率** | 平均Token消耗/任务 | 14,500 Tokens | **3,200 Tokens** (由于渐进式技能加载与焦点缩放) | \-77.9% |
| **视觉对齐** | GUI Grounding精度 | 18.9% (复杂三维软件界面) | **48.1%** (YOLOv8+Florence-2细粒度解析) | \+29.2% |
| **商业目标** | 端到端任务成功率 | 35.0% | **88.4%** | \+53.4% |

## **项目工程实施计划：一周冲刺指南 (The One-Week Sprint)**

要在紧凑的一周时间内完成从架构设计到量化评估的全流程，必须避免陷入重复造轮子（如从头手写通信协议或视觉模型）的泥潭。核心精力应集中在“组装成熟组件”、“设计Harness约束”和“提取评估指标”上。

### **阶段一：基础设施构建与环境调通 (第1-2天)**

* **基础环境隔离：** 使用Conda或UV创建干净的Python 3.10+虚拟环境。  
* **框架引入：**  
  * 方向1 (Harness)：初始化LangGraph项目结构，配置基于SQLite的MemorySaver以实现状态检查点记录26。通过langchain-mcp-adapters库接入至少两个开源的MCP服务器作为测试数据源78。  
  * 方向2 (GUI)：从GitHub克隆微软OmniParser官方仓库。利用80GB显存的充裕资源，将YOLOv8交互区域检测模型与Florence-2功能描述模型的权重完整加载到显存中，并暴露出FastAPI推理端口57。编写基于PyAutoGUI和pywin32的底层动作执行脚本，并封装为工具23。

### **阶段二：核心认知流与脚手架逻辑开发 (第3-4天)**

* **状态图编排（Graph Construction）：** 利用LangGraph构建循环工作流。设计节点：如Reasoning\_Node（思考与规划）、Action\_Node（工具执行）、Verification\_Node（断言检验）23。利用条件边（Conditional Edges）控制循环的跳出逻辑。  
* **Harness与技能系统实现（Harness Implementation）：**  
  * 方向1：实现技能系统的“渐进式披露”。编写一段逻辑，在Agent启动时仅将SKILL.md文件中的YAML Frontmatter加载到System Prompt中，只有当正则匹配到触发词时，才利用文件I/O读取完整的Markdown指令体注入上下文15。  
  * 方向2：实现视觉智能体的“区域聚焦（RegionFocus）”重试机制。如果在一次Action\_Node的输出中，模型对屏幕某个按钮的空间坐标信心不足，则在图的边上触发回调机制，命令OmniParser对特定象限进行放大截屏并重新解析62。

### **阶段三：数据集构建与自动化量化评估 (第5-6天)**

* **测试基准构建：** 定义一个包含10到20个测试用例的本地微型基准（Mini-Benchmark）。这些任务必须具有明确的验收标准（Acceptance Criteria）。  
* **遥测与可观测性（Observability）：** 利用LangSmith或本地的自定义Logger，详细记录每一次状态转换、工具调用的入参出参、端到端响应时间以及消耗的Token数81。  
* **裁判模型脚本（LLM-as-a-Judge）：** 编写一套自动化评估流水线，利用高性能的大模型（如GPT-4o）作为裁判，依据Agent GPA框架（Goal, Plan, Action）对记录的运行轨迹（Traces）进行打分和分类76。自动计算并输出Pass@1通过率、工具调用准确率和Normalized Gain等核心指标。

### **阶段四：架构复盘与文档沉淀 (第7天)**

* **架构图绘制：** 输出高质量的系统架构流图，清晰标明LangGraph、MCP协议/OmniParser、LLM端点与执行沙盒之间的边界与通信协议。  
* **数据可视化：** 整理第三阶段收集到的量化数据，生成诸如“应用Harness约束前后的Token消耗对比折线图”、“引入OmniParser解析前后的点击精度混淆矩阵”等可视化图表，为简历中的项目描述和后续的面试展示提供最具说服力的技术论据。

## **结语**

在构建新一代人工智能应用时，原始的大模型算力已逐渐成为一种标准化的“基础设施（Utility）”，真正的工程护城河在于如何通过严密的架构设计将这些算力转化为可靠、精准且可复用的生产力。本报告所深度剖析的Harness Engineering理念及其外延的Agent Skills框架，旨在通过坚实的系统约束、状态管理与反馈闭环，彻底解决通用大模型在执行长周期复杂任务时的失控与退化问题；而基于OmniParser V2等前沿纯视觉解析技术的GUI智能体架构，则抛弃了依赖底层代码结构的脆弱传统路径，使AI真正获得了近乎人类视角的泛化交互能力。

无论最终选择深耕于自我进化的技能合成引擎，还是专注于驾驭复杂三维软件的纯视觉桌面助手，这两个方向的设计蓝图均完全契合当前业界从“多模态理解”向“多模态自主操作”跨越的最前沿趋势。依托LangGraph等成熟且健壮的状态图编排技术，辅以严谨的Agent GPA可量化评估体系，开发者不仅能在一周的时间预算内交付一个架构清晰、逻辑闭环的高质量工程项目，更能借此全面展示自身在系统思维、前沿技术栈整合以及数据驱动优化方面的深厚专业素养与工程化落地能力。

## **方案1A实施路线**
选择方案 1A（基于轨迹分析的自治技能合成与自我进化智能体）是一个非常出色的决定。这个方向完美契合了当前 AI 工程界最前沿的 **Harness Engineering** 和 **Agent Skills** 范式，且“自我进化”的闭环逻辑在面试中极具技术深度和故事性。

为了在一周（约7天）内高效且高质量地交付这个项目，我们需要对架构进行收敛，将重点放在**“执行-反思-提炼-验证”**的核心循环上。以下是为你量身定制的详细执行计划与架构细化方案。

### 核心架构设计 (The Self-Evolving Loop)

参考前沿的 Trace2Skill 和 ClawTrace 等研究，我们将系统的自我进化提炼为一条数据流管道：

1. **Executor（执行者）**：尝试解决给定的代码或数据处理任务，无论成功失败，都生成一份包含 Token 消耗、报错和 API 调用步骤的执行轨迹日志（TraceCard）。

2. **Evaluator（反思者）**：分析 TraceCard，找出导致高成本的冗余步骤（Prune 策略），保留成功的核心操作（Preserve 策略），或修复失败的逻辑（Repair 策略）。

3. **Synthesizer（合成者）**：将反思结果打包，自动生成符合规范的 `SKILL.md` 文件（包含触发条件和具体指令）\[1\]。

4. **Verifier（验证门控）**：在一个隔离的沙盒中，仅加载新生成的技能重新执行任务，若 $Pass@1$（一次性通过率）提升或 Token 消耗下降，则正式将该技能合并到技能库中。

\---

### 一周详细执行计划 (7-Day Sprint Plan)

#### Day 1：基础设施搭建与基线执行器 (Infrastructure & Base Executor)

* **目标**：搭建基础的 LangGraph 循环，实现一个“无技能”状态下的基线智能体。

* **具体任务**：

  1. 使用 Python 初始化项目，安装 `langgraph`、`langchain` 等核心依赖。

  2. 定义 `AgentState`，包含 `messages`、`current\_task`、`scratchpad`（暂存区）等字段。

  3. 构建 **Executor 节点**：接入你充足的 LLM API（如 GPT-4o 或 Claude 3.5 Sonnet），赋予其基础的 Python 执行工具（可通过简单的 Docker 容器封装或 `subprocess` 限制执行以防主机风险）。

  4. 收集一个包含 15-20 个特定领域任务的微型数据集（建议选择**复杂 CSV 数据清洗**或**特定格式的日志解析**，这类任务容易出现反复试错）。

#### Day 2：轨迹遥测与日志系统 (Trajectory Telemetry & TraceCards)

* **目标**：让智能体的每一步执行都变得“可观测”，为后续的自我反思提供数据。

* **具体任务**：

  1. 在 LangGraph 的节点流转中，编写一个中间件或监听器，记录每一次 Tool Call（工具调用）的输入、输出、耗时和报错信息。

  2. 任务结束后，将这些数据汇总生成一份 `TraceCard`（YAML 或 JSON 格式）。

  3. `TraceCard` 中必须明确包含：任务目标、调用步骤序列、最终是否成功、以及累计消耗的 Token 数量。

#### Day 3：反思与技能提炼引擎 (Reflection & Distillation Engine)

* **目标**：开发“大脑”部分，使系统能够从 `TraceCard` 中提取标准操作程序 (SOP)。

* **具体任务**：

  1. 新增 **Evaluator 智能体**。将其系统提示词设定为：“你是一个高级 AI 架构师，请分析这份执行轨迹，指出执行者在哪里进行了无效的尝试（如调用了不存在的库函数、正则匹配错误），并总结出一条避免这些错误的最佳实践”。

  2. 新增 **Synthesizer 智能体**。将 Evaluator 的结论转化为标准化的技能文件夹结构：

     skills/my-new-skill/

     ├── SKILL.md

  3. 确保生成的 `SKILL.md` 包含 YAML 前言（`name` 和 `description`，用于动态触发）以及 Markdown 格式的核心指令\[2, 1\]。

#### Day 4：技能的动态加载机制 (Progressive Disclosure)

* **目标**：实现 Harness 的核心特性——按需加载，避免上下文污染。

* **具体任务**：

  1. 修改第一天编写的基线 Executor 的启动逻辑。

  2. 在启动时，系统仅扫描 `skills/` 目录，并将所有技能的 `name` 和 `description` 注入系统提示词（这被称为渐进式披露的“发现阶段”）\[2\]。

  3. 为 Executor 提供一个 `load\_skill` 工具。当 LLM 判断当前任务匹配某个技能的 description 时，它会调用此工具，系统随之读取对应的 `SKILL.md` 内容并放入当前上下文（“激活与执行阶段”）\[2\]。

#### Day 5：确定性验证与沙盒回放 (Verification Gate)

* **目标**：构建“验证门控”，确保自我合成的技能确实有效，防止技能库退化。

* **具体任务**：

  1. 编写自动化验证脚本：当新技能生成后，重置 Executor 的记忆，强制其只携带新技能重新挑战原有任务。

  2. 对比执行数据：如果新一轮的 Token 消耗低于历史记录，且顺利得出正确结果，则将技能状态标记为 `verified=True`，正式存入持久化技能库；否则丢弃（或触发重新提炼）\[3\]。

#### Day 6：量化实验与数据收集 (Evaluation & Metrics)

* **目标**：为你的简历跑出具有说服力的对比数据。

* **具体任务**：

  1. 运行你的 20 个测试用例，记录在 **No Skills（零预置技能）** 状态下的表现。

  2. 开启 Self-Evolving 循环，让系统自动做题并生成技能。

  3. 再次运行相同的测试集，记录在 **Self-Generated Skills（自我生成技能）** 状态下的表现。

  4. 重点计算并保存以下指标：

     * **Pass@1 (一次性通过率)**：无需人工干预且一次得出正确结果的比例。

     * **Token 优化率**：计算有了技能库之后，平均每个任务节省的 Token 百分比。

     * **Normalized Gain (归一化收益 $g$)**：衡量技能库如何缩小当前成功率与 100% 完美成功率之间的差距。

#### Day 7：项目封装与简历输出 (Documentation & Resume Prep)

* **目标**：将工程成果转化为可以直接在面试中展示的亮点。

* **具体任务**：

  1. 清理代码，添加注释，规范化 `README.md`。

  2. 使用 Mermaid 或 Draw.io 绘制系统的双循环状态机架构图（Execution Loop & Synthesis Loop）。

  3. **提炼简历 Bullet Points（参考写法）**：

     * *“主导设计并实现了一个基于 LangGraph 的自我进化智能体系统，引入 TraceCard 机制对 Agent 执行轨迹进行自动化观测与提炼。”*

     * *“实现了符合业界标准的渐进式 Agent Skills 动态加载框架，将冗余 Token 消耗降低了 XX%，显著缓解了长上下文遗忘问题。”*

     * *“设计了基于隔离沙盒的确定性验证门控，使系统在 20 个复杂数据处理任务上的 Pass@1 通过率从 XX% 自主提升至 XX%。”*

### 给你的额外建议

在实施过程中，**不要一开始就追求太复杂的测试任务**。聚焦于诸如“将非标准的 JSON 字符串清洗并转换为特定的 CSV 格式”这类任务。这类任务对基础 LLM 来说容易在正则表达式或键值对提取上犯错并产生大量重试循环，最能明显体现出“反思错误 \-\> 生成专属 Skill \-\> 下次一次性通过”的系统价值。

#### **引用的著作**

1. From Prompt Engineering to Harness Engineering: The Layer That Makes AI Agents Actually Work | by Steven Cen | Mar, 2026 | Medium, 访问时间为 五月 1, 2026， [https://medium.com/@cenrunzhe/from-prompt-engineering-to-harness-engineering-the-layer-that-makes-ai-agents-actually-work-466fe0489fbe](https://medium.com/@cenrunzhe/from-prompt-engineering-to-harness-engineering-the-layer-that-makes-ai-agents-actually-work-466fe0489fbe)  
2. 8 best open-source AI agent frameworks on GitHub in 2026 | AY Automate, 访问时间为 五月 1, 2026， [https://www.ayautomate.com/blog/best-open-source-ai-agent-frameworks](https://www.ayautomate.com/blog/best-open-source-ai-agent-frameworks)  
3. 马文熙-南京大学-硕士-中文简历A-20260415.pdf  
4. OmniParser for Pure Vision-Based GUI Agent | Microsoft Research, 访问时间为 五月 1, 2026， [https://www.microsoft.com/en-us/research/wp-content/uploads/2025/01/WEF-2025\_Leave-Behind\_OmniParser-for-Pure-Vision-Based-GUI-Agent.pdf](https://www.microsoft.com/en-us/research/wp-content/uploads/2025/01/WEF-2025_Leave-Behind_OmniParser-for-Pure-Vision-Based-GUI-Agent.pdf)  
5. OmniParser V2: Turning Any LLM into a Computer Use Agent \- Microsoft Research, 访问时间为 五月 1, 2026， [https://www.microsoft.com/en-us/research/articles/omniparser-v2-turning-any-llm-into-a-computer-use-agent/](https://www.microsoft.com/en-us/research/articles/omniparser-v2-turning-any-llm-into-a-computer-use-agent/)  
6. OmniParser for Pure Vision Based GUI Agent, 访问时间为 五月 1, 2026， [https://microsoft.github.io/OmniParser/](https://microsoft.github.io/OmniParser/)  
7. From Prompt Engineering to Harness Engineering | by Ruiwen (Rei-1) \- Level Up Coding, 访问时间为 五月 1, 2026， [https://levelup.gitconnected.com/from-prompt-engineering-to-harness-engineering-0be55b7d32b7](https://levelup.gitconnected.com/from-prompt-engineering-to-harness-engineering-0be55b7d32b7)  
8. The Third Evolution: Why Harness Engineering Replaced Prompting in 2026 | Epsilla Blog, 访问时间为 五月 1, 2026， [https://www.epsilla.com/blogs/harness-engineering-evolution-prompt-context-autonomous-agents](https://www.epsilla.com/blogs/harness-engineering-evolution-prompt-context-autonomous-agents)  
9. Agent Harness for Large Language Model Agents: A Survey\[v1\] | Preprints.org, 访问时间为 五月 1, 2026， [https://www.preprints.org/manuscript/202604.0428/v1](https://www.preprints.org/manuscript/202604.0428/v1)  
10. Harness Engineering: The Missing Layer Behind AI Agents \- Louis-François Bouchard, 访问时间为 五月 1, 2026， [https://www.louisbouchard.ai/harness-engineering/](https://www.louisbouchard.ai/harness-engineering/)  
11. The Anatomy of an Agent Harness \- LangChain, 访问时间为 五月 1, 2026， [https://www.langchain.com/blog/the-anatomy-of-an-agent-harness](https://www.langchain.com/blog/the-anatomy-of-an-agent-harness)  
12. ai-boost/awesome-harness-engineering \- GitHub, 访问时间为 五月 1, 2026， [https://github.com/ai-boost/awesome-harness-engineering](https://github.com/ai-boost/awesome-harness-engineering)  
13. Agent Skills :Standard for Smarter AI | by Plaban Nayak \- Medium, 访问时间为 五月 1, 2026， [https://nayakpplaban.medium.com/agent-skills-standard-for-smarter-ai-bde76ea61c13](https://nayakpplaban.medium.com/agent-skills-standard-for-smarter-ai-bde76ea61c13)  
14. The Agentic Stack: A Deep Dive into Agent Skills vs. Model Context Protocol (MCP) | by Jiten Oswal | CodeToDeploy, 访问时间为 五月 1, 2026， [https://medium.com/codetodeploy/the-agentic-stack-a-deep-dive-into-agent-skills-vs-model-context-protocol-mcp-9f378ce0db14](https://medium.com/codetodeploy/the-agentic-stack-a-deep-dive-into-agent-skills-vs-model-context-protocol-mcp-9f378ce0db14)  
15. Agent Skills – Codex | OpenAI Developers, 访问时间为 五月 1, 2026， [https://developers.openai.com/codex/skills](https://developers.openai.com/codex/skills)  
16. Agent Skills Overview \- Agent Skills, 访问时间为 五月 1, 2026， [https://agentskills.io/home](https://agentskills.io/home)  
17. The Complete Guide to Building Skills for Claude | Anthropic, 访问时间为 五月 1, 2026， [https://resources.anthropic.com/hubfs/The-Complete-Guide-to-Building-Skill-for-Claude.pdf](https://resources.anthropic.com/hubfs/The-Complete-Guide-to-Building-Skill-for-Claude.pdf)  
18. 10 Must-Have Skills for Claude (and Any Coding Agent) in 2026 | by unicodeveloper | Mar, 2026, 访问时间为 五月 1, 2026， [https://medium.com/@unicodeveloper/10-must-have-skills-for-claude-and-any-coding-agent-in-2026-b5451b013051](https://medium.com/@unicodeveloper/10-must-have-skills-for-claude-and-any-coding-agent-in-2026-b5451b013051)  
19. SkillsBench: Benchmarking how well agent skills work across diverse tasks | Hacker News, 访问时间为 五月 1, 2026， [https://news.ycombinator.com/item?id=47040430](https://news.ycombinator.com/item?id=47040430)  
20. EvoSkills: Self-Evolving Agent Skills via Co-Evolutionary Verification \- arXiv, 访问时间为 五月 1, 2026， [https://arxiv.org/html/2604.01687v1](https://arxiv.org/html/2604.01687v1)  
21. CoEvoSkills: Self-Evolving Agent Skills via Co-Evolutionary Verification \- arXiv, 访问时间为 五月 1, 2026， [https://arxiv.org/html/2604.01687v2](https://arxiv.org/html/2604.01687v2)  
22. Reinforcement Learning for Self-Improving Agent with Skill Library \- arXiv, 访问时间为 五月 1, 2026， [https://arxiv.org/html/2512.17102v2](https://arxiv.org/html/2512.17102v2)  
23. nabhpatodi10/Computer-Use-Agent \- GitHub, 访问时间为 五月 1, 2026， [https://github.com/nabhpatodi10/Computer-Use-Agent](https://github.com/nabhpatodi10/Computer-Use-Agent)  
24. I spent months trying to make my agents recursively self-improve so they can run more autonomously. Here's what actually worked : r/AI\_Agents \- Reddit, 访问时间为 五月 1, 2026， [https://www.reddit.com/r/AI\_Agents/comments/1s63az9/i\_spent\_months\_trying\_to\_make\_my\_agents/](https://www.reddit.com/r/AI_Agents/comments/1s63az9/i_spent_months_trying_to_make_my_agents/)  
25. How to Build a Self-Improving AI Agent That Learns From Its Own Mistakes | MindStudio, 访问时间为 五月 1, 2026， [https://www.mindstudio.ai/blog/self-improving-ai-agent-feedback-loop](https://www.mindstudio.ai/blog/self-improving-ai-agent-feedback-loop)  
26. Building Your First AI Agent in 2025: A Beginner's Guide to Google's Agent Development Kit, 访问时间为 五月 1, 2026， [https://medium.com/@Micheal-Lanham/building-your-first-ai-agent-in-2025-a-beginners-guide-to-google-s-agent-development-kit-2d9077667b39](https://medium.com/@Micheal-Lanham/building-your-first-ai-agent-in-2025-a-beginners-guide-to-google-s-agent-development-kit-2d9077667b39)  
27. Evaluating AI Agent Skills \- Langfuse, 访问时间为 五月 1, 2026， [https://langfuse.com/blog/2026-02-26-evaluate-ai-agent-skills](https://langfuse.com/blog/2026-02-26-evaluate-ai-agent-skills)  
28. GenAI\_Agents/all\_agents\_tutorials/self\_improving\_agent.ipynb at main \- GitHub, 访问时间为 五月 1, 2026， [https://github.com/NirDiamant/GenAI\_Agents/blob/main/all\_agents\_tutorials/self\_improving\_agent.ipynb](https://github.com/NirDiamant/GenAI_Agents/blob/main/all_agents_tutorials/self_improving_agent.ipynb)  
29. \[2512.17102\] Reinforcement Learning for Self-Improving Agent with Skill Library \- arXiv, 访问时间为 五月 1, 2026， [https://arxiv.org/abs/2512.17102](https://arxiv.org/abs/2512.17102)  
30. Agent Skills \- Claude API Docs, 访问时间为 五月 1, 2026， [https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)  
31. The open guide to Harness Engineering — concepts, tutorials, papers, tools, and resources for building and managing AI agent runtimes. · GitHub, 访问时间为 五月 1, 2026， [https://github.com/nexu-io/harness-engineering-guide](https://github.com/nexu-io/harness-engineering-guide)  
32. LangGraph Implementation | Claude Code Skill for AI Agents \- MCP Market, 访问时间为 五月 1, 2026， [https://mcpmarket.com/tools/skills/langgraph-implementation](https://mcpmarket.com/tools/skills/langgraph-implementation)  
33. The 10 Best Context Engineering Open Source Projects in 2025 \- Medium, 访问时间为 五月 1, 2026， [https://medium.com/@contextspace/the-10-best-context-engineering-open-source-projects-in-2025-a93b4c6862cd](https://medium.com/@contextspace/the-10-best-context-engineering-open-source-projects-in-2025-a93b4c6862cd)  
34. How to measure agent performance: metrics, methods, and ROI \- DataRobot, 访问时间为 五月 1, 2026， [https://www.datarobot.com/blog/how-to-measure-agent-performance/](https://www.datarobot.com/blog/how-to-measure-agent-performance/)  
35. Guide to Agent Harnesses: Building, Measuring, and Improving Your Agent \- Paragon, 访问时间为 五月 1, 2026， [https://www.useparagon.com/learn/guide-to-agent-harnesses/](https://www.useparagon.com/learn/guide-to-agent-harnesses/)  
36. AI agent evaluation: Metrics, strategies, and best practices | by Dave Davies \- Medium, 访问时间为 五月 1, 2026， [https://medium.com/online-inference/ai-agent-evaluation-metrics-strategies-and-best-practices-8a00a5b17377](https://medium.com/online-inference/ai-agent-evaluation-metrics-strategies-and-best-practices-8a00a5b17377)  
37. SkillsBench: Benchmarking How Well Agent Skills Work Across Diverse Tasks \- alphaXiv, 访问时间为 五月 1, 2026， [https://www.alphaxiv.org/overview/2602.12670](https://www.alphaxiv.org/overview/2602.12670)  
38. Beyond Quantity: Trajectory Diversity Scaling for Code Agents \- arXiv, 访问时间为 五月 1, 2026， [https://arxiv.org/html/2602.03219v2](https://arxiv.org/html/2602.03219v2)  
39. Benchmarking How Well Agent Skills Work Across Diverse Tasks \- SkillsBench, 访问时间为 五月 1, 2026， [https://www.skillsbench.ai/skillsbench.pdf](https://www.skillsbench.ai/skillsbench.pdf)  
40. SkillsBench: Benchmarking How Well Agent Skills Work Across Diverse Tasks \- arXiv, 访问时间为 五月 1, 2026， [https://arxiv.org/html/2602.12670v1](https://arxiv.org/html/2602.12670v1)  
41. I Tried 20+ MCP (Model Context Protocol) Courses on Udemy: Here are My Top 5 Recommendations for…, 访问时间为 五月 1, 2026， [https://medium.com/javarevisited/i-tried-20-mcp-model-context-protocol-courses-on-udemy-here-are-my-top-5-recommendations-for-921440120326](https://medium.com/javarevisited/i-tried-20-mcp-model-context-protocol-courses-on-udemy-here-are-my-top-5-recommendations-for-921440120326)  
42. 9 Hands-On MCP Projects to Strengthen Your AI Portfolio \- ProjectPro, 访问时间为 五月 1, 2026， [https://www.projectpro.io/article/mcp-projects/1142](https://www.projectpro.io/article/mcp-projects/1142)  
43. punkpeye/awesome-mcp-servers: A collection of MCP servers. \- GitHub, 访问时间为 五月 1, 2026， [https://github.com/punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers)  
44. Model Context Protocol (MCP): Revolutionizing Developer Workflows with AI Integration · community · Discussion #174921 \- GitHub, 访问时间为 五月 1, 2026， [https://github.com/orgs/community/discussions/174921](https://github.com/orgs/community/discussions/174921)  
45. Forcing agents to use the right tools — MCP \+ Skills \+ LangGraph demo \- Reddit, 访问时间为 五月 1, 2026， [https://www.reddit.com/r/LangChain/comments/1sz87ei/forcing\_agents\_to\_use\_the\_right\_tools\_mcp\_skills/](https://www.reddit.com/r/LangChain/comments/1sz87ei/forcing_agents_to_use_the_right_tools_mcp_skills/)  
46. Top 5 MCP Project Ideas for Seamless AI Integration | by Sebastian Buzdugan | Medium, 访问时间为 五月 1, 2026， [https://medium.com/@sebuzdugan/top-5-anthropic-mcp-project-ideas-for-seamless-ai-integration-faeffe11cce7](https://medium.com/@sebuzdugan/top-5-anthropic-mcp-project-ideas-for-seamless-ai-integration-faeffe11cce7)  
47. What is Agent Harness? How Does it Work? \- PuppyGraph, 访问时间为 五月 1, 2026， [https://www.puppygraph.com/blog/agent-harness](https://www.puppygraph.com/blog/agent-harness)  
48. How do you evaluate your agent project and how do you measure it? : r/AI\_Agents \- Reddit, 访问时间为 五月 1, 2026， [https://www.reddit.com/r/AI\_Agents/comments/1q9vbz3/how\_do\_you\_evaluate\_your\_agent\_project\_and\_how\_do/](https://www.reddit.com/r/AI_Agents/comments/1q9vbz3/how_do_you_evaluate_your_agent_project_and_how_do/)  
49. Code execution with MCP: building more efficient AI agents \- Anthropic, 访问时间为 五月 1, 2026， [https://www.anthropic.com/engineering/code-execution-with-mcp](https://www.anthropic.com/engineering/code-execution-with-mcp)  
50. Mastering Agents: Metrics for Evaluating AI Agents \- Galileo AI, 访问时间为 五月 1, 2026， [https://galileo.ai/blog/metrics-for-evaluating-ai-agents](https://galileo.ai/blog/metrics-for-evaluating-ai-agents)  
51. OmniParser for Pure Vision Based GUI Agent \- arXiv, 访问时间为 五月 1, 2026， [https://arxiv.org/html/2408.00203v1](https://arxiv.org/html/2408.00203v1)  
52. OmniParser for pure vision-based GUI agent \- Microsoft Research, 访问时间为 五月 1, 2026， [https://www.microsoft.com/en-us/research/articles/omniparser-for-pure-vision-based-gui-agent/](https://www.microsoft.com/en-us/research/articles/omniparser-for-pure-vision-based-gui-agent/)  
53. 40+ Agentic AI Use Cases with Real-life Examples \- AIMultiple, 访问时间为 五月 1, 2026， [https://aimultiple.com/agentic-ai](https://aimultiple.com/agentic-ai)  
54. Phi-Ground Tech Report: Advancing Perception in GUI Grounding \- arXiv, 访问时间为 五月 1, 2026， [https://arxiv.org/html/2507.23779v1](https://arxiv.org/html/2507.23779v1)  
55. OmniParser v2 Projects \- AI Tinkerers, 访问时间为 五月 1, 2026， [https://aitinkerers.org/technologies/omniparser-v2](https://aitinkerers.org/technologies/omniparser-v2)  
56. OmniParser V2 \- Azure AI Foundry Labs | Early-Stage AI Experiments & Prototypes, 访问时间为 五月 1, 2026， [https://labs.ai.azure.com/projects/omniparserv2/](https://labs.ai.azure.com/projects/omniparserv2/)  
57. Build a Local Vision Agent for Windows 11 using OmniParser V2 and OmniTool, 访问时间为 五月 1, 2026， [https://www.analyticsvidhya.com/blog/2025/03/vision-agent-using-omniparser-and-omnitool/](https://www.analyticsvidhya.com/blog/2025/03/vision-agent-using-omniparser-and-omnitool/)  
58. GUI-Actor: Coordinate-Free Visual Grounding for GUI Agents \- OpenReview, 访问时间为 五月 1, 2026， [https://openreview.net/forum?id=5fSkinHw7w](https://openreview.net/forum?id=5fSkinHw7w)  
59. X-PLUG/MobileAgent: Mobile-Agent: The Powerful GUI Agent Family \- GitHub, 访问时间为 五月 1, 2026， [https://github.com/x-plug/mobileagent](https://github.com/x-plug/mobileagent)  
60. ScreenSpot-Pro: GUI Grounding for Professional High-Resolution Computer Use \- Kaixin LI, 访问时间为 五月 1, 2026， [https://likaixin2000.github.io/papers/ScreenSpot\_Pro.pdf](https://likaixin2000.github.io/papers/ScreenSpot_Pro.pdf)  
61. ScreenSpot-Pro: GUI Grounding for Professional High-Resolution Computer Use, 访问时间为 五月 1, 2026， [https://huggingface.co/blog/Ziyang/screenspot-pro](https://huggingface.co/blog/Ziyang/screenspot-pro)  
62. ScreenSpot-Pro: GUI Grounding for Professional High-Resolution Computer Use \- arXiv, 访问时间为 五月 1, 2026， [https://arxiv.org/html/2504.07981v1](https://arxiv.org/html/2504.07981v1)  
63. elasticdotventures/blender-agent-tools \- GitHub, 访问时间为 五月 1, 2026， [https://github.com/elasticdotventures/blender-agent-tools](https://github.com/elasticdotventures/blender-agent-tools)  
64. 3D-Agent Blender AI Assistant \- Built a multi-agent system on top of Blender's MCP and Python API and sharing architecture learnings for the lab discussion, 访问时间为 五月 1, 2026， [https://devtalk.blender.org/t/3d-agent-blender-ai-assistant-built-a-multi-agent-system-on-top-of-blenders-mcp-and-python-api-and-sharing-architecture-learnings-for-the-lab-discussion/44260](https://devtalk.blender.org/t/3d-agent-blender-ai-assistant-built-a-multi-agent-system-on-top-of-blenders-mcp-and-python-api-and-sharing-architecture-learnings-for-the-lab-discussion/44260)  
65. OmniParser AutoGUI MCP Server: The Ultimate Guide for AI Engineers \- Skywork, 访问时间为 五月 1, 2026， [https://skywork.ai/skypage/en/omniparser-autogui-mcp-server-guide/1977651279892897792](https://skywork.ai/skypage/en/omniparser-autogui-mcp-server-guide/1977651279892897792)  
66. Visual Test-time Scaling for GUI Agent Grounding \- arXiv, 访问时间为 五月 1, 2026， [https://arxiv.org/html/2505.00684v2](https://arxiv.org/html/2505.00684v2)  
67. The ultimate guide to AI agent architectures in 2025 \- DEV Community, 访问时间为 五月 1, 2026， [https://dev.to/sohail-akbar/the-ultimate-guide-to-ai-agent-architectures-in-2025-2j1c](https://dev.to/sohail-akbar/the-ultimate-guide-to-ai-agent-architectures-in-2025-2j1c)  
68. Agentic AI Success Metrics: 5 KPIs That Prove ROI \- Put It Forward, 访问时间为 五月 1, 2026， [https://www.putitforward.com/agentic-ai/agentic-ai-success-metrics](https://www.putitforward.com/agentic-ai/agentic-ai-success-metrics)  
69. One year of agentic AI: Six lessons from the people doing the work \- McKinsey, 访问时间为 五月 1, 2026， [https://www.mckinsey.com/capabilities/quantumblack/our-insights/one-year-of-agentic-ai-six-lessons-from-the-people-doing-the-work](https://www.mckinsey.com/capabilities/quantumblack/our-insights/one-year-of-agentic-ai-six-lessons-from-the-people-doing-the-work)  
70. Building an AI‑Powered QA Test Generator: A Multi‑Agent Workflow with LangGraph \+ MCP | by Theofilos Tougountzoglou | Medium, 访问时间为 五月 1, 2026， [https://medium.com/@tougountzoglou.theofilos/building-an-ai-powered-qa-test-generator-a-multi-agent-workflow-with-langgraph-mcp-14916cbf901f](https://medium.com/@tougountzoglou.theofilos/building-an-ai-powered-qa-test-generator-a-multi-agent-workflow-with-langgraph-mcp-14916cbf901f)  
71. OmniParser V2: Screen Parsing tool for Pure Vision Based GUI Agent | Vibe Weekly Vol.004, 访问时间为 五月 1, 2026， [https://dev.to/vibeweekly/omniparser-v2-screen-parsing-tool-for-pure-vision-based-gui-agent-vibe-weekly-vol004-2ig0](https://dev.to/vibeweekly/omniparser-v2-screen-parsing-tool-for-pure-vision-based-gui-agent-vibe-weekly-vol004-2ig0)  
72. Harness engineering: Structured workflows for AI-assisted development, 访问时间为 五月 1, 2026， [https://developers.redhat.com/articles/2026/04/07/harness-engineering-structured-workflows-ai-assisted-development](https://developers.redhat.com/articles/2026/04/07/harness-engineering-structured-workflows-ai-assisted-development)  
73. Demystifying evals for AI agents \- Anthropic, 访问时间为 五月 1, 2026， [https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)  
74. AI Agent Evaluation: How to Build Custom Benchmarks That Actually Test Intelligence, 访问时间为 五月 1, 2026， [https://www.mindstudio.ai/blog/ai-agent-custom-benchmarks-evaluation](https://www.mindstudio.ai/blog/ai-agent-custom-benchmarks-evaluation)  
75. Agent Evaluation Framework 2026: Metrics, Rubrics & Benchmarks \- Galileo AI, 访问时间为 五月 1, 2026， [https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)  
76. What's Your Agent's GPA? A Framework for Evaluating AI Agent Reliability \- Snowflake, 访问时间为 五月 1, 2026， [https://www.snowflake.com/en/engineering-blog/ai-agent-evaluation-gpa-framework/](https://www.snowflake.com/en/engineering-blog/ai-agent-evaluation-gpa-framework/)  
77. AI Agent Evaluation: Metrics, Traces, Human Review, and Workflows \- Confident AI, 访问时间为 五月 1, 2026， [https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide)  
78. Stop Stuffing Your System Prompt: Build Scalable Agent Skills in LangGraph, 访问时间为 五月 1, 2026， [https://pessini.medium.com/stop-stuffing-your-system-prompt-build-scalable-agent-skills-in-langgraph-a9856378e8f6](https://pessini.medium.com/stop-stuffing-your-system-prompt-build-scalable-agent-skills-in-langgraph-a9856378e8f6)  
79. Using MCP with LangGraph agents \- YouTube, 访问时间为 五月 1, 2026， [https://www.youtube.com/watch?v=OX89LkTvNKQ](https://www.youtube.com/watch?v=OX89LkTvNKQ)  
80. GitHub \- microsoft/OmniParser: A simple screen parsing tool towards pure vision based GUI agent, 访问时间为 五月 1, 2026， [https://github.com/microsoft/omniparser](https://github.com/microsoft/omniparser)  
81. How to Build Reliable AI Agents by Engineering the System, Not the Model | deepset Blog, 访问时间为 五月 1, 2026， [https://www.deepset.ai/blog/harness-engineering](https://www.deepset.ai/blog/harness-engineering)  
82. Improving Deep Agents with harness engineering \- LangChain, 访问时间为 五月 1, 2026， [https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering)

[image1]: <data:image/png;base64,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>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAoAAAAZCAYAAAAIcL+IAAAAxElEQVR4XmNgGAVDB7AC8SQgVkeXQAbMQPwRiDcC8W8grgHi5ygqgGA6EP8HYgUoXxyIrzOgKeRhgChCFpQB4icMEGfAgQcDROEaJDEXIP4HxNFIYgx7GCBuskES28oA0SyIJMZwAIgPAzEvkhjINJBCFACyGuQeRSi/gQGi6CpMAQyAwg4kAbIOpOkdlD8fWRE2kA7EX4HYGFkQFhPI4AEDxDRGZMEMBlRHgyRBfFskMTCIYoAETQQQNzJAFPmgqKAJAAAjfSiXUunxUQAAAABJRU5ErkJggg==>

[image3]: <data:image/png;base64,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>

[image4]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA8AAAAZCAYAAADuWXTMAAAAu0lEQVR4XmNgGAUDB2YA8X8C+CMQM8M0YAO9DBCFi5DEOIDYFio+C0kcAzwA4m9AbIomDgJLGSAGsKBLwABIEqSIEV0CCO4y4NEszgCRxGYryDCQ3BV0CRiwYYAoEEGXAAJtBoicGboECICcsoYBokAGiCUZIAqToWIgrABTjA5Atv4G4ifoEsSAIgaI6VvRJYgBDxggml3QxIkCMH+BEgRJQIkBovEfugQhAEpuxxkQmkF8ZRQVo2CAAQCYLC3W5JrnqwAAAABJRU5ErkJggg==>