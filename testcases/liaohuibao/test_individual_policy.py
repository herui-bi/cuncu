"""个单投保自动化测试（聊惠保 2027 H5）。

用例数据维护在 data/liaohuibao/caseData.xlsx 的 policy 工作表：
- test_type=payer_age        投保人年龄边界（按投保日计算，18 周岁拦截）
- test_type=insured_age       被保人年龄无限制（未满 1 岁与超百岁可保）
- test_type=insured_limit    被保人数量上限（8 人可保 / 子女上限 4 人）
- test_type=cert_type        多证件类型被保人保存
- test_type=relation_options 投被保人关系下拉选项
- test_type=premium          保费计算与家庭优惠
- test_type=h5_*             支付方式与医保个账支付提示
- test_type=family_tag       家庭优惠标签
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

import allure
import pytest

from pages.liaohuibao.individual_policy_page import IndividualPolicyPage
from utils import execution_recorder
from utils.excel_reader import read_cases
from utils.id_card import generate_id_no
from utils.identity import (
    age_at,
    birth_of,
    find as find_identity,
    next_available,
)

POLICY_CASES = read_cases("policy", workbook="data/liaohuibao/caseData.xlsx")

# 聊城市行政区划代码（生成身份证号用）
AREA_CODE = "371500"
# 聊惠保 2027 生效日（被保人年龄按生效日计算）
EFFECTIVE_DATE = date(2027, 1, 1)
_REL_TOKEN = re.compile(r"([+-]\d+)([YMD])")


def _cases(*test_types: str) -> list[dict[str, str]]:
    return [case for case in POLICY_CASES if case.get("test_type") in test_types]


def _split(case: dict[str, str], key: str) -> list[str]:
    return [
        item.strip() for item in (case.get(key) or "").split(",") if item.strip()
    ]


def _shift(base: date, amount: int, unit: str) -> date:
    if unit == "D":
        return base + timedelta(days=amount)
    if unit == "M":
        month = base.month - 1 + amount
        year = base.year + month // 12
        month = month % 12 + 1
        day = min(base.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)
    return date(base.year + amount, base.month, base.day)


def _birth(expr: str) -> str:
    """解析出生日期：支持 YYYY-MM-DD 与 REL:-18Y+1D 这类相对投保日的表达式。"""
    expr = (expr or "").strip()
    if not expr:
        raise ValueError("出生日期为空")
    if not expr.startswith("REL:"):
        date.fromisoformat(expr)
        return expr
    current = date.today()
    for amount, unit in _REL_TOKEN.findall(expr[4:]):
        current = _shift(current, int(amount), unit)
    return current.isoformat()


def _payer_identity(case: dict[str, str]) -> tuple[str, str, str]:
    """缴费人身份：优先 Excel 指定，其次实名身份池，最后才用生成号（仅限不触发实名的用例）。"""
    name = case["payer_name"]
    phone = (case.get("payer_phone") or "").strip()
    explicit = (case.get("payer_id_no") or "").strip()
    if explicit:
        return name, explicit, phone

    found = find_identity(name=name)
    if found:
        return found["name"], found["id_no"], phone or found["phone"]

    generated = generate_id_no(
        _birth(case["payer_birth_date"]), 1, area_code=AREA_CODE
    )
    execution_recorder.record(
        "缴费人未匹配到实名身份",
        f"{name} 使用生成号，仅适用于不触发实名的前端校验用例",
    )
    return name, generated, phone


def _resolve_insured(
    name: str,
    birth_expr: str,
    explicit_id: str,
    used_ids: set[str],
) -> tuple[str, str, str]:
    """被保人身份：Excel 显式证件号 → 实名池同名身份 → 实名池按序分配 → 生成号兜底。"""
    birth = _birth(birth_expr)
    if explicit_id:
        used_ids.add(explicit_id.upper())
        return name, explicit_id, birth

    found = find_identity(name=name)
    if found is None:
        found = next_available(exclude_ids=used_ids)
        if found:
            execution_recorder.record(
                "被保人改用实名身份",
                f"{name} → {found['name']} / {found['id_no']}（二要素校验需姓名与证件号一致）",
            )

    if found:
        used_ids.add(found["id_no"].upper())
        real_birth = birth_of(found["id_no"]).isoformat()
        if real_birth != birth:
            execution_recorder.record(
                "实名身份出生日期与用例不一致",
                f"{found['name']}：用例 {birth} / 实名 {real_birth}，按实名身份执行",
            )
        return found["name"], found["id_no"], real_birth

    execution_recorder.record(
        "实名身份池不足", f"{name} 使用生成号，无法通过二要素校验，请在 data/verified_identities.csv 补充"
    )
    return name, generate_id_no(birth, 1, area_code=AREA_CODE), birth


def _people(case: dict[str, str]) -> list[dict[str, str]]:
    """把 Excel 中逗号分隔的多被保人数据拆成逐人配置。"""
    names = _split(case, "insured_names")
    births = _split(case, "insured_birth_dates")
    assert names, f'{case["case_id"]} 未填写被保人姓名或出生日期'
    assert len(names) == len(births), (
        f'{case["case_id"]} 的 insured_names 与 insured_birth_dates 数量不一致'
    )
    id_nos = _split(case, "insured_id_nos")
    relations = _split(case, "insured_relations")
    certs = _split(case, "insured_cert_types")
    _, payer_id, _ = _payer_identity(case)
    used_ids = {payer_id.upper()}
    people = []
    for index, (name, birth_expr) in enumerate(zip(names, births)):
        cert_type = certs[index] if index < len(certs) else "身份证"
        explicit_id = id_nos[index] if index < len(id_nos) else ""
        name, id_no, birth = _resolve_insured(name, birth_expr, explicit_id, used_ids)
        people.append(
            {
                "name": name,
                "birth": birth,
                "id_no": id_no,
                "relation": relations[index] if index < len(relations) else "子女",
                "cert_type": cert_type,
            }
        )
    return people


def _register(policy: IndividualPolicyPage, case: dict[str, str]) -> None:
    """缴费人录入、短信验证与快速注册登录；已登录时直接复用，不再重复填写。"""
    if policy.is_logged_in():
        execution_recorder.record(
            "复用已登录状态", "跳过缴费人信息填写、短信验证与快速注册"
        )
        return

    name, id_no, phone = _payer_identity(case)
    assert age_at(id_no) >= 18, f"缴费人必须为成年人：{name} / {id_no}"
    with allure.step(f"填写缴费人：{name} / {id_no} / {phone}"):
        policy.fill_payer(
            name, id_no, phone, case.get("payer_cert_type") or "身份证"
        )

    with allure.step(f'获取短信验证码并输入：{case["payer_sms_code"]}'):
        policy.send_sms_code()
        policy.fill_sms_code(case["payer_sms_code"])
        policy.blur()

    with allure.step("确认以投保人信息快速注册或登录"):
        policy.confirm_quick_register()

    with allure.step("保存登录态，供后续执行复用"):
        policy.save_session()


def _build_insureds(
    policy: IndividualPolicyPage, people: list[dict[str, str]], case: dict[str, str]
) -> list[str]:
    """逐人新增并填写被保人，清理账号历史被保人，按需选择产品版本。

    登录态下首张卡片是缴费人「本人」只读卡（无输入框），因此每名被保人
    （含第一名）都通过「添加被保人」新增空白卡后填写，不做 index=0 假定。
    """
    ids: list[str] = []
    for order, person in enumerate(people):
        assert policy.add_insured_card(), (
            f'添加第 {order + 1} 名被保人失败，可能已触发被保人数量上限'
        )
        policy.cleanup_insureds(set(ids), keep_empty=True)
        empty_index = [
            i for i, state in enumerate(policy.insured_states()) if not state.get("id")
        ]
        assert empty_index, f'添加被保人后未出现空白卡片：{person["name"]}'
        index = empty_index[-1]

        with allure.step(
            f'填写被保人{order + 1}：{person["name"]} / {person["id_no"]} / {person["relation"]}'
        ):
            policy.fill_insured_card(
                index,
                person["relation"],
                person["name"],
                person["id_no"],
                person["cert_type"],
            )

        ids.append(person["id_no"])
        policy.cleanup_insureds(set(ids))

    version = _order_version(case)
    if version:
        with allure.step(f"切换产品版本：{version}"):
            policy.select_version(version)
    return ids


def _order_version(case: dict[str, str]) -> str:
    """产品版本为订单级二选一（升级版/基础版），取配置值即可。"""
    return (case.get("plan_selection") or "").split(",")[0].strip()


def _assert_family_discount(policy: IndividualPolicyPage, expected: str) -> None:
    expected = (expected or "").strip()
    if not expected:
        return
    actual = policy.family_discount_visible()
    visible = "可见" if actual else "不可见"
    execution_recorder.record(
        "校验家庭优惠标签", f"期望{'可见' if expected == 'Y' else '不可见'}，实际{visible}"
    )
    assert actual == (expected == "Y"), (
        f"家庭优惠标签不符：期望 {expected}，实际 {visible}"
    )


def _assert_per_person(
    policy: IndividualPolicyPage, case: dict[str, str], people: list[dict[str, str]]
) -> None:
    """现网卡片不再展示每人金额，按每人期望保费求和对订单总价校验。"""
    expected = _split(case, "expected_per_person_amounts")
    actual = policy.total_price()
    if not expected:
        execution_recorder.record(
            "订单保费合计", f"{actual} 元 / {len(people)} 人（未配置每人保费）"
        )
        assert actual > 0, "订单保费合计应大于 0"
        return

    for index, amount in enumerate(expected):
        execution_recorder.record(
            f'被保人{index + 1} 期望保费（{people[index]["birth"]}）', f"{amount} 元"
        )
    total = sum(float(amount) for amount in expected)
    if len(expected) >= 3:
        total -= 5 * len(expected)
        execution_recorder.record("家庭优惠", f"满 3 人每人立减 5 元，共减 {5 * len(expected)} 元")
    if (case.get("expected_total_price") or "").strip():
        return
    assert abs(actual - total) < 0.01, (
        f"保费合计不符：期望 {total} 元，实际 {actual} 元"
    )


def _assert_total(policy: IndividualPolicyPage, case: dict[str, str]) -> None:
    expected_total = (case.get("expected_total_price") or "").strip()
    if not expected_total:
        return
    actual = policy.total_price()
    execution_recorder.record(
        "校验保费合计", f"期望 {expected_total} 元，实际 {actual} 元"
    )
    assert actual == int(expected_total), (
        f"保费合计不符：期望 {expected_total} 元，实际 {actual} 元"
    )


def _set_meta(case: dict[str, str]) -> None:
    allure.dynamic.feature(case["feature"])
    allure.dynamic.story(case["story"])
    allure.dynamic.title(f'{case["case_id"]} {case["title"]}')
    allure.dynamic.severity(case["severity"])
    execution_recorder.set_title(f'{case["case_id"]} {case["title"]}')


# ---------- 投保人年龄边界 ----------


@pytest.mark.policy
@pytest.mark.parametrize(
    "case", _cases("payer_age"), ids=[c["case_id"] for c in _cases("payer_age")]
)
def test_payer_age_check(page, case):
    """按投保日计算投保人年龄：满 18 周岁放行，未满 18 周岁前端拦截。

    该用例只校验前端年龄提示，不发送短信、不注册登录，因此可使用生成号。
    """
    _set_meta(case)
    policy = IndividualPolicyPage(page).open_payer_form(fresh=True)
    name, id_no, phone = _payer_identity(case)
    with allure.step(f"填写缴费人：{name} / {id_no} / {phone}"):
        policy.fill_payer(
            name, id_no, phone, case.get("payer_cert_type") or "身份证"
        )

    blocked = case["expected_value"] != "pass"
    with allure.step("校验投保人年龄："):
        policy.blur()
        if blocked:
            tip = case["expected_tip"]
            assert policy.tip_visible(tip), f"未出现预期拦截提示：{tip}"
            execution_recorder.record("投保人年龄拦截生效", tip)
        else:
            assert not policy.tip_visible(
                IndividualPolicyPage.PAYER_AGE_TIP, timeout=3000
            ), "投保人已满 18 周岁，不应出现年龄拦截提示"
            execution_recorder.record("投保校验通过", "无年龄拦截提示")


# ---------- 被保人年龄 ----------


@pytest.mark.policy
@pytest.mark.parametrize(
    "case", _cases("insured_age"), ids=[c["case_id"] for c in _cases("insured_age")]
)
def test_insured_age_check(page, case):
    """被保人年龄按生效日计算且无年龄限制，未满 1 岁与超百岁均可投保。"""
    _set_meta(case)
    policy = IndividualPolicyPage(page).open_payer_form()
    _register(policy, case)

    people = _people(case)
    _build_insureds(policy, people, case)
    person = people[0]
    with allure.step(
        f'校验被保人年龄 {person["birth"]}（生效日 {EFFECTIVE_DATE}）可正常保存'
    ):
        index = policy.insured_index(person["id_no"])
        amount = policy.total_price()
        execution_recorder.record(
            "被保人保存成功",
            f'{person["name"]} / {person["id_no"]}（卡片 {index + 1}）',
        )
        execution_recorder.record("订单保费合计", f"{amount} 元")
        assert amount > 0, "被保人保费应大于 0"
        allure.attach(page.screenshot(), "被保人年龄校验", allure.attachment_type.PNG)


# ---------- 被保人数量上限 ----------


@pytest.mark.policy
@pytest.mark.parametrize(
    "case", _cases("insured_limit"), ids=[c["case_id"] for c in _cases("insured_limit")]
)
def test_insured_limit(page, case):
    """个单支持 8 位被保人；子女关系最多 4 人，第 5 位子女被前端拦截。"""
    _set_meta(case)
    policy = IndividualPolicyPage(page).open_payer_form()
    _register(policy, case)

    people = _people(case)
    _build_insureds(policy, people, case)
    with allure.step(f'校验被保人数量：{case["expected_value"]} 位'):
        actual = policy.insured_cards().count()
        expected = int(case["expected_value"])
        execution_recorder.record(
            "校验被保人数量", f"期望 {expected}，实际 {actual}"
        )
        assert actual == expected, (
            f"被保人数量不符：期望 {expected}，实际 {actual}"
        )

    if case.get("expected_tip"):
        with allure.step("点击新增被保人，校验提示："):
            assert policy.add_insured_card() is False, "第 9 位被保人未被前端限制"
            assert policy.tip_visible(case["expected_tip"]), (
                f'未出现预期提示：{case["expected_tip"]}'
            )
    allure.attach(page.screenshot(), "被保人数量上限", allure.attachment_type.PNG)


# ---------- 多证件类型 ----------


@pytest.mark.policy
@pytest.mark.parametrize(
    "case", _cases("cert_type"), ids=[c["case_id"] for c in _cases("cert_type")]
)
def test_cert_type(page, case):
    """身份证、护照、港澳居民来往内地通行证、台湾居民来往大陆通行证均可正常保存。"""
    _set_meta(case)
    policy = IndividualPolicyPage(page).open_payer_form()
    _register(policy, case)

    people = _people(case)
    _build_insureds(policy, people, case)
    with allure.step(f'校验 {len(people)} 类证件类型的被保人均保存成功'):
        actual = policy.insured_cards().count()
        assert actual == len(people), (
            f"被保人数量不符：期望 {len(people)}，实际 {actual}"
        )
        for person in people:
            card_index = policy.insured_index(person["id_no"])
            execution_recorder.record(
                f'{person["cert_type"]} 保存成功',
                f'{person["name"]} / {person["id_no"]}（卡片 {card_index + 1}）',
            )
        amount = policy.total_price()
        execution_recorder.record(
            "订单保费合计", f"{amount} 元 / {len(people)} 人"
        )
        assert amount > 0, "被保人保费应大于 0"
    allure.attach(page.screenshot(), "多证件类型被保人", allure.attachment_type.PNG)


# ---------- 关系下拉选项 ----------


@pytest.mark.policy
@pytest.mark.parametrize(
    "case",
    _cases("relation_options"),
    ids=[c["case_id"] for c in _cases("relation_options")],
)
def test_relation_options(page, case):
    """投被保人关系下拉选项为本人、父母、配偶、子女、其他，无多余选项。"""
    _set_meta(case)
    policy = IndividualPolicyPage(page).open_payer_form()
    _register(policy, case)

    people = _people(case)
    _build_insureds(policy, people, case)
    with allure.step(f'校验关系下拉选项：{case["expected_value"]}'):
        expected = [item for item in case["expected_value"].split("|") if item]
        actual = policy.relation_options(0)
        execution_recorder.record("关系下拉实际选项", "、".join(actual))
        assert actual == expected, (
            f"关系下拉选项不符：期望 {expected}，实际 {actual}"
        )


# ---------- 保费与家庭优惠 ----------


@pytest.mark.policy
@pytest.mark.parametrize(
    "case", _cases("premium"), ids=[c["case_id"] for c in _cases("premium")]
)
def test_premium_and_family_discount(page, case):
    """校验每人展示的产品与保费、是否享受家庭优惠以及保费合计。"""
    _set_meta(case)
    policy = IndividualPolicyPage(page).open_payer_form()
    _register(policy, case)

    people = _people(case)
    _build_insureds(policy, people, case)
    with allure.step("校验每个被保人保费与订单合计"):
        _assert_per_person(policy, case, people)

    with allure.step("校验家庭优惠标签与保费合计"):
        _assert_family_discount(policy, case.get("expected_family_discount", ""))
        _assert_total(policy, case)
        allure.attach(page.screenshot(), "保费与家庭优惠", allure.attachment_type.PNG)


# ---------- H5 支付方式 ----------


@pytest.mark.policy
@pytest.mark.parametrize(
    "case", _cases("h5_account"), ids=[c["case_id"] for c in _cases("h5_account")]
)
def test_h5_account_payment_popup(page, case):
    """纯 H5 首页选择个账支付：弹出医保提示弹窗，关闭后可切换其他支付方式。"""
    _set_meta(case)
    policy = IndividualPolicyPage(page).open_payer_form()
    _register(policy, case)
    _build_insureds(policy, _people(case), case)

    with allure.step(f'选择支付方式：{case["payment_method"]}'):
        policy.select_payment(case["payment_method"])

    with allure.step("点击立即参保，校验医保个账支付提示弹窗"):
        policy.check_agreement()
        policy.read_agreements()
        policy.submit()
        actual = policy.account_pay_popup_text()
        assert actual, "选择个账支付后未弹出医保支付提示"
        expected = case.get("expected_popup_text") or ""
        if expected:
            assert actual == expected, f"弹窗文案不符：期望 {expected}，实际 {actual}"
        allure.attach(page.screenshot(), "医保个账支付提示", allure.attachment_type.PNG)

    with allure.step("关闭弹窗后可切换其他支付方式"):
        policy.close_account_pay_popup()
        policy.select_payment("微信支付")
        execution_recorder.record("关闭弹窗后切换为其他支付方式", "微信支付")


@pytest.mark.policy
@pytest.mark.parametrize(
    "case",
    _cases("h5_account_pending"),
    ids=[c["case_id"] for c in _cases("h5_account_pending")],
)
def test_h5_pending_account_payment_popup(page, case):
    """纯 H5 先用微信支付发起，再切换为医保支付后提交，弹出医保支付提示弹窗。"""
    _set_meta(case)
    policy = IndividualPolicyPage(page).open_payer_form()
    _register(policy, case)
    _build_insureds(policy, _people(case), case)

    with allure.step("先在待支付页使用微信支付发起参保"):
        policy.select_payment("微信支付")
        policy.check_agreement()
        policy.read_agreements()
        policy.submit()
        policy.page.wait_for_timeout(3000)
        assert not policy.account_pay_popup_text(timeout=3000), (
            "非个账支付不应出现医保提示弹窗"
        )

    with allure.step(f'切换支付方式：{case["payment_method"]}'):
        policy.select_payment(case["payment_method"])

    with allure.step("点击立即参保，校验医保个账支付提示弹窗"):
        policy.submit()
        actual = policy.account_pay_popup_text()
        assert actual, "待支付页选择个账支付后未弹出医保支付提示"
        expected = case.get("expected_popup_text") or ""
        if expected:
            assert actual == expected, f"弹窗文案不符：期望 {expected}，实际 {actual}"
        allure.attach(page.screenshot(), "待支付页个账支付提示", allure.attachment_type.PNG)


@pytest.mark.policy
@pytest.mark.parametrize(
    "case", _cases("h5_wechat"), ids=[c["case_id"] for c in _cases("h5_wechat")]
)
def test_h5_wechat_payment(page, case):
    """纯 H5 首页选择非个账支付：无提示弹窗，直接进入收银台。"""
    _set_meta(case)
    policy = IndividualPolicyPage(page).open_payer_form()
    _register(policy, case)
    _build_insureds(policy, _people(case), case)

    with allure.step(f'选择支付方式：{case["payment_method"]}'):
        policy.select_payment(case["payment_method"])

    with allure.step("点击立即参保，校验无医保提示弹窗"):
        policy.check_agreement()
        policy.read_agreements()
        policy.submit()
        actual = policy.account_pay_popup_text(timeout=3000)
        assert not actual, f"非个账支付不应弹出医保提示：{actual}"
        execution_recorder.record("非个账支付无提示弹框", "校验通过")

    with allure.step("校验已进入收银台"):
        assert policy.in_cashier(), "选择微信支付后未进入收银台"
        allure.attach(page.screenshot(), "收银台", allure.attachment_type.PNG)


# ---------- 家庭优惠标签 ----------


@pytest.mark.policy
@pytest.mark.parametrize(
    "case", _cases("family_tag"), ids=[c["case_id"] for c in _cases("family_tag")]
)
def test_family_discount_tag(page, case):
    """满足家庭优惠条件的订单展示家庭优惠标签。"""
    _set_meta(case)
    policy = IndividualPolicyPage(page).open_payer_form()
    _register(policy, case)

    people = _people(case)
    _build_insureds(policy, people, case)
    with allure.step("校验订单展示家庭优惠标签"):
        assert policy.insured_cards().count() == len(people)
        _assert_family_discount(policy, case.get("expected_family_discount", ""))
        allure.attach(page.screenshot(), "家庭优惠标签", allure.attachment_type.PNG)
