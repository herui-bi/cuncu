"""登录页对象（示例站点 saucedemo，内网系统按实际页面调整定位）。"""

from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage


class LoginPage(BasePage):
    USERNAME_INPUT = "#user-name"
    PASSWORD_INPUT = "#password"
    LOGIN_BUTTON = "#login-button"
    ERROR_MESSAGE = "[data-test='error']"
    LOGIN_LOGO = ".login_logo"

    def open(self) -> "LoginPage":
        super().open(self.config.login_path)
        self.wait_visible(self.LOGIN_BUTTON)
        return self

    def login(self, username: str, password: str) -> "LoginPage":
        self.fill(self.USERNAME_INPUT, username, "用户名")
        self.fill(self.PASSWORD_INPUT, password, "密码")
        self.click(self.LOGIN_BUTTON, "登录按钮")
        return self

    @property
    def error_locator(self) -> Locator:
        return self.page.locator(self.ERROR_MESSAGE)

    def error_message(self) -> str:
        return self.error_locator.inner_text()
