"""生成 Excel 数据驱动模板 data/caseData.xlsx（含 login 工作表与字段说明）。"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "data" / "caseData.xlsx"

HEADERS = [
    "case_id",
    "title",
    "feature",
    "story",
    "severity",
    "username",
    "password",
    "expected",
    "expected_message",
    "enabled",
]

ROWS = [
    ("login_001", "标准用户登录成功", "登录", "账号登录", "critical",
     "standard_user", "secret_sauce", "success", "", "Y"),
    ("login_002", "锁定用户登录被拦截", "登录", "异常账号", "normal",
     "locked_out_user", "secret_sauce", "error", "Sorry, this user has been locked out", "Y"),
    ("login_003", "密码错误登录失败", "登录", "错误凭证", "normal",
     "standard_user", "wrong_password", "error", "Username and password do not match", "Y"),
    ("login_004", "用户名为空登录失败", "登录", "必填校验", "normal",
     "", "secret_sauce", "error", "Username is required", "Y"),
    ("login_005", "密码为空登录失败", "登录", "必填校验", "normal",
     "standard_user", "", "error", "Password is required", "Y"),
]

FIELD_NOTES = [
    ("case_id", "用例编号，作为 pytest 参数化 ID，必填且唯一"),
    ("title", "用例标题，展示在 Allure 报告中"),
    ("feature", "Allure 一级分类（功能模块）"),
    ("story", "Allure 二级分类（业务场景）"),
    ("severity", "Allure 严重级别：blocker/critical/normal/minor/trivial"),
    ("username", "登录用户名"),
    ("password", "登录密码"),
    ("expected", "期望结果：success=登录成功，error=登录失败并提示"),
    ("expected_message", "期望错误提示文案（expected=error 时校验）"),
    ("enabled", "是否启用：Y=执行，N=跳过"),
]


def build() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "login"

    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    body_font = Font(name="微软雅黑", size=10)

    sheet.append(HEADERS)
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row in ROWS:
        sheet.append(row)

    widths = [12, 26, 12, 14, 12, 18, 16, 12, 46, 10]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.font = body_font
            cell.alignment = Alignment(vertical="center")
    sheet.freeze_panes = "A2"

    notes = workbook.create_sheet("说明")
    notes.append(["字段", "说明"])
    for cell in notes[1]:
        cell.fill = header_fill
        cell.font = header_font
    for field, note in FIELD_NOTES:
        notes.append([field, note])
    notes.column_dimensions["A"].width = 20
    notes.column_dimensions["B"].width = 60
    for row in notes.iter_rows(min_row=2):
        for cell in row:
            cell.font = body_font
            cell.alignment = Alignment(vertical="center", wrap_text=True)
    notes.freeze_panes = "A2"

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(TARGET)
    print(f"已生成数据模板: {TARGET}")


if __name__ == "__main__":
    build()
