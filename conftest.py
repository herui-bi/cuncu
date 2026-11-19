"""全局 fixture：环境配置、浏览器参数、登录态、失败截图与日志。"""

from __future__ import annotations

from pathlib import Path

import allure
import pytest
import webbrowser
from playwright.sync_api import Page

from utils import execution_recorder
from utils.config_loader import get_config, set_active
from utils.logger import setup_logger

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "reports" / "artifacts"

logger = setup_logger()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--env",
        action="store",
        default=None,
        help="运行项目，对应 config/environments/<项目>/<阶段>.yaml 的目录名",
    )


def pytest_configure(config: pytest.Config) -> None:
    cfg = get_config(config.getoption("--env"))
    set_active(cfg)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    logger.info("运行项目: %s | 阶段: %s | base_url: %s", cfg.env, cfg.stage, cfg.base_url)


@pytest.fixture(scope="session")
def config():
    return get_config()


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, config):
    """在 pytest-playwright 默认参数上追加项目级浏览器配置。"""
    overrides = {
        "viewport": config.viewport,
        "ignore_https_errors": config.ignore_https_errors,
        "locale": config.locale,
        "is_mobile": config.is_mobile,
    }
    if config.auth_enabled and config.auth_state_path.exists():
        overrides["storage_state"] = str(config.auth_state_path)
    return {**browser_context_args, **overrides}


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args, config, pytestconfig):
    headed = pytestconfig.getoption("--headed")
    return {
        **browser_type_launch_args,
        "headless": config.headless and not headed,
        "slow_mo": config.slow_mo,
    }


@pytest.fixture
def login_page(page: Page):
    from pages.login_page import LoginPage

    return LoginPage(page)


@pytest.fixture
def logged_in_page(login_page, config) -> Page:
    """打开系统并完成登录，供依赖登录态的用例直接使用。"""
    from pages.inventory_page import InventoryPage

    login_page.open().login(config.auth_username, config.auth_password)
    InventoryPage(login_page.page).wait_loaded()
    return login_page.page


def pytest_runtest_setup(item: pytest.Item) -> None:
    execution_recorder.start(item.name)


# 惠衢保升级用例执行优先级：查看/选择类优先，退款/支付等消耗数据的用例放在最后
_EXEC_PRIORITY = {
    "list_entry": 0,
    "detail_entry": 1,
    "upgrade_page": 2,
    "selection": 3,
    "amount": 4,
    "tips": 5,
    "validation": 6,
    "group_upgrade": 7,
    "payment": 8,
}
_ORDERED_MODULES = ("test_order_upgrade.py",)


def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    """按用例类型重排执行顺序，避免退款/支付用例先消耗数据导致查看类用例无数据。"""
    positions = [
        index for index, item in enumerate(items) if any(m in item.nodeid for m in _ORDERED_MODULES)
    ]
    if not positions:
        return

    def priority(item: pytest.Item) -> int:
        callspec = getattr(item, "callspec", None)
        case = (callspec.params.get("case") if callspec else None) or {}
        return _EXEC_PRIORITY.get(str(case.get("test_type", "")), len(_EXEC_PRIORITY))

    ordered = sorted((items[index] for index in positions), key=priority)
    for position, item in zip(positions, ordered):
        items[position] = item


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    for line in execution_recorder.summary_lines():
        print(line)
    # 报告写入后会清空历史，钉钉通知需要提前取快照
    cases = execution_recorder.history()
    path = execution_recorder.write_report(get_config().base_url)
    print(f"测试报告（含执行过程）: {path}")
    _notify_dingtalk(path, cases)
    webbrowser.open(path.resolve().as_uri())


def _notify_dingtalk(report_path, cases: list[dict]) -> None:
    """配置了 DINGTALK_WEBHOOK 时，推送执行结果到钉钉群。"""
    import os

    cfg = {
        "webhook": os.getenv("DINGTALK_WEBHOOK", ""),
        "secret": os.getenv("DINGTALK_SECRET", ""),
        "at_mobiles": os.getenv("DINGTALK_AT_MOBILES", ""),
    }
    if not cfg["webhook"]:
        return
    try:
        from utils.dingtalk import notify_dingtalk

        notify_dingtalk(cases, get_config().base_url, str(report_path), cfg)
    except Exception as exc:  # 通知失败不影响测试结果与报告生成
        logger.warning("钉钉群通知发送失败: %s", exc)


def _failure_reason(report: pytest.TestReport) -> str:
    """提取失败原因：优先断言消息，其次完整堆栈。"""
    crash = getattr(report.longrepr, "reprcrash", None)
    message = getattr(crash, "message", "")
    if message:
        return str(message)
    return (report.longreprtext or "").strip()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)

    if report.when == "call" or (
        report.when == "setup" and (report.failed or report.skipped)
    ):
        result = "通过" if report.passed else ("失败" if report.failed else "跳过")
        error = _failure_reason(report) if report.failed else ""
        steps = execution_recorder.finish(result, report.duration, error)
        if steps:
            allure.attach(
                "\n".join(steps),
                name="执行过程",
                attachment_type=allure.attachment_type.TEXT,
            )

    if report.failed and report.when in ("setup", "call"):
        page = item.funcargs.get("page")
        if isinstance(page, Page) and not page.is_closed():
            try:
                screenshot = page.screenshot(full_page=True)
                allure.attach(
                    screenshot,
                    name="失败截图",
                    attachment_type=allure.attachment_type.PNG,
                )
            except Exception as exc:  # 截图失败不应影响测试结果
                logger.warning("失败截图采集失败: %s", exc)
