# 框架契约

## 目录职责

| 路径 | 职责 |
|---|---|
| `config/config.yaml` | 公共配置：默认环境、登录账号、浏览器参数、超时、Excel 路径；支持 `${VAR:-默认值}` |
| `config/environments/<项目>/<阶段>.yaml` | 各项目测试地址配置（如 `huiqubao/test.yaml`）；`--env` 传项目目录名，阶段用 `TEST_STAGE` 切换 |
| `utils/config_loader.py` | `get_config()` 全局配置单例；`config.url(path)` 拼接地址 |
| `utils/excel_reader.py` | `read_cases(sheet)` 返回 `list[dict[str, str]]`，仅返回 `enabled=Y` 的行 |
| `utils/logger.py` | `setup_logger()` 提供 `tb_ui` 日志，写入 `logs/` |
| `pages/base_page.py` | `open` / `click` / `fill` / `text` / `is_visible` / `wait_visible` / `wait_url` / `expect_visible` / `expect_text` / `expect_url` / `screenshot` |
| `conftest.py` | fixtures：`config`、`browser_context_args`、`browser_type_launch_args`、`login_page`、`logged_in_page`、`page`（pytest-playwright）；失败截图附到 Allure |
| `pytest.ini` | marker、失败重试 2 次、失败保留截图/视频/trace、Allure 与 JUnit 输出 |

## fixture 使用

- `page`：pytest-playwright 提供，每个用例独立浏览器上下文
- `login_page`：返回已打开登录页的 `LoginPage`
- `logged_in_page`：完成默认账号登录并等待首页加载，返回 `Page`；与 `page` 同源，不要同时声明两者
- `config`：session 级配置对象，含 `auth_username`、`auth_password`、`base_url` 等

## 命名规范

- 页面对象：`pages/<module>_page.py`，类 `<Module>Page`
- 用例文件：`testcases/test_<module>.py`，函数 `test_<行为>`
- Excel sheet：按业务模块一个 sheet（如 `login`、`inventory`、`order`）
- case_id：模块前缀 + 三位序号，如 `order_001`
- marker：现有 `smoke`、`login`、`inventory`、`excel`、`p0`；新增必须先写入 `pytest.ini` 的 `markers`

## Excel 列规范

通用列（固定在前）：

| 列 | 说明 |
|---|---|
| case_id | 唯一编号，作为 pytest 参数化 ID |
| title | 中文用例标题 |
| feature | Allure 一级分类 |
| story | Allure 二级分类 |
| severity | blocker / critical / normal / minor / trivial |

业务列按模块追加，例如登录模块使用 `username`、`password`，订单模块可使用 `order_no`、`status`。

断言列：

| 列 | 说明 |
|---|---|
| expected | 期望结果标识，如 `success` / `error`，用例内解析 |
| expected_message | 期望提示文案，断言时使用子串包含 |
| enabled | `Y` 执行，`N` 跳过 |

新增 sheet 时，先写表头，再写数据行；表头名称即 `read_cases` 返回 dict 的键。

## 断言

- 元素状态与文本使用 `playwright.sync_api.expect`
- 错误提示使用 `assert expected_message in xxx.error_message()` 形式的子串断言
- 断言表达式要能表达业务含义，避免 `assert True` 这类占位

## 常用命令

```powershell
# 单文件
.venv\Scripts\python.exe -m pytest testcases\test_order.py --reruns 0

# 按 marker
.venv\Scripts\python.exe -m pytest -m smoke

# 全量并生成 Allure 报告
powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1 -OpenReport
```

## 产物位置

- 失败截图 / 视频 / trace：`reports/artifacts/`
- 日志：`logs/ui_YYYYMMDD_HHMMSS.log`
- Allure 原始结果：`reports/allure-results/`
