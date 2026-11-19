---
name: "huiqubao-data-prep"
description: "Prepares and verifies test data for 惠衢保 order-upgrade automation: order states, 个账支付 data generation, shard SQL, reuse/expiry rules. Invoke when adding or running 惠衢保 upgrade cases or when cases skip for missing order data."
---

# 惠衢保升级用例数据准备与校验

用于在新增或执行 `testcases/huiqubao/test_order_upgrade.py` 前，准备并核对所需订单数据。
本条 skill 只描述**怎么做**；具体每例需要什么数据以 `docs/testcases/huiqubao7_data_prep.md`
和 `data/huiqubao/caseData.xlsx` 的「前置数据需求」/「数据获取方式」/「数据是否就绪」三列为准，禁止在 skill 中记录订单号。

## 1. 数据需求从哪里读

1. 公共前置（所有用例共用）：见 `docs/testcases/huiqubao7_data_prep.md` 的「〇、公共前置数据」（测试入口、缴费人身份、登录态、产品保费、数据库、环境变量）。
2. 逐条数据需求：打开 `data/huiqubao/caseData.xlsx` 的 `upgrade` 工作表：
   - `前置数据需求`：该用例需要的订单类型（产品号、状态、支付方式、人数、是否全额）
   - `数据获取方式`：获取方式（已有数据 / 真实支付造数 / 页签动态匹配）
   - `数据是否就绪`：`Y` 表示数据就绪，`N` 表示待补
   - `是否启用`：`Y` 才会真正执行；`N` 时用例 skip 并直接输出「前置数据需求」
2. 执行前逐行确认「是否启用」为 `Y` 的行「数据是否就绪」为 `Y`，否则先补数或临时置 `N`，不要靠失败暴露缺数。

## 2. 订单状态与可复用性

| 状态 | 含义 | 是否可复用 |
| --- | --- | --- |
| `paid` | 已支付，保单 `paidWaitInsure` | 可复用（查看/选择类用例） |
| `waitPay` | 待支付 | 约 30 分钟自动关闭，禁止跨轮复用、禁止写死订单号 |
| `rebates` | 部分退款（部分保单 `refundedRevoked`） | 可复用；已退款被保人无操作按钮 |
| `refunded` | 全额退款 | 可复用；只能验证「仅查看详情」 |
| `closed` | 已取消/超时关闭 | 可复用 |
| `closedReverso` | 冲正关闭 | 可复用 |

消耗型用例（升级支付、退款、多人升级）会**真实退款**原订单保单，执行后订单变为 `rebates` / `refunded`，
不可再用于需要 `paid` 的用例，必须一例一单，并排在所有查看类用例之后执行
（`conftest.py` 已按 `test_type` 重排：查看/选择 → 金额/提示 → 多人升级 → 支付）。

## 3. 造数路径

1. **个账支付（医保）**：收银台医保渠道展示为「个账支付」，底层 `payMethod=ybpay`。
   测试环境可用个账支付完成真实支付，从而得到「已支付」的医保订单；升级支付阶段仅 mock `ybPay` 接口
   （`mock_yb_payment`），成功后跳 `#/partSuccess`。
2. **微信支付**：mock 仅作用于前端（JSAPI 回调 + H5 支付链接），后端订单仍为 `waitPay`，
   因此微信「已支付」订单只能由外部真实支付产生，不能靠 mock 造数。
3. **升级版/尊享版已支付订单**：对基础版已支付订单执行真实升级 + 真实支付（个账/微信），
   或直接购买对应产品；升级产生的待支付订单若不支付，30 分钟后关闭，不构成数据。
4. **部分退款订单**：对已支付订单在详情页对某一位被保人执行「申请退款」，退款成功后订单变 `rebates`，
   适合验证「已退款被保人不可升级 / 升级页仅展示未退款被保人」。

## 4. 查数 SQL（只读）

```sql
-- 订单（表名按订单号末位 0-9 路由）
SELECT order_no, status, pay_method, amount, number, product_code, create_time
FROM mth_insure_core.insure_order_<末位>
WHERE order_no = ?;

-- 保单
SELECT policy_id, product_code, status, premium
FROM mth_insure_core.insure_order_policy_<末位>
WHERE order_no = ?;

-- 账号下所有可用已支付/部分退款订单
SELECT order_no, product_code, status, pay_method, amount, number, create_time
FROM mth_insure_core.insure_order_<0..9>
WHERE user_id = ? AND project_code = 'CITY000110-1' AND status IN ('paid','rebates');
```

仅执行 SELECT；库连接走 `utils/db.py` + `config/environments/huiqubao/<env>.yaml`，执行时设置 `TEST_ENV=huiqubao`。

## 5. 执行策略：改数据/字段不跑用例，改动代码才回归

**修改 Excel 数据、字段名、列顺序、新增/调整用例行属于数据维护，不触发用例执行。**
执行用例只在用户明确要求「执行自动化测试 / 回归」时进行，两者严格分开：

| 变更类型 | 动作 |
| --- | --- |
| Excel 改订单号 / 造数状态更新 / 列名与列顺序调整 | 只改 Excel + 同步 `huiqubao7_data_prep.md` 清单，不执行用例 |
| 页面对象 / 断言逻辑改动 | `python -m py_compile` 校验语法，等用户要求时再回归 |
| 用户明确要求执行 | 全量执行 `python -m pytest testcases/huiqubao/test_order_upgrade.py -q --reruns 0` |

数据维护后的快速自检（不打开浏览器，秒级完成）：

```powershell
# 1. Excel 读取是否正常、开关数量是否正确
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); from testcases.huiqubao.test_order_upgrade import CASES; print(len(CASES), len([c for c in CASES if not c.get('_disabled')]))"

# 2. 语法校验
.\.venv\Scripts\python.exe -m py_compile testcases/huiqubao/test_order_upgrade.py pages/huiqubao/order_upgrade_page.py
```

回归只做一次：改动代码后等用户指令统一执行全量，禁止每改一个字段就跑一遍用例。

## 6. 执行前核对清单（仅在全量执行时做一次）

1. Excel 中「是否启用」为 `Y` 的用例，「数据是否就绪」均为 `Y`。
2. `paid` 订单在「已支付」页签可见；`rebates` 在「部分退款」；`refunded` 在「已退款」；`waitPay` 在「待支付」。
3. 待支付类用例不写死订单号，按页签动态匹配；页签为空时应 skip 而非失败。
4. 消耗型用例所需订单数量 ≥ 用例数（045/046 需两笔不同的多人已支付订单）。
5. 缴费人使用 `data/verified_identities.csv` 中已实名身份（当前 钟诚 420102198401140032 / 19370919218 / 短信码 888888）。

## 7. 常见问题

- **登录页被「是否以投保人信息快速注册或登录」弹窗遮挡**：页面对象 `open_home` 会自动点「手动注册登录」，若页面改版需同步选择器。
- **升级订单生成失败且升级历史表无记录**：多为原订单已被整单退款，改为从详情单个被保人进入升级，由前端自动退款所选保单。
- **医保退款失败（提示医保账户异常）**：优先重试或改用新订单；升级退款依赖原医保账户状态。
- **报告出现数据类失败**：先查订单状态是否漂移（超时关闭/已被其他用例退款），再判定是否脚本问题。
