# 格式参考：东营惠民保自动化测试.xmind

本文件只是**格式与落地示例**，用于演示如何把 xmind 用例转成代码。其中的缴费人、保费、浮层等常量只属于个单投保业务，不要套用到其他模块。

## 一、xmind 固定写法

```text
东营惠民保自动化测试                    ← L0 根主题
└─ 个单投保                            ← L1 模块
   └─ tc‑p1：个单投保‑<场景>‑<校验>     ← L2 用例（连接符为全角 ‑ U+2011）
      ├─ 步骤1：进入个单投保……点击确认   ← L3 步骤
      └─ 进入个单投保……，录入出生日期…   ← L3 步骤（可省略“步骤N：”）
         └─ 预期结果：系统识别该被保人为成年人  ← L4 预期
```

- 第 1 条用例的步骤下还挂了 `预期结果：页面可选择升级版和成长守护版`
- 每条用例的“步骤1”完全相同，是公共前置：投保须知 → 填缴费人 → 短信验证 → 快速注册
- 标题与日期都用全角 `‑`，解析时先归一化
- “2007-12-31 判定为成年人”在 xmind 中出现两次，去重后只保留一条

## 二、11 个主题 → 10 条唯一用例

| case_id | story | 标题（去前缀） | 预期结果 |
|---|---|---|---|
| policy_001 | 未成年人年龄校验 | 个单投保-未成年人年龄校验-2008-01-01判定为未成年人 | 可选择升级版和成长守护版 |
| policy_002 | 未成年人年龄校验 | 个单投保-未成年人年龄校验-2008-01-01以前出生判定为成年人 | 录入 2007-12-31，识别为成年人 |
| policy_003 | 未成年人年龄校验 | 个单投保-未成年人年龄校验-2008-01-01以后出生判定为未成年人 | 录入 2008-01-02，识别为未成年人 |
| policy_004 | 产品版本选择 | 个单投保-产品版本选择-成年人可选版本校验 | 默认升级版；可选基础版、升级版；无少儿守护版 |
| policy_005 | 产品版本选择 | 个单投保-产品版本选择-多被保人各自独立选择产品版本 | 两被保人版本互相独立、无覆盖 |
| policy_006 | 升级版保费优惠 | 个单投保-升级版保费优惠-订单升级版被保人小于5人，浮层提示即将满足优惠 | 3 升级版；浮层提示再添 2 名；原价 |
| policy_007 | 升级版保费优惠 | 个单投保-升级版保费优惠-订单升级版被保人等于5人，浮层提示已满足优惠，保费减10 | 5 升级版；浮层提示已满足；每人 -10 |
| policy_008 | 升级版保费优惠 | 个单投保-升级版保费优惠-订单升级版被保人大于5人，校验优惠生效 | 6 升级版；每人 -10 |
| policy_009 | 订单混合版本 | 个单投保-订单混合版本，不满足优惠条件，所有被保人原价 | 4 升级 + 1 基础；全部原价 |
| policy_010 | 升级版保费优惠 | 个单投保-升级版保费优惠-订单混合版本，仅升级版被保人享受减10 | 5 升级 + 1 基础；升级版每人 -10 |

编号以 `data/dongying/caseData.xlsx` 现状为准，新增用例从最大编号 +1 顺延，不重排。

## 三、policy 工作表列（示例）

| 列 | 说明 |
|---|---|
| `case_id` / `title` / `feature` / `story` / `severity` | 通用列，`feature` 固定「个单投保」 |
| `test_type` | `age` / `version` / `multi` / `premium` |
| `payer_name` `payer_id_no` `payer_phone` `payer_sms_code` | 缴费人四要素，固定 钟诚 / 420102198401140032 / 19370919218 / 888888 |
| `insured_names` | 姓名，逗号分隔 |
| `insured_birth_dates` | `YYYY-MM-DD`，逗号分隔，与姓名个数一致 |
| `insured_relations` | 关系，逗号分隔；只能「子女」 |
| `plan_selection` | 各被保人要选的计划，逗号分隔，空位表示不改默认（如 `,基础版`） |
| `expected_insured_types` | 未成年人 / 成年人，逗号分隔 |
| `expected_versions` | 允许的计划集合，竖线分隔（如 `基础版\|升级版`） |
| `expected_default_versions` | 默认选中计划 |
| `payment_method` | 如「微信支付」 |
| `expected_float_text` | 浮层 DOM 文本 |
| `expected_total_price` | 合计保费（整数元） |
| `order_no` / `expected_share_code` | 下单回填；期望为空时只回显实际值 |
| `enabled` | `Y` / `N` |

## 四、步骤 → 页面方法（`pages/dongying/individual_policy_page.py` 中的 `IndividualPolicyPage`）

| xmind 文案 | 方法 |
|---|---|
| 进入投保页、点姓名、关闭投保须知 | `open_payer_form()` |
| 填写缴费人姓名/证件号/手机号 | `fill_payer(name, id_no, phone)` |
| 获取验证码、输入 888888、点空白失焦 | `send_sms_code()` / `fill_sms_code()` / `blur()` |
| 快速注册登录确认 | `confirm_quick_register()` |
| 新增被保人 | `add_insured_card()` + `cleanup_insureds(keep_ids, keep_empty=True)` |
| 选择关系、填姓名与证件号 | `fill_insured_card(index, 关系, 姓名, 证件号, 期望类型)` |
| 系统识别未成年人/成年人 | 证件号由 `generate_id_no(出生日期)` 生成；断言 `minor_tip_visible(index)` / `wait_insured_identified(type, index)` |
| 选择计划 | `select_plan(index, 计划)`；读可选项 `available_plans(index)`；读默认 `selected_plan(index)` |
| 底部固定浮层 | `float_text()` |
| 页面保费 | `total_price()` |
| 支付、协议、立即投保、签字 | `select_payment()` / `check_agreement()` / `read_agreements()` / `submit()` / `sign(缴费人姓名)` |
| 下单后取订单号 | `latest_order_detail_no()`，再 `get_order_share_code(order_no)` |

## 五、金额与浮层规则

| 项 | 值 |
|---|---|
| 升级版 | 149 元；成长守护版 99 元；基础版 99 元 |
| 优惠 | 本单升级版人数 ≥5 → 全员每人 -10 元；<5 → 原价 |
| 浮层 N<5 | `本订单再添{5-N}名及以上升级版被保人，升级版全员每人保费立减10元` |
| 浮层 N≥5 | `本订单升级版全员每人保费立减10元` |

算例：成长守护版 + 基础版 = 198；3 升级 = 447；5 升级 = 695；6 升级 = 834；4 升级 + 1 基础 = 695；5 升级 + 1 基础 = 794。

xmind 里的“即将满足…/恭喜！已满足…”是图片，DOM 中不存在，期望列只填上面两条纯文本。

## 六、多被保人构建顺序

```python
policy.clear_to_single_insured()
for order, person in enumerate(people):
    if order:
        policy.add_insured_card()                       # 新卡片追加在末尾
        policy.cleanup_insureds(set(ids), keep_empty=True)
        index = 最后一个证件号为空的卡片
    policy.fill_insured_card(index, person["relation"], person["name"], person["id_no"], person["expected_type"])
    ids.append(person["id_no"])
    policy.cleanup_insureds(set(ids))                   # 只保留自己的卡片
    if person["plan"]:
        policy.select_plan(policy.insured_index(person["id_no"]), person["plan"])
```

## 七、该模块的踩坑记录

- 证件号失焦后系统异步识别年龄，并回填账号历史被保人（可能到 20 张），需等约 2.5s 后按证件号清理，不能按姓名
- 删除按钮数量必须与可见卡片数量一致，按卡片索引点删除
- 新增空卡片姓名可能为 `None`，判空用 `name in (None, "")`
- 关系「子女」要求出生日期晚于缴费人 1984-01-14，否则提示“被保人子女年龄必须小于缴费人”，添加失败
- 存在待支付订单时会弹 `.tip-bg`，需点 `.closeImg` 关闭
- 测试环境右下角 vConsole 浮层遮挡“立即投保”，`submit()` 中已置隐
- 签字页按缴费人姓名逐字签署，签完点「完成签名」
- 下单用例会真实产生订单，`-k` 筛选时避免重复下单

## 八、该样例的落地结果

`testcases/dongying/test_individual_policy.py` 共 11 个执行项（10 条用例 + 1 条下单校验），全量执行 11 passed，报告：`reports/execution-report.html`。数据文件 `data/dongying/caseData.xlsx`，页面对象 `pages/dongying/individual_policy_page.py`，`testcases/dongying/test_database.py` 复用同一 workbook 做分表 share_code 校验。
