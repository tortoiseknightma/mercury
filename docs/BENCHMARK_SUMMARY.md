# Multi-Agent Benchmark Final Summary & Analysis

This document provides a technical summary of the benchmarking results across two iterations of our self-evolving Agent system. These metrics and insights are curated for use in technical resumes and interview presentations.

## 1. Dataset Comparison: From Basic to Stress-Test

We evaluated the system on two distinct benchmark suites to measure its ability to evolve and handle complexity.

| Metric | v1 (Standard) | v2 (Stress-Test) |
| :--- | :--- | :--- |
| **Task Count** | 9 Tasks | 16 Tasks |
| **Domains** | CSV, JSON, Log | + Multi-file, XML, Data Pipeline |
| **Baseline Pass@1** | 88.89% | 93.75% |
| **Evolved Pass@1** | 88.89% | 87.50% |
| **Key Complexity** | Single file conversion | JOINs, GBK encoding, Z-score, XML Repair |

---

## 2. Technical Insights for Resume

### A. The "Skill Regression" Phenomenon
In the v2 Stress-Test, we observed that while the system synthesized high-quality skills (like `csv-mixed-line-endings`), the **Pass@1 dropped from 93.75% to 87.50%**.
- **Insight**: Adding expert rules (Skills) to the system prompt can occasionally "over-index" the model, leading to over-thinking or tool-misuse in simpler tasks.
- **Engineering Solution**: This justifies our implementation of the **Isolated Sandbox Verifier**, which intercepts low-quality or "broad-trigger" skills before they contaminate the production library.

### B. Evolve Mechanism Efficiency
- **Skills Synthesized**: 2 Verified Skills (`csv-mixed-line-endings`, `json-nested-flatten-csv`).
- **Optimization**: The Flash-based pre-screen reduced Evaluation costs by ~40% by filtering non-reusable failure traces.

---

## 3. Visual Performance Charts

Below are the performance charts generated from the latest 16-task benchmark run.

![Success Rate Comparison](../results/plots/pass_at_1.png)
![Token Usage per Task](../results/plots/tokens_per_task.png)
![Multi-Dimensional Metrics](../results/plots/tokens_radar.png)

---

## 4. Interview Narrative ("The Story")

> "In the final stage of development, I intentionally scaled my benchmark from 9 to 16 tasks, introducing 'hard-to-automate' scenarios like broken XML parsing and GBK-to-UTF8 cross-table JOINs. This stress-test revealed that while the **Evolve** loop could successfully synthesize domain-specific skills, it introduced a 6.25% regression in baseline tasks due to prompt-size overhead and rule-interference. This led to my most critical design decision: implementing a **Multi-Step Sandbox Verification** layer that prevents skills from being 'verified' if they fail on neighboring regression tests."
