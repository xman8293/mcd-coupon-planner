r"""总控：券驱动点餐的端到端流水线，Skill 层的唯一入口。

六阶段（全部确定性，LLM 只消费最终 JSON）：
    ①拉数据   mcp_client.call_tool
    ②解析     coupon_parser.parse_coupons
    ③分类     classifier.classify_all
    ④排程+放弃 optimizer.plan_week
    ⑤官方验价 verify.verify_plan（净薅额=原价-实付，单位分换算）
    ⑥输出 JSON 契约 → SKILL.md 渲染层

CLI 用法（端到端联调）：
    py scripts/planner.py <storeCode> [本周顿数]

--- @ty.aicoding@1791777660771 ---
"""

from __future__ import annotations

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

from classifier import classify_all
from coupon_parser import parse_coupons
from mcp_client import McpError, call_tool
from optimizer import plan_week
from verify import verify_plan

ERROR_HINTS = {
    "no_token": "未配置 MCD_MCP_TOKEN：请去 open.mcd.cn/mcp 控制台手机号登录领取，"
                "并设置为环境变量后重试",
}


def _human_error(e: McpError) -> str:
    """把结构化错误翻成人话（Skill 层直接念）。

    --- @ty.aicoding@1791777660771 ---
    """
    msg = str(e)
    if msg == "no_token":
        return ERROR_HINTS["no_token"]
    if msg.startswith("http:401") or msg.startswith("http:403"):
        return "Token 已失效：请去 open.mcd.cn/mcp 重新领取并更新环境变量"
    if msg.startswith("network"):
        return "网络不通：检查网络后重试"
    return f"接口异常：{msg[:120]}"


def run(store_code: str, meals: int = 3) -> dict:
    """端到端跑一次，返回 JSON 契约；任何失败转为人类可读错误。

    --- @ty.aicoding@1791777660771 ---
    """
    try:
        coupons_md = call_tool("query-my-coupons", {})
        account_md = call_tool("query-my-account", {})
    except McpError as e:
        return {"ok": False, "error": _human_error(e)}

    classified = classify_all(parse_coupons(coupons_md))
    result = plan_week(classified, meals=meals)
    result["plan"] = verify_plan(result["plan"], store_code)

    verified = [p for p in result["plan"] if p.get("verified")]
    result["total"] = {
        "meals": len(result["plan"]),
        "verified": len(verified),
        "pay": round(sum(p["pay"] for p in verified), 2),
        "original": round(sum(p["original"] for p in verified), 2),
        "save": round(sum(p["save"] for p in verified), 2),
    }
    # 积分只抠关键数字（已过期=痛点故事）
    result["account_raw"] = account_md[-400:]
    result["ok"] = True
    return result


if __name__ == "__main__":
    _store = sys.argv[1] if len(sys.argv) > 1 else "1950104"
    _meals = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    print(json.dumps(run(_store, _meals), ensure_ascii=False, indent=2))
