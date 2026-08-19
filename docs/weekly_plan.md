# 周度执行计划书

> 本文档把 `README.md` 中的 12 个月里程碑（M1–M12）展开到周粒度（每月 W1–W4），便于按文件追踪 TODO、按里程碑推进，不绑定具体日历日期。
>
> 四个研究问题：RQ1 `dsl/`,`data/` · RQ2 `editor/context/` · RQ3 `verify/` · RQ4 `data/real_parts/`,`deploy/`
>
> English version: [`docs/weekly_plan_en.md`](weekly_plan_en.md)

---

## M1 — DSL v1 语法定稿

对应 README「现在从哪开始」步骤 1–2。

**W1**
- [ ] 项目启动
- [ ] 锁定设计原则（`grammar.md` §1）
- [ ] 对照输送机零件词汇（轴/辊/皮带轮/链轮/支架/机架）检查基础操作集 §4.1 是否够用

产出与文件：`dsl/grammar.md` §1, §4.1

**W2**
- [x] 设计新增操作 replace/pattern/mirror/constraint（§4.2）
- [x] 敲定 §8 待定项：edit 与 replace 的边界
- [x] 敲定 §8 待定项：constraint 最小集合

产出与文件：`dsl/grammar.md` §4.2, §8

**W3**
- [x] 实现 `dsl/ast.py`：为 replace/pattern/mirror/constraint 补专用节点与校验（清掉 TODO(M1)）
- [x] `dsl/registry.py` 派生名 ROLES 枚举定稿

产出与文件：`dsl/ast.py`, `dsl/registry.py`

**W4**
- [x] 实现 `dsl/parser.py` 递归下降解析器
- [x] 以 `grammar.md` §7 的 5 步链示例做单元测试（见 `tests/test_dsl_parser.py`）
- [x] 敲定手写 vs lark/antlr（§8 最后一项）

产出与文件：`dsl/parser.py`

---

## M2 — 编译执行 + 评估框架 v1

**W1**
- [ ] 实现 `dsl/compiler.py`：AST → FreeCAD Part/PartDesign 调用
- [ ] 跑通 §3 示例（sketch/extrude/pocket/fillet）

产出与文件：`dsl/compiler.py`

**W2**
- [x] 完善 `dsl/registry.py` 的 `rebind()`：真正改写依赖图与下游 Ref（而不只是返回冲突列表）
- [x] 接入 compiler

产出与文件：`dsl/registry.py`

**W3**
- [x] 实现 `eval/harness.py` 的 `score_chain()`（TODO(M1)）
- [x] 逐步做 parse_ok / refs_valid / prior_preserved 打分

产出与文件：`eval/harness.py`

**W4**
- [x] 搭建 `eval/benchmarks/chains_3step` `_5step` `_10step` 场景
- [x] 手写 DSL 链跑通 harness 作冒烟测试 → **连续编辑基准 v1**
- [x] 补 `grammar.md` 定稿附注

产出与文件：`eval/benchmarks/`, `dsl/grammar.md`

- [ ] **里程碑（M2 阶段末）**：扩展 DSL v1 规格 + 连续编辑基准 v1

---

## M3 — 复合编辑数据合成启动

**W1**
- [ ] `data/synth/synthesize.py`：实现圆柱→多边形 replace 变换的 `synthesize_pairs()`
- [ ] 内核校验暂用桩（真正过滤依赖 M6）

产出与文件：`data/synth/synthesize.py`

**W2**
- [ ] 新增圆角↔倒角合成变换
- [ ] 新增孔阵列变更合成变换
- [ ] 目标吞吐对齐 30k 指令数据集 v1

产出与文件：`data/synth/synthesize.py`

**W3**
- [ ] `data/instruct/generate.py`：接入渲染图对 + DSL 对 → VLM
- [ ] 先产出参数级指令（最易层级）

产出与文件：`data/instruct/generate.py`

**W4**
- [ ] 扩展到运算级指令
- [ ] 扩展到功能级指令
- [ ] 补上复合编辑特化类型（替换/重新布置/约束维持）

产出与文件：`data/instruct/generate.py`

---

## M4 — 数据放量 + 微调基础设施

**W1**
- [ ] 放量跑 `synthesize_pairs()` 冲量到数据集 v1 目标规模
- [ ] 跟踪内核通过率

产出与文件：`data/synth/`

**W2**
- [ ] `editor/model.py`：实现 `EditModel.__init__`（transformers 加载 + peft 挂 LoRA）
- [ ] 预留 bitsandbytes 量化加载路径（供 M10 复用）

产出与文件：`editor/model.py`

**W3**
- [ ] `scripts/train.py`：实现 LoRA 训练循环
- [ ] 读取 `data/synth` + `data/real_parts`

产出与文件：`scripts/train.py`

**W4**
- [ ] 数据 QA：去重
- [ ] 数据 QA：有效性抽检
- [ ] 冻结数据集 v1

产出与文件：`data/synth/`, `data/real_parts/`

---

## M5 — 首轮微调 + G1 中期检查

**W1**
- [ ] 启动数据集 v1 上的首轮 LoRA 微调（参数级 + 复合编辑）

产出与文件：`scripts/train.py`

**W2**
- [ ] `editor/model.py` 的 `generate()`：实现基于 valid_refs 的约束解码钩子
- [ ] 该钩子是 RQ2 的基础，供后续上下文策略复用

产出与文件：`editor/model.py`

**W3**
- [ ] `editor/infer.py` 的 `_build_prompt()`：拼装指令/当前 DSL/few-shot 模板
- [ ] 跑通 `scripts/run_edit.py` 的 `edit_once()`

产出与文件：`editor/infer.py`, `scripts/run_edit.py`

**W4**
- [ ] G1 中期测量：真实零件留出集上的参数级编辑 IoU / 解析率（目标 ≥0.93 / ≥96%）
- [ ] 整理中期检查结果

产出与文件：`eval/metrics.py`

- [ ] **里程碑（M5 阶段末）**：数据集 v1（3 万指令）+ G1 中期检查

---

## M6 — 四重验证回路

**W1**
- [ ] `verify/kernel.py` 的 `check()`：调 `dsl/compiler.py` 重新生成模型
- [ ] 做 B-rep 校验（自相交、开放壳）

产出与文件：`verify/kernel.py`

**W2**
- [ ] `verify/rules.py` 的 `check()`：用 trimesh/shapely 测最小壁厚
- [ ] 测孔边界距离
- [ ] 测指令值 vs 结果尺寸，对照 `config/default.yaml` 阈值

产出与文件：`verify/rules.py`

**W3**
- [ ] `verify/visual.py` 的 `check()`：编辑前后渲染图交给 VLM 打分（1–5）
- [ ] 通过阈值 ≥4（见 config）

产出与文件：`verify/visual.py`

**W4**
- [ ] `verify/type_check.py` 的 `check()`：复用先行零件分类器
- [ ] 确认编辑前后类型不变

产出与文件：`verify/type_check.py`

---

## M7 — Self-Repair 回路 + 中期演示

**W1**
- [ ] `verify/repair.py` 的 `run()`：串起 kernel→rules→visual→type_check
- [ ] 失败原因结构化后回灌 `editor/infer.py` 重新生成

产出与文件：`verify/repair.py`

**W2**
- [ ] 落实 `config` 中 `verify.repair.max_self_repair`（3 轮）→ HITL 移交路径
- [ ] 接入待审队列（`deploy/ui` 前置）

产出与文件：`verify/repair.py`, `config/default.yaml`

**W3**
- [ ] 注入 `defect_injection/` 缺陷用例（跨边界孔、管道连接缝隙、过度编辑）
- [ ] 用 `eval/metrics.py` 的 `defect_recall()` 做首次 G4 测量

产出与文件：`eval/benchmarks/defect_injection/`, `eval/metrics.py`

**W4**
- [ ] 中期演示准备：在若干真实零件上跑通 `scripts/run_edit.py` 全链路（editor.infer → verify.repair → 输出）
- [ ] 冻结演示脚本/材料

产出与文件：`scripts/run_edit.py`

- [ ] **里程碑（M7 阶段末）**：中期演示（G4 首测）

---

## M8 — 连续编辑上下文实验

**W1**
- [ ] `editor/context/strategies.py` 的 `FullHistory.build()`：拼接全部 DSL 历史（基线）

产出与文件：`editor/context/strategies.py`

**W2**
- [ ] `SummarizedSubtree.build()`：特征树摘要 + 相关子树摘录

产出与文件：`editor/context/strategies.py`

**W3**
- [ ] 在 3/5/10 步基准上跑 FullHistory / CurrentOnly / SummarizedSubtree 对照实验，测劣化曲线
- [ ] 用 `eval/harness.py` 的 `ref_break_rate` → G3 测量（5 步 <5% 目标）

产出与文件：`eval/benchmarks/`, `eval/harness.py`

**W4**
- [ ] 第二轮真实零件变型设计历史采集
- [ ] 扩充二轮微调数据（衔接 M9）

产出与文件：`data/real_parts/`

---

## M9 — 二轮微调

**W1**
- [ ] 重建训练集：v1 合成数据
- [ ] 加入二轮真实零件编辑
- [ ] 加入 M7–M8 暴露出的困难案例

产出与文件：`data/synth/`, `data/real_parts/`

**W2**
- [ ] 启动第二轮 LoRA 微调
- [ ] 重点针对复合编辑与长链薄弱点

产出与文件：`scripts/train.py`

**W3**
- [ ] 在新 checkpoint 上重测 G2（复合 IoU/解析，目标 ≥0.80/≥85%）
- [ ] 重测 G3（引用崩溃率）

产出与文件：`eval/metrics.py`, `eval/harness.py`

**W4**
- [ ] 回归检查二轮训练未拖累 G1
- [ ] 整理 G2·G3 测量报告

产出与文件：`eval/`

- [ ] **里程碑（M9 阶段末）**：G2 · G3 测量

---

## M10 — 真实零件评估 + 内网推理优化

**W1**
- [ ] `deploy/quantize.py` 的 `quantize()`：对二轮 checkpoint 做 bitsandbytes/GPTQ int4 量化
- [ ] 目标单卡 24GB

产出与文件：`deploy/quantize.py`

**W2**
- [ ] 在量化模型上重跑 G1–G3
- [ ] 核对相对全精度的性能损失

产出与文件：`eval/`

**W3**
- [ ] 测量 G6 单次编辑响应（目标 ≤30 秒）
- [ ] 超预算则调 batch/KV-cache 设置

产出与文件：`deploy/quantize.py`

**W4**
- [ ] 在 `data/real_parts` 留出集上跑完整 G1、G2、G4 评估
- [ ] 这是唯一算数的达标集

产出与文件：`data/real_parts/`, `eval/`

---

## M11 — HITL UI 试点 + 最终测量

**W1**
- [ ] 搭建 `deploy/ui` 审批/驳回界面（streamlit）
- [ ] 自然语言输入
- [ ] 编辑前后 3D 对比
- [ ] 审批/驳回按钮

产出与文件：`deploy/ui/`

**W2**
- [ ] 把审核结果接回训练数据（通过 `verify/repair.py` 的 escalated_to_human / failure_log 路径）
- [ ] 小批量真实编辑试点

产出与文件：`deploy/ui/`, `verify/repair.py`

**W3**
- [ ] 从试点队列统计中测量 G5 自动确认率（目标 ≥80%）

产出与文件：`deploy/ui/`

**W4**
- [ ] 在完整真实零件留出集上做 G1–G6 最终测量
- [ ] 汇总结果表

产出与文件：`eval/`

- [ ] **里程碑（M11 阶段末）**：G1～G6 最终测量

---

## M12 — 结果整理 + 系统 v1.0

**W1**
- [ ] 汇总四个 RQ 的结果图表
- [ ] 起草各 RQ 的发现小节

产出与文件：—

**W2**
- [ ] 撰写最终报告/论文（方法、DSL 设计、验证回路、真实零件结果）
- [ ] 在讨论/局限小节回应风险登记项 R1（re-binding 冲突发生率）
- [ ] 回应 R2（连续编辑增量校验开销）
- [ ] 回应 R4（合成 vs 真实数据差距）

产出与文件：—

**W3**
- [ ] 冻结系统 v1.0（`dsl/`、`editor/`、`verify/`、`deploy/` 定版）
- [ ] 完善 README/文档
- [ ] 内部评审

产出与文件：全仓库

**W4**
- [ ] 提交最终报告
- [ ] 复盘并列出延后到未来工作的事项

产出与文件：—

- [ ] **里程碑（M12 阶段末）**：最终报告 + 系统 v1.0

---

## 定量目标时间线

| 指标 | 首次测量 | 最终测量 |
|---|---|---|
| G1 参数级 IoU/解析 | M5 W4 中期检查 | M11 W4 |
| G2 复合编辑 IoU/解析 | M9 W3 | M11 W4 |
| G3 引用崩溃率 | M8 W3 | M9 W3 → M11 W4 |
| G4 缺陷检出/误检 | M7 W3 首测 | M10 W4 → M11 W4 |
| G5 自动确认率 | M11 W3 | M11 W4 |
| G6 单次编辑延迟 | M10 W3 | M10 W3 |

所有目标只认真实零件留出集，合成数据不算达标（见 `README.md`）。
