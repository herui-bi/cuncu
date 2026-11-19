"""记录用例执行过程，并在会话结束时输出 HTML 测试报告。"""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "reports" / "execution-report.html"

_current: dict = {}
_history: list[dict] = []


def start(case_id: str) -> None:
    """开始记录一个用例。"""
    global _current
    _current = {
        "case_id": case_id,
        "steps": [],
        "started": datetime.now(),
        "result": "",
        "duration": 0.0,
        "error": "",
    }


def set_title(title: str) -> None:
    if _current:
        _current["title"] = title


def record(action: str, detail: str = "") -> None:
    """记录一步执行动作。"""
    if not _current:
        return
    _current["steps"].append(
        {"time": datetime.now().strftime("%H:%M:%S"), "action": action, "detail": detail}
    )


def finish(result: str, duration: float, error: str = "") -> list[str]:
    """结束当前用例记录，返回纯文本执行过程；error 为用例失败原因。"""
    global _current
    if not _current:
        return []
    _current["result"] = result
    _current["duration"] = duration
    _current["error"] = error
    # 同一用例重跑时用最新结果覆盖，避免失败重试后又通过的用例在报告中重复计数
    for index, case in enumerate(_history):
        if case["case_id"] == _current["case_id"]:
            _history[index] = _current
            break
    else:
        _history.append(_current)
    lines = [
        f'{step["time"]}  {step["action"]}' + (f'：{step["detail"]}' if step["detail"] else "")
        for step in _current["steps"]
    ]
    _current = {}
    return lines


def brief_error(error: str) -> str:
    """从完整堆栈中提取一行失败原因，供控制台汇总与钉钉通知使用。"""
    lines = [line.strip() for line in error.splitlines() if line.strip()]
    if not lines:
        return ""
    reason = lines[-1]
    return reason[2:].strip() if reason.startswith("E ") else reason


def _brief(error: str) -> str:
    """旧别名，兼容已有调用。"""
    return brief_error(error)


def history() -> list[dict]:
    """返回当前已记录的用例结果，供钉钉通知等外部模块使用。"""
    return list(_history)


def summary_lines() -> list[str]:
    """返回本次执行的用例结果汇总，供控制台输出通过/失败结论。"""
    total = len(_history)
    passed = sum(1 for case in _history if case["result"] == "通过")
    failed = sum(1 for case in _history if case["result"] == "失败")
    skipped = total - passed - failed
    lines = ["", "========== 测试执行结果 =========="]
    for case in _history:
        title = case.get("title") or case["case_id"]
        lines.append(f'[{case["result"]}] {title}　耗时 {case["duration"]:.2f}s')
        if case["result"] == "失败" and case.get("error"):
            lines.append(f'　　失败原因：{_brief(case["error"])}')
    lines.append(f"用例总数：{total}　通过：{passed}　失败：{failed}　跳过：{skipped}")
    if not total:
        lines.append("结论：无执行结果")
    elif failed:
        lines.append("结论：失败")
    elif passed == total:
        lines.append("结论：全部通过")
    else:
        lines.append("结论：存在跳过用例")
    lines.append("==================================")
    return lines


def write_report(base_url: str = "") -> Path:
    """生成 HTML 测试报告，包含每个用例的执行过程。"""
    total = len(_history)
    passed = sum(1 for case in _history if case["result"] == "通过")
    failed = sum(1 for case in _history if case["result"] == "失败")
    skipped = total - passed - failed
    duration = sum(case["duration"] for case in _history)
    conclusion = "失败" if failed else ("全部通过" if total and passed == total else "无执行结果")
    conclusion_color = "#cf222e" if conclusion == "失败" else "#1a7f37"
    pass_pct = passed / total * 100 if total else 0.0
    fail_pct = failed / total * 100 if total else 0.0
    skip_pct = 100.0 - pass_pct - fail_pct if total else 100.0

    rows = []
    for case in _history:
        color = {"通过": "#1a7f37", "失败": "#cf222e"}.get(case["result"], "#6e7781")
        title = case.get("title") or case["case_id"]
        steps = "".join(
            f'<li><span class="time">{escape(step["time"])}</span>'
            f'{escape(step["action"])}'
            + (f'<span class="detail">{escape(step["detail"])}</span>' if step["detail"] else "")
            + "</li>"
            for step in case["steps"]
        )
        error = (
            f'<div class="error"><b>失败原因：</b>\n{escape(case["error"])}</div>'
            if case["result"] == "失败" and case.get("error")
            else ""
        )
        rows.append(
            f'<section><h2>{escape(title)}</h2>'
            f'<p class="meta">结果：<b style="color:{color}">{escape(case["result"])}</b>'
            f'　耗时：{case["duration"]:.2f}s</p>'
            f'{error}'
            f'<ol class="steps">{steps}</ol></section>'
        )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>UI 自动化测试报告</title>
<style>
body {{ font-family: "Microsoft YaHei", Arial, sans-serif; margin: 32px; color: #1f2328; }}
h1 {{ font-size: 22px; margin-bottom: 8px; }}
.summary {{ background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 16px; margin-bottom: 24px; }}
.summary span {{ margin-right: 24px; }}
section {{ border: 1px solid #d0d7de; border-radius: 6px; padding: 16px; margin-bottom: 20px; }}
h2 {{ font-size: 16px; margin: 0 0 8px; }}
.meta {{ color: #57606a; font-size: 13px; margin: 0 0 12px; }}
.steps {{ padding-left: 22px; font-size: 13px; line-height: 1.9; }}
.time {{ color: #6e7781; margin-right: 10px; font-family: Consolas, monospace; }}
.detail {{ color: #57606a; margin-left: 6px; }}
.error {{ background: #fff5f5; border-left: 4px solid #cf222e; border-radius: 4px; padding: 10px 12px; margin: 0 0 12px; font-size: 12.5px; line-height: 1.7; color: #82071e; white-space: pre-wrap; word-break: break-all; font-family: Consolas, "Microsoft YaHei", monospace; }}
.overview {{ display: flex; align-items: center; gap: 40px; border: 1px solid #d0d7de; border-radius: 6px; padding: 20px 28px; margin-bottom: 24px; }}
.pie {{ width: 180px; height: 180px; border-radius: 50%; position: relative; flex: none; }}
.pie-inner {{ position: absolute; inset: 0; margin: auto; width: 110px; height: 110px; background: #fff; border-radius: 50%; display: flex; flex-direction: column; align-items: center; justify-content: center; }}
.pie-total {{ font-size: 30px; font-weight: 600; line-height: 1.1; }}
.pie-label {{ font-size: 12px; color: #57606a; }}
.legend {{ list-style: none; padding: 0; margin: 0; font-size: 14px; line-height: 2; }}
.legend i {{ display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 8px; vertical-align: -1px; }}
</style>
</head>
<body>
<h1>UI 自动化测试报告</h1>
<div class="overview">
<div class="pie" style="background: conic-gradient(#1a7f37 0% {pass_pct:.2f}%, #cf222e {pass_pct:.2f}% {pass_pct + fail_pct:.2f}%, #8c959f {pass_pct + fail_pct:.2f}% 100%);">
<div class="pie-inner"><span class="pie-total">{total}</span><span class="pie-label">执行用例</span></div>
</div>
<ul class="legend">
<li><i style="background:#1a7f37"></i>执行 {total} 条，成功 {passed} 条（{pass_pct:.1f}%）</li>
<li><i style="background:#cf222e"></i>失败 {failed} 条（{fail_pct:.1f}%）</li>
<li><i style="background:#8c959f"></i>跳过 {skipped} 条（{skip_pct:.1f}%）</li>
</ul>
</div>
<div class="summary">
<span>运行时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</span>
<span>环境：{escape(base_url)}</span>
<span>用例总数：{total}</span>
<span>通过：{passed}</span>
<span>失败：{failed}</span>
<span>跳过：{skipped}</span>
<span>总耗时：{duration:.2f}s</span>
<span>结论：<b style="color:{conclusion_color}">{conclusion}</b></span>
</div>
{"".join(rows)}
</body>
</html>
"""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(html, encoding="utf-8")
    _history.clear()
    return REPORT
