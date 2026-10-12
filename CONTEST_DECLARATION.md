# 参赛声明（CONTEST_DECLARATION）

## 原创性

本作品（SKILL.md 及 scripts/ 下全部代码）由作者本人原创，开发过程完整记录于 [workbuddy.md](workbuddy.md)。未抄袭、未套用第三方 Skill 作品；仅使用麦当劳官方 MCP 公开接口与 Python 标准库，无第三方依赖。

## 合规性

- 本作品仅通过麦当劳官方开放的 MCP 接口（https://mcp.mcd.cn）访问数据，调用频率远低于官方限流（600 次/分）。
- 不涉及任何逆向、抓包、绕过风控等非官方手段。

## 敏感信息声明

- **Token 安全**：本仓库不含任何 Token、手机号、订单号等个人信息。MCP Token 由使用者自行在 open.mcd.cn 领取并通过环境变量 `MCD_MCP_TOKEN` 注入；`mcp-config.example.json` 中仅含 `${MCD_MCP_TOKEN}` 占位符。
- **个人数据**：开发阶段的真实券数据（tests/fixtures/my_coupons.md）已在 .gitignore 中排除，不进入仓库；仓库内仅保留匿名化示例数据。
- **资金安全**：下单流程需用户显式确认，金额一律以官方 calculate-price 接口为准；本作品不接触支付环节本身（支付在麦当劳官方收银台完成）。

## 作者

崔鹏（个人开发者）
