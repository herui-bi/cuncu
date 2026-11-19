---
name: testcase-to-ui-code
description: Convert Excel or document test cases into Playwright pytest UI code for this POM framework, including page objects, Excel data rows, and Allure metadata. Use when asked to turn 测试用例 into automation scripts. Do not use for API tests.
---

# 测试用例转 UI 自动化代码

把手工测试用例落地为本仓库既有分层下的可运行用例。保持现有风格，不另起一套结构。

## 输入

- Excel（优先 `data/caseData.xlsx`）、Markdown/Word 文档，或用户直接粘贴的用例文本
- 用例通常包含前置条件、操作步骤、预期结果；同一流程可能附带多组测试数据
- 信息缺失时只集中问一次，其余按仓库约定推断

## 流程

1. 拆分：每条用例拆成单一验证点。同一业务流有 2 组以上数据时走 Excel 数据驱动；否则写独立 pytest 用例。
2. 定位：先查 `pages/` 是否已有页面对象可复用。新增页面时用 Playwright MCP（`mcp_Playwright`）打开真实系统确认定位器。
3. 页面对象：放在 `pages/<module>_page.py`，类名 `<Module>Page`，继承 `BasePage`。选择器写成类常量，动作方法返回 `self`，只封装操作与等待，业务断言留在用例中（加载校验可参考 `InventoryPage.wait_loaded`）。
4. 用例：放在 `testcases/test_<module>.py`，函数名 `test_<行为>`。必须带业务 marker，新 marker 先注册进 `pytest.ini`。Allure 的 feature/story/title/severity 使用中文。
5. fixture：需要已登录页面用 `logged_in_page`；需要登录页交互用 `login_page`。地址与账号从 `config` 读取，禁止硬编码。
6. Excel 驱动：数据追加到对应业务 sheet，列结构遵循 `references/framework-contract.md`；用例用 `read_cases(sheet)` + `parametrize(ids=case_id)` + `allure.dynamic`。
7. 验证：`.venv\Scripts\python.exe -m pytest <file> --reruns 0`。失败先修定位或等待，不得放宽、跳过或删除断言。
8. 交付：列出新增/修改的文件、运行命令、新增数据行说明。

## 定位与等待规则

- 优先 `get_by_role` / `get_by_label` / `get_by_test_id`，其次稳定 CSS 或 `data-test` 属性
- 禁止绝对 XPath、长 nth-child 链、`time.sleep` 和固定毫秒等待
- 统一使用 Playwright 自动等待与 `expect`

## 约束

- 不为单个用例改动 `conftest.py` 的核心 fixture；确需扩展时在回复中说明原因
- 不硬编码 `base_url`、账号、密码、环境地址
- 不删除或重命名已有页面对象、用例、Excel 行
- 一条 pytest 用例只对应一个验证点，多组数据放 Excel
- 代码注释、用例标题、Allure 文案使用中文

## 参考

- `references/framework-contract.md` — 分层职责、fixture 清单、marker、命名与 Excel 列规范
- `references/templates.md` — 页面对象、普通用例、Excel 数据驱动用例与追加数据行的模板
