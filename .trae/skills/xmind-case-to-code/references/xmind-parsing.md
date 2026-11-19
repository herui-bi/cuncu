# XMind 解析指南

## 一、包结构

xmind 是 zip 包，常见条目：

| 条目 | 说明 |
|---|---|
| `content.json` | 新格式主题树；顶层可能是 sheet 列表 `[{...}]`，也可能是 `{"sheets": [{...}]}`，甚至单个 sheet 的 `{"rootTopic": ...}` |
| `content.xml` | XMind 8 旧格式，`<topic>` 嵌套 `<children><topics type="attached">` |
| `metadata.json` / `manifest.json` | 元信息，无需解析 |
| `Thumbnails/` | 缩略图，忽略 |

sheet 结构：`{"title": "画布 1", "rootTopic": {...}}`；主题节点：`title`、`children.attached`、`children.detached`、`notes.plain.content`、`labels`、`markers[].markerId`。

## 二、解析脚本（JSON 版）

```python
import json
import re
import zipfile


def load_sheets(path: str) -> list[dict]:
    with zipfile.ZipFile(path) as zf:
        raw = zf.read("content.json").decode("utf-8")
    data = json.loads(raw)
    if isinstance(data, list):
        return data
    return data.get("sheets") or [{"title": "", "rootTopic": data.get("rootTopic", {})}]


def walk(topic: dict, depth: int = 0):
    """按先序产出 (depth, topic)。"""
    yield depth, topic
    for child in (topic.get("children") or {}).get("attached", []):
        yield from walk(child, depth + 1)


def dump(path: str) -> None:
    for sheet in load_sheets(path):
        print(f"=== {sheet.get('title')} ===")
        for depth, topic in walk(sheet["rootTopic"]):
            print("  " * depth + "- " + topic.get("title", ""))
```

先 dump 出层级树再写映射，不要凭猜测套层级。

## 三、旧版 content.xml 兜底

```python
import xml.etree.ElementTree as ET
import zipfile


def load_xml_topics(path: str):
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("content.xml"))

    def walk(topic, depth=0):
        title = (topic.findtext("title") or "").strip()
        yield depth, title
        for child in topic.findall("./children/topics/topic"):
            yield from walk(child, depth + 1)

    for topic in root.findall(".//sheet/rootTopic"):
        yield from walk(topic)
```

## 四、语义识别

层级名不固定，按语义判断：

- **模块**：根主题的第一层子节点；若第一层直接就是用例标题，则整个 xmind 视为单模块
- **用例**：带 `tc-`、`tc‑p1：`、`case-` 前缀的节点；无前缀时取“有子步骤且不是步骤节点”的最深层
- **步骤**：以 `步骤N：` 开头，或含动作动词（进入、点击、填写、选择、查看、上传……）
- **预期结果**：以 `预期结果：` / `期望结果：` 开头，可能挂在步骤下，也可能直接挂在用例下；没有预期结果节点的用例先向用户确认
- **前置条件**：标题含“前置”，或 `notes` 文本
- **优先级**：`markers` 中 `priority-1~7` → blocker / critical / normal / minor / trivial，无 marker 用 normal

## 五、归一化

```python
REPLACEMENTS = {"\u2011": "-", "\u2010": "-", "－": "-", "：": ":", "，": ",", "（": "(", "）": ")"}


def normalize(text: str) -> str:
    for src, dst in REPLACEMENTS.items():
        text = text.replace(src, dst)
    return re.sub(r"\s+", " ", text).strip()


def strip_prefix(title: str) -> str:
    return re.sub(r"^(tc[-\s]*p\d+[:：]\s*|tc[-\s]*)?", "", normalize(title)).strip()
```

注意：

- 日期在 xmind 里常用 `2008‑01‑02`（U+2011），必须先归一化再被业务代码解析
- 步骤文本常含换行与弹窗原文（如“温馨提示\n是否以…？”），按动作语义拆分，不逐字抄
- 同名标题出现多次即为重复用例，保留第一条，且不占编号

## 六、解析产物

先形成清单再写代码，每行一条唯一用例：

| 序号 | 模块 | 用例标题（去前缀） | 步骤动作清单 | 预期结果 | 优先级 | 备注 |
|---|---|---|---|---|---|---|
| 1 | 个单投保 | 未成年人年龄校验-2008-01-01判定为未成年人 | 填写缴费人→短信验证→快速注册→填写被保人 | 可选升级版和成长守护版 | p1 | — |

确认清单后再进入数据与代码生成，避免直接边解析边写导致漏用例或重复。
