"""验证钉钉机器人接通：读取 .env 中的 DINGTALK_* 配置，向群发一条测试消息。

用法：python scripts/verify_dingtalk.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.dingtalk import notify_dingtalk


def main() -> None:
    import os

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    cfg = {
        "webhook": os.getenv("DINGTALK_WEBHOOK", ""),
        "secret": os.getenv("DINGTALK_SECRET", ""),
        "at_mobiles": os.getenv("DINGTALK_AT_MOBILES", ""),
    }
    if not cfg["webhook"]:
        print("未配置 DINGTALK_WEBHOOK，请先在 .env 中填写")
        sys.exit(1)

    ok = notify_dingtalk(
        [
            {
                "case_id": "verify",
                "title": "钉钉机器人连通验证",
                "result": "通过",
                "duration": 0.1,
                "steps": [],
                "error": "",
            }
        ],
        base_url="验证消息",
        report_path="这是一条连通性测试消息，收到即表示机器人接通成功",
        dingtalk_cfg=cfg,
    )
    if ok:
        print("发送成功，请到钉钉群确认是否收到消息")
    else:
        print("未发送，请检查 .env 配置")
        sys.exit(1)


if __name__ == "__main__":
    main()
