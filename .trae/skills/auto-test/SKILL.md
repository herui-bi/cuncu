---
name: "auto-test"
description: "Convert docs/testcases docs (.docx/.xmind/.md) to test cases and pytest UI automation, then run. Invoke when user says 需求文档生成用例、用例转代码 or 自动化测试 执行xxx."
---

# 自动化测试（用例文档 → 用例 → 脚本 → 执行 → 报告）

一句话触发（任选一句）：

- `/auto-test 执行 docs/testcases/东营惠民保2027投保对接 (1).docx`
- `/auto-test 把 docs/testcases/东营惠民保2027投保对接 (1).docx 生成测试用例并转成自动化代码`
- `/auto-test 东营惠民保2027 需求文档生成用例，用例转代码`

不写斜杠时也可说「根据 docs/testcases/xxx.docx 生成用例并转成自动化代码」。按下面 SOP 全链路执行，不要反复确认流程，只在遇到阻断问题时提问。

## 输入约定

- **用例来源固定为 `docs/testcases/` 目录**：用户消息中指定的文件名或关键词匹配该目录下的文档；未指定时列出目录内容（`.docx` / `.xmind` / `.md`），同一项目取最新修改的那份。
- 业务范围：只处理该文档涉及的模块；用户说「执行聊惠保」时不得连带跑东营或其他未涉及模块。
- 环境：从文档标题或项目名推断 `--env`（聊惠保 → `liaohuibao`，东营 → `dongying`），无法推断时用 `config/config.yaml` 的默认 env。

## 第 1 步：读取用例文档

1. 用项目自带解析器读取文档，不要凭文件名猜测内容：

```powershell
python utils/doc_reader.py "docs/testcases/东营惠民保2027投保对接 (1).docx"
```

覆盖 `.docx`（段落 + 表格，表格按 ` | ` 分隔单元格）、`.xmind`（节点层级缩进）、`.md`（原文）。解析结果直接作为用例来源。
2. 从文档中提取：项目/产品名、投保须知与规则、被保人规则、支付方式、报文与接口约定、用例或场景表格、期望结果。
3. 同时读取现有约定，确保新增代码与仓库一致：
   - `pytest.ini`（testpaths=`testcases`、`--browser chromium`、allure/junit/截图输出目录）
   - `config/environments/<项目>/<阶段>.yaml`、`config/config.yaml`
   - 已有页面对象 `pages/<project>/`、用例 `testcases/<project>/`、数据 `data/<project>/caseData.xlsx`
   - 通用工具 `utils/`（`excel_reader.read_cases`、`config_loader.get_config`、`doc_reader.read_document`）
4. 若项目已有同类页面对象与脚本，优先复用/补充，不要重复造轮子。

## 第 2 步：生成测试用例（文档 → 用例清单）

文档里的描述通常不是可直接执行的用例，必须先转成结构化用例再写代码：

1. 用例清单落盘到 `docs/testcases/<项目>_cases.md`（如 `docs/testcases/dongying2027_cases.md`），每条用例包含：
   - 用例编号（`<项目缩写>_001` 递增，全项目唯一）
   - 用例标题（业务可读，如「被保人年龄 17 岁可正常投保」）
   - 前置条件（登录态、环境、所需账号/身份）
   - 操作步骤（有序、可被页面操作一一对应）
   - 测试数据（可落到 `caseData.xlsx` 的字段：姓名、证件、关系、年龄、支付方式、期望值）
   - 预期结果（可断言的文本/元素/URL/接口字段）
   - 优先级与是否可自动化
2. 覆盖维度：正向流程、年龄边界、人数与关系上限、证件类型、保费与优惠、支付方式、协议勾选、异常提示。
3. 文档中无法自动化的条目（如人工审核、线下流程）保留在清单中并标注「人工验证」，不得静默丢弃。

## 第 3 步：校验用例完整性

逐条检查并在生成代码前输出校验结论（缺失项用清单列出）：

- 必填：用例编号、标题、操作步骤、预期结果。
- 测试数据可落地到 `caseData.xlsx` 且无自相矛盾（如出生日期与关系冲突、配偶人数超限）。
- 预期结果可被断言；不可断言的明确标注。
- 环境依赖齐全：入口地址、测试账号、验证码获取方式；缺失则在执行阶段定位并报告，不得伪造成功。
- 编号唯一、步骤可顺序执行、不依赖前一条用例未说明的残留状态。

存在阻断性缺失（无入口地址、无账号、预期为空）时，先列清单再执行能执行的部分。

## 第 4 步：用例转 pytest 脚本

按第 2 步的用例清单逐条落地到测试目录（本项目为 `testcases/<project>/`，等价于用户所说的 tests 目录），一条清单用例对应一条数据行 + 一个断言分支：

- 页面对象：`pages/<project>/xxx_page.py`，继承 `pages/base_page.py` 的 `BasePage`。
- 用例文件：`testcases/<project>/test_xxx.py`，使用 `pytest.mark.parametrize` + `read_cases(sheet, workbook="data/<project>/caseData.xlsx")` 做数据驱动。
- 测试数据：写入/更新 `data/<project>/caseData.xlsx` 对应 sheet，列名与用例字段一一对应，保留 `enabled` 开关。
- Allure 元数据：`@allure.epic/feature/story/title/severity`，标题与用例编号一致；用例清单里的「人工验证」条目跳过生成，但要在报告里列出。
- 代码与清单一致性：清单新增/修改后必须同步 Excel 与断言，禁止代码里有清单未覆盖的断言分支。
- 断言：所有预期结果必须落到断言；等待使用 Playwright `expect` / `wait_for_function`，禁止裸 `sleep` 兜底。
- 实名与账号：姓名/证件号会触发二要素（姓名 + 身份证号）校验，**禁止用 `generate_id_no` 生成投被保人身份冒充实名**。
  - 真实身份统一维护在 `data/verified_identities.csv`（`name,id_no,phone,note`），认证通过的成年人账号才能作缴费人。
  - 数据解析顺序：Excel 显式证件号 → 实名池按姓名匹配 → 回退生成号（仅限不触发实名的前端校验用例，且必须记录告警）。
  - 池中身份不足时向用户索要真实身份补充，不要编造。
- 登录态复用：首次执行完成缴费人注册后自动保存到 `auth/<env>_state.json`，后续执行直接注入登录态、跳过缴费人填写与短信验证；需要回归未登录流程时删除该文件或使用 `open_payer_form(fresh=True)`。
- 运行前自检：`python -m py_compile` 通过；新选择器先在页面确认存在。

## 第 5 步：执行 pytest

在仓库根目录执行（Windows PowerShell）：

```powershell
python -m pytest testcases/<project> -v --reruns 0
```

- 调试阶段显式加 `--reruns 0`，快速暴露真实失败；稳定后按 `pytest.ini` 默认重跑。
- 需要指定环境时追加 `--env <env>`。
- 出现失败先看 `reports/artifacts` 截图与 `reports/junit.xml` 定位，修复后重跑失败用例，再跑一次全量确认。
- 连续两次同类失败不要盲目重试，先判断是脚本问题、数据问题还是现网页面变更，并向用户说明结论。

## 第 6 步：输出报告与失败汇总

1. Allure 报告：

```powershell
allure generate reports/allure-results -o reports/allure-report --clean
```

若 `allure` CLI 不存在，保留 `reports/allure-results` 原始结果，并说明安装/查看方式；同时用 `reports/junit.xml` 生成文本汇总。

2. 失败原因与截图汇总：从 `reports/junit.xml` 提取失败/错误用例，读取 `<failure message="...">` / `<error message="...">` 作为失败原因；按用例名匹配 `reports/artifacts` 下的截图、trace、video 路径。项目自带 HTML 报告 `reports/execution-report.html` 会在失败用例卡片内展示「失败原因」区块，可直接查看。

3. 最终回复用户时给出简要表格：通过数 / 失败数 / 跳过数、失败用例编号 + 失败原因（断言消息或异常首行）+ 失败截图路径、报告路径（`reports/allure-report/index.html`、`reports/execution-report.html`、`reports/junit.xml`）。禁止只回「已执行完成」而不给结果。

4. 钉钉群通知：`.env` 中配置了 `DINGTALK_WEBHOOK` 时，`conftest.py` 会在会话结束自动推送结果到群，无需额外操作；未配置时提醒用户「在 .env 填入 DINGTALK_WEBHOOK 即可自动推送钉钉群」。

## 收尾

- 清理本次产生的临时探针脚本与中间日志，不删除用户文件。
- 不改动与本次用例无关的代码；不提交 git（除非用户明确要求）。
