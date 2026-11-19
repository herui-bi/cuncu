"""惠衢保 2027 订单升级（7.0 二期）页面对象。

覆盖：H5 短信登录、订单列表状态页签与订单卡片、订单详情被保人行、
保障方案升级页（被保人行程、可升级方案单选、退款说明、需支付金额、
协议勾选与一键升级校验提示）。
"""

from __future__ import annotations

import json
import re
import time
from decimal import Decimal

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError, expect

from pages.base_page import BasePage
from utils import execution_recorder

# 测试环境固定短信验证码
SMS_CODE = "888888"

# 惠衢保 7.0 二期项目号，网关接口需携带 x-insure-projectcode
PROJECT_CODE = "CITY000110-1"

# 微信支付 mock：JSAPI 回调直接返回成功，H5 支付链接跳转回支付成功页
WECHAT_PAY_MOCK_JS = """
(() => {
  const okBridge = (cb) => setTimeout(() => cb && cb({err_msg: 'get_brand_wcpay_request:ok'}), 50);
  window.WeixinJSBridge = {
    invoke: (api, params, cb) => {
      if (api === 'getBrandWCPayRequest') { okBridge(cb); }
      else if (cb) { setTimeout(() => cb({err_msg: api + ':ok'}), 0); }
    },
    on: () => {},
    call: () => {}
  };
  window.wx = window.wx || {};
  window.wx.config = () => {};
  window.wx.ready = (cb) => setTimeout(cb, 0);
  window.wx.error = () => {};
  document.dispatchEvent(new Event('WeixinJSBridgeReady'));
})();
"""


def _money(value: Decimal) -> str:
    """金额转页面展示文本：0.02 → 0.02，0.00 → 0。"""
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


class OrderUpgradePage(BasePage):
    NOTICE_CONFIRM = "我知道了"
    ORDER_CARD = ".orderList .order"
    DETAIL_CONTAINER = ".orderDetail"
    DETAIL_STATUS = ".detail-header h3"
    UPGRADE_CONTAINER = ".ordersUpgrade"
    UPGRADE_ROW = ".upgrade-card .card-row"
    PLAN_ITEM = ".col-upgrade .radio-item"

    def __init__(self, page: Page):
        super().__init__(page)
        self.payer_name = page.locator("input[placeholder='请输入姓名']").first
        self.payer_id_no = page.locator("input[placeholder='请输入身份证号']").first
        self.payer_phone = page.locator("input[placeholder='请输入手机号码']").first
        self.sms_code = page.locator("input[placeholder='请输入验证码']").first

    # ---------- 登录 ----------
    def open_home(self) -> "OrderUpgradePage":
        super().open()
        quick_login = self.page.locator(".van-dialog").filter(has_text="快速注册或登录")
        try:
            if quick_login.count() and quick_login.first.is_visible():
                quick_login.first.get_by_text("手动注册登录", exact=True).click()
                expect(quick_login.first).to_be_hidden()
        except Exception:  # 未出现快速登录弹窗时忽略
            pass
        self.payer_name.wait_for(state="visible")
        self.hide_debug_panel()
        return self

    def hide_debug_panel(self) -> None:
        """隐藏 vConsole 调试浮层，避免遮挡元素。"""
        self.page.evaluate(
            "() => { const el = document.querySelector('#__vconsole'); if (el) el.style.display='none'; }"
        )

    def login_with_verified_identity(
        self,
        name: str,
        id_no: str,
        phone: str,
        sms_code: str = SMS_CODE,
    ) -> "OrderUpgradePage":
        """使用实名身份完成 H5 短信快速注册/登录。"""
        self.open_home()
        if self.page.evaluate("() => !!localStorage.getItem('token')"):
            execution_recorder.record("已存在登录态", "跳过登录")
            return self

        self.payer_name.click()
        notice = self.page.get_by_text(self.NOTICE_CONFIRM)
        if notice.count():
            notice.first.click()
            expect(notice.first).to_be_hidden()
            execution_recorder.record("关闭投保须知弹窗")

        self.payer_name.fill(name)
        self.payer_id_no.fill(id_no)
        self.payer_phone.fill(phone)
        assert self.payer_name.input_value() == name, "缴费人姓名未写入"
        assert self.payer_id_no.input_value() == id_no, "缴费人证件号未写入"
        assert self.payer_phone.input_value() == phone, "缴费人手机号未写入"
        execution_recorder.record("填写缴费人信息", f"{name} / {id_no} / {phone}")

        self.page.locator("body").click(position={"x": 10, "y": 300})
        self.page.get_by_text("获取验证码", exact=True).first.click()
        expect(self.page.get_by_text(re.compile(r"\d+s\s*重新发送"))).to_be_visible()
        execution_recorder.record("获取短信验证码")

        self.sms_code.fill(sms_code)
        assert self.sms_code.input_value() == sms_code, "短信验证码未写入"
        self.page.locator("body").click(position={"x": 10, "y": 300})

        confirm = self.page.locator(".van-dialog__confirm")
        confirm.wait_for(state="visible")
        confirm.click()
        self.page.wait_for_function("() => !!localStorage.getItem('token')")
        execution_recorder.record("短信快速登录成功", f"手机号 {phone}")
        return self

    # ---------- 订单列表 ----------
    def open_orders(self) -> "OrderUpgradePage":
        url = re.sub(r"#/.*$", "#/orders", self.config.base_url)
        self.page.goto(url)
        self.page.locator(self.ORDER_CARD).first.wait_for(state="visible")
        self.hide_debug_panel()
        execution_recorder.record("进入订单列表页", url)
        return self

    def switch_status(self, status: str) -> "OrderUpgradePage":
        """切换订单状态页签（全部/待支付/已支付/部分退款/已退款/已取消）。"""
        tab = self.page.locator(".van-tab").filter(has_text=status).first
        tab.click()
        expect(tab).to_have_class(re.compile("van-tab--active"))
        self.page.locator(self.ORDER_CARD).first.wait_for(state="visible")
        execution_recorder.record("切换订单状态页签", status)
        return self

    def switch_status_soft(self, status: str, timeout: int = 8000) -> list[str]:
        """切换页签并返回订单号；页签为空时返回空列表，不抛超时。"""
        tab = self.page.locator(".van-tab").filter(has_text=status).first
        tab.click()
        expect(tab).to_have_class(re.compile("van-tab--active"))
        try:
            self.page.locator(self.ORDER_CARD).first.wait_for(state="visible", timeout=timeout)
        except PlaywrightTimeoutError:
            execution_recorder.record("切换订单状态页签（无订单）", status)
            return []
        execution_recorder.record("切换订单状态页签", status)
        return self.order_numbers()

    def order_card(self, order_no: str) -> Locator:
        card = self.page.locator(self.ORDER_CARD).filter(has_text=order_no).first
        card.wait_for(state="visible")
        return card

    def order_numbers(self) -> list[str]:
        """当前状态页签下所有订单号（按卡片顺序）。"""
        texts = self.page.locator(self.ORDER_CARD).all_inner_texts()
        return [match.group(0) for match in (re.search(r"[A-Z]\d{15,}", text) for text in texts) if match]

    def card_buttons(self, order_no: str) -> list[str]:
        card = self.order_card(order_no)
        return [text.strip() for text in card.locator("button").all_inner_texts() if text.strip()]

    def open_order_detail(self, order_no: str) -> "OrderUpgradePage":
        with self.page.expect_response(lambda r: "/core/order/detail" in r.url and r.ok):
            self.order_card(order_no).get_by_text("查看详情", exact=True).first.click()
        return self._wait_detail_loaded(order_no)

    def open_order_detail_direct(self, order_no: str) -> "OrderUpgradePage":
        """无「查看详情」入口的订单（如待支付）通过路由直接打开详情。"""
        url = re.sub(r"#/.*$", f"#/orderDetail?orderNo={order_no}", self.config.base_url)
        self.page.goto(url)
        return self._wait_detail_loaded(order_no)

    def _wait_detail_loaded(self, order_no: str) -> "OrderUpgradePage":
        expect(self.page).to_have_url(re.compile(r"#/orderDetail\?orderNo="))
        self.page.locator(self.DETAIL_CONTAINER).wait_for(state="visible")
        # 详情接口返回后 Vue 才渲染状态与被保人数据，等标题与非空状态出现再断言
        self.page.wait_for_function(
            "() => { const el = document.querySelector('.detail-header h3');"
            " return el && el.innerText.trim().length > 0; }"
        )
        self.page.locator("dl.userInfo").nth(1).locator("dd").first.wait_for(state="visible")
        self.page.wait_for_function(
            "() => { const dds = document.querySelectorAll("
            "'.orderDetail dl.userInfo')[1].querySelectorAll('dd');"
            " return Array.from(dds).every(dd => {"
            " const b = dd.querySelector('.order-info b');"
            " const i = dd.querySelector('.order-info i');"
            " return b && b.innerText.trim() && i && i.innerText.trim(); }); }"
        )
        self.hide_debug_panel()
        execution_recorder.record("打开订单详情", order_no)
        return self

    # ---------- 订单详情 ----------
    def detail_status(self) -> str:
        return self.page.locator(self.DETAIL_STATUS).inner_text().strip()

    def _insured_items(self) -> Locator:
        blocks = self.page.locator("dl.userInfo")
        assert blocks.count() >= 2, "订单详情未渲染被保人区块"
        return blocks.nth(1).locator("dd")

    def insured_count(self) -> int:
        return self._insured_items().count()

    def insured_name(self, index: int) -> str:
        return self._insured_items().nth(index).locator(".order-info b").inner_text().strip()

    def insured_status(self, index: int) -> str:
        return self._insured_items().nth(index).locator(".order-info i").inner_text().strip()

    def insured_buttons(self, index: int) -> list[str]:
        item = self._insured_items().nth(index)
        return [
            text.strip()
            for text in item.locator(".bottom-btn .todo-btn").all_inner_texts()
            if text.strip()
        ]

    def wait_insured_buttons(self, index: int, expected: list[str], timeout: int = 10000) -> None:
        """等待被保人操作按钮渲染完成（详情接口返回后按钮异步渲染）。"""
        item = self._insured_items().nth(index)
        if expected:
            expect(item.locator(".bottom-btn .todo-btn").first).to_be_visible(timeout=timeout)
        else:
            expect(item.locator(".bottom-btn .todo-btn")).to_have_count(0, timeout=timeout)

    def first_upgradeable_insured(self, timeout: int = 15000) -> int | None:
        """返回第一位展示「升级保障」按钮的被保人下标，已退款被保人会被跳过。"""
        try:
            self.page.wait_for_function(
                "() => { const blocks = document.querySelectorAll('.orderDetail dl.userInfo');"
                " const dds = blocks[1] ? blocks[1].querySelectorAll('dd') : [];"
                " return Array.from(dds).some(dd => {"
                " const st = dd.querySelector('.order-info i');"
                " const refunded = st && st.innerText.includes('已退款');"
                " return !refunded && Array.from(dd.querySelectorAll('.bottom-btn .todo-btn'))"
                "   .some(b => b.innerText.trim() === '升级保障'); }); }",
                timeout=timeout,
            )
        except Exception:  # 无升级入口时回落到直接扫描
            pass
        for index in range(self.insured_count()):
            if "升级保障" in self.insured_buttons(index):
                return index
        return None

    def click_insured_upgrade(self, index: int = 0) -> "OrderUpgradePage":
        """从订单详情某位被保人点击「升级保障」，只带该被保人进入升级页。"""
        item = self._insured_items().nth(index)
        name = self.insured_name(index)
        item.get_by_text("升级保障", exact=True).first.click()
        self.wait_upgrade_page()
        execution_recorder.record("详情页点击被保人「升级保障」", name)
        return self

    # ---------- 升级页 ----------
    def wait_upgrade_page(self) -> "OrderUpgradePage":
        expect(self.page).to_have_url(re.compile(r"#/ordersUpgrade\?orderNo="))
        self.page.locator(self.UPGRADE_CONTAINER).wait_for(state="visible")
        self.page.locator(self.UPGRADE_ROW).first.wait_for(state="visible")
        self.hide_debug_panel()
        execution_recorder.record("进入保障方案升级页", self.page.url)
        return self

    def open_upgrade_from_list(self, order_no: str) -> "OrderUpgradePage":
        self.order_card(order_no).get_by_text("升级保障", exact=True).first.click()
        self.wait_upgrade_page()
        execution_recorder.record("订单列表点击「升级保障」", order_no)
        return self

    def upgrade_rows(self) -> Locator:
        return self.page.locator(self.UPGRADE_ROW)

    def upgrade_row_count(self) -> int:
        return self.upgrade_rows().count()

    def row_insured_name(self, row: int) -> str:
        return self.upgrade_rows().nth(row).locator(".col-name").inner_text().strip()

    def row_current_plan(self, row: int) -> str:
        return self.upgrade_rows().nth(row).locator(".col-current p").inner_text().strip()

    def row_plans(self, row: int) -> list[str]:
        return [
            text.strip().splitlines()[0]
            for text in self.upgrade_rows().nth(row).locator(self.PLAN_ITEM).all_inner_texts()
            if text.strip()
        ]

    def row_plan_price(self, row: int, plan: str) -> Decimal:
        item = self.upgrade_rows().nth(row).locator(self.PLAN_ITEM).filter(has_text=plan).first
        return self._parse_amount(item.locator(".price").inner_text())

    def select_plan(self, row: int, plan: str) -> "OrderUpgradePage":
        item = self.upgrade_rows().nth(row).locator(self.PLAN_ITEM).filter(has_text=plan).first
        item.scroll_into_view_if_needed()
        item.click()
        execution_recorder.record("点击升级方案", f"第{row + 1}位被保人 {plan}")
        return self

    def expect_plan_selected(self, row: int, plan: str, selected: bool = True) -> None:
        icon = self.upgrade_rows().nth(row).locator(self.PLAN_ITEM).filter(has_text=plan).first.locator(
            ".radio-icon"
        )
        if selected:
            expect(icon).to_have_class(re.compile(r"\bchecked\b"))
        else:
            expect(icon).not_to_have_class(re.compile(r"\bchecked\b"))
        execution_recorder.record(
            "校验方案选中状态", f'第{row + 1}位被保人 {plan} → {"选中" if selected else "未选中"}'
        )

    def selected_count(self) -> int:
        return self.page.locator(f"{self.UPGRADE_ROW} .radio-icon.checked").count()

    def amount_text(self) -> str:
        return self.page.locator(".amount").inner_text().strip()

    def amount_value(self) -> Decimal:
        return self._parse_amount(self.amount_text())

    def expect_amount(self, value: Decimal) -> None:
        expect(self.page.locator(".amount .price")).to_have_text(f"￥{_money(value)}")
        execution_recorder.record("校验需支付金额", f"￥{_money(value)}")

    def refund_tips(self) -> str:
        return re.sub(r"\s+", " ", self.page.locator(".tips").inner_text()).strip()

    def operation_tip(self) -> str:
        return self.page.locator(".tips-sub").inner_text().strip()

    def agreement_checked(self) -> bool:
        return self.page.locator(".agree-checkbox").first.get_attribute("aria-checked") == "true"

    def set_agreement(self, checked: bool) -> "OrderUpgradePage":
        box = self.page.locator(".agree-checkbox").first
        if self.agreement_checked() != checked:
            box.click()
        expect(box).to_have_attribute("aria-checked", "true" if checked else "false")
        execution_recorder.record("协议勾选状态", "已勾选" if checked else "未勾选")
        return self

    def click_upgrade(self) -> None:
        self.page.locator(".pay-btn").click()
        execution_recorder.record("点击「一键升级」")

    def click_upgrade_expect_toast(self, retries: int = 2) -> str:
        """点击「一键升级」并读取校验提示；上一条提示淡出期间点击可能被吞，按需重试。"""
        for _ in range(retries):
            self.click_upgrade()
            toast = self.page.locator(".van-toast__text:visible").last
            try:
                toast.wait_for(state="visible", timeout=3000)
            except PlaywrightTimeoutError:
                continue
            text = toast.inner_text().strip()
            execution_recorder.record("校验操作提示", text)
            return text
        raise AssertionError("点击「一键升级」后未出现校验提示")

    # ---------- 原保单退款（真实） ----------
    def _gateway(self) -> str:
        match = re.match(r"(https?://[^/]+)", self.config.base_url)
        assert match, f"无法从地址解析网关域名：{self.config.base_url}"
        return f"{match.group(1)}/gateway"

    def _api_headers(self) -> dict[str, str]:
        token = self.page.evaluate("() => localStorage.getItem('token') || ''")
        assert token, "登录态缺少 token，无法调用退款接口"
        return {
            "x-insure-token": token,
            "x-insure-projectcode": PROJECT_CODE,
            "content-type": "application/json",
        }

    def _post_api(self, path: str, payload: dict) -> dict:
        response = self.page.request.post(
            f"{self._gateway()}{path}",
            data=json.dumps(payload, ensure_ascii=False),
            headers=self._api_headers(),
        )
        assert response.ok, f"接口 {path} 请求失败：HTTP {response.status}"
        return response.json()

    def query_order_detail(self, order_no: str) -> dict:
        response = self.page.request.get(
            f"{self._gateway()}/core-service/api/v1/core/order/detail?orderNo={order_no}",
            headers=self._api_headers(),
        )
        assert response.ok, f"查询订单详情失败：HTTP {response.status}"
        result = response.json().get("result") or {}
        assert result.get("orderNo") == order_no, f"订单详情返回异常：{json.dumps(result, ensure_ascii=False)[:300]}"
        return result

    def refund_original_policies(self, order_no: str, timeout: int = 180) -> list[dict]:
        """真实退款原订单的已支付保单，并等待全部退款完成（refunded*）。

        与升级页「一键升级」的自动退款逻辑一致：先解除支付签约，再提交退款申请，
        然后轮询订单详情直到每张保单状态以 refunded 开头。
        """
        detail = self.query_order_detail(order_no)
        policies = [
            item
            for item in detail.get("orderPolicyQueryRespList") or []
            if str(item.get("status", "")).startswith("paid")
        ]
        assert policies, f"订单 {order_no} 下没有可退款的已支付保单"
        user_id = self.page.evaluate("() => localStorage.getItem('userId') || ''")
        order_type = detail.get("orderType") or "C"
        pay_method = detail.get("payMethod") or policies[0].get("payMethod") or ""

        for policy in policies:
            policy_id = policy["policyId"]
            cancel = self._post_api(
                "/pay-service/api/v2/pay/contract/cancel",
                {
                    "projectCode": PROJECT_CODE,
                    "payMethod": policy.get("payMethod") or pay_method,
                    "orderNo": order_no,
                    "cancelReason": "产品升级退款主动解约",
                    "policyId": policy_id,
                },
            )
            if not (cancel.get("success") is True or cancel.get("code") == "200000"):
                # 未签约支付方式可能无需解约，最终以退款结果为准
                execution_recorder.record(
                    "解除支付签约未成功", f'{policy.get("insuredName")}：{cancel.get("message")}'
                )

            refund = self._post_api(
                "/pay-service/api/v2/refund/apply",
                {
                    "userId": user_id,
                    "bizOrderNo": order_no,
                    "orderType": order_type,
                    "bizSubOrderNo": policy_id,
                    "refundReason": "其他-升级产品自动退款",
                },
            )
            assert refund.get("success") is True or refund.get("code") == "200000", (
                f'原保单退款申请失败：{policy.get("insuredName")} / {policy_id} → '
                f'{json.dumps(refund, ensure_ascii=False)[:300]}'
            )
            execution_recorder.record("原保单申请退款", f'{policy.get("insuredName")} / {policy_id}')

        policy_ids = [item["policyId"] for item in policies]
        deadline = time.time() + timeout
        statuses: dict[str, str] = {}
        while True:
            current = self.query_order_detail(order_no)
            statuses = {
                item["policyId"]: str(item.get("status", ""))
                for item in current.get("orderPolicyQueryRespList") or []
            }
            pending = [pid for pid in policy_ids if not statuses.get(pid, "").startswith("refunded")]
            if not pending:
                break
            assert time.time() < deadline, (
                f"等待原保单退款超时（{timeout}s），当前状态：{json.dumps(statuses, ensure_ascii=False)}"
            )
            self.page.wait_for_timeout(2000)

        execution_recorder.record(
            "原保单退款完成", "、".join(f"{pid}={statuses[pid]}" for pid in policy_ids)
        )
        return policies

    # ---------- 一键升级提交与收银台 ----------
    def submit_upgrade(self, source_order_no: str = "", timeout: int = 60000) -> str:
        """点击一键升级并确认弹窗，返回生成的升级订单号。

        测试环境网关偶发 504（后端实际已建单），响应无订单号时回查数据库：
        按升级历史表定位原订单最新关联的升级订单（waitPay）作为结果。
        """
        payload: dict = {}
        try:
            with self.page.expect_response(
                lambda response: response.request.method == "POST"
                and response.url.split("?")[0].endswith("/core/order/upgrade"),
                timeout=timeout,
            ) as response_info:
                self.click_upgrade()
                confirm = self.page.locator(".van-dialog__confirm").last
                confirm.wait_for(state="visible")
                confirm.click()
            payload = response_info.value.json()
        except Exception as exc:  # 网关超时等异常，转数据库兜底
            execution_recorder.record("升级下单响应异常", f"{type(exc).__name__}，回查数据库")
        order_no = ((payload or {}).get("result") or {}).get("orderNo") or ""
        if not order_no and source_order_no:
            order_no = self._find_upgrade_order_in_db(source_order_no)
        assert order_no, f"升级订单生成失败：{json.dumps(payload, ensure_ascii=False)[:500]}"
        execution_recorder.record("生成升级订单", order_no)
        self.wait_pay_page()
        return order_no

    @staticmethod
    def _find_upgrade_order_in_db(source_order_no: str) -> str:
        """升级历史表回查：原订单最新生成的待支付升级订单号。"""
        from utils.db import query_one

        row = query_one(
            "SELECT upgrade_order_no FROM mth_insure_core.insure_order_policy_upgrade_history"
            " WHERE original_order_no=%s ORDER BY id DESC LIMIT 1",
            (source_order_no,),
        )
        return (row or {}).get("upgrade_order_no") or ""

    def wait_pay_page(self) -> "OrderUpgradePage":
        expect(self.page).to_have_url(re.compile(r"#/pay\?"))
        self.page.locator(".pay-list .van-cell").first.wait_for(state="visible")
        self.hide_debug_panel()
        execution_recorder.record("进入收银台", self.page.url)
        return self

    def pay_order_no(self) -> str:
        match = re.search(r"orderNo=([^&]+)", self.page.url)
        assert match, f"收银台 URL 未携带订单号：{self.page.url}"
        return match.group(1)

    def pay_methods(self) -> list[str]:
        texts = self.page.locator(".pay-list .van-cell__title").all_inner_texts()
        return [text.strip().splitlines()[0] for text in texts if text.strip()]

    def pay_method_item(self, name: str) -> Locator:
        return self.page.locator(".pay-list .van-cell").filter(has_text=name).first

    def selected_pay_method(self) -> str:
        items = self.page.locator(".pay-list .van-cell")
        for index in range(items.count()):
            if items.nth(index).locator(".van-radio__icon--checked").count():
                return items.nth(index).locator(".van-cell__title").inner_text().strip().splitlines()[0]
        return ""

    def select_pay_method(self, name: str) -> "OrderUpgradePage":
        self.pay_method_item(name).click()
        expect(self.pay_method_item(name).locator(".van-radio__icon")).to_have_class(
            re.compile(r"van-radio__icon--checked")
        )
        execution_recorder.record("选择支付方式", name)
        return self

    def expect_default_pay_method(self, expected: str) -> None:
        actual = self.selected_pay_method()
        assert actual == expected, f"收银台默认支付方式不符：期望 {expected}，实际 {actual}"
        execution_recorder.record("校验默认支付方式", actual)

    def accept_pay_protocol(self) -> "OrderUpgradePage":
        """勾选收银台「我已阅读并同意《支付协议》」。"""
        box = self.page.locator(".checkbox-box .van-checkbox").first
        if box.get_attribute("aria-checked") != "true":
            box.click()
        expect(box).to_have_attribute("aria-checked", "true")
        execution_recorder.record("勾选收银台支付协议")
        return self

    def click_pay(self) -> None:
        self.page.locator(".pay-btn .primary-btn").first.click()
        execution_recorder.record("点击「支付」")

    def mock_wechat_payment(self) -> None:
        """mock 微信支付回调成功，仅覆盖支付环节，升级下单与退款走真实接口。

        - 微信 JSAPI 支付回调返回成功
        - 微信 H5 支付链接直接跳转支付成功页（测试环境无真实扣款）
        """
        page = self.page
        page.add_init_script(WECHAT_PAY_MOCK_JS)
        page.evaluate(WECHAT_PAY_MOCK_JS)

        def handle_h5_pay(route) -> None:
            match = re.search(r"bizOrderNo=([^&]+)", route.request.url)
            order_no = match.group(1) if match else ""
            target = re.sub(r"#/.*$", f"#/paySuccess?orderNo={order_no}", self.config.base_url)
            route.fulfill(
                status=200,
                content_type="text/html; charset=utf-8",
                body=f"<html><meta charset='utf-8'><script>location.replace('{target}')</script></html>",
            )

        page.route(re.compile(r"/pay-service/api/v1/pay/wx/h5"), handle_h5_pay)
        execution_recorder.record("启用微信支付 mock", "JSAPI 回调成功，H5 支付链接跳转支付成功页")

    # ---------- 个账支付（医保 ybpay） ----------
    YB_PAY_CONFIRM_TEXT = "本次投保将使用您的医保账户余额支付。"

    def mock_yb_payment(self) -> None:
        """mock 个账支付：ybPay 接口直接返回成功，前端跳转 partSuccess 页。"""
        page = self.page

        def handle_yb_pay(route) -> None:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {"code": "200000", "message": "消息处理成功", "result": True, "success": True}
                ),
            )

        page.route(re.compile(r"/core/order/ybPay"), handle_yb_pay)
        execution_recorder.record("启用个账支付 mock", "ybPay 接口返回成功，跳转 partSuccess 页")

    def pay_with_yb(self, order_no: str) -> None:
        """收银台个账支付：确认弹窗后等待跳转 partSuccess 页（原支付方式为医保个账）。"""
        confirm = self.page.locator(".van-dialog__confirm").last
        confirm.wait_for(state="visible")
        confirm.click()
        expect(self.page).to_have_url(
            re.compile(rf"#/partSuccess\?orderNo={re.escape(order_no)}"), timeout=30000
        )
        execution_recorder.record("个账支付成功", f"跳转 partSuccess：{self.page.url}")

    def wait_pay_success(self) -> None:
        expect(self.page).to_have_url(re.compile(r"#/paySuccess\?orderNo="), timeout=30000)
        execution_recorder.record("进入支付成功页", self.page.url)

    def cancel_pending_order(self, order_no: str) -> None:
        """取消待支付订单（mock 支付后后端仍为待支付，用于清理数据）。"""
        url = re.sub(r"#/.*$", f"#/orderDetail?orderNo={order_no}", self.config.base_url)
        self.page.goto(url)
        cancel = self.page.locator(".title-btn .todo-btn").filter(has_text="取消订单").first
        cancel.wait_for(state="visible")
        cancel.click()
        confirm = self.page.locator(".van-dialog__confirm").last
        if confirm.count():
            confirm.wait_for(state="visible")
            confirm.click()
        execution_recorder.record("清理待支付升级订单", order_no)

    def toast_text(self) -> str:
        # Vant 会保留上一条已隐藏的 toast 节点，需按可见节点取最新文本
        toast = self.page.locator(".van-toast__text:visible").last
        toast.wait_for(state="visible")
        text = toast.inner_text().strip()
        execution_recorder.record("校验操作提示", text)
        return text

    def wait_toast_hidden(self) -> None:
        expect(self.page.locator(".van-toast__text:visible")).to_have_count(0)

    @staticmethod
    def _parse_amount(text: str) -> Decimal:
        match = re.search(r"￥\s*([\d.]+)", text)
        assert match, f"未读取到金额：{text!r}"
        return Decimal(match.group(1))
