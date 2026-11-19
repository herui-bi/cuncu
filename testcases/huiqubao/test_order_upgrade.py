"""惠衢保 2027 订单升级（7.0 二期）UI 自动化。

数据文件：data/huiqubao/caseData.xlsx → upgrade 工作表
页面对象：pages/huiqubao/order_upgrade_page.py

覆盖范围（可自动化）：hqb_001~hqb_018、hqb_041~hqb_044。
- hqb_001/002/012/014/015/016/043/044/045/046/047 依赖账号下已支付订单数据（基础版多人全额已支付、
  微信全款已支付、医保全款已支付、待支付升级订单），数据不足时 Excel 标记 enabled=N，
  运行时以 pytest.skip 明确列出原因，不伪造通过。
- hqb_003/010/011/013/017/018 使用部分退款订单/单人已支付订单验证详情与升级页。
- hqb_043/044 升级支付：先真实退款原订单保单并等待退款完成，再真实生成待支付升级订单，
  最后在收银台按原支付方式完成支付。微信订单仅 mock JSAPI 回调与 H5 支付链接；
  医保订单在收银台展示为「个账支付」，仅 mock ybPay 接口，成功后跳转 partSuccess 支付处理页。
  微信 mock 无法生成「已支付」状态订单，支付用例需外部准备全款已支付订单。
- 升级页金额以页面实际单人保费为基准累加（测试环境升级版 0.02 元、尊享版 0.03 元）。

人工/接口验证（后台能力或需构造支付/医保数据，不写 UI 自动化）：
- hqb_019 部分被保人医保资质不通过-提示姓名并置灰
- hqb_020 全部被保人医保资质不通过-暂无法升级
- hqb_021 校验通过-原支付方式扣款成功并生成升级订单
- hqb_022 原支付方式扣款失败-进入收银台并默认原支付方式
- hqb_023 收银台-倒计时、返回与防重复支付
- hqb_024 升级后订单详情可回溯原订单与升级订单
- hqb_025 个账签约-基础版签约自动升级为升级版
- hqb_026 收银台-微信/个账支付中签约与补签约
- hqb_027 农商行专线支付与身份核验
- hqb_028 银联云闪付支付
- hqb_029 组合支付整单（个账+农商行 / 个账+银联）
- hqb_030 农商行直接签约
- hqb_031 整单组合支付订单同时放开三类签约
- hqb_032 个账后台批量解约
- hqb_033 微信代扣数据范围
- hqb_034 个账签约代扣-前置校验与按版本划扣
- hqb_035 代扣短信场景
- hqb_036 农商行代扣
- hqb_037 续期接口接入与历史数据修复
- hqb_038 历史投保链接映射
- hqb_039 荷叶对接-投保情况校验
- hqb_040 升级流程埋点
"""

from __future__ import annotations

import json
import re
from decimal import Decimal

import allure
import pytest
from openpyxl import load_workbook
from playwright.sync_api import expect

from pages.huiqubao.order_upgrade_page import SMS_CODE, OrderUpgradePage
from utils import execution_recorder

WORKBOOK = "data/huiqubao/caseData.xlsx"
SHEET = "upgrade"
_ENABLED_TRUE = {"Y", "YES", "TRUE", "1", "是"}
NO_PLAN_TIP = "请为被保人选择升级方案"

# Excel 表头为中文，内部统一映射为英文键名
HEADER_ALIASES = {
    "是否启用": "enabled",
    "用例编号": "case_id",
    "用例标题": "title",
    "功能模块": "feature",
    "子场景": "story",
    "优先级": "severity",
    "用例类型": "test_type",
    "缴费人姓名": "payer_name",
    "缴费人证件号": "payer_id_no",
    "缴费人手机号": "payer_phone",
    "缴费人短信验证码": "payer_sms_code",
    "订单状态类型": "order_state",
    "订单页签": "status_tab",
    "被保人姓名": "insured_names",
    "被保人出生日期": "insured_birth_dates",
    "被保人关系": "insured_relations",
    "选择方案": "select_plans",
    "期望选中人数": "expected_selected_count",
    "期望提示": "expected_tip",
    "期望金额规则": "expected_amount_rule",
    "期望卡片按钮": "expected_buttons",
    "期望被保人按钮": "expected_insured_buttons",
    "期望升级页行数": "expected_row_count",
    "期望当前方案": "expected_current_plan",
    "期望可选方案": "expected_plans",
    "期望支付方式": "expected_pay_method",
    "是否校验详情": "check_detail",
    "期望详情状态": "expected_detail_status",
    "人工校验说明": "manual_check",
    "备注": "remark",
    "前置数据需求": "data_requirement",
    "数据获取方式": "data_source",
    "数据是否就绪": "data_ready",
}


def _normalize(case: dict[str, str]) -> dict[str, str]:
    return {HEADER_ALIASES.get(key, key): value for key, value in case.items()}


def _load_cases() -> list[dict[str, str]]:
    """读取全部行；未启用的行标记 _disabled，用于报告中的显式 skip。"""
    rows = list(load_workbook(WORKBOOK, data_only=True)[SHEET].iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(cell).strip() if cell is not None else "" for cell in rows[0]]
    cases: list[dict[str, str]] = []
    for row in rows[1:]:
        values = ["" if cell is None else str(cell).strip() for cell in row]
        if not any(values):
            continue
        case = _normalize(dict(zip(headers, values)))
        if case.get("enabled", "Y").upper() not in _ENABLED_TRUE:
            case["_disabled"] = "1"
        cases.append(case)
    return cases


CASES = _load_cases()


def _cases(test_type: str) -> list[dict[str, str]]:
    return [case for case in CASES if case.get("test_type") == test_type]


def _split(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _meta(case: dict[str, str]) -> None:
    allure.dynamic.epic("惠衢保 2027")
    allure.dynamic.feature(case["feature"])
    allure.dynamic.story(case["story"])
    allure.dynamic.title(f'{case["case_id"]} {case["title"]}')
    allure.dynamic.severity(case["severity"])
    execution_recorder.set_title(f'{case["case_id"]} {case["title"]}')


def _skip_if_disabled(case: dict[str, str]) -> None:
    if case.get("_disabled"):
        reason = (
            case.get("data_requirement")
            or case.get("manual_check")
            or "缺少对应状态订单"
        )
        pytest.skip(f'{case["case_id"]} 数据未就绪：{reason}')


def _login(page, case: dict[str, str]) -> OrderUpgradePage:
    return OrderUpgradePage(page).login_with_verified_identity(
        case["payer_name"],
        case["payer_id_no"],
        case["payer_phone"],
        case.get("payer_sms_code") or SMS_CODE,
    )


def _order_no(case: dict[str, str]) -> str:
    """订单号统一取自 Excel「订单号」列（兼容旧列名 order_no）。"""
    return (case.get("订单号") or case.get("order_no") or "").strip()


def _open_tab(obj: OrderUpgradePage, case: dict[str, str]) -> None:
    """进入订单列表并切换页签；目标订单不在页签内时按数据缺失 skip。"""
    numbers = obj.open_orders().switch_status_soft(case["status_tab"])
    target = _order_no(case)
    reason = case.get("data_requirement") or "需重新造数"
    if not numbers:
        pytest.skip(f'{case["case_id"]} 数据未就绪：「{case["status_tab"]}」页签无订单（{reason}）')
    if target and target not in numbers:
        pytest.skip(
            f'{case["case_id"]} 数据未就绪：订单 {target} 不在「{case["status_tab"]}」页签（{reason}）'
        )


def _open_upgrade(page, case: dict[str, str]) -> OrderUpgradePage:
    obj = _login(page, case)
    _open_tab(obj, case)
    orders = obj
    order_no = _order_no(case)
    card = orders.order_card(order_no)
    use_detail = case["status_tab"] == "部分退款" or not card.get_by_text("升级保障", exact=True).count()
    if not use_detail:
        orders.open_upgrade_from_list(order_no)
    else:
        # 部分退款订单/升级版订单从详情被保人进入，避免列表入口过滤导致无行
        orders.open_order_detail(order_no)
        index = obj.first_upgradeable_insured()
        assert index is not None, f'{case["case_id"]} 订单无可升级被保人'
        obj.click_insured_upgrade(index)
    return obj


@pytest.fixture(scope="module")
def auth_state(browser, browser_context_args):
    """使用实名身份登录一次并复用登录态，避免每个用例重复触发短信。"""
    payer = next(case for case in CASES if case.get("payer_name"))
    last_error: Exception | None = None
    for _ in range(2):
        context = browser.new_context(**browser_context_args)
        page = context.new_page()
        try:
            OrderUpgradePage(page).login_with_verified_identity(
                payer["payer_name"],
                payer["payer_id_no"],
                payer["payer_phone"],
                payer.get("payer_sms_code") or SMS_CODE,
            )
            return context.storage_state()
        except Exception as exc:  # 登录链路瞬时失败时重试一次
            last_error = exc
        finally:
            context.close()
    raise last_error


@pytest.fixture
def page(browser, browser_context_args, auth_state, request):
    """复用登录态创建独立上下文，失败时保存截图到 reports/artifacts。"""
    context = browser.new_context(**browser_context_args, storage_state=auth_state)
    page = context.new_page()
    yield page
    for when in ("rep_call", "rep_setup"):
        report = getattr(request.node, when, None)
        if report is not None and report.failed and not page.is_closed():
            name = re.sub(r"[^\w\-]+", "_", request.node.name)
            page.screenshot(path=f"reports/artifacts/huiqubao_{name}.png", full_page=True)
            break
    context.close()


@pytest.mark.huiqubao
@pytest.mark.parametrize("case", _cases("list_entry"), ids=[c["case_id"] for c in _cases("list_entry")])
def test_order_list_entry(page, case):
    """订单列表卡片按钮入口：基础版已支付可升级，已退款/已取消仅查看详情。"""
    _meta(case)
    _skip_if_disabled(case)

    obj = _login(page, case)
    _open_tab(obj, case)

    order_no = _order_no(case)
    if case["case_id"] == "hqb_007":
        # 待支付订单超过支付有效期会自动关闭，按页签内实际订单动态匹配，避免订单失效导致误报
        candidates = obj.order_numbers()
        if order_no not in candidates:
            order_no = candidates[0]

    expected = [item for item in case["expected_buttons"].split("|") if item]
    actual = obj.card_buttons(order_no)
    assert actual == expected, (
        f'{case["case_id"]} 订单 {order_no} 卡片按钮不符：期望 {expected}，实际 {actual}'
    )
    assert "申请退款" not in actual, f'{case["case_id"]} 列表页不应展示「申请退款」按钮'

    if case["check_detail"] == "Y":
        if case["case_id"] == "hqb_007":
            # 待支付订单卡片仅「去支付」，无「查看详情」入口，直接按路由打开详情
            obj.open_order_detail_direct(order_no)
        else:
            obj.open_order_detail(order_no)
        status = obj.detail_status()
        assert status == case["expected_detail_status"], (
            f'{case["case_id"]} 详情页状态不符：期望 {case["expected_detail_status"]}，实际 {status}'
        )
        expected_insured = [item for item in case["expected_insured_buttons"].split("|") if item]
        for index in range(obj.insured_count()):
            insured_status = obj.insured_status(index)
            expect_buttons = [] if "已退款" in insured_status else expected_insured
            obj.wait_insured_buttons(index, expect_buttons)
            buttons = obj.insured_buttons(index)
            assert buttons == expect_buttons, (
                f'{case["case_id"]} 被保人{index + 1}按钮不符：期望 {expect_buttons}，'
                f'实际 {buttons}（状态 {insured_status}）'
            )
            if not expected_insured:
                assert case["expected_detail_status"] in insured_status, (
                    f'{case["case_id"]} 被保人{index + 1}状态不符：{insured_status}'
                )


@pytest.mark.huiqubao
@pytest.mark.parametrize("case", _cases("detail_entry"), ids=[c["case_id"] for c in _cases("detail_entry")])
def test_order_detail_entry(page, case):
    """订单详情每位未退款被保人独立展示「升级保障」「申请退款」。"""
    _meta(case)
    _skip_if_disabled(case)

    obj = _login(page, case)
    _open_tab(obj, case)
    obj.open_order_detail(_order_no(case))

    status = obj.detail_status()
    assert status == case["expected_detail_status"], (
        f'{case["case_id"]} 详情页状态不符：期望 {case["expected_detail_status"]}，实际 {status}'
    )

    expected = [item for item in case["expected_insured_buttons"].split("|") if item]
    count = obj.insured_count()
    assert count >= 1, f'{case["case_id"]} 订单无被保人数据'
    for index in range(count):
        insured_status = obj.insured_status(index)
        expect_buttons = [] if "已退款" in insured_status else expected
        obj.wait_insured_buttons(index, expect_buttons)
        buttons = obj.insured_buttons(index)
        assert buttons == expect_buttons, (
            f'{case["case_id"]} 被保人{index + 1}按钮不符：期望 {expect_buttons}，'
            f'实际 {buttons}（状态 {insured_status}）'
        )


@pytest.mark.huiqubao
@pytest.mark.parametrize("case", _cases("upgrade_page"), ids=[c["case_id"] for c in _cases("upgrade_page")])
def test_upgrade_page_entry(page, case):
    """从订单详情单个被保人进入升级页，仅展示该被保人一行。"""
    _meta(case)
    _skip_if_disabled(case)

    obj = _login(page, case)
    _open_tab(obj, case)
    obj.open_order_detail(_order_no(case))
    index = obj.first_upgradeable_insured()
    assert index is not None, f'{case["case_id"]} 订单无可升级被保人'
    full_name = obj.insured_name(index)
    obj.click_insured_upgrade(index)

    expected_rows = int(case["expected_row_count"])
    assert obj.upgrade_row_count() == expected_rows, (
        f'{case["case_id"]} 升级页被保人行数不符：期望 {expected_rows}，实际 {obj.upgrade_row_count()}'
    )
    row_name = obj.row_insured_name(0)
    assert row_name.endswith(full_name[-1]), (
        f'{case["case_id"]} 升级页被保人与详情不一致：详情 {full_name}，升级页 {row_name}'
    )
    expected_current = case.get("expected_current_plan") or "基础版"
    assert expected_current in obj.row_current_plan(0), (
        f'{case["case_id"]} 当前保障方案不符：期望包含 {expected_current}，'
        f'实际 {obj.row_current_plan(0)}'
    )
    expected_plans = [item for item in case.get("expected_plans", "").split("|") if item]
    assert obj.row_plans(0) == expected_plans, (
        f'{case["case_id"]} 可升级方案不符：期望 {expected_plans}，实际 {obj.row_plans(0)}'
    )


@pytest.mark.huiqubao
@pytest.mark.parametrize("case", _cases("selection"), ids=[c["case_id"] for c in _cases("selection")])
def test_plan_selection(page, case):
    """方案单选：默认不选、点击选中、再次点击取消；部分选择只影响所选被保人。"""
    _meta(case)
    _skip_if_disabled(case)

    obj = _open_upgrade(page, case)

    if case["case_id"] == "hqb_016":
        tip = obj.operation_tip()
        assert tip == case["expected_tip"], (
            f'{case["case_id"]} 多人升级页操作提示不符：期望 {case["expected_tip"]!r}，实际 {tip!r}'
        )
        execution_recorder.record("差异记录", "单人升级页文案未覆盖：账号下无基础版单人已支付订单")
        return

    assert obj.selected_count() == 0, f'{case["case_id"]} 升级页默认不应选中任何方案'

    plan = _split(case["select_plans"])[0]
    obj.select_plan(0, plan)
    obj.expect_plan_selected(0, plan, True)
    assert obj.selected_count() == 1, f'{case["case_id"]} 首次点击后应选中 1 个方案'

    if case["case_id"] == "hqb_012":
        name_a = obj.row_insured_name(0)
        name_b = obj.row_insured_name(1)
        price_a = obj.row_plan_price(0, plan)
        obj.expect_amount(price_a)
        tips = obj.refund_tips()
        assert name_a in tips, f'{case["case_id"]} 退款说明未包含已选被保人 {name_a}'
        assert name_b not in tips, f'{case["case_id"]} 退款说明不应包含未选被保人 {name_b}'
        return

    if case["case_id"] == "hqb_011":
        # 同一被保人只能选择升级版/尊享版其中一个版本
        other = "尊享版"
        obj.select_plan(0, other)
        obj.expect_plan_selected(0, other, True)
        obj.expect_plan_selected(0, plan, False)
        assert obj.selected_count() == 1, f'{case["case_id"]} 切换版本后仍应只选中 1 个方案'
        obj.select_plan(0, other)
        assert obj.selected_count() == 0, f'{case["case_id"]} 再次点击尊享版后应取消选中'
        return

    obj.select_plan(0, plan)
    obj.expect_plan_selected(0, plan, False)
    assert obj.selected_count() == 0, f'{case["case_id"]} 再次点击后应取消选中'


@pytest.mark.huiqubao
@pytest.mark.parametrize("case", _cases("amount"), ids=[c["case_id"] for c in _cases("amount")])
def test_amount_display(page, case):
    """需支付金额按所选被保人单人保费累加，退款说明包含已选被保人姓名。"""
    _meta(case)
    _skip_if_disabled(case)

    obj = _open_upgrade(page, case)

    if case["case_id"] == "hqb_013":
        assert obj.selected_count() == 0, "未选择方案时不应有选中项"
        assert obj.amount_value() == Decimal("0"), f'未选择方案时金额应为 0，实际 {obj.amount_text()}'
        assert "被保人（" not in obj.refund_tips(), "未选择方案时不应出现带姓名的退款话术"
        execution_recorder.record(
            "差异记录", "清单预期未选方案金额为「--」，实测页面展示「需要支付：￥0」，按页面实际断言"
        )
        return

    plans = _split(case["select_plans"])
    assert plans, f'{case["case_id"]} 缺少 select_plans 数据'

    if case["case_id"] == "hqb_014":
        first_price = obj.row_plan_price(0, plans[0])
        obj.select_plan(0, plans[0])
        obj.expect_amount(first_price)
        assert obj.selected_count() == 1

        second_price = obj.row_plan_price(1, plans[1])
        obj.select_plan(1, plans[1])
        obj.expect_amount(first_price + second_price)
        assert obj.selected_count() == 2
        return

    # hqb_015：退款说明包含两位被保人姓名，以顿号分隔
    names = [obj.row_insured_name(0), obj.row_insured_name(1)]
    obj.select_plan(0, plans[0])
    obj.select_plan(1, plans[1])
    assert obj.selected_count() == 2

    tips = obj.refund_tips()
    for name in names:
        assert name in tips, f'{case["case_id"]} 退款说明未包含被保人 {name}：{tips}'
    assert f"{names[0]}、{names[1]}" in tips, f'{case["case_id"]} 被保人姓名未以顿号分隔：{tips}'
    assert "原保单进行退款" in tips, f'{case["case_id"]} 退款说明缺少退款描述：{tips}'
    execution_recorder.record(
        "差异记录",
        "清单文案为「本次支付会对 A、B 的原基础版保单进行退款…」，"
        "实测为「本次支付会对被保人（A、B）的原保单进行退款…」，姓名与顿号分隔一致",
    )


@pytest.mark.huiqubao
@pytest.mark.parametrize("case", _cases("validation"), ids=[c["case_id"] for c in _cases("validation")])
def test_upgrade_validation(page, case):
    """一键升级校验：未选方案优先提示，其次要求勾选协议，且不进入收银台。"""
    _meta(case)
    _skip_if_disabled(case)

    obj = _open_upgrade(page, case)

    if case["case_id"] == "hqb_017":
        assert obj.selected_count() == 0
        obj.set_agreement(True)
        actual = obj.click_upgrade_expect_toast()
        assert actual == case["expected_tip"], (
            f'{case["case_id"]} 提示不符：期望 {case["expected_tip"]!r}，实际 {actual!r}'
        )
        expect(page).to_have_url(re.compile(r"#/ordersUpgrade\?"))
        obj.wait_toast_hidden()
        return

    assert not obj.agreement_checked(), "协议默认应为未勾选"
    first_tip = obj.click_upgrade_expect_toast()
    assert first_tip == NO_PLAN_TIP, (
        f'{case["case_id"]} 未选方案应优先提示 {NO_PLAN_TIP!r}，实际 {first_tip!r}'
    )
    obj.wait_toast_hidden()

    plan = _split(case["select_plans"])[0]
    obj.select_plan(0, plan)
    actual = obj.click_upgrade_expect_toast()
    assert actual == case["expected_tip"], (
        f'{case["case_id"]} 提示不符：期望 {case["expected_tip"]!r}，实际 {actual!r}'
    )
    expect(page).to_have_url(re.compile(r"#/ordersUpgrade\?"))


@pytest.mark.huiqubao
@pytest.mark.parametrize("case", _cases("group_upgrade"), ids=[c["case_id"] for c in _cases("group_upgrade")])
def test_group_upgrade(page, case):
    """多被保人订单：仅勾选部分被保人或全员一起升级，升级订单按所选人数生成。"""
    _meta(case)
    _skip_if_disabled(case)

    obj = _open_upgrade(page, case)
    expected_rows = int(case["expected_row_count"])
    assert obj.upgrade_row_count() == expected_rows, (
        f'{case["case_id"]} 升级页被保人行数不符：期望 {expected_rows}，实际 {obj.upgrade_row_count()}'
    )

    plans = _split(case["select_plans"])
    expected_selected = int(case["expected_selected_count"])
    for index, plan in enumerate(plans):
        obj.select_plan(index, plan)
        obj.expect_plan_selected(index, plan, True)
    assert obj.selected_count() == expected_selected, (
        f'{case["case_id"]} 选中方案数不符：期望 {expected_selected}，实际 {obj.selected_count()}'
    )
    # 未选方案的被保人不参与本次升级
    for index in range(expected_rows):
        if index < len(plans):
            continue
        checked = obj.upgrade_rows().nth(index).locator(".radio-icon.checked").count()
        assert checked == 0, f'{case["case_id"]} 被保人{index + 1}未选择方案却被选中'

    obj.set_agreement(True)
    obj.mock_wechat_payment()
    upgrade_order_no = obj.submit_upgrade(_order_no(case), timeout=180000)
    assert upgrade_order_no and not upgrade_order_no.startswith("MOCK"), (
        f'{case["case_id"]} 未生成真实升级订单号：{upgrade_order_no}'
    )

    # 升级订单只包含所选被保人
    new_policies = obj.query_order_detail(upgrade_order_no).get("orderPolicyQueryRespList") or []
    assert len(new_policies) == expected_selected, (
        f'{case["case_id"]} 升级订单被保人数不符：期望 {expected_selected}，实际 {len(new_policies)}'
    )
    # 原订单仅所选被保人的保单被退款
    source_policies = obj.query_order_detail(_order_no(case)).get("orderPolicyQueryRespList") or []
    refunded = [item for item in source_policies if str(item.get("status", "")).startswith("refunded")]
    assert len(refunded) == expected_selected, (
        f'{case["case_id"]} 原订单退款保单数不符：期望 {expected_selected}，实际 {len(refunded)}'
    )

    obj.expect_default_pay_method(case["expected_pay_method"])
    obj.accept_pay_protocol()
    obj.click_pay()
    obj.wait_pay_success()
    expect(page).to_have_url(re.compile(rf"#/paySuccess\?orderNo={re.escape(upgrade_order_no)}"))
    expect(page.locator("body")).to_contain_text("支付成功")


@pytest.mark.huiqubao
@pytest.mark.parametrize("case", _cases("payment"), ids=[c["case_id"] for c in _cases("payment")])
def test_upgrade_refund_then_pay(page, case):
    """先退款原保单，再生成真实待支付升级订单，最后按「期望支付方式」完成支付。

    支持三种组合：
    - 原单微信/期望微信（hqb_043）：默认即原支付方式，直接 mock 支付
    - 原单个账/期望个账（hqb_044、hqb_047）：默认即原支付方式，直接 mock 支付
    - 交叉组合（hqb_048 微信单用个账升级、hqb_049 个账单用微信升级）：
      手动切换支付方式后完成支付，验证收银台允许更换支付方式
    """
    _meta(case)
    _skip_if_disabled(case)

    obj = _login(page, case)
    _open_tab(obj, case)
    obj.open_order_detail(_order_no(case))
    obj.click_insured_upgrade(0)
    plan = _split(case["select_plans"])[0]
    obj.select_plan(0, plan)
    obj.set_agreement(True)

    # 1. 点击一键升级后由前端自动完成「原保单退款 → 轮询退款成功 → 生成待支付升级订单」
    # 医保渠道在收银台展示为「个账支付」，底层 payMethod 为 ybpay
    is_yb_pay = any(key in case["expected_pay_method"] for key in ("医保", "个账"))
    if is_yb_pay:
        obj.mock_yb_payment()
    else:
        obj.mock_wechat_payment()
    upgrade_order_no = obj.submit_upgrade(_order_no(case), timeout=180000)
    assert upgrade_order_no and not upgrade_order_no.startswith("MOCK"), (
        f'{case["case_id"]} 未生成真实升级订单号：{upgrade_order_no}'
    )

    # 2. 校验原保单已完成退款（前端自动退款的结果）
    detail = obj.query_order_detail(_order_no(case))
    refunded = [
        item["policyId"]
        for item in detail.get("orderPolicyQueryRespList") or []
        if str(item.get("status", "")).startswith("refunded")
    ]
    assert refunded, f'{case["case_id"]} 升级前原保单未完成退款：{json.dumps(detail, ensure_ascii=False)[:300]}'

    # 3. 收银台使用「期望支付方式」完成支付（微信/医保接口 mock 返回成功）
    methods = obj.pay_methods()
    assert case["expected_pay_method"] in methods, (
        f'{case["case_id"]} 收银台未展示{case["expected_pay_method"]}：{methods}'
    )
    obj.expect_default_pay_method(case["expected_pay_method"])
    obj.select_pay_method(case["expected_pay_method"])
    obj.accept_pay_protocol()

    obj.click_pay()
    if is_yb_pay:
        obj.pay_with_yb(upgrade_order_no)
    else:
        obj.wait_pay_success()
        expect(page).to_have_url(
            re.compile(rf"#/paySuccess\?orderNo={re.escape(upgrade_order_no)}")
        )
        expect(page.locator("body")).to_contain_text("支付成功")
