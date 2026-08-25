# 8 月 25 日变更日志

- 实现 FreeCAD 后端的圆形 `pocket` 与顶部外缘 `fillet`。
- 引入终端实体跟踪，特征修改后不再把旧实体重新融合进结果。
- §3 完整示例已通过真实 OCCT 内核验证，完整测试为 191 项通过。
- 新增可重复生成的 HTML、PNG 与 STL 可视化验证报告。

```mermaid
flowchart LR
    A[sketch] --> B[extrude]
    B --> C[pocket]
    C --> D[fillet]
    D --> E[有效 Solid]
```
