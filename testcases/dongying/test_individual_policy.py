"""个单投保自动化测试（源自 docs/testcases/东营惠民保2027投保对接 (1).docx）。

用例数据维护在 data/dongying/caseData.xlsx 的 policy 工作表：
- test_type=age     被保人年龄校验（2008-01-01 分界、未成年人 / 成年人识别与可选版本）
- test_type=version 成年人默认升级版且不展示少儿守护版
- test_type=multi   多被保人各自独立选择产品版本
- test_type=premium 升级版订单 ≥5 人优惠浮层与保费合计
- test_type=order   完整下单：强制阅读协议、签字临摹、订单号与 share_code

被保人不做外部参保资格校验，证件号按出生日期生成仅用于年龄识别；缴费人必须使用
data/verified_identities.csv 中的实名身份，保证快速注册与二要素通过。
"""

from __future__ import annotations

import allure
import pytest

from pages.dongying.individual_policy_page import IndividualPolicyPage
from utils import execution_recorder
from utils.db import get_order_share_code
from utils.excel_reader import read_cases
from utils.id_card import generate_id_no
from utils.identity import find as find_identity
from utils.identity import next_available

POLICY_CASES = read_cases("policy", workbook="data/dongying/caseData.xlsx")

# 现网未成年人版本名称在「少儿守护版」与「成长守护版」之间变更过，比对时统一归一化
_MEMBER_PLAN_ALIASES = {"成长守护版": "少儿守护版"}


def _normalize_plan(name: str) -> str:
    plan = name.strip()
    return _MEMBER_PLAN_ALIASES.get(plan, plan)


def _cases(*test_types: str) -> list[dict[str, str]]:
    return [case for case in POLICY_CASES if case.get("test_type") in test_types]


def _split(case: dict[str, str], key: str) -> list[str]:
    return [item.strip() for item in (case.get(key) or "").split(",") if item.strip()]


def _resolve_insured_id(
    name: str,
    birth: str,
    explicit_id: str,
    used_ids: set[str],
) -> str:
    """被保人身份：Excel 显式证件号 → 实名池 → 按出生日期生成（页面不做外部参保资格校验）。"""
    if explicit_id:
        used_ids.add(explicit_id.upper())
        return explicit_id

    found = find_identity(name=name) or next_available(exclude_ids=used_ids)
    if found:
        used_ids.add(found["id_no"].upper())
        execution_recorder.record(
            "被保人改用实名身份",
            f'{name} → {found["name"]} / {found["id_no"]}',
        )
        return found["id_no"]

    generated = generate_id_no(birth, 1)
    execution_recorder.record(
        "被保人使用生成身份证号",
        f"{name} / {generated}（仅用于年龄识别，页面不做参保资格外部校验）",
    )
    return generated


def _people(case: dict[str, str]) -> list[dict[str, str]]:
    """把 Excel 中逗号分隔的多被保人数据拆成逐人配置，并解析可用证件号。"""
    names = _split(case, "insured_names")
    births = _split(case, "insured_birth_dates")
    assert names and len(names) == len(births), (
        f'{case["case_id"]} 的 insured_names 与 insured_birth_dates 数量不一致'
    )
    relations = _split(case, "insured_relations")
    plans = _split(case, "plan_selection")
    types = _split(case, "expected_insured_types")
    explicit_ids = _split(case, "insured_id_nos")
    used_ids = {(case.get("payer_id_no") or "").strip().upper()}
    people = []
    for index, (name, birth) in enumerate(zip(names, births)):
        explicit = explicit_ids[index] if index < len(explicit_ids) else ""
        people.append(
            {
                "name": name,
                "birth": birth,
                "relation": relations[index] if index < len(relations) else "子女",
                "plan": plans[index] if index < len(plans) else "",
                "expected_type": types[index] if index < len(types) else "",
                "id_no": _resolve_insured_id(name, birth, explicit, used_ids),
            }
        )
    return people


def _register(policy: IndividualPolicyPage, case: dict[str, str]) -> None:
    """缴费人录入、短信验证与快速注册登录。"""
    with allure.step(
        f'填写缴费人：{case["payer_name"]} / {case["payer_id_no"]} / {case["payer_phone"]}'
    ):
        policy.fill_payer(case["payer_name"], case["payer_id_no"], case["payer_phone"])

    with allure.step(f'获取短信验证码并输入：{case["payer_sms_code"]}'):
        policy.send_sms_code()
        policy.fill_sms_code(case["payer_sms_code"])
        policy.blur()

    with allure.step("确认以投保人信息快速注册或登录"):
        policy.confirm_quick_register()


def _build_insureds(policy: IndividualPolicyPage, people: list[dict[str, str]]) -> list[str]:
    """逐人新增并填写被保人，清理账号历史被保人，按需选择保障计划。"""
    policy.clear_to_single_insured()
    ids: list[str] = []
    for order, person in enumerate(people):
        if order == 0:
            index = 0
        else:
            policy.add_insured_card()
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
                person["expected_type"],
            )

        ids.append(person["id_no"])
        policy.cleanup_insureds(set(ids))

        if person["plan"]:
            with allure.step(f'被保人{order + 1}选择保障计划：{person["plan"]}'):
                policy.select_plan(policy.insured_index(person["id_no"]), person["plan"])
    return ids


def _assert_selected_plans(
    policy: IndividualPolicyPage, people: list[dict[str, str]], ids: list[str]
) -> None:
    """校验每张卡片各自保存所选版本，未被其他卡片覆盖。"""
    for person, id_no in zip(people, ids):
        if not person["plan"]:
            continue
        index = policy.insured_index(id_no)
        actual = _normalize_plan(policy.selected_plan(index))
        expected = _normalize_plan(person["plan"])
        assert actual == expected, (
            f'被保人 {person["name"]} 保障计划被覆盖：期望 {person["plan"]}，实际 {actual}'
        )
        execution_recorder.record(
            f'校验被保人 {person["name"]} 保障计划', f'实际 {actual}'
        )


def _assert_float_and_total(policy: IndividualPolicyPage, case: dict[str, str]) -> None:
    expected_float = (case.get("expected_float_text") or "").strip()
    if expected_float:
        actual_float = policy.float_text()
        execution_recorder.record("校验底部浮层文案", actual_float)
        # 文档中的「即将满足/恭喜」前缀与现网 DOM 可能不一致，按核心文案包含匹配
        assert expected_float in actual_float, (
            f'浮层文案不符：期望包含 {expected_float!r}，实际 {actual_float!r}'
        )

    expected_total = (case.get("expected_total_price") or "").strip()
    if expected_total:
        actual_total = policy.total_price()
        execution_recorder.record("校验保费合计", f"期望 {expected_total} 元，实际 {actual_total} 元")
        assert actual_total == int(expected_total), (
            f'保费合计不符：期望 {expected_total} 元，实际 {actual_total} 元'
        )


@pytest.mark.policy
@pytest.mark.parametrize("case", _cases("age"), ids=[c["case_id"] for c in _cases("age")])
def test_insured_age_check(page, case):
    """按证件号识别被保人年龄，并校验可选的保障计划与默认版本。"""
    allure.dynamic.feature(case["feature"])
    allure.dynamic.story(case["story"])
    allure.dynamic.title(f'{case["case_id"]} {case["title"]}')
    allure.dynamic.severity(case["severity"])
    execution_recorder.set_title(f'{case["case_id"]} {case["title"]}')

    policy = IndividualPolicyPage(page).open_payer_form()
    _register(policy, case)

    person = _people(case)[0]
    _build_insureds(policy, [person])

    with allure.step(
        f'校验年龄识别：{person["expected_type"]}（出生日期 {person["birth"]} 由证件号解析）'
    ):
        expected_minor = person["expected_type"] == "未成年人"
        actual_tip = policy.minor_tip_visible(0)
        assert actual_tip == expected_minor, (
            f'年龄识别不符：期望 {person["expected_type"]}，'
            f'监护人提示{"可见" if actual_tip else "不可见"}'
        )
        allure.attach(page.screenshot(), "被保人识别后", allure.attachment_type.PNG)

    with allure.step("校验可选保障计划"):
        expected_versions = [_normalize_plan(name) for name in case["expected_versions"].split("|") if name]
        plans = [_normalize_plan(name) for name in policy.available_plans(0)]
        assert set(plans) == set(expected_versions), f"保障计划实际：{plans}，期望：{expected_versions}"
        execution_recorder.record("校验可选保障计划", "、".join(plans))

    with allure.step("校验默认选中版本"):
        expected_default = (case.get("expected_default_versions") or "").strip()
        if expected_default:
            actual_default = _normalize_plan(policy.selected_plan(0))
            assert actual_default == expected_default, (
                f"默认版本不符：期望 {expected_default}，实际 {actual_default}"
            )
            execution_recorder.record("校验默认保障计划", actual_default)


@pytest.mark.policy
@pytest.mark.parametrize(
    "case", _cases("version"), ids=[c["case_id"] for c in _cases("version")]
)
def test_adult_version_options(page, case):
    """成年被保人默认选中升级版，可选项为基础版/升级版，不展示少儿守护版。"""
    allure.dynamic.feature(case["feature"])
    allure.dynamic.story(case["story"])
    allure.dynamic.title(f'{case["case_id"]} {case["title"]}')
    allure.dynamic.severity(case["severity"])
    execution_recorder.set_title(f'{case["case_id"]} {case["title"]}')

    policy = IndividualPolicyPage(page).open_payer_form()
    _register(policy, case)

    person = _people(case)[0]
    _build_insureds(policy, [person])

    with allure.step("校验成年人可选项与默认选中版本"):
        expected_versions = [_normalize_plan(name) for name in case["expected_versions"].split("|") if name]
        plans = [_normalize_plan(name) for name in policy.available_plans(0)]
        assert set(plans) == set(expected_versions), f"保障计划实际：{plans}，期望：{expected_versions}"
        assert "少儿守护版" not in plans, f"成年人不应展示少儿守护版，实际：{plans}"
        execution_recorder.record("校验可选保障计划", "、".join(plans))

    with allure.step("校验默认选中升级版"):
        actual_default = _normalize_plan(policy.selected_plan(0))
        assert actual_default == case["expected_default_versions"].strip(), (
            f'默认版本不符：期望 {case["expected_default_versions"]}，实际 {actual_default}'
        )
        execution_recorder.record("校验默认保障计划", actual_default)


@pytest.mark.policy
@pytest.mark.parametrize("case", _cases("multi"), ids=[c["case_id"] for c in _cases("multi")])
def test_multi_insured_versions(page, case):
    """多个被保人各自选择版本，互不覆盖。"""
    allure.dynamic.feature(case["feature"])
    allure.dynamic.story(case["story"])
    allure.dynamic.title(f'{case["case_id"]} {case["title"]}')
    allure.dynamic.severity(case["severity"])
    execution_recorder.set_title(f'{case["case_id"]} {case["title"]}')

    policy = IndividualPolicyPage(page).open_payer_form()
    _register(policy, case)

    people = _people(case)
    ids = _build_insureds(policy, people)

    with allure.step("校验各被保人版本互相独立、无覆盖"):
        _assert_selected_plans(policy, people, ids)
        allure.attach(page.screenshot(), "多被保人版本选择后", allure.attachment_type.PNG)

    _assert_float_and_total(policy, case)


@pytest.mark.policy
@pytest.mark.parametrize("case", _cases("premium"), ids=[c["case_id"] for c in _cases("premium")])
def test_upgrade_premium_discount(page, case):
    """升级版家庭单保费优惠：浮层文案与全员保费立减。"""
    allure.dynamic.feature(case["feature"])
    allure.dynamic.story(case["story"])
    allure.dynamic.title(f'{case["case_id"]} {case["title"]}')
    allure.dynamic.severity(case["severity"])
    execution_recorder.set_title(f'{case["case_id"]} {case["title"]}')

    policy = IndividualPolicyPage(page).open_payer_form()
    _register(policy, case)

    people = _people(case)
    ids = _build_insureds(policy, people)

    with allure.step("校验各被保人保障计划"):
        _assert_selected_plans(policy, people, ids)

    with allure.step("校验底部浮层文案与保费合计"):
        _assert_float_and_total(policy, case)
        allure.attach(page.screenshot(), "保费优惠校验后", allure.attachment_type.PNG)


@pytest.mark.policy
def test_create_order_and_check_share_code(page):
    """完整下单并签字，在订单详情页取订单号，比对分表 share_code 与用例期望值。"""
    case = {item["case_id"]: item for item in POLICY_CASES}["policy_012"]
    allure.dynamic.feature(case["feature"])
    allure.dynamic.story("订单创建与分享码校验")
    allure.dynamic.title(f'{case["case_id"]} 创建订单并从订单详情取订单号校验 share_code')
    allure.dynamic.severity(case["severity"])
    execution_recorder.set_title(f'{case["case_id"]} 创建订单并校验 share_code')

    policy = IndividualPolicyPage(page).open_payer_form()
    _register(policy, case)
    _build_insureds(policy, _people(case))

    with allure.step("选择微信支付并阅读全部协议"):
        policy.select_payment(case["payment_method"])
        policy.check_agreement()
        policy.read_agreements()

    with allure.step(f'点击立即投保并按缴费人姓名签字：{case["payer_name"]}'):
        policy.submit()
        policy.sign(case["payer_name"])
        page.wait_for_timeout(3000)

    with allure.step("在订单详情页获取订单号"):
        order_no = policy.latest_order_detail_no()
        execution_recorder.record("订单创建成功", order_no)
        allure.attach(
            f"订单号：{order_no}",
            name="订单详情",
            attachment_type=allure.attachment_type.TEXT,
        )

    with allure.step("按订单尾号查询分表 share_code 并与用例期望值比对"):
        actual = get_order_share_code(order_no)
        expected = case.get("expected_share_code", "").strip()
        execution_recorder.record("数据库校验 share_code", f"期望 {expected!r}，实际 {actual!r}")
        if not expected:
            # 用例未填写期望值时只回显实际值，便于补充到 Excel 后开启严格比对
            allure.attach(
                f"订单号：{order_no}\nshare_code：{actual!r}\n用例未填写期望值",
                name="share_code 实际值",
                attachment_type=allure.attachment_type.TEXT,
            )
            return
        assert actual == expected, (
            f"订单 {order_no} 的 share_code 不符，期望 {expected!r}，实际 {actual!r}"
        )
