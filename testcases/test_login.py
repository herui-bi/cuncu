"""登录用例：Excel 数据驱动（登录成功 / 异常账号 / 必填校验）。"""

from __future__ import annotations

import re

import allure
import pytest
from playwright.sync_api import expect

from pages.login_page import LoginPage
from utils.excel_reader import read_cases

LOGIN_CASES = read_cases("login")


@pytest.mark.excel
@pytest.mark.login
@pytest.mark.parametrize(
    "case",
    LOGIN_CASES,
    ids=[case.get("case_id") or f"row-{index}" for index, case in enumerate(LOGIN_CASES, 1)],
)
def test_login(page, case):
    allure.dynamic.feature(case.get("feature") or "登录")
    allure.dynamic.story(case.get("story") or "账号登录")
    allure.dynamic.title(f'{case.get("case_id", "")} {case.get("title", "")}'.strip())
    allure.dynamic.severity(case.get("severity") or "normal")

    login = LoginPage(page)
    login.open()
    login.login(case["username"], case["password"])

    if case["expected"].lower() == "success":
        expect(page).to_have_url(re.compile(r".*/inventory\.html"))
        expect(page.locator(".title")).to_have_text("Products")
    else:
        expect(login.error_locator).to_be_visible()
        expected_message = case.get("expected_message", "")
        if expected_message:
            assert expected_message in login.error_message()
