"""个单投保（聊惠保 2027 H5）页面对象。

聊惠保与东营惠民保同属一套 H5 投保平台，页面结构与 class 命名基本一致；
两者差异在本文件中单独封装：证件类型下拉、投被保人关系下拉、投保人年龄拦截、
8 位被保人上限、按人展示「产品 / 金额」、家庭优惠标签与医保个账支付弹窗。
"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect

from pages.base_page import BasePage
from utils import execution_recorder
from utils.session import has_session, read_local_storage, state_path


class IndividualPolicyPage(BasePage):
    """聊惠保个单投保页：投保信息、被保人卡片、保费与家庭优惠、支付方式。"""

    NOTICE_CONFIRM = "我知道了"
    REGISTER_TIP = "是否以【投保人】信息快速注册或登录？"
    SUBMIT_TEXT = "立即投保"
    PAYER_AGE_TIP = "用户年龄不能小于18"
    INSURED_LIMIT_TIP = "被保人关系为【子女】的数量已达上限,请重新选择"
    ACCOUNT_PAY_POPUP = "如需医保个账支付，请前往聊惠保公众号-个人中心支付或选用其他支付方式"
    FAMILY_DISCOUNT_TAG = "家庭优惠"
    CERT_TYPES = "身份证,护照,港澳居民来往内地通行证,台湾居民来往大陆通行证"
    FORM_AREA = ".insure-area"
    CARD = ".insure-info:visible"
    DELETE_BUTTON = ".insure-box .insured dd:has-text('删除')"
    CARD_STATE_JS = """(selector) => Array.from(document.querySelectorAll(selector))
        .filter(el => el.offsetParent !== null)
        .filter(el => el.querySelector("input[placeholder='请输入姓名']"))
        .map(el => {
            const name = el.querySelector("input[placeholder='请输入姓名']");
            const idNo = el.querySelector("input[placeholder='请输入居民身份证号']")
                || el.querySelector("input[placeholder='请输入证件号']");
            return {name: name ? name.value : null, id: idNo ? idNo.value : null};
        })"""

    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self.payer_name = page.locator("input[placeholder='请输入姓名']").first
        self.payer_cert_type = page.locator(
            "input[placeholder='请选择证件类型']"
        ).first
        self.payer_id_no = page.locator(
            "input[placeholder='请输入居民身份证号'], input[placeholder='请输入证件号']"
        ).first
        self.payer_phone = page.locator("input[placeholder='请输入手机号码']").first
        self.image_captcha = page.locator("input[placeholder='请输验证码']").first
        self.sms_code = page.locator("input[placeholder='请输入验证码']").first

    # ---------- 缴费人（投保人） ----------

    def open_payer_form(self, fresh: bool = False) -> "IndividualPolicyPage":
        """进入投保页；已登录则直接复用账号，未登录才走投保须知与缴费人填写。"""
        self.open()
        if not fresh and self.apply_saved_session():
            self.wait_page_ready()
            execution_recorder.record(
                "复用已保存的登录态", "缴费人信息由账号自动带出，跳过填写与短信验证"
            )
            return self
        if fresh and self.is_logged_in():
            self.sign_out()
        execution_recorder.record("点击缴费人姓名输入框，触发投保须知弹窗")
        self.payer_name.click()
        notice = self.page.get_by_text(self.NOTICE_CONFIRM)
        notice.wait_for(state="visible")
        notice.click()
        execution_recorder.record("点击「我知道了」关闭投保须知")
        expect(notice).to_be_hidden()
        return self

    def wait_page_ready(self) -> "IndividualPolicyPage":
        """等待投保页渲染出缴费人区域。"""
        self.page.get_by_text("本人信息（缴费人）").first.wait_for(
            state="visible", timeout=20000
        )
        return self

    def is_logged_in(self, timeout: int = 5000) -> bool:
        """缴费人区域是否处于「已登录只读」状态。"""
        marker = self.page.get_by_text("修改信息").first
        try:
            marker.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            return False

    def apply_saved_session(self) -> bool:
        """把保存的登录态注入当前页面并重载，返回是否成功登录。"""
        if self.is_logged_in(timeout=2000):
            return True
        path = state_path(self.config.env)
        items = read_local_storage(path, self.config.base_url)
        if not has_session(items):
            return False
        self.page.evaluate(
            "(items) => items.forEach((item) => localStorage.setItem(item.name, item.value))",
            items,
        )
        execution_recorder.record("注入本地保存的登录态", str(path))
        self.page.reload()
        try:
            self.page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        return self.is_logged_in(timeout=8000)

    def save_session(self) -> None:
        """保存当前登录态，供后续执行直接复用。"""
        path = state_path(self.config.env)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.page.context.storage_state(path=str(path))
        execution_recorder.record("保存登录态", str(path))

    def sign_out(self) -> "IndividualPolicyPage":
        """清除本地登录标识并重载，回到未登录状态。"""
        self.page.evaluate(
            "() => ['token', 'userId', 'openId'].forEach((key) => localStorage.removeItem(key))"
        )
        self.page.reload()
        self.wait_page_ready()
        return self

    def select_cert_type(self, cert_type: str, card=None) -> "IndividualPolicyPage":
        """在缴费人（card 为空）或指定被保人卡片上选择证件类型。"""
        scope = card if card is not None else self
        trigger = scope.locator("input[placeholder='请选择证件类型']").first
        trigger.click()
        popup = self.page.locator(".van-popup:visible")
        popup.wait_for(state="visible")
        # vant picker 列表按文本匹配
        option = popup.get_by_text(cert_type, exact=True).first
        option.click()
        self.page.wait_for_timeout(400)
        confirm = popup.get_by_text("确认", exact=True)
        if confirm.count() and confirm.first.is_visible():
            confirm.first.click()
        self.page.wait_for_timeout(400)
        expect(trigger).to_have_value(re.compile(cert_type))
        execution_recorder.record("选择证件类型", cert_type)
        return self

    def fill_payer(
        self, name: str, id_no: str, phone: str, cert_type: str = "身份证"
    ) -> "IndividualPolicyPage":
        """填写缴费人信息并校验写入结果。"""
        if cert_type != "身份证":
            self.select_cert_type(cert_type)
        self.payer_name.fill(name)
        execution_recorder.record("填写缴费人", f"{name} / {id_no} / {phone}")
        self.payer_id_no.fill(id_no)
        self.payer_phone.fill(phone)
        actual_name = self.payer_name.input_value()
        actual_id_no = self.payer_id_no.input_value()
        actual_phone = self.payer_phone.input_value()
        assert actual_name == name, f"缴费人姓名未写入，期望 {name!r}，实际 {actual_name!r}"
        assert actual_id_no == id_no, (
            f"缴费人证件号未写入，期望 {id_no!r}，实际 {actual_id_no!r}"
        )
        assert actual_phone == phone, (
            f"缴费人手机号未写入，期望 {phone!r}，实际 {actual_phone!r}"
        )
        return self

    def send_sms_code(self) -> "IndividualPolicyPage":
        """点击获取验证码，等待按钮进入重新发送倒计时。"""
        self.page.get_by_text("获取验证码", exact=True).click()
        expect(self.page.get_by_text(re.compile(r"\d+s\s*重新发送"))).to_be_visible()
        execution_recorder.record("点击获取验证码", "短信发送成功，按钮进入重新发送倒计时")
        return self

    def fill_sms_code(self, code: str) -> "IndividualPolicyPage":
        self.sms_code.fill(code)
        assert self.sms_code.input_value() == code, "短信验证码未写入"
        execution_recorder.record("输入短信验证码", code)
        return self

    def blur(self) -> "IndividualPolicyPage":
        """点击空白处让验证码输入框失焦。"""
        self.page.locator("body").click(position={"x": 10, "y": 300})
        return self

    def confirm_quick_register(self) -> "IndividualPolicyPage":
        """确认以投保人信息快速注册或登录。"""
        tip = self.page.get_by_text(self.REGISTER_TIP)
        tip.wait_for(state="visible")
        self.page.get_by_text("确认", exact=True).click()
        expect(tip).to_be_hidden()
        execution_recorder.record("确认以投保人信息快速注册或登录")
        pending = self.page.locator(".tip-bg")
        self.page.wait_for_timeout(1500)
        if pending.is_visible():
            pending.locator(".closeImg").click()
            expect(pending).to_be_hidden()
            execution_recorder.record("关闭待支付订单提示弹窗")
        return self

    def submit(self) -> "IndividualPolicyPage":
        """点击立即投保（隐藏测试环境 vConsole 后点按钮）。"""
        self.page.evaluate(
            "() => { const el = document.querySelector('#__vconsole');"
            " if (el) el.style.display = 'none'; }"
        )
        button = self.page.get_by_text(self.SUBMIT_TEXT).last
        button.scroll_into_view_if_needed()
        button.click()
        execution_recorder.record("点击「立即投保」")
        return self

    def tip_visible(self, text: str, timeout: int = 5000) -> bool:
        """指定提示文案是否出现（用于前端校验拦截提示）。"""
        tip = self.page.get_by_text(text).first
        try:
            tip.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            return False

    def wait_product_selection(self) -> "IndividualPolicyPage":
        """投保校验通过后，等待进入被保人卡片与产品选择区域。"""
        self.page.locator(self.FORM_AREA).wait_for(state="visible")
        self.page.locator("input[placeholder='请输入姓名']").last.wait_for(
            state="visible"
        )
        execution_recorder.record("投保校验通过，进入产品选择页")
        return self

    # ---------- 被保人卡片 ----------

    def insured_cards(self):
        """当前可编辑的被保人卡片；登录态下首张「本人」只读卡不参与填写。"""
        return self.page.locator(self.CARD).filter(
            has=self.page.locator("input[placeholder='请输入姓名']")
        )

    def card(self, index: int = 0):
        """按顺序获取第 index 张被保人卡片。"""
        return self.insured_cards().nth(index)

    def insured_states(self) -> list[dict]:
        """读取每张被保人卡片的姓名与证件号。"""
        return self.page.evaluate(self.CARD_STATE_JS, ".insure-info")

    def insured_index(self, id_no: str) -> int:
        """按证件号定位被保人卡片序号。"""
        for index, state in enumerate(self.insured_states()):
            if state.get("id") == id_no:
                return index
        raise AssertionError(f"未找到证件号为 {id_no} 的被保人卡片")

    def cleanup_insureds(
        self, keep_ids: set[str], keep_empty: bool = False
    ) -> "IndividualPolicyPage":
        """仅保留指定证件号的卡片；keep_empty 时额外保留最后一张新增的空卡片。"""
        removed = 0
        for _ in range(60):
            states = self.insured_states()
            keep_index = {
                i for i, state in enumerate(states) if state.get("id") in keep_ids
            }
            empty_index = [i for i, state in enumerate(states) if not state.get("id")]
            if keep_empty and empty_index:
                keep_index.add(empty_index[-1])
            targets = [i for i in range(len(states)) if i not in keep_index]
            if not targets:
                break
            delete = self.page.locator(self.DELETE_BUTTON)
            button = delete.nth(targets[-1])
            button.scroll_into_view_if_needed()
            button.click()
            self._confirm_delete()
            removed += 1
        self.page.wait_for_timeout(1200)
        if removed:
            execution_recorder.record("清理多余被保人", f"删除 {removed} 张卡片")
        return self

    def _confirm_delete(self) -> None:
        confirm = self.page.locator(".van-dialog__confirm")
        if confirm.count() and confirm.first.is_visible():
            confirm.first.click()
        self.page.wait_for_timeout(400)

    def add_insured_card(self) -> bool:
        """点击「添加被保人」。返回是否成功新增（被上限拦截时返回 False）。"""
        before = self.insured_cards().count()
        add = self.page.get_by_text("添加被保人", exact=True).last
        add.scroll_into_view_if_needed()
        add.click()
        if self.tip_visible(self.INSURED_LIMIT_TIP, timeout=2500):
            execution_recorder.record("添加被保人被拦截", self.INSURED_LIMIT_TIP)
            return False
        try:
            self.page.wait_for_function(
                """(count) => Array.from(document.querySelectorAll('.insure-info'))
                    .filter(el => el.offsetParent !== null)
                    .filter(el => el.querySelector("input[placeholder='请输入姓名']"))
                    .length > count""",
                arg=before,
                timeout=8000,
            )
        except Exception as exc:
            raise AssertionError(
                f"添加被保人失败：卡片数仍为 {before}，请检查上一张卡片是否填写完整"
            ) from exc
        execution_recorder.record("添加被保人", f"被保人卡片 {before} → {before + 1}")
        return True

    def open_relation_dropdown(self, index: int) -> "IndividualPolicyPage":
        """被保人关系是横向 tab，无需展开，滚动到可见即可。"""
        self.card(index).locator(".relation").scroll_into_view_if_needed()
        execution_recorder.record(f"定位被保人{index + 1}", "投被保人关系选项")
        return self

    def relation_options(self, index: int = 0) -> list[str]:
        """读取第 index 张被保人卡片的关系选项（本人/父母/配偶/子女/其他）。"""
        items = self.card(index).locator(".relation .van-tab")
        options: list[str] = []
        for order in range(items.count()):
            item = items.nth(order)
            if item.is_visible():
                options.append(item.inner_text().strip())
        execution_recorder.record(
            f"读取被保人{index + 1}", f"关系选项：{'、'.join(options)}"
        )
        return options

    def choose_relation(self, index: int, relation: str) -> bool:
        """在第 index 张卡片选择关系；新卡片默认已选中「本人」时直接复用。"""
        card = self.card(index)
        active = card.locator(".relation .van-tab--active")
        if active.count() and active.first.inner_text().strip() == relation:
            execution_recorder.record(
                f"被保人{index + 1} 关系已默认选中", relation
            )
            return True

        card.get_by_text(relation, exact=True).first.click()
        self.page.wait_for_timeout(800)
        active = card.locator(".relation .van-tab--active")
        applied = active.count() > 0 and active.first.inner_text().strip() == relation
        if not applied:
            execution_recorder.record(
                f"被保人{index + 1} 关系「{relation}」未生效", "可能触发关系上限拦截"
            )
        return applied

    def cert_type_options(self, index: int = 0) -> list[str]:
        """读取第 index 张被保人卡片可选的证件类型后关闭浮层。"""
        card = self.card(index)
        trigger = card.locator("input[placeholder='请选择证件类型']").first
        trigger.click()
        popup = self.page.locator(".van-popup:visible")
        popup.wait_for(state="visible")
        items = popup.locator(".van-picker-column__item, .van-action-sheet__item")
        options: list[str] = []
        for order in range(min(items.count(), 10)):
            item = items.nth(order)
            if item.is_visible():
                options.append(item.inner_text().strip())
        cancel = self.page.get_by_text("取消", exact=True)
        if cancel.count() and cancel.first.is_visible():
            cancel.first.click()
        self.page.mouse.move(10, 10)
        execution_recorder.record(
            f"读取被保人{index + 1}", f"证件类型选项：{'、'.join(options)}"
        )
        return options

    def _fill_extra_fields(self, card, sex: str) -> None:
        """非身份证证件类型需补填出生日期与性别。"""
        birth = card.locator("input[placeholder='请选择出生日期']").first
        if birth.count() and birth.is_visible():
            birth.click()
            self.page.locator(".van-datetime-picker .van-picker__confirm").click()
            self.page.wait_for_timeout(600)
        gender = card.locator("input[placeholder='请选择性别']").first
        if gender.count() and gender.is_visible():
            gender.click()
            sheet = self.page.locator(".van-action-sheet:visible")
            sheet.get_by_text(sex, exact=True).first.click()
            self.page.wait_for_timeout(600)

    def fill_insured_card(
        self,
        index: int,
        relation: str,
        name: str,
        id_no: str,
        cert_type: str = "身份证",
        expected_type: str = "",
    ) -> "IndividualPolicyPage":
        """填写第 index 张被保人卡片的关系、证件类型、姓名与证件号。"""
        card = self.card(index)
        assert self.choose_relation(index, relation), (
            f"被保人{index + 1}关系「{relation}」选择失败"
        )
        if cert_type != "身份证":
            self.select_cert_type(cert_type, card)
        card.locator("input[placeholder='请输入姓名']").fill(name)
        id_input = card.locator(
            "input[placeholder='请输入居民身份证号'], input[placeholder='请输入证件号']"
        ).first
        id_input.fill(id_no)
        self.page.locator("body").click(position={"x": 10, "y": 300})
        if cert_type != "身份证":
            self._fill_extra_fields(card, "女" if relation == "配偶" else "男")
        execution_recorder.record(
            f"填写被保人{index + 1}", f"{name} / {id_no} / {relation}"
        )
        self.page.wait_for_timeout(2500)
        if expected_type:
            self.wait_insured_identified(expected_type, index)
        return self

    def wait_insured_identified(self, insured_type: str, index: int = 0) -> None:
        """等待系统按证件号识别年龄并刷新保障计划。"""
        marker = "成长守护版" if insured_type == "未成年人" else "基础版"
        expect(self.card(index).get_by_text(marker, exact=True).first).to_be_visible()
        execution_recorder.record(
            f"系统识别被保人{index + 1}为{insured_type}",
            f"保障计划已刷新，出现「{marker}」",
        )

    # ---------- 产品版本（升级版 / 基础版） ----------

    def current_version(self) -> str:
        """读取当前选中的产品版本：升级版 / 基础版。"""
        index = self.page.evaluate(
            """() => {
                const tabs = Array.from(document.querySelectorAll('.tab-box .tab-placeholder'));
                return tabs.findIndex(el => el.classList.contains('active'));
            }"""
        )
        return {0: "升级版", 1: "基础版"}.get(index, "")

    def select_version(self, version: str) -> "IndividualPolicyPage":
        """切换订单产品版本，升级版与基础版可来回切换。"""
        key = "基础版" if "基础" in version else "升级版"
        index = 1 if key == "基础版" else 0
        before = self.current_version()
        tabs = self.page.locator(".tab-box li")
        tabs.nth(index).scroll_into_view_if_needed()
        tabs.nth(index).click()
        self.page.wait_for_timeout(1200)
        actual = self.current_version()
        assert actual == key, f"版本切换失败：期望 {key}，实际 {actual}"
        execution_recorder.record("切换产品版本", f"{before or '未选中'} → {actual}")
        return self

    # ---------- 保费与优惠 ----------

    def family_discount_visible(self) -> bool:
        """订单是否展示家庭优惠标签。"""
        return self.page.get_by_text(self.FAMILY_DISCOUNT_TAG).first.is_visible()

    def float_text(self) -> str:
        """底部固定浮层文案。"""
        text = self.page.locator(".fixed-tips-box").inner_text()
        return re.sub(r"\s+", " ", text).strip()

    def total_price(self) -> int:
        """底部保费合计（元/年）。"""
        text = self.page.locator(".total-price .price").inner_text()
        digits = re.sub(r"\D", "", text)
        if not digits:
            text = self.page.locator(".total-price").inner_text()
            digits = re.sub(r"\D", "", text)
        assert digits, f"未读取到保费金额：{text!r}"
        return int(digits)

    # ---------- 支付 ----------

    def select_payment(self, method: str) -> "IndividualPolicyPage":
        """选择支付方式：点击选项右侧圆圈，并处理可能出现的投保须知弹窗。"""
        pay = self.page.locator(".payMethod:visible").first
        pay.scroll_into_view_if_needed()
        items = pay.locator(".payLi")
        texts = [t for t in items.all_inner_texts() if t.strip()]
        target = next(
            index
            for index, text in enumerate(texts)
            if text.strip().startswith(method)
        )
        item = items.nth(target)
        item.locator(".checkWrap").click()
        notice = self.page.get_by_text(self.NOTICE_CONFIRM).last
        if notice.is_visible():
            notice.click()
            expect(notice).to_be_hidden()
        expect(item.locator(".radio").first).to_be_visible()
        execution_recorder.record("选择支付方式", method)
        return self

    def check_agreement(self) -> "IndividualPolicyPage":
        """下滑到底部，勾选协议阅读复选框。"""
        self.page.mouse.wheel(0, 8000)
        self.page.wait_for_timeout(500)
        icon = self.page.locator(".van-checkbox__icon").first
        icon.click()
        expect(icon).to_have_class(re.compile(r".*--checked.*"))
        execution_recorder.record("下滑到底部，勾选协议阅读复选框")
        return self

    def read_agreements(self) -> "IndividualPolicyPage":
        """逐个下滑协议并点击“我已阅读并确认”，直到所有协议阅读完成。"""
        popup = self.page.locator(".van-popup--bottom").filter(
            has_text="以下条款需要您再次确认"
        ).last
        popup.wait_for(state="visible")
        for index in range(8):
            if not popup.is_visible():
                break
            scroller = popup.locator(".virtualselect").first
            confirm = popup.locator("button.confirm-btn")
            for _ in range(4):
                scroller.hover()
                self.page.mouse.wheel(0, 30000)
                self.page.wait_for_timeout(600)
                if confirm.is_enabled():
                    break
            expect(confirm).to_be_enabled()
            confirm.click()
            execution_recorder.record(
                "协议下滑到底部，点击「我已阅读并确认」", f"第 {index + 1} 份协议"
            )
            self.page.wait_for_timeout(1200)
        expect(popup).to_be_hidden()
        return self

    def account_pay_popup_text(self, timeout: int = 6000) -> str:
        """点击立即参保后，读取医保个账支付提示弹窗文案（未出现返回空串）。"""
        tip = self.page.get_by_text(self.ACCOUNT_PAY_POPUP).first
        try:
            tip.wait_for(state="visible", timeout=timeout)
        except Exception:
            return ""
        text = re.sub(r"\s+", " ", tip.inner_text()).strip()
        execution_recorder.record("出现医保个账支付提示弹窗", text)
        return text

    def close_account_pay_popup(self) -> "IndividualPolicyPage":
        """关闭医保个账支付提示弹窗。"""
        popup = self.page.locator(".van-dialog").filter(
            has_text=self.ACCOUNT_PAY_POPUP
        ).last
        if popup.count():
            confirm = popup.get_by_text("我知道了")
            if not confirm.count():
                confirm = popup.get_by_text("确定")
            confirm.first.click()
            expect(popup).to_be_hidden()
            execution_recorder.record("关闭医保个账支付提示弹窗")
        return self

    def in_cashier(self, timeout: int = 6000) -> bool:
        """是否已进入收银台页面。"""
        pattern = re.compile("收银台|确认支付|支付订单")
        try:
            self.page.get_by_text(pattern).first.wait_for(
                state="visible", timeout=timeout
            )
            return True
        except Exception:
            return False
