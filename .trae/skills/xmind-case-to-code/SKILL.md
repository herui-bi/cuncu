---
name: xmind-case-to-code
description: 把 XMind 测试用例转换为本项目可运行的 Playwright pytest UI 自动化代码（页面对象 + Excel 数据行 + Allure 元数据 + 运行验证）。当用户提供 .xmind 测试用例文件，或表达「根据 xmind 生成自动化测试代码」「xmind 用例转自动化脚本」「把测试用例落地成 UI 自动化」「补充/更新某模块的 xmind 用例自动化」「按用例生成页面对象、测试数据、断言」等意图时触发，适用于任意业务模块。不用于接口/API 测试；Excel、Word 或直接粘贴文本的用例请改用 testcase-to-ui-code。
---

# XMind 用例转 UI 自动化代码（项目通用）

把 XMind 中的手工用例落地为本仓库既有分层下的可运行用例。用例格式不固定为某一个产品：任何“模块 → 用例标题 → 步骤 → 预期结果”结构的 xmind 都按本流程处理。东营惠民保 xmind 只是**格式参考样例**，其中的业务常量不可套用到其他模块。

## 触发场景

满足任一条即按本技能执行：

- 用户提供 `.xmind` 用例文件（如 `docs/testcases/*.xmind`），要求生成、补充或更新自动化代码
- 用户说「根据测试用例生成自动化测试代码」「xmind 用例转自动化脚本」「用例落自动化」「按用例生成页面对象 / 测试数据 / 断言」
- 用户要求按 xmind 中的步骤与预期结果校验页面行为（含保费、版本、浮层、提示等业务规则）
- 用户要求重跑、修复或扩展由 xmind 用例生成的测试用例

不触发：只做接口/API 测试；用例在 Excel、Word 或聊天文本中（改用 `testcase-to-ui-code`）；只要求执行已有用例或出报告。

## 输入

- 任意 `.xmind` 文件（XMind 8 / Zen / 2020+ 均可），主题树包含模块、用例标题、操作步骤、预期结果
- 用户也可只粘贴用例文本或指定某几条标题；指定标题时只处理 xmind 中真实存在的节点
- 信息缺失（账号、测试数据、期望值无法确定）时集中问一次，其余按仓库约定推断

## 项目隔离（每次只生成一个项目的代码）

每次执行只对应一个项目（一个 xmind / 一个被测系统），不同项目的代码与数据互不混用。项目用 slug 区分：优先沿用已有目录名；新建时取项目名的英文或拼音小写（如 `dongying`），仅含字母、数字、下划线。

```text
pages/<slug>/                     项目页面对象（含 __init__.py）
testcases/<slug>/                 项目用例（含 __init__.py）
data/<slug>/caseData.xlsx         项目专属 Excel，只含本项目 sheet
pages/base_page.py、conftest.py、utils/、config/   全项目共用，不改
```

- 新建项目：创建上述三个目录与 `__init__.py`；Excel 新建 workbook（通用列 + 本项目业务列），不复制其他项目的 sheet 与业务常量
- 已有项目：只在原文件追加，保持既有 case_id 编号与 Excel 行，不重排、不并入其他项目
- 读数据必须显式指定本项目 workbook：`read_cases("policy", workbook="data/<slug>/caseData.xlsx")`，不要依赖 `config.yaml` 的全局 `excel.path`
- 只改本项目目录内的文件；确需改动共用层（`conftest.py`、`utils/`、`config/`）时在交付说明里写明原因
- 运行范围限定本项目：`pytest testcases\<slug>`
- 交付时写清本项目的目录、数据文件与运行命令，不声称覆盖了其他项目

## 一、解析

xmind 是 zip 包，主题树在 `content.json` 中（顶层可能是 sheet 列表，也可能是 `{"sheets": [...]}`），旧文件可能只有 `content.xml`。解析细节与可直接运行的脚本见 [xmind-parsing.md](references/xmind-parsing.md)。

识别规则（按语义，不硬扣层级名）：

| 语义 | 识别方式 |
|---|---|
| 根主题 | sheet 的 `rootTopic.title`，通常是项目名 |
| 模块 | 根主题下一层，通常为业务模块名 |
| 用例 | 模块下一层，标题常带 `tc-`/`tc‑p1：` 前缀 |
| 步骤 | 用例的子主题，常以 `步骤N：` 开头或无编号的动作描述 |
| 预期结果 | 步骤的子主题，以 `预期结果：` 开头；也可能直接挂在用例下 |
| 前置条件 / 备注 | `notes`、`labels` 或“前置条件”节点 |
| 优先级 | `markers`（priority-1~7）→ severity blocker~trivial |

必须做归一化：

- 全角/不换行连字符 `‑`(U+2011)、全角逗号、全角括号统一为 ASCII
- 日期统一 `YYYY-MM-DD`
- 去掉 `tc-`、`tc‑p1：`、`步骤N：`、`预期结果：` 等前缀后再落到数据
- 标题完全相同的节点视为重复用例，去重后只保留一条且不占编号

## 二、拆分与归类

1. 每条用例拆成单一验证点；同一业务流有 2 组以上数据时合并为一条数据驱动用例
2. 用例编号沿用业务前缀（如 `policy_`、`order_`）；**已有编号保持不变**，新用例从该前缀最大编号 +1 顺延
3. 用例标题拆为「场景」与「校验点」：`story` 用场景，`title` 保留完整标题
4. 预期结果是自然语言，逐条翻译成可执行断言。无法翻译的期望（依赖人工判断、无页面表现）集中问用户，不臆造断言

## 三、落地

1. **页面对象**：先查 `pages/<slug>/`、`pages/` 是否已有可复用页面对象。新增时放 `pages/<slug>/<module>_page.py`，类名 `<Module>Page` 继承 `BasePage`；选择器写成类常量，动作方法返回 `self`，只封装操作与等待，业务断言留在用例层
2. **Excel 数据**：写入 `data/<slug>/caseData.xlsx` 对应业务 sheet，列规范见 [framework-integration.md](references/framework-integration.md)；新增行不覆盖既有行
3. **用例**：放在 `testcases/<slug>/test_<module>.py`，函数名 `test_<行为>`，`parametrize(ids=case_id)` + `allure.dynamic` 中文元数据 + `execution_recorder.set_title`
4. **marker**：复用已注册 marker；新增 marker 必须先写入 `pytest.ini` 的 `markers`
5. **等待与定位**：Playwright 自动等待 + `expect`，禁止绝对 XPath、长 `nth-child` 链、`time.sleep`；确有异步回填/接口刷新时，用业务标志元素或 `wait_for_function` 等待，不用固定毫秒裸等
6. **验证**：`$env:HEADLESS='true'; & '.venv\Scripts\python.exe' -m pytest testcases\<slug> -q --reruns 0`，全绿才算完成；失败先修定位与等待，禁止放宽、跳过或删除断言
7. **交付**：列出新增/修改文件、用例数、执行结果表、报告路径（`reports/execution-report.html`、`reports/junit.xml`）

## 四、格式参考样例

[xmind 参考样例](references/dongying-reference.md) 以「东营惠民保自动化测试.xmind」为例，完整展示了：

- 固定格式写法（`tc‑p1：个单投保‑<场景>‑<校验>`、步骤与预期结果的挂载方式）
- 从 11 个主题去重为 10 条用例、并映射到 `policy_001~010` 的过程
- 该模块的 Excel 列、保费/浮层规则、步骤→页面方法映射与踩坑记录

只在处理个单投保（policy）用例时参考其中业务常量；其他模块只借鉴格式与分析方法。

## 约束

- 不为单个用例改 `conftest.py` 核心 fixture；需要扩展时在交付说明里写明原因
- 不硬编码 `base_url`、账号、密码；测试数据只放本项目 Excel
- 不删除或重命名已有页面对象、用例、Excel 行；不为 xmind 之外的场景补用例
- 一次执行只落一个项目，不把 A 项目的用例、数据、页面对象写进 B 项目
- 一条 pytest 用例只对应一个验证点，多组数据走 Excel
- 代码注释、用例标题、Allure 文案使用中文

## 参考

- [xmind-parsing.md](references/xmind-parsing.md) — XMind 包结构、解析脚本、层级识别与归一化
- [framework-integration.md](references/framework-integration.md) — Excel/pytest/Allure/POM 集成约定与代码模板
- [dongying-reference.md](references/dongying-reference.md) — 东营惠民保 xmind 作为格式参考的完整实例
