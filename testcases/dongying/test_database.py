"""数据库校验：按订单尾号定位分表，比对 share_code 与用例期望值。"""

from __future__ import annotations

import allure
import pytest

from utils.db import order_policy_table, query_order_policy
from utils.excel_reader import read_cases

# 仅取配置了订单号的用例，订单号由创建订单后回填
CASES = [
    case
    for case in read_cases("policy", workbook="data/dongying/caseData.xlsx")
    if case.get("order_no", "").strip()
]


@pytest.mark.smoke
@allure.feature("数据库")
@allure.story("分享码校验")
@allure.title("创建订单后按订单尾号查询 share_code 并与用例期望比对")
@pytest.mark.parametrize("case", CASES, ids=[case["case_id"] for case in CASES])
def test_order_share_code(case: dict[str, str]) -> None:
    order_no = case["order_no"].strip()
    expected = case.get("expected_share_code", "").strip()
    table = order_policy_table(order_no)

    row = query_order_policy(order_no, columns="order_no, share_code, status")
    allure.attach(
        f"分表：{table}\n订单数据：{row}",
        name="查询结果",
        attachment_type=allure.attachment_type.TEXT,
    )

    assert row is not None, f"{table} 中未找到订单 {order_no}"
    actual = row.get("share_code") or ""
    assert actual == expected, (
        f"订单 {order_no} 的 share_code 不符，期望 {expected!r}，实际 {actual!r}"
    )
