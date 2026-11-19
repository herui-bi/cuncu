# 接入本仓库的框架约定

## 一、分层职责

| 路径 | 职责 |
|---|---|
| `config/config.yaml`、`config/environments/<项目>/<阶段>.yaml` | 地址、浏览器参数、超时、默认 Excel 路径；禁止在用例里硬编码 |
| `utils/config_loader.py` | `get_config()` 单例，`config.url(path)` 拼地址 |
| `utils/excel_reader.py` | `read_cases(sheet, workbook)` → `list[dict[str, str]]`，跳过 `enabled != Y` 的行 |
| `utils/execution_recorder.py` | `start` / `record` / `finish` / `set_title`，执行过程进报告 |
| `utils/id_card.py` 等业务工具 | 生成合法测试数据，避免手编超长数字 |
| `pages/base_page.py` | `open` / `click` / `fill` / `text` / `is_visible` / `wait_visible` / `expect_*` / `screenshot` |
| `pages/<slug>/<module>_page.py` | 项目页面对象：选择器常量 + 动作方法（返回 `self`），不做业务断言 |
| `testcases/<slug>/test_<module>.py` | 项目用例：数据驱动 + 业务断言 + Allure 元数据 |
| `data/<slug>/caseData.xlsx` | 项目专属测试数据，只含本项目 sheet |
| `conftest.py` | `page` / `config` / 登录态 fixture、失败截图、会话结束汇总与报告 |

## 二、Excel 数据表

- 每个项目独立的 `data/<slug>/caseData.xlsx`，一个业务模块一个 sheet；表头即 `read_cases` 返回 dict 的键，列顺序与列名稳定，不随意改名
- 读取时显式传入本项目文件：`read_cases("policy", workbook="data/<slug>/caseData.xlsx")`；`workbook` 支持绝对路径或仓库根目录相对路径，缺省才回退 `config.yaml` 的 `excel.path`
- 通用列（固定在前）：`case_id`、`title`、`feature`、`story`、`severity`、`enabled`
- 业务列按模块追加，如账号密码、被保人信息、订单号；可复用业务列再按场景加期望列
- 多值字段约定：
  - 列表型字段（姓名、日期、计划）用英文逗号 `,` 分隔，个数必须对齐，代码里断言长度一致
  - 集合型期望（可选版本等）用竖线 `|` 分隔，避免与列表字段混淆
- 期望值留空的语义必须写进代码并说明：例如 `expected_*` 为空表示“只回显实际值，不做严格断言”，避免因空值造成假失败
- 测试数据（姓名、证件号、金额）只放 Excel，不写进测试函数

## 三、用例写法

```python
CASES = read_cases("policy", workbook="data/<slug>/caseData.xlsx")


def _cases(*test_types: str) -> list[dict[str, str]]:
    return [case for case in CASES if case.get("test_type") in test_types]


@pytest.mark.policy
@pytest.mark.parametrize("case", _cases("premium"), ids=[c["case_id"] for c in _cases("premium")])
def test_upgrade_premium_discount(page, case):
    allure.dynamic.feature(case["feature"])
    allure.dynamic.story(case["story"])
    allure.dynamic.title(f'{case["case_id"]} {case["title"]}')
    allure.dynamic.severity(case["severity"])
    execution_recorder.set_title(f'{case["case_id"]} {case["title"]}')

    policy = IndividualPolicyPage(page).open_payer_form()
    _register(policy, case)          # 公共前置流程
    people = _people(case)

    with allure.step("校验各被保人保障计划"):
        ...
```

要求：

- 函数名 `test_<行为>`，文件 `testcases/<slug>/test_<module>.py`，新 marker 先注册进 `pytest.ini`
- `parametrize(ids=case_id)`，Allure 元数据用中文
- 每个与预期结果对应的校验放在独立 `allure.step` 中，断言失败信息写清“期望 / 实际”
- 关键节点 `allure.attach(page.screenshot(), ...)` 保留现场
- 公共流程（注册、登录、下单等）抽成模块内私有函数，不在每条用例里复制

## 四、页面对象写法

```python
class XxxPage(BasePage):
    CARD = ".xxx:visible"

    def __init__(self, page: Page) -> None:
        super().__init__(page)

    def open_form(self) -> "XxxPage":
        self.open()
        self.page.locator("input[placeholder='请输入姓名']").first.wait_for(state="visible")
        return self

    def fill_field(self, value: str) -> "XxxPage":
        field = self.page.locator("input[placeholder='请输入姓名']").first
        field.fill(value)
        expect(field).to_have_value(value)
        execution_recorder.record("填写姓名", value)
        return self
```

要求：

- 选择器优先 `get_by_role` / `get_by_label` / `get_by_test_id`，其次稳定 CSS / `data-*`；禁止绝对 XPath 与长 `nth-child` 链
- 方法只做操作与等待，断言留给用例；确需前置校验（如元素已加载）可保留最小 `expect`
- 异步刷新（接口回填、卡片动态插入）用 `wait_for_function` 或业务标志元素等待，禁止 `time.sleep` 与裸固定毫秒等待
- 每个动作写 `execution_recorder.record`，保证报告能还原执行过程

## 五、运行与产物

```powershell
$env:HEADLESS='true'
& '.venv\Scripts\python.exe' -m pytest testcases\<slug> -q --reruns 0
# 单条
& '.venv\Scripts\python.exe' -m pytest testcases\<slug> -k "policy_006" -q --reruns 0
```

- 只跑本项目目录，避免把其他项目的用例一起带进回归
- 结果汇总、`reports/execution-report.html`、`reports/junit.xml` 由 `conftest.py` 自动产出
- 失败先看 traceback 与失败截图：定位错就改选择器，时序问题就改成业务等待；不得放宽断言、加 `skip`、删用例
- 全量跑批前确认用例不会相互污染（重复下单、共享账号历史数据等）

## 六、约束

- 不改 `conftest.py` 核心 fixture；确需扩展时在交付说明写明原因
- 项目之间不共享用例、页面对象、Excel 与 case_id 编号；每次只改 `pages/<slug>/`、`testcases/<slug>/`、`data/<slug>/` 下的文件
- 不删除或重命名已有页面对象、用例、Excel 行
- 一条用例只验一个点；多组数据放 Excel
- 代码注释、用例标题、Allure 文案使用中文
