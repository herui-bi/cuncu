"""身份证号生成：按出生日期生成符合 GB 11643 校验规则的 18 位号码。"""

from __future__ import annotations

from datetime import date

# 东营市东营区行政区划代码
DEFAULT_AREA_CODE = "370502"
_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_CHECK_CODES = "10X98765432"


def generate_id_no(birth_date: str, sequence: int = 1, area_code: str = DEFAULT_AREA_CODE) -> str:
    """按出生日期（YYYY-MM-DD）与顺序号生成合法身份证号。

    顺序号同时决定性别（奇数男、偶数女），范围 1~999。
    """
    year, month, day = (int(part) for part in birth_date.split("-"))
    date(year, month, day)  # 校验日期真实存在
    if not 1 <= sequence <= 999:
        raise ValueError(f"顺序号需在 1~999 之间：{sequence}")
    body = f"{area_code}{year:04d}{month:02d}{day:02d}{sequence:03d}"
    if len(body) != 17:
        raise ValueError(f"行政区划代码需为 6 位：{area_code!r}")
    total = sum(int(digit) * weight for digit, weight in zip(body, _WEIGHTS))
    return body + _CHECK_CODES[total % 11]
