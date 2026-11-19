# 代码模板

下面的模板以“订单模块”为例，实际使用时替换模块名、定位器与业务列。

## 页面对象

```python
"""订单页面对象。"""

from pages.base_page import BasePage


class OrderPage(BasePage):
    TITLE = ".page-title"
    SEARCH_INPUT = "[data-test='order-search']"
    SEARCH_BUTTON = "[data-test='order-search-submit']"
    RESULT_ROW = ".order-row"
    RESULT_TEXT = ".order-row .order-no"
    ERROR_MESSAGE = ".alert-error"

    def wait_loaded(self) -> "OrderPage":
        self.expect_text(self.TITLE, "订单管理")
        return self

    def search(self, keyword: str) -> "OrderPage":
        self.fill(self.SEARCH_INPUT, keyword, "订单号")
        self.click(self.SEARCH_BUTTON, "查询按钮")
        return self

    def result_count(self) -> int:
        return self.page.locator(self.RESULT_ROW).count()

    def result_text(self) -> str:
        return self.page.locator(self.RESULT_TEXT).first.inner_text()

    def error_message(self) -> str:
        return self.text(self.ERROR_MESSAGE)
```

## 普通用例（单组数据）

```python
"""订单查询用例。"""

import allure
import pytest
from playwright.sync_api import expect

from pages.order_page import OrderPage


@pytest.mark.smoke
@pytest.mark.order
@allure.feature("订单")
@allure.story("订单查询")
@allure.title("按订单号查询返回唯一结果")
@allure.severity(allure.severity_level.CRITICAL)
def test_search_order_by_number(logged_in_page):
    order = OrderPage(logged_in_page).wait_loaded()
    order.search("SO-20261027-001")

    expect(order.page.locator(order.RESULT_ROW).first).to_be_visible()
    assert order.result_count() == 1
    assert "SO-20261027-001" in order.result_text()
```

注意：`order`、`smoke` 等 marker 必须先写入 `pytest.ini` 的 `markers`，否则 `--strict-markers` 会直接报错。

## Excel 数据驱动用例

```python
"""订单查询用例（Excel 数据驱动）。"""

import allure
import pytest
from playwright.sync_api import expect

from pages.order_page import OrderPage
from utils.excel_reader import read_cases

CASES = read_cases("order")


@pytest.mark.excel
@pytest.mark.order
@pytest.mark.parametrize(
    "case",
    CASES,
    ids=[case.get("case_id") or f"row-{index}" for index, case in enumerate(CASES, 1)],
)
def test_search_order_by_excel(logged_in_page, case):
    allure.dynamic.feature(case.get("feature") or "订单")
    allure.dynamic.story(case.get("story") or "订单查询")
    allure.dynamic.title(f'{case.get("case_id", "")} {case.get("title", "")}'.strip())
    allure.dynamic.severity(case.get("severity") or "normal")

    order = OrderPage(logged_in_page).wait_loaded()
    order.search(case["order_no"])

    if case["expected"].lower() == "success":
        expect(order.page.locator(order.RESULT_ROW).first).to_be_visible()
        assert case["order_no"] in order.result_text()
    else:
        expect(order.page.locator(order.ERROR_MESSAGE)).to_be_visible()
        expected_message = case.get("expected_message", "")
        if expected_message:
            assert expected_message in order.error_message()
```

## 追加 Excel 数据行

在项目根目录执行，按表头映射追加，避免列顺序不一致：

```python
from openpyxl import load_workbook

path = "data/caseData.xlsx"
workbook = load_workbook(path)
sheet = workbook["order"]
headers = [cell.value for cell in sheet[1]]

row = {
    "case_id": "order_001",
    "title": "按订单号查询成功",
    "feature": "订单",
    "story": "订单查询",
    "severity": "critical",
    "order_no": "SO-20261027-001",
    "expected": "success",
    "expected_message": "",
    "enabled": "Y",
}
sheet.append([row.get(header, "") for header in headers])
workbook.save(path)
```

新建 sheet 时先写第一行表头，再追加数据行：

```python
from openpyxl import load_workbook

path = "data/caseData.xlsx"
workbook = load_workbook(path)
sheet = workbook.create_sheet("order")
sheet.append(["case_id", "title", "feature", "story", "severity", "order_no", "expected", "expected_message", "enabled"])
workbook.save(path)
```
