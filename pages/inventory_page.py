"""商品列表页对象（示例站点 saucedemo，内网系统按实际页面调整定位）。"""

from __future__ import annotations

from pages.base_page import BasePage


class InventoryPage(BasePage):
    TITLE = ".title"
    ITEM = ".inventory_item"
    ITEM_NAME = ".inventory_item_name"
    ITEM_BUTTON = "button"
    CART_BADGE = ".shopping_cart_badge"
    CART_LINK = ".shopping_cart_link"
    SORT_SELECT = "[data-test='product-sort-container']"

    def wait_loaded(self) -> "InventoryPage":
        self.expect_text(self.TITLE, "Products")
        return self

    def item_count(self) -> int:
        return self.page.locator(self.ITEM).count()

    def item_names(self) -> list[str]:
        return self.page.locator(self.ITEM_NAME).all_inner_texts()

    def add_first_item_to_cart(self) -> None:
        self.page.locator(self.ITEM).first.locator(self.ITEM_BUTTON).click()

    def cart_count(self) -> int:
        badge = self.page.locator(self.CART_BADGE)
        return int(badge.inner_text()) if badge.is_visible() else 0

    def sort_by(self, value: str) -> None:
        self.page.locator(self.SORT_SELECT).select_option(value)
