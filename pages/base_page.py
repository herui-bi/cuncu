"""页面基类：封装常用操作与断言，统一日志和超时。"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from utils import execution_recorder
from utils.config_loader import get_config
from utils.logger import setup_logger

logger = setup_logger()


class BasePage:
    def __init__(self, page: Page):
        self.page = page
        self.config = get_config()
        self.page.set_default_timeout(self.config.default_timeout)
        self.page.set_default_navigation_timeout(self.config.navigation_timeout)

    def open(self, path: str = "") -> "BasePage":
        url = self.config.url(path)
        logger.info("打开页面: %s", url)
        execution_recorder.record("打开页面", url)
        self.page.goto(url)
        return self

    def click(self, selector: str, description: str = "") -> None:
        logger.info("点击: %s %s", description or selector, selector)
        execution_recorder.record("点击", description or selector)
        self.page.locator(selector).click()

    def fill(self, selector: str, value: str, description: str = "") -> None:
        logger.info("输入: %s %s", description or selector, selector)
        execution_recorder.record("输入", f"{description or selector} = {value}")
        self.page.locator(selector).fill(value)

    def text(self, selector: str) -> str:
        return self.page.locator(selector).inner_text()

    def is_visible(self, selector: str) -> bool:
        return self.page.locator(selector).is_visible()

    def wait_visible(self, selector: str) -> None:
        self.page.locator(selector).wait_for(state="visible")

    def wait_url(self, pattern: str) -> None:
        self.page.wait_for_url(pattern)

    def expect_visible(self, selector: str) -> None:
        expect(self.page.locator(selector)).to_be_visible()

    def expect_text(self, selector: str, text: str) -> None:
        expect(self.page.locator(selector)).to_have_text(text)

    def expect_url(self, pattern: str) -> None:
        expect(self.page).to_have_url(pattern)

    def screenshot(self, name: str) -> bytes:
        return self.page.screenshot(path=f"reports/artifacts/{name}.png", full_page=True)
