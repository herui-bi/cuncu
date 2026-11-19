"""用例文档解析：把 docs/testcases 下的 docx / xmind / md 转成纯文本。"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_text(path: Path) -> str:
    """按顺序输出段落与表格行，表格单元格用 " | " 分隔。"""
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    body = root.find(f"{WORD}body")
    if body is None:
        return ""
    lines: list[str] = []
    for child in body:
        if child.tag == f"{WORD}p":
            text = "".join(node.text or "" for node in child.iter(f"{WORD}t")).strip()
            if text:
                lines.append(text)
        elif child.tag == f"{WORD}tbl":
            for row in child.iter(f"{WORD}tr"):
                cells = [
                    "".join(node.text or "" for node in cell.iter(f"{WORD}t")).strip()
                    for cell in row.findall(f"{WORD}tc")
                ]
                if any(cells):
                    lines.append(" | ".join(cells))
    return "\n".join(lines)


def _xmind_text(path: Path) -> str:
    """按层级输出 XMind 节点标题（兼容 content.json 与 content.xml）。"""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if "content.json" in names:
            data = json.loads(archive.read("content.json"))
            lines: list[str] = []

            def walk(topic: dict, depth: int) -> None:
                title = (topic.get("title") or "").strip()
                if title:
                    lines.append("  " * depth + title)
                for child in (topic.get("children") or {}).get("attached", []):
                    walk(child, depth + 1)

            for sheet in data:
                walk(sheet.get("rootTopic") or {}, 0)
            return "\n".join(lines)

        root = ElementTree.fromstring(archive.read("content.xml"))

    lines = []

    def walk(node: ElementTree.Element, depth: int) -> None:
        title = node.find("title")
        text = (title.text or "").strip() if title is not None else ""
        if text:
            lines.append("  " * depth + text)
        for topics in node.findall("children/topics"):
            for child in topics.findall("topic"):
                walk(child, depth + 1)

    for sheet in root.findall("sheet"):
        for topic in sheet.findall("topic"):
            walk(topic, 0)
    return "\n".join(lines)


def read_document(path: str | Path) -> str:
    """读取用例文档并返回纯文本，供生成测试用例使用。"""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _docx_text(path)
    if suffix == ".xmind":
        return _xmind_text(path)
    if suffix in (".md", ".txt"):
        return path.read_text(encoding="utf-8")
    raise ValueError(f"不支持的用例文档类型：{suffix}")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if target is None:
        raise SystemExit("用法: python utils/doc_reader.py docs/testcases/xxx.docx")
    print(read_document(target))
