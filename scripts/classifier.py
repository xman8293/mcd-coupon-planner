"""券分类器：五分类 + 时段落位标签。

五分类（排程与优化策略各不相同）：
    redeem   兑换型：0 元/免费兑换，直接用
    special  特价型：固定用券价（如 9.9 冰美式），直接用
    discount 折扣型：按比例打折（如 7 折），订单越大省越多
    bogo     买赠型：买一送一，价值=赠品等价
    threshold满减型：满 X 减 Y——唯一的硬问题，需要凑单 DP（optimizer）

时段落位（由有效期约束 + 名称推断）：
    breakfast / lunch / afternoon_tea / dinner / any

CLI 用法（联调）：
    py scripts/classifier.py tests/fixtures/my_coupons.md

--- @ty.aicoding@1791776602135 ---
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass

sys.stdout.reconfigure(encoding="utf-8")

from coupon_parser import Coupon, parse_coupons

_RE_THRESHOLD = re.compile(r"满\s*([0-9.]+)\s*减\s*([0-9.]+)")
_RE_DISCOUNT = re.compile(r"([0-9.]+)\s*折|([一二三四五六七八九]+)折")

_TYPE_LABELS = {
    "redeem": "兑换型",
    "special": "特价型",
    "discount": "折扣型",
    "bogo": "买赠型",
    "threshold": "满减型",
}


@dataclass
class ClassifiedCoupon:
    """带券型与时段标签的券。

    --- @ty.aicoding@1791776602135 ---
    """

    coupon: Coupon
    ctype: str                      # redeem/special/discount/bogo/threshold
    ctype_label: str                # 中文名
    slot: str = "any"               # breakfast/lunch/afternoon_tea/dinner/any
    threshold: float | None = None  # 满减门槛（仅 threshold 型）
    minus: float | None = None      # 满减立减额（仅 threshold 型）
    reason: str = ""                # 分类依据（写进说明书/调试）


def _infer_slot(c: Coupon) -> str:
    """由时段约束+名称推断可落位时段；约束缺失时按名称，再缺省 any。

    --- @ty.aicoding@1791776602135 ---
    """
    if c.day_start and c.day_end:
        end_h = int(c.day_end.split(":")[0]) + int(c.day_end.split(":")[1]) / 60
        if end_h <= 10.5:
            return "breakfast"
    name = c.name
    if "早餐" in name or "猪柳蛋" in name or "松饼" in name:
        return "breakfast"
    if "下午茶" in name:
        return "afternoon_tea"
    return "any"


def classify(c: Coupon) -> ClassifiedCoupon:
    """单券分类：先看优惠文案形态，再看名称关键词，兜底特价型。

    --- @ty.aicoding@1791776602135 ---
    """
    text = f"{c.name} {c.benefit_text or ''}"
    m = _RE_THRESHOLD.search(text)
    if m:
        return ClassifiedCoupon(
            coupon=c, ctype="threshold", ctype_label=_TYPE_LABELS["threshold"],
            slot=_infer_slot(c), threshold=float(m.group(1)), minus=float(m.group(2)),
            reason=f"命中满减模式「{m.group(0)}」",
        )
    if _RE_DISCOUNT.search(text):
        return ClassifiedCoupon(
            coupon=c, ctype="discount", ctype_label=_TYPE_LABELS["discount"],
            slot=_infer_slot(c), reason="命中折扣模式「折」",
        )
    if re.search(r"买\s*一\s*送\s*一|买\d+送\d+|买.*送", c.name):
        return ClassifiedCoupon(
            coupon=c, ctype="bogo", ctype_label=_TYPE_LABELS["bogo"],
            slot=_infer_slot(c), reason="名称命中买赠模式",
        )
    if c.price == 0 or re.search(r"免费|0\s*元|兑换", text):
        return ClassifiedCoupon(
            coupon=c, ctype="redeem", ctype_label=_TYPE_LABELS["redeem"],
            slot=_infer_slot(c), reason="免费/兑换关键词",
        )
    return ClassifiedCoupon(
        coupon=c, ctype="special", ctype_label=_TYPE_LABELS["special"],
        slot=_infer_slot(c), reason="固定用券价，默认特价型",
    )


def classify_all(coupons: list[Coupon]) -> list[ClassifiedCoupon]:
    """批量分类。

    --- @ty.aicoding@1791776602135 ---
    """
    return [classify(c) for c in coupons]


if __name__ == "__main__":
    src = open(sys.argv[1], encoding="utf-8").read()
    out = [
        {
            "name": cc.coupon.name,
            "ctype": cc.ctype_label,
            "slot": cc.slot,
            "threshold": cc.threshold,
            "minus": cc.minus,
            "reason": cc.reason,
        }
        for cc in classify_all(parse_coupons(src))
    ]
    print(json.dumps(out, ensure_ascii=False, indent=2))
