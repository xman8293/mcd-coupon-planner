r"""官方验价层：所有钱数必须经过 calculate-price，LLM 与本地估算一律不算数。

关键链路（2026-10-12 实测打通）：
    query-store-coupons(storeCode, beType, orderType)
        → 券身份（couponId/couponCode/productCode，注意该接口只回"当前时段可用"的券）
    calculate-price(items=[{couponId, couponCode, quantity}])
        → data.{originalPrice, discount, price}（单位：分）
    净薅额 = originalPrice - price

注意：query-my-coupons / available-coupons 均为 Markdown 无券码，
券身份唯一来源是 query-store-coupons（或 auto-bind-coupons 领取时返回）。

CLI 用法（联调）：
    py scripts/verify.py <storeCode>

--- @ty.aicoding@1791777440638 ---
"""

from __future__ import annotations

import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

from mcp_client import McpError, call_tool


def extract_json(text: str) -> dict:
    """从 MCP 混合输出（说明文档 + 原始 JSON）中抠出 JSON 体。

    --- @ty.aicoding@1791777440638 ---
    """
    m = re.search(r'\{"success".*\}', text, re.S)
    if not m:
        raise McpError("rpc:no_json_in_response")
    return json.loads(m.group(0))


def list_store_coupons(store_code: str, be_type: int = 1, order_type: int = 1) -> list[dict]:
    """拉取门店当前可用券（含券码与适用商品编码）。

    --- @ty.aicoding@1791777440638 ---
    """
    text = call_tool("query-store-coupons", {
        "storeCode": store_code, "beType": be_type, "orderType": order_type,
    })
    data = extract_json(text)
    if not data.get("success"):
        raise McpError(f"rpc:{data.get('message', 'query-store-coupons failed')}")
    return [
        {
            "title": c["title"],
            "couponId": c["couponId"],
            "couponCode": c["couponCode"],
            "valid": c.get("tradeDateTime", ""),
            "productCode": (c.get("products") or [{}])[0].get("productCode"),
            "productName": (c.get("products") or [{}])[0].get("productName"),
        }
        for c in data.get("data", [])
    ]


def price_with_coupon(store_code: str, coupon: dict,
                      be_type: int = 1, order_type: int = 1) -> dict:
    """单券官方算价，返回 {pay, original, save}（单位：元，两位小数）。

    --- @ty.aicoding@1791777440638 ---
    """
    text = call_tool("calculate-price", {
        "storeCode": store_code, "beType": be_type, "orderType": order_type,
        "items": [{
            "couponId": coupon["couponId"],
            "couponCode": coupon["couponCode"],
            "quantity": 1,
        }],
    })
    data = extract_json(text)
    if not data.get("success"):
        raise McpError(f"rpc:{data.get('message', 'calculate-price failed')}")
    d = data["data"]
    fen = lambda v: round((v or 0) / 100, 2)
    return {
        "pay": fen(d.get("price")),
        "original": fen(d.get("originalPrice")),
        "save": fen(d.get("discount")),
    }


def verify_plan(plan: list[dict], store_code: str) -> list[dict]:
    """给排程逐项盖官方价章；门店当前不可用的券如实标注不硬算。

    --- @ty.aicoding@1791777440638 ---
    """
    store_coupons = {c["title"]: c for c in list_store_coupons(store_code)}
    out = []
    for entry in plan:
        item = dict(entry)
        sc = store_coupons.get(entry["coupon"])
        if not sc:
            item["verified"] = False
            item["note"] = "常去门店当前时段不可用（可能不在可用时段/渠道）"
        else:
            try:
                p = price_with_coupon(store_code, sc)
                item.update({
                    "verified": True,
                    "pay": p["pay"],
                    "original": p["original"],
                    "save": p["save"],
                    "product": sc["productName"],
                })
            except McpError as e:
                item["verified"] = False
                item["note"] = f"算价失败：{e}"
        out.append(item)
    return out


if __name__ == "__main__":
    store = sys.argv[1] if len(sys.argv) > 1 else "1950104"
    coupons = list_store_coupons(store)
    print(f"门店 {store} 当前可用券 {len(coupons)} 张：")
    for c in coupons:
        p = price_with_coupon(store, c)
        print(f"  {c['title']}（{c['productName']}）"
              f" → 付 {p['pay']} 元 / 原价 {p['original']} 元 / 净薅 {p['save']} 元")
