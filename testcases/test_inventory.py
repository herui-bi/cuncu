"""商品与购物车用例：演示 POM + 登录态 fixture 的常规写法。"""

from __future__ import annotations

import allure
import pytest

from pages.inventory_page import InventoryPage


@pytest.mark.smoke
@pytest.mark.inventory
@allure.feature("商品")
@allure.story("购物车")
@allure.title("登录后可查看商品列表并加入购物车")
@allure.severity(allure.severity_level.CRITICAL)
def test_add_first_item_to_cart(logged_in_page):
    inventory = InventoryPage(logged_in_page)
    names = inventory.item_names()
    allure.attach(
        "\n".join(names),
        name="商品列表",
        attachment_type=allure.attachment_type.TEXT,
    )

    assert inventory.item_count() > 0, "商品列表为空"
    inventory.add_first_item_to_cart()
    assert inventory.cart_count() == 1, "购物车角标数量不为 1"
