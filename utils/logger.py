"""日志：控制台 + 文件双输出，每次运行生成独立日志文件。"""

from __future__ import annotations

import logging
import sys
from datetime import datetime

from utils.config_loader import ROOT

LOG_DIR = ROOT / "logs"


def setup_logger(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("tb_ui")
    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.propagate = False
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(
        LOG_DIR / f"ui_{datetime.now():%Y%m%d_%H%M%S}.log", encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
