# 更新日志 / Changelog

> English version, reframed as a milestone/progress report (e.g. for a group meeting): [`CHANGELOG_en.md`](CHANGELOG_en.md)

## 2026-07-29 — 项目从零搭建，M1 完成

这周从零开始搭这个项目。当前进度：整体模块骨架 + DSL v1 语法定稿，M1 全部完成。

## 背景：这个 DSL 到底是什么、为什么要造一个

工程师的指令是自然语言（"轴加长到 250"），这对软件来说太模糊，没法直接执行或验证。直接让 LLM 生成 CAD 内核（FreeCAD/OCCT）的原始 API 调用，又太复杂、LLM 容易写错。所以这个项目定义了一门自造的小语言——**DSL（领域专用语言，Domain-Specific Language）**——作为两者之间的中间层：

```
自然语言指令          →   [LLM]   →          DSL 文本                 →   [dsl/compiler.py]   →   真的在 CAD 内核上执行
"轴加长到 250"                   edit(target=body, set=length, value=250);                     FreeCAD 真的把轴拉长
```

LLM 只需要学会生成这种格式固定、结构简单的文本（`sketch(...)`、`extrude(...)`、`replace(...)` 等），不用直接操作复杂的 CAD API。而且因为这门语言语法固定、简单，它生成的每一句话都能被自动检查——解析、在内核上重新执行、按尺寸规则量测等——确认没问题才会被采纳。`dsl/grammar.md` 就是这门 DSL 的规格书：定义了有哪些操作（相当于"动词"）、这些操作怎么拼成一句话（相当于"句子结构"），以及它最与众不同的设计——一条语句怎么引用前面某条语句建出来的特征。

**为什么"引用"这么关键——拓扑命名问题**：大多数参数化 CAD 软件里，你想改的某个面/边经常是靠"位置"（比如"第 3 个面"）或坐标来指认的。一旦模型前面的某一步变了，这些位置可能悄悄错位，后面的编辑就改到了错误的几何上——这是业界公认的"拓扑命名问题"（Topological Naming Problem）。这个项目的 DSL 换了个做法：用永久不变的符号标签指代几何，比如 `body.face_top`，哪怕 `body` 本身被大改了，这个标签依然有效。具体看 `grammar.md` §6 的例子：

```dsl
# 改之前
body = extrude(profile=circle_sk, length=200);
h    = pocket(on=body.face_top, ...);          # h 引用的是 body 的顶面

# 指令："把主体从圆柱换成六棱柱"
replace(target=body, with=extrude(profile=hex_sk, length=200));
# body.face_top 依然有效 → h 自动指向新实体的顶面
```

即使 `body` 整个形状都变了（圆柱→六棱柱），`h` 对 `body.face_top` 的引用从头到尾都没失效过——这就是"引用稳定"这套设计要解决的具体问题。

这周的产出（见下）正是把这套规格定了下来，并且真的写了一个能读懂这门语言的解析器，把 DSL 文本变成程序能执行、能检查的结构。

### 1. 项目骨架

按研究计划的四个 RQ 搭了完整的模块划分：

- `dsl/`：DSL 定义与解析器（RQ1）
- `editor/`：编辑引擎，含 `context/`（RQ2 连续编辑上下文管理）
- `verify/`：四重验证回路（RQ3）—— kernel / rules / visual / type_check / repair
- `eval/`：评估框架 —— harness / metrics / benchmarks
- `data/`：数据合成（synth）、指令生成（instruct）、真实零件（real_parts, RQ4）
- `deploy/`：内网部署（RQ4）—— 量化 + 审核 UI
- `scripts/`：训练入口、端到端单次编辑入口
- `config/default.yaml`：全局配置（模型、路径、验证阈值）

除了 `dsl/ast.py`、`dsl/parser.py`（见下）之外，其余模块目前是清晰接口 + TODO（标注到具体里程碑 M3/M6/M8/M10），按计划逐个里程碑再填实现。

### 2. 周度执行计划书

把 12 个月的里程碑（M1–M12）展开成周粒度的可执行清单，每周任务是打勾格式（`- [ ]`），中英文各一份：`docs/weekly_plan.md` / `docs/weekly_plan_en.md`。

### 3. DSL v1 语法定稿

`dsl/grammar.md` 定了这套 DSL 的完整规格：

- **设计原则**：引用稳定优先（几何用不变符号名指代，不用坐标——解决拓扑命名问题）、可复合、可验证、对 LLM 友好
- **操作集**：基础操作（sketch/extrude/revolve/fillet/chamfer/pocket/groove/edit）+ 本项目核心贡献的 4 个复合编辑操作（replace/pattern/mirror/constraint）
- **引用语法**：点号引用（`body.face_top`）+ 阵列实例引用（`pat1[*]`/`pat1[2]`）
- **`replace` 的重新绑定语义**（RQ2 关键难点）：换特征时下游引用怎么自动跟着改
- **派生名 role 枚举**：7 个角色（face_top/face_bottom/axis/wall/floor/edge_top/edge_bottom）+ 每个操作产出哪些角色的对照表
- **设计决策记录**：`edit`/`replace` 边界、`constraint` 最小集合（dim: equal/range/ratio；geom: concentric/coplanar/parallel）、pattern 引用计数展开语义、role 枚举、解析器实现策略 —— 5 项关键设计决策定了下来并写明依据

### 4. 解析器实现 + 测试

- `dsl/ast.py`：AST 节点（`Statement`/`Ref`/`Quantity`/`OpCall`）+ 四个新操作的参数校验
- `dsl/parser.py`：手写递归下降解析器，支持完整语法（引用、阵列下标、数值单位、括号列表、嵌套操作调用）
- `tests/test_dsl_parser.py`：13 个 pytest 用例，覆盖 `grammar.md` 全部示例（含 RQ2 用的 5 步编辑链）+ 校验报错场景，全部通过

### 当前状态

M1（DSL v1 语法定稿）全部完成。下一步 M2：接 `dsl/compiler.py` 到 FreeCAD、完善 `dsl/registry.py` 的 `rebind()`、实现 `eval/harness.py` 的连续编辑评分逻辑（产出连续编辑基准 v1）。

---

## 附录：产出内容

### A. 项目目录结构

```
LLM-CAD-Editor/
├── CHANGELOG.md
├── CHANGELOG_en.md
├── README.md
├── pytest.ini
├── requirements.txt
├── config/
│   └── default.yaml
├── data/
│   ├── instruct/generate.py
│   ├── real_parts/README.md
│   └── synth/synthesize.py
├── deploy/
│   ├── quantize.py
│   └── ui/README.md
├── docs/
│   ├── weekly_plan.md
│   └── weekly_plan_en.md
├── dsl/
│   ├── ast.py
│   ├── compiler.py
│   ├── grammar.md
│   ├── parser.py
│   └── registry.py
├── editor/
│   ├── context/
│   │   ├── __init__.py
│   │   └── strategies.py
│   ├── infer.py
│   └── model.py
├── eval/
│   ├── benchmarks/README.md
│   ├── harness.py
│   └── metrics.py
├── scripts/
│   ├── run_edit.py
│   └── train.py
├── tests/
│   └── test_dsl_parser.py
└── verify/
    ├── kernel.py
    ├── repair.py
    ├── rules.py
    ├── type_check.py
    └── visual.py
```

### B. `dsl/grammar.md` 关键内容摘录

**操作集（§4）**

| Op | 作用 | 关键参数 |
|---|---|---|
| `sketch`  | 二维草图 | `plane`, `circle`/`rect`/`polygon` |
| `extrude` | 拉伸 | `profile`, `length`, `dir` |
| `revolve` | 旋转 | `profile`, `axis`, `angle` |
| `fillet`  | 圆角 | `on`（边引用）, `radius` |
| `chamfer` | 倒角 | `on`（边引用）, `dist` |
| `pocket`  | 挖槽/孔 | `on`（面引用）, profile, `depth` |
| `groove`  | 环槽 | `on`, `profile`, `axis` |
| `edit`    | 单值参数修改（操作类型不变，不触发重新绑定） | `target`（特征引用）, `set`（字段名）, `value` |
| `replace` | 特征替换 | `target`（特征引用）, `with`（新操作）——**必须触发下游重新绑定** |
| `pattern` | 阵列复制 | `feature`, `type`(linear/circular), `count`, `spacing`/`angle` |
| `mirror`  | 镜像 | `feature`, `plane` |
| `constraint` | 约束声明 | `type`(dim/geom), `on`, `value` |

**派生名 role（§5）**：`face_top`, `face_bottom`, `axis`, `wall`, `floor`, `edge_top`, `edge_bottom`

**完整示例（§7，RQ2 基准用的 5 步编辑链）**

```dsl
# initial
sk1  = sketch(plane=XY, circle=[center=origin, r=20]);
body = extrude(profile=sk1, length=200);

# step1: lengthen  →  body.length: 200 → 250
edit(target=body, set=length, value=250);

# step2: drill top hole
h1 = pocket(on=body.face_top, circle=[center=body.axis, r=6], depth=180);

# step3: pattern the hole
p1 = pattern(feature=h1, type=circular, count=4, angle=90);

# step4: cylinder → hex prism (triggers re-binding)
replace(target=body, with=extrude(profile=hex(r=20), length=250));

# step5: chamfer top edge
chamfer(on=body.edge_top, dist=1.5);
```

### C. 解析器是怎么实现的

`dsl/parser.py` 分两个阶段：**先分词（tokenize），再递归下降解析（recursive descent）**，这是写解析器最经典的套路。

**第一阶段：分词——把一整段文字切成一个个"词"**

人读 `body = extrude(profile=sk1, length=200);` 一眼就知道哪是变量名、哪是符号，但程序得先把这条字符串切成一串"最小单位"（token）：`body`、`=`、`extrude`、`(`、`profile`、`=`、`sk1`、`,`、`length`、`=`、`200`、`)`、`;`。

对应第 19–37 行的 `_TOKEN_RE`——一个带"命名分组"的正则表达式，给每一种"词"定义识别规则：长得像数字的算 `NUMBER`，字母开头的算 `IDENT`（标识符/操作名），`(`、`)`、`,` 等符号各算一类。第 51–64 行的 `_tokenize()` 逐行扫描文本，每命中一次记一个 token，同时记下第几行（`lineno`）——这个行号就是后面报错定位的来源；空白跳过（`SKIP`），扫到不认识的字符就报错（`MISMATCH`）。

**第二阶段：递归下降解析——把"词的序列"拼回有意义的结构**

"递归下降"的意思是：语法里每一条规则（grammar.md §3 的 `program`、`statement`、`args`、`value`）都对应写一个函数，函数之间互相调用；又因为语法本身是"套娃"的（一个 `value` 可以是另一个操作调用，这个调用里又有自己的 `args`，`args` 里又有自己的 `value`），所以这些函数也会调用自己——这就是"递归"。

对应关系：

| 语法规则 | 对应函数 | 在干嘛 |
|---|---|---|
| `program ::= statement*` | `parse_program()`（94–99 行） | 一直读语句，直到读到末尾（EOF） |
| `statement ::= feature_def \| edit_op` | `_parse_statement()`（101–121 行） | 看第一个词后面跟不跟 `=`，决定是"具名语句"还是"裸操作" |
| `args ::= key=value, ...` | `_parse_args()`（123–136 行） | 循环读 `key = value`，遇到逗号就继续，没有就停 |
| `value ::= number \| reference \| ...` | `_parse_value()`（138–154 行） | 看下一个词是数字/字符串/括号/标识符，分别走不同分支 |
| 标识符后续的引用/嵌套调用/下标 | `_parse_ident_value()`（156–188 行） | **递归发生的地方**（见下） |

关键的"递归"发生在 `_parse_ident_value()`：读到一个标识符（比如 `extrude`）之后，往后偷看一眼：

- 后面跟 `(` → 说明这是一个**嵌套的操作调用**（比如 `with=extrude(...)` 里的 `extrude(...)`），于是**再调用一次 `_parse_args()`** 解析它的参数——而 `_parse_args()` 内部解析每个 value 时又可能再调用 `_parse_ident_value()`，如果里面还有操作调用（比如 `extrude(profile=hex(r=20), ...)` 里的 `hex(...)`），就再递归一层。这正是 `replace(target=body, with=extrude(profile=hex(r=20), length=250))` 这种"操作套操作套操作"能被正确解开的原因。
- 后面跟 `[` → 阵列下标引用（`pat1[*]`/`pat1[2]`）
- 都不是 → 普通引用（`body.face_top`）

三个公共小工具贯穿所有解析函数：`_peek()`（往后看一个词，不消耗）、`_advance()`（消耗当前词，往后走一格）、`_expect(kind)`（要求下一个词必须是指定类型，不是就报错，带行号）。`_validate()`（87–92 行）在每解析完一个 `replace`/`pattern`/`mirror`/`constraint` 语句后顺手调用 `dsl/ast.py` 的 `validate_new_op()`——校验是**嵌在解析过程里**的，不是解析完再单独跑一遍。

**用一句真实的话走一遍流程**，以 `body = extrude(profile=sk1, length=200);` 为例：

```
_parse_statement()
  读到 "body"，往后看到 "="，确定是 feature_def
  读到操作名 "extrude"，读到 "("
  → 调 _parse_args("RPAREN")
       读 "profile" "=" → 调 _parse_value() → 读到标识符 "sk1"，后面不跟 "(" 或 "["，返回 Ref(["sk1"])
       读到 ","，继续
       读 "length" "=" → 调 _parse_value() → 读到数字 "200"，返回 Quantity(200.0)
       读到 ")"，_parse_args 结束，返回 {"profile": Ref(["sk1"]), "length": Quantity(200.0)}
  读到 ")"，读到 ";"
  → 返回 Statement(name="body", op="extrude", args={...})
```

顶层的 `parse()` 函数（第 210 行）把"分词"和"这一整套递归解析"串起来：`_Parser(_tokenize(text)).parse_program()`，一句话。

### D. 解析器实际运行结果（结果，非代码）

**D1. 把 §7 的 5 步链喂给解析器，看它拆出来的结构**

```
Statement(name='sk1', op='sketch', args={'plane': Ref(path=['XY']), 'circle': {'center': Ref(path=['origin']), 'r': Quantity(value=20.0)}})
Statement(name='body', op='extrude', args={'profile': Ref(path=['sk1']), 'length': Quantity(value=200.0)})
Statement(name=None, op='edit', args={'target': Ref(path=['body']), 'set': Ref(path=['length']), 'value': Quantity(value=250.0)})
Statement(name='h1', op='pocket', args={'on': Ref(path=['body', 'face_top']), 'circle': {'center': Ref(path=['body', 'axis']), 'r': Quantity(value=6.0)}, 'depth': Quantity(value=180.0)})
Statement(name='p1', op='pattern', args={'feature': Ref(path=['h1']), 'type': Ref(path=['circular']), 'count': Quantity(value=4.0), 'angle': Quantity(value=90.0)})
Statement(name=None, op='replace', args={'target': Ref(path=['body']), 'with': OpCall(op='extrude', args={'profile': OpCall(op='hex', args={'r': Quantity(value=20.0)}), 'length': Quantity(value=250.0)})})
Statement(name=None, op='chamfer', args={'on': Ref(path=['body', 'edge_top']), 'dist': Quantity(value=1.5)})
```

**说明**：这证明解析器不是只在纸面上定义了语法，而是真的能把 5 步链原样吃透——尤其是第 6 条 `replace` 语句，它的 `with` 参数被正确拆成了一个独立的 `extrude` 操作节点，而这个 `extrude` 里的 `profile` 又嵌套了一个 `hex` 操作节点。这种"操作套操作"的写法（对应 grammar.md §6 的重新绑定语义）是最容易解析错的地方，这里验证了没错。

**代码位置**：整条流水线是 `dsl/parser.py` 的 `parse()`（第 210–220 行）→ `_tokenize()`（51–64 行）→ `_Parser.parse_program()`（94–99 行）→ `_parse_statement()`（101–121 行）→ `_parse_args()`（123–136 行）→ `_parse_value()`（138–154 行）；`replace` 里嵌套操作调用的识别逻辑在 `_parse_ident_value()`（156–188 行，关键是 162–171 行）。对应的 AST 节点类型（`Statement`/`Ref`/`Quantity`/`OpCall`）定义在 `dsl/ast.py` 第 12–53 行。

**D2. 校验逻辑实际拦截效果**

| 输入 | 违反了什么规则 | 实际报错 |
|---|---|---|
| `replace(target=body);` | `replace` 少了必填的 `with` | `replace(...) missing required arg(s): with` |
| `replace(target=body, with=hex_sk);` | `with` 必须是嵌套操作调用，不能是普通引用 | ``replace(...): `with` must be a nested operation call`` |
| `pattern(feature=h1, type=triangular, count=4);` | `type` 只能是 `linear`/`circular` | `pattern(...): type must be one of ['circular', 'linear'], got triangular` |
| `mirror(feature=h1);` | 少了必填的 `plane` | `mirror(...) missing required arg(s): plane` |
| `constraint(type=dim, on=body.length);` | 少了必填的 `value` | `constraint(...) missing required arg(s): value` |

**说明**：这 5 条都是"语法上能读、但语义上不合规"的例子。解析器在读到这一步时就直接报错、不往下走，不会让一条看着能跑、实际语义有问题的编辑指令混进后面的建模/验证环节——这是 `dsl/ast.py` 的 `validate_new_op()` 在起作用。

**代码位置**：校验逻辑是 `dsl/ast.py` 的 `validate_new_op()`（第 73–95 行），必填参数表是同文件的 `NEW_OP_REQUIRED_ARGS`（59–64 行）；被 `dsl/parser.py` 的 `_Parser._validate()`（87–92 行）在三处调用：解析 `name = op(...)` 时（112 行）、解析裸操作语句时（120 行）、解析嵌套操作调用时（170 行）。

**D3. 语法错误能定位到具体行**

输入（第一条语句忘了写分号）：
```dsl
sk1 = sketch(plane=XY
body = extrude(profile=sk1, length=200);
```
实际报错：
```
ParseError: expected RPAREN, got IDENT 'body' (line 2)
```

**说明**：出错时能精确报出第几行，之后不管是人工调 DSL 脚本，还是把这个错误结构化后喂回给 LLM 重新生成（M6 的 self-repair 回路要用到这个信息），都有明确的定位可用。

**代码位置**：行号来自 `dsl/parser.py` 的 `_tokenize()`（第 51–64 行，逐行扫描时记录 `lineno`）和 `_Token` 类（44–48 行）；报错本身在 `_expect()`（81–85 行）里抛出。

**D4. 数值单位可选，解析结果统一**

输入：`edit(target=body, set=length, value=250 mm);`
解析出的 `value` 参数：`250.0mm`（即 `Quantity(value=250.0, unit='mm')`）

**说明**：单位（mm/deg）按 grammar.md §2 的定义是可选的，这里验证了带单位和不带单位（如 §7 示例里的 `value=250`）都能正确解析成同一种 `Quantity` 类型，下游代码不用为"有没有单位"分两套处理逻辑。

**代码位置**：`dsl/parser.py` 的 `_parse_value()` 第 141–146 行（读完数字后检查下一个 token 是不是 `mm`/`deg`）；`_UNITS` 集合定义在第 17 行；`Quantity` 类型定义在 `dsl/ast.py` 第 24–31 行。

### E. 测试结果

`tests/test_dsl_parser.py` 的 13 个测试，每个测的是：

- `test_section3_basic_example`（`tests/test_dsl_parser.py:16-36`）：grammar.md §3 的基础示例（sketch/extrude/pocket/fillet）能正确解析成对应的语句和参数
- `test_section6_replace_rebinding_example`（`tests/test_dsl_parser.py:39-54`）：§6 的 replace 示例，`with` 被正确解析成嵌套操作
- `test_section7_five_step_chain`（`tests/test_dsl_parser.py:57-102`）：§7 的 5 步链（RQ2 基准链），7 条语句全部结构正确
- `test_parse_ref`（`tests/test_dsl_parser.py:105-116`，3 组参数化用例）：三种引用写法（`body.face_top`、`pat1[*]`、`pat1[2]`）都能正确解析
- `test_new_op_validation_errors`（`tests/test_dsl_parser.py:119-131`，5 组参数化用例）：上面 D2 的 5 种违规调用都能被正确拦截
- `test_syntax_error_reports_line_number`（`tests/test_dsl_parser.py:134-137`）：语法错误能报出正确的行号
- `test_quantity_unit_parsing`（`tests/test_dsl_parser.py:140-142`）：带单位的数值能正确解析

实际运行结果：

```
$ python -m pytest -v
collected 13 items

tests/test_dsl_parser.py::test_section3_basic_example PASSED
tests/test_dsl_parser.py::test_section6_replace_rebinding_example PASSED
tests/test_dsl_parser.py::test_section7_five_step_chain PASSED
tests/test_dsl_parser.py::test_parse_ref[body.face_top-expected_path0-None] PASSED
tests/test_dsl_parser.py::test_parse_ref[pat1[*]-expected_path1-*] PASSED
tests/test_dsl_parser.py::test_parse_ref[pat1[2]-expected_path2-2] PASSED
tests/test_dsl_parser.py::test_new_op_validation_errors[replace(target=body);] PASSED
tests/test_dsl_parser.py::test_new_op_validation_errors[replace(target=body, with=hex_sk);] PASSED
tests/test_dsl_parser.py::test_new_op_validation_errors[pattern(feature=h1, type=triangular, count=4);] PASSED
tests/test_dsl_parser.py::test_new_op_validation_errors[mirror(feature=h1);] PASSED
tests/test_dsl_parser.py::test_new_op_validation_errors[constraint(type=dim, on=body.length);] PASSED
tests/test_dsl_parser.py::test_syntax_error_reports_line_number PASSED
tests/test_dsl_parser.py::test_quantity_unit_parsing PASSED

============================= 13 passed in 0.08s ==============================
```
