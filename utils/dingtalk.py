"""钉钉群机器人通知：测试执行结束后推送结果汇总与失败原因。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime

from utils.execution_recorder import brief_error
from utils.logger import setup_logger

logger = setup_logger()


def _signed_url(webhook: str, secret: str) -> str:
    """机器人安全设置为「加签」时，追加 timestamp + sign。"""
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(
        secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(digest))
    return f"{webhook}&timestamp={timestamp}&sign={sign}"


def _post(url: str, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        body = json.loads(response.read().decode("utf-8"))
    if body.get("errcode") != 0:
        raise RuntimeError(f"钉钉接口返回错误: {body}")


def _build_text(cases: list[dict], base_url: str, report_path: str) -> str:
    total = len(cases)
    passed = sum(1 for case in cases if case["result"] == "通过")
    failed = sum(1 for case in cases if case["result"] == "失败")
    skipped = total - passed - failed
    duration = sum(case["duration"] for case in cases)

    lines = [
        "#### 镁信 UI 自动化测试结果",
        f"- 运行时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 环境：{base_url or '未配置'}",
        f"- 用例总数：{total}，通过：{passed}，失败：{failed}，跳过：{skipped}",
        f"- 总耗时：{duration:.1f}s",
        f"- 测试报告：{report_path}",
    ]

    failed_cases = [case for case in cases if case["result"] == "失败"]
    if failed_cases:
        lines.append(f"**失败用例（{len(failed_cases)}）**")
        for case in failed_cases[:10]:
            title = case.get("title") or case["case_id"]
            reason = brief_error(case.get("error") or "")
            line = f"- {title}"
            if reason:
                line += f"：{reason[:150]}"
            lines.append(line)
        if len(failed_cases) > 10:
            lines.append(f"- 其余 {len(failed_cases) - 10} 条见测试报告")

    return "\n\n".join(lines)


def notify_dingtalk(
    cases: list[dict], base_url: str, report_path: str, dingtalk_cfg: dict
) -> bool:
    """推送执行结果到钉钉群；未配置 webhook 时跳过并返回 False。"""
    webhook = str(dingtalk_cfg.get("webhook") or "").strip()
    if not webhook:
        logger.info("未配置 DINGTALK_WEBHOOK，跳过钉钉群通知")
        return False

    secret = str(dingtalk_cfg.get("secret") or "").strip()
    url = _signed_url(webhook, secret) if secret else webhook

    at_mobiles = [
        item.strip()
        for item in str(dingtalk_cfg.get("at_mobiles") or "").split(",")
        if item.strip()
    ]
    text = _build_text(cases, base_url, report_path)
    if at_mobiles:
        text += "\n\n" + " ".join(f"@{mobile}" for mobile in at_mobiles)

    payload = {
        "msgtype": "markdown",
        "markdown": {"title": "镁信 UI 自动化测试结果", "text": text},
        "at": {"atMobiles": at_mobiles, "isAtAll": False},
    }
    _post(url, payload)
    logger.info("钉钉群通知已发送")
    return True
