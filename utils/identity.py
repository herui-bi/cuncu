"""实名身份池：二要素（姓名 + 身份证号）校验只能使用真实身份。

`generate_id_no` 生成的号码只保证 GB 11643 校验位合法，姓名则是编造的，
无法通过实名二要素校验。因此凡是会触发实名的场景（缴费人注册登录、
被保人实名核验），姓名与证件号都必须来自真实身份。

真实身份维护在 data/verified_identities.csv，表头：
    name,id_no,phone,note
用例按需取用；池中缺失时由调用方显式告警，而不是静默生成假身份。
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POOL_PATH = ROOT / "data" / "verified_identities.csv"

# 身份证号中出生日期所在区间
_BIRTH_SLICE = slice(6, 14)


def load_pool(path: Path | str | None = None) -> list[dict[str, str]]:
    """读取实名身份池，忽略空行与缺证件号的行。"""
    target = Path(path) if path else POOL_PATH
    if not target.exists():
        return []
    with target.open(encoding="utf-8-sig", newline="") as file:
        rows = []
        for row in csv.DictReader(file):
            name = (row.get("name") or "").strip()
            id_no = (row.get("id_no") or "").strip().upper()
            if not name or not id_no:
                continue
            rows.append(
                {
                    "name": name,
                    "id_no": id_no,
                    "phone": (row.get("phone") or "").strip(),
                    "note": (row.get("note") or "").strip(),
                }
            )
        return rows


def birth_of(id_no: str) -> date:
    """从 18 位身份证号中解析出生日期。"""
    raw = id_no[_BIRTH_SLICE]
    return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))


def age_at(id_no: str, on: date | None = None) -> int:
    """按指定日期（默认今天）计算周岁。"""
    today = on or date.today()
    birth = birth_of(id_no)
    return today.year - birth.year - (
        (today.month, today.day) < (birth.month, birth.day)
    )


def find(
    name: str | None = None, id_no: str | None = None, path: Path | str | None = None
) -> dict[str, str] | None:
    """按姓名或证件号在池中查找真实身份。"""
    for person in load_pool(path):
        if name and person["name"] == name.strip():
            return person
        if id_no and person["id_no"] == id_no.strip().upper():
            return person
    return None


def pick(
    index: int = 0,
    adult_only: bool = False,
    exclude_ids: set[str] | None = None,
    path: Path | str | None = None,
) -> dict[str, str] | None:
    """按顺序取第 index 个可用身份；不足时返回 None。"""
    excluded = {item.upper() for item in (exclude_ids or set())}
    candidates = [
        person
        for person in load_pool(path)
        if person["id_no"] not in excluded
        and (not adult_only or age_at(person["id_no"]) >= 18)
    ]
    if index >= len(candidates):
        return None
    return candidates[index]


def next_available(
    exclude_ids: set[str] | None = None,
    adult_only: bool = False,
    path: Path | str | None = None,
) -> dict[str, str] | None:
    """取池中第一个未被占用且满足条件的身份；池为空或全部占用时返回 None。"""
    return pick(
        index=0,
        adult_only=adult_only,
        exclude_ids=exclude_ids,
        path=path,
    )
