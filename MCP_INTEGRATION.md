# MCP 集成说明（MCP_INTEGRATION）

## 接入方式

- 端点：`https://mcp.mcd.cn/mcp-servers/mcd-mcp`
- 协议：HTTP POST + JSON-RPC（`tools/call` / `tools/list`），无会话
- 认证：`Authorization: Bearer <Token>`，Token 从环境变量 `MCD_MCP_TOKEN` 读取
- 注意：curl 直连会被 WAF 拦截（返回 202 空响应），请使用常规 HTTP 客户端（本作品用 Python urllib）

## 使用的 MCP 工具

| 工具 | 用途 | 调用时机 |
|---|---|---|
| `query-my-coupons` | 拉取我的券（Markdown 文本） | 规划①拉数据 |
| `query-my-account` | 积分余额 / 已过期积分 | 规划① + 临期积分提醒 |
| `available-coupons` | 当前可领的券 | 规划①（提示"还能领"） |
| `query-nearby-stores` | 选常去门店（storeCode） | 首次配置 / 流程一参数 |
| `query-store-coupons` | **券身份唯一来源**（couponId/couponCode/productCode） | 验价前 |
| `calculate-price` | **官方算价**：originalPrice/discount/price（分） | 每个方案验价 + 下单前 |
| `query-meals` | 菜单价格池（currentPrice/originalPrice） | 满减凑单 DP |
| `auto-bind-coupons` | 绑券 | 用户确认后（不可逆，置于确认闸门后） |
| `create-order` | 下单（到店 beType=1 / 外送 beType=2） | 用户确认后 |
| `delivery-create-address` | 外送地址 | 首次外送时 |
| `query-order` / `order-list` | 查单回执、失败核对 | 下单后 |

## 关键调用流程

### 规划（本周薅单）

```
query-my-coupons ──► 解析/分类/排程（本地确定性）
query-store-coupons ──► 券身份（couponId+couponCode）
calculate-price ──► 每张券验价（净薅额 = originalPrice - price）
```

### 下单（确认后）

```
亮明细(calculate-price 的数字) → 用户说"确认"
→ auto-bind-coupons → create-order → 支付引导 → query-order 回执
任何一步失败：报停在哪一步；查单确认无单后才可重来
```

## 业务价值

- **券身份链路补全**：`query-my-coupons`/`available-coupons` 均返回无券码的 Markdown，券的 couponId/couponCode 只能由 `query-store-coupons`（或领取时 `auto-bind-coupons` 返回值）获得——这是集成过程中发现并绕过的最大坑，已写入 `verify.py` 注释。
- **服务端时段过滤**：门店券接口只回"当前时段可用"的券（早餐券中午查不到），本作品如实标注而非硬算。
- **每单限 1 券**（实测）：排程约束按此实现。

## 限流与健壮性

- 四路数据并行拉取（ThreadPoolExecutor，4 并发），单接口失败不拖垮整体
- 结构化错误分类（no_token / http / rpc / network）→ 人话提示（如"Token 已失效，请重新领取"）
