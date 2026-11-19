"""Excel 数据驱动：读取项目专属 caseData.xlsx 中的用例数据。"""

from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from utils.config_loader import get_config

ROOT = Path(__file__).resolve().parent.parent

_ENABLED_TRUE = {"Y", "YES", "TRUE", "1", "是"}


def read_cases(sheet: str, workbook: str | Path | None = None) -> list[dict[str, str]]:
    """读取指定工作表的用例数据，enabled 列非 Y 的行会被跳过。

    workbook 指定项目专属数据文件（如 data/dongying/caseData.xlsx）；
    相对路径基于仓库根目录，缺省取 config.yaml 中的 excel.path。
    """
    path = Path(workbook) if workbook is not None else get_config().excel_path
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        raise FileNotFoundError(f"未找到 Excel 数据文件: {path}")

    book = load_workbook(path, data_only=True)
    if sheet not in book.sheetnames:
        raise KeyError(f"Excel 中不存在工作表 [{sheet}]，现有工作表: {book.sheetnames}")

    rows = list(book[sheet].iter_rows(values_only=True))
    if not rows:
        return []

    headers = [str(cell).strip() if cell is not None else "" for cell in rows[0]]
    cases: list[dict[str, str]] = []
    for row in rows[1:]:
        values = ["" if cell is None else str(cell).strip() for cell in row]
        if not any(values):
            continue
        case = dict(zip(headers, values))
        if case.get("enabled", "Y").upper() not in _ENABLED_TRUE:
            continue
        cases.append(case)
    return cases
