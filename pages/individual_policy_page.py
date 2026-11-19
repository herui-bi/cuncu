"""个单投保（东营惠民保 H5）页面对象。"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect

from pages.base_page import BasePage
from utils import execution_recorder

# 提取画布虚影字形的骨架路径（Zhang-Suen 细化 + 8 邻域路径追踪）
SKELETON_JS = """(el) => {
    const w = el.width, h = el.height;
    const data = el.getContext('2d').getImageData(0, 0, w, h).data;
    const img = new Uint8Array(w * h);
    for (let i = 0; i < w * h; i++) img[i] = data[i * 4 + 3] > 10 ? 1 : 0;

    const at = (x, y) => (x >= 0 && x < w && y >= 0 && y < h) ? img[y * w + x] : 0;
    let changed = true;
    while (changed) {
        changed = false;
        for (let phase = 0; phase < 2; phase++) {
            const remove = [];
            for (let y = 1; y < h - 1; y++) {
                for (let x = 1; x < w - 1; x++) {
                    if (!at(x, y)) continue;
                    const p2 = at(x, y - 1), p3 = at(x + 1, y - 1), p4 = at(x + 1, y),
                          p5 = at(x + 1, y + 1), p6 = at(x, y + 1), p7 = at(x - 1, y + 1),
                          p8 = at(x - 1, y), p9 = at(x - 1, y - 1);
                    const neighbors = [p2, p3, p4, p5, p6, p7, p8, p9];
                    const b = neighbors.reduce((acc, value) => acc + value, 0);
                    if (b < 2 || b > 6) continue;
                    let a = 0;
                    for (let i = 0; i < 8; i++) if (!neighbors[i] && neighbors[(i + 1) % 8]) a++;
                    if (a !== 1) continue;
                    if (phase === 0 && (p2 * p4 * p6 || p4 * p6 * p8)) continue;
                    if (phase === 1 && (p2 * p4 * p8 || p2 * p6 * p8)) continue;
                    remove.push([x, y]);
                }
            }
            for (const [x, y] of remove) img[y * w + x] = 0;
            if (remove.length) changed = true;
        }
    }

    const neighbors = (x, y) => {
        const out = [];
        for (const [dx, dy] of [[0,-1],[1,-1],[1,0],[1,1],[0,1],[-1,1],[-1,0],[-1,-1]]) {
            const nx = x + dx, ny = y + dy;
            if (nx >= 0 && nx < w && ny >= 0 && ny < h && img[ny * w + nx]) out.push([nx, ny]);
        }
        return out;
    };
    const degree = (x, y) => neighbors(x, y).length;
    const visited = new Uint8Array(w * h);
    const paths = [];

    const walk = (sx, sy) => {
        const path = [[sx, sy]];
        visited[sy * w + sx] = 1;
        let cx = sx, cy = sy;
        while (true) {
            const next = neighbors(cx, cy).filter(([nx, ny]) => !visited[ny * w + nx]);
            if (!next.length) break;
            next.sort((a, b) => degree(b[0], b[1]) - degree(a[0], a[1]));
            const [nx, ny] = next[0];
            visited[ny * w + nx] = 1;
            path.push([nx, ny]);
            cx = nx; cy = ny;
        }
        if (path.length >= 2) paths.push(path);
    };

    for (let y = 1; y < h - 1; y++) for (let x = 1; x < w - 1; x++)
        if (img[y * w + x] && !visited[y * w + x] && degree(x, y) === 1) walk(x, y);
    for (let y = 1; y < h - 1; y++) for (let x = 1; x < w - 1; x++)
        if (img[y * w + x] && !visited[y * w + x]) walk(x, y);

    return paths;
}"""


class IndividualPolicyPage(BasePage):
    """个单投保页面：投保须知、缴费人快速注册、被保人与保障计划。"""

    NOTICE_CONFIRM = "我知道了"
    REGISTER_TIP = "是否以【投保人】信息快速注册或登录？"
    GUARDIAN_TIP = "您添加的被保人未满18周岁，请填写监护人信息"
    AGREEMENT_POPUP = ".van-popup--bottom"
    AGREEMENT_TITLE = "以下条款需要您再次确认"
    AGREEMENT_SCROLLER = ".virtualselect"
    AGREEMENT_CONFIRM = "button.confirm-btn"
    FORM_AREA = ".insure-area"

    def __init__(self, page: Page) -> None:
        super().__init__(page)
        # 页面中缴费人在前、被保人在后，姓名/证件号输入框各出现两次
        self.payer_name = page.locator("input[placeholder='请输入姓名']").first
        self.payer_id_no = page.locator("input[placeholder='请输入身份证号']").first
        self.payer_phone = page.locator("input[placeholder='请输入手机号码']").first
        self.sms_code = page.locator("input[placeholder='请输入验证码']").first

    def open(self) -> "IndividualPolicyPage":
        super().open()
        self.payer_name.wait_for(state="visible")
        return self

    def open_payer_form(self) -> "IndividualPolicyPage":
        """进入投保页，并通过首次点击姓名时出现的投保须知弹窗。"""
        self.open()
        execution_recorder.record("点击缴费人姓名输入框，触发投保须知弹窗")
        self.payer_name.click()
        notice = self.page.get_by_text(self.NOTICE_CONFIRM)
        notice.wait_for(state="visible")
        notice.click()
        execution_recorder.record("点击「我知道了」关闭投保须知")
        expect(notice).to_be_hidden()
        return self

    def fill_payer(self, name: str, id_no: str, phone: str) -> "IndividualPolicyPage":
        """填写缴费人姓名、证件号、手机号，并校验写入结果。"""
        self.payer_name.fill(name)
        execution_recorder.record("填写缴费人姓名", name)
        self.payer_id_no.fill(id_no)
        execution_recorder.record("填写缴费人证件号", id_no)
        self.payer_phone.fill(phone)
        execution_recorder.record("填写缴费人手机号", phone)
        actual_name = self.payer_name.input_value()
        actual_id_no = self.payer_id_no.input_value()
        actual_phone = self.payer_phone.input_value()
        assert actual_name == name, f"缴费人姓名未写入，期望 {name!r}，实际 {actual_name!r}"
        assert actual_id_no == id_no, f"缴费人证件号未写入，期望 {id_no!r}，实际 {actual_id_no!r}"
        assert actual_phone == phone, f"缴费人手机号未写入，期望 {phone!r}，实际 {actual_phone!r}"
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
        execution_recorder.record("点击空白处，验证码输入框失焦")
        return self

    def confirm_quick_register(self) -> "IndividualPolicyPage":
        """确认以投保人信息快速注册或登录。"""
        tip = self.page.get_by_text(self.REGISTER_TIP)
        tip.wait_for(state="visible")
        self.page.get_by_text("确认", exact=True).click()
        expect(tip).to_be_hidden()
        execution_recorder.record("确认以投保人信息快速注册或登录")
        # 该投保人已有待支付订单时，会弹层提示，先关闭再继续
        pending = self.page.locator(".tip-bg")
        self.page.wait_for_timeout(1500)
        if pending.is_visible():
            pending.locator(".closeImg").click()
            expect(pending).to_be_hidden()
            execution_recorder.record("关闭待支付订单提示弹窗")
        return self

    def select_payment(self, method: str) -> "IndividualPolicyPage":
        """选择支付方式：点击选项右侧圆圈，并处理可能出现的投保须知弹窗。"""
        pay = self.page.locator(".payMethod:visible").first
        pay.scroll_into_view_if_needed()
        items = pay.locator(".payLi")
        target = next(
            index
            for index, text in enumerate(items.all_inner_texts())
            if text.strip().startswith(method)
        )
        item = items.nth(target)
        item.locator(".checkWrap").click()
        notice = self.page.get_by_text(self.NOTICE_CONFIRM).last
        if notice.is_visible():
            notice.click()
            expect(notice).to_be_hidden()
        # 选中后勾选图标可见
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
        popup = self.page.locator(self.AGREEMENT_POPUP).filter(has_text=self.AGREEMENT_TITLE).last
        popup.wait_for(state="visible")
        for index in range(8):
            if not popup.is_visible():
                break
            scroller = popup.locator(self.AGREEMENT_SCROLLER).first
            confirm = popup.locator(self.AGREEMENT_CONFIRM)
            # 滚轮下滑到底部，按钮才会由 disabled 变为可点击
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

    def submit(self) -> "IndividualPolicyPage":
        """点击立即投保。"""
        # 测试环境页面右下角注入 vConsole 调试浮层，会遮挡底部按钮
        self.page.evaluate(
            "() => { const el = document.querySelector('#__vconsole'); if (el) el.style.display = 'none'; }"
        )
        self.page.locator(".save-btn").click()
        execution_recorder.record("所有协议阅读完成，点击立即投保")
        return self

    def _trace_ghost(self, canvas) -> None:
        """按画布虚影字形的骨架路径逐笔描绘。"""
        box = canvas.bounding_box()
        paths = canvas.evaluate(SKELETON_JS)
        for path in paths:
            start_x, start_y = path[0]
            self.page.mouse.move(box["x"] + start_x, box["y"] + start_y)
            self.page.mouse.down()
            for x, y in path[1:]:
                self.page.mouse.move(box["x"] + x, box["y"] + y)
            self.page.mouse.up()

    def sign(self, name: str) -> "IndividualPolicyPage":
        """签字页仅逐字签署缴费人姓名，签完后点击「完成签名」。"""
        popup = self.page.locator(".sign-name-popup")
        popup.wait_for(state="visible")
        for _ in range(len(name)):
            title = popup.locator(".title").inner_text().replace("\n", " ")
            execution_recorder.record("逐字签名", title)
            self._trace_ghost(popup.locator("canvas").first)
            next_button = popup.get_by_text("下一字", exact=True)
            if next_button.count() and next_button.first.is_visible():
                next_button.first.click()
                self.page.wait_for_timeout(1200)
        finish_button = popup.get_by_text("完成签名", exact=True)
        if not finish_button.count():
            finish_button = popup.get_by_text("立即投保", exact=True)
        finish_button.first.click()
        expect(popup).to_be_hidden()
        execution_recorder.record("签字完成，点击「完成签名」", f"已签署缴费人姓名：{name}")
        return self

    # ---------- 多被保人卡片 ----------
    CARD = ".insure-info:visible"
    DELETE_BUTTON = ".insure-box .insured dd:has-text('删除')"
    CARD_STATE_JS = """() => Array.from(document.querySelectorAll('.insure-info'))
        .filter(el => el.offsetParent !== null)
        .map(el => {
            const name = el.querySelector("input[placeholder='请输入姓名']");
            const idNo = el.querySelector("input[placeholder='请输入身份证号']");
            return {name: name ? name.value : null, id: idNo ? idNo.value : null};
        })"""

    def insured_cards(self):
        """当前可见的被保人卡片。"""
        return self.page.locator(self.CARD)

    def card(self, index: int = 0):
        """按顺序获取第 index 张被保人卡片。"""
        return self.insured_cards().nth(index)

    def insured_states(self) -> list[dict[str, str | None]]:
        """读取每张被保人卡片的姓名与证件号（老被保人卡片无证件号输入框）。"""
        return self.page.evaluate(self.CARD_STATE_JS)

    def insured_index(self, id_no: str) -> int:
        """按证件号定位被保人卡片序号。"""
        for index, state in enumerate(self.insured_states()):
            if state.get("id") == id_no:
                return index
        raise AssertionError(f"未找到证件号为 {id_no} 的被保人卡片")

    def clear_to_single_insured(self) -> "IndividualPolicyPage":
        """删除除第一张外的全部被保人卡片（含账号历史被保人）。"""
        removed = 0
        delete = self.page.locator(self.DELETE_BUTTON)
        while delete.count() > 1 and removed < 40:
            delete.last.click()
            self._confirm_delete()
            removed += 1
        if removed:
            execution_recorder.record("清理历史被保人", f"删除 {removed} 张卡片，保留 1 张")
        return self

    def cleanup_insureds(
        self, keep_ids: set[str], keep_empty: bool = False
    ) -> "IndividualPolicyPage":
        """仅保留指定证件号的卡片；keep_empty 时额外保留最后一张新增的空卡片。"""
        removed = 0
        for _ in range(60):
            states = self.insured_states()
            keep_index = {i for i, state in enumerate(states) if state.get("id") in keep_ids}
            empty_index = [i for i, state in enumerate(states) if not state.get("id")]
            if keep_empty and empty_index:
                keep_index.add(empty_index[-1])
            targets = [i for i in range(len(states)) if i not in keep_index]
            if not targets:
                break
            delete = self.page.locator(self.DELETE_BUTTON)
            assert delete.count() == len(states), (
                f"删除按钮数量 {delete.count()} 与被保人卡片数量 {len(states)} 不一致"
            )
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

    def add_insured_card(self) -> "IndividualPolicyPage":
        """点击「添加被保人」，等待新卡片出现。"""
        before = self.insured_cards().count()
        add = self.page.get_by_text("添加被保人", exact=True).last
        add.scroll_into_view_if_needed()
        add.click()
        self.page.wait_for_function(
            """(count) => Array.from(document.querySelectorAll('.insure-info'))
                .filter(el => el.offsetParent !== null).length > count""",
            arg=before,
        )
        execution_recorder.record("添加被保人", f"被保人卡片 {before} → {before + 1}")
        return self

    def fill_insured_card(
        self,
        index: int,
        relation: str,
        name: str,
        id_no: str,
        expected_type: str = "",
    ) -> "IndividualPolicyPage":
        """填写第 index 张被保人卡片的关系、姓名与证件号。"""
        card = self.card(index)
        card.get_by_text(relation, exact=True).click()
        self.page.wait_for_timeout(800)
        card.locator("input[placeholder='请输入姓名']").fill(name)
        card.locator("input[placeholder='请输入身份证号']").fill(id_no)
        self.page.locator("body").click(position={"x": 10, "y": 300})
        execution_recorder.record(f"填写被保人{index + 1}", f"{name} / {id_no} / {relation}")
        # 证件号失焦后系统会异步识别年龄并回填账号历史被保人，需等待完成再清理卡片
        self.page.wait_for_timeout(2500)
        if expected_type:
            self.wait_insured_identified(expected_type, index)
        return self

    def wait_insured_identified(self, insured_type: str, index: int = 0) -> None:
        """等待系统按证件号识别年龄；未成年人出现成长守护版，成年人出现基础版。"""
        marker = "成长守护版" if insured_type == "未成年人" else "基础版"
        expect(self.card(index).get_by_text(marker, exact=True).first).to_be_visible()
        execution_recorder.record(
            f"系统识别被保人{index + 1}为{insured_type}", f"保障计划已刷新，出现「{marker}」"
        )

    def minor_tip_visible(self, index: int = 0) -> bool:
        """第 index 张被保人卡片是否展示未成年人监护人提示。"""
        return self.card(index).locator(".guarder-tip").is_visible()

    def available_plans(self, index: int = 0) -> list[str]:
        """读取第 index 张被保人卡片当前可见的保障计划选项。"""
        card = self.card(index)
        items = card.locator(".payLi")
        plans = []
        for order in range(items.count()):
            item = items.nth(order)
            if item.is_visible():
                plans.append(item.locator(".titleWrap").inner_text().strip())
        return plans

    def selected_plan(self, index: int = 0) -> str:
        """读取第 index 张被保人卡片当前选中的保障计划，未选中返回空串。"""
        card = self.card(index)
        items = card.locator(".payLi")
        for order in range(items.count()):
            item = items.nth(order)
            if not item.is_visible():
                continue
            if item.locator("img.radio").first.is_visible():
                return item.locator(".titleWrap").inner_text().strip()
        return ""

    def select_plan(self, index: int, plan: str) -> "IndividualPolicyPage":
        """选择第 index 张被保人卡片的保障计划。"""
        card = self.card(index)
        items = card.locator(".payLi")
        for order in range(items.count()):
            item = items.nth(order)
            if item.is_visible() and item.locator(".titleWrap").inner_text().strip() == plan:
                item.locator(".checkWrap").click()
                self.page.wait_for_timeout(800)
                actual = self.selected_plan(index)
                assert actual == plan, f"被保人{index + 1}保障计划选择失败，期望 {plan}，实际 {actual}"
                execution_recorder.record(f"被保人{index + 1}选择保障计划", plan)
                return self
        raise AssertionError(f"被保人{index + 1}不存在可选保障计划：{plan}")

    def float_text(self) -> str:
        """底部固定浮层文案（升级版家庭单优惠提示）。"""
        text = self.page.locator(".fixed-tips-box").inner_text()
        return re.sub(r"\s+", " ", text).strip()

    def total_price(self) -> int:
        """底部保费合计（元/年）。"""
        text = self.page.locator(".total-price .price").inner_text()
        digits = re.sub(r"\D", "", text)
        assert digits, f"未读取到保费金额：{text!r}"
        return int(digits)

    def open_orders(self) -> "IndividualPolicyPage":
        """进入订单列表页。"""
        url = re.sub(r"#/.*$", "#/orders", self.config.base_url)
        self.page.goto(url)
        self.page.locator(".orderList .order").first.wait_for(state="visible")
        execution_recorder.record("进入订单列表页", url)
        return self

    def latest_order_no(self) -> str:
        """从订单列表第一张卡片读取订单号。"""
        self.open_orders()
        text = self.page.locator(".orderList .order").first.inner_text()
        match = re.search(r"E\d{15,}", text)
        assert match, f"订单卡片中未找到订单号：{text!r}"
        execution_recorder.record("订单列表获取订单号", match.group(0))
        return match.group(0)

    def latest_order_detail_no(self) -> str:
        """进入最新订单详情页，从详情页读取订单号。"""
        self.open_orders()
        self.page.locator(".orderList .order").first.get_by_text("查看详情", exact=True).click()
        self.page.wait_for_timeout(2000)
        text = self.page.inner_text("body")
        match = re.search(r"(?:订单号|订单编号)[:：]\s*(E\d{15,})", text)
        assert match, f"订单详情页未找到订单号：{text[:300]!r}"
        execution_recorder.record("订单详情页获取订单号", match.group(1))
        return match.group(1)
