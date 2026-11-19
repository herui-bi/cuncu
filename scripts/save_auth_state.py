"""登录一次并保存登录态到 auth/storage_state.json，供内网系统用例复用。"""

from __future__ import annotations

from playwright.sync_api import sync_playwright

from utils.config_loader import get_config


def main() -> None:
    config = get_config()
    selectors = config.auth.get("selectors") or {}
    state_path = config.auth_state_path
    state_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(ignore_https_errors=config.ignore_https_errors)
        page = context.new_page()
        page.goto(config.url(config.login_path))

        if config.auth_username:
            page.fill(selectors.get("username", "#user-name"), config.auth_username)
            page.fill(selectors.get("password", "#password"), config.auth_password)
            page.click(selectors.get("submit", "#login-button"))

        input("请在浏览器中完成登录（含验证码），确认已进入系统后按回车保存登录态...")
        context.storage_state(path=str(state_path))
        browser.close()

    print(f"登录态已保存: {state_path}")
    print("将 config/config.yaml 中 auth.enabled 设为 true 即可自动复用")


if __name__ == "__main__":
    main()
