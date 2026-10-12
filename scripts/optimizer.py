r"""优化器：过期排程 + 建议放弃清单 + 满减凑单 DP。

三块确定性逻辑：
1. plan_week()   —— 把本周券按"过期日升序 + 预估节省降序"贪心排进就餐日历，
                    装不下的进放弃清单并附人话理由。
2. 放弃理由生成   —— 金句"最高级的薅羊毛是知道哪张不该薅"的执行层。
3. optimize_threshold() —— 满减凑单 DP：sum(商品) ≥ 门槛前提下最小化溢出
                    （sum - 门槛），平局取件数少；约束至少一件主食、禁离谱组合。

CLI 用法（联调）：
    py scripts/optimizer.py ..\tests\fixtures\my_coupons.md [本周顿数]

--- @ty.aicoding@1791776602135 ---
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8")

from classifier import ClassifiedCoupon, classify_all
from coupon_parser import parse_coupons

SLOTS_PER_DAY = ["breakfast", "lunch", "dinner"]
_SLOT_LABELS = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐", "any": "全天"}


def _to_date(iso: str) -> date:
    return datetime.fromisoformat(iso).date()


def _est_save(cc: ClassifiedCoupon) -> float:
    """预估单券节省额（缺菜单原价时的粗估，验价阶段会被官方价修正）。

    --- @ty.aicoding@1791776602135 ---
    """
    c = cc.coupon
    if cc.ctype == "threshold":
        return cc.minus or 0.0
    if cc.ctype == "bogo":
        return c.price or 0.0          # 赠一份，粗估省一份的钱
    if cc.ctype == "redeem":
        return 99.0                    # 免费兑换优先级最高
    return (c.price or 0.0) * 0.3      # 特价型粗估 30% 折扣力度


def _eligible_dates(cc: ClassifiedCoupon, start: date, horizon: int = 8) -> list[date]:
    """券在 [start, start+horizon) 内可用的日期（含星期约束）。

    --- @ty.aicoding@1791776602135 ---
    """
    c = cc.coupon
    vf = _to_date(c.valid_from) if c.valid_from else start
    vt = _to_date(c.valid_to) if c.valid_to else start
    days = []
    for i in range(horizon):
        d = start + timedelta(days=i)
        if d < vf or d > vt:
            continue
        if c.weekdays and d.isoweekday() not in c.weekdays:
            continue
        days.append(d)
    return days


def _give_up_reason(cc: ClassifiedCoupon, why: str) -> dict:
    """生成放弃清单条目（理由要具体，不糊弄）。

    --- @ty.aicoding@1791776602135 ---
    """
    c = cc.coupon
    if why == "no_slot":
        if cc.slot == "breakfast" and c.valid_from and c.valid_to:
            vf, vt = _to_date(c.valid_from), _to_date(c.valid_to)
            reason = (
                f"仅 {vf.month}月{vf.day}日-{vt.month}月{vt.day}日 "
                f"{c.day_start}-{c.day_end} 早餐时段可用，时间窗太窄，"
                f"专为它早起不值当"
            )
        else:
            reason = "有效期与本周就餐计划没有交集"
    elif why == "plan_full":
        reason = f"本周计划已排满，它在优先级末尾（{cc.ctype_label}，预估节省最低）"
    elif why == "high_threshold":
        reason = (
            f"满{cc.threshold:.0f}减{cc.minus:.0f} 相当于 "
            f"{cc.minus / cc.threshold * 100:.0f}% 力度，门槛高省得少，"
            f"硬凑反而多花钱"
        )
    else:
        reason = "综合优先级不足"
    return {"name": c.name, "ctype": cc.ctype_label, "reason": reason}


def plan_week(
    classified: list[ClassifiedCoupon],
    meals: int = 3,
    today: date | None = None,
) -> dict:
    """本周排程：贪心分配，产出 plan + give_up。

    约束：每顿饭（date+slot）最多用 1 张券（实测每单限 1 券）。

    --- @ty.aicoding@1791776738189 ---
    """
    today = today or date.today()
    # 满减力度过差的直接劝退（折扣率 < 12%）
    pool, give_up = [], []
    for cc in classified:
        if cc.ctype == "threshold" and cc.minus and cc.threshold:
            if cc.minus / cc.threshold < 0.12:
                give_up.append(_give_up_reason(cc, "high_threshold"))
                continue
        pool.append(cc)

    pool.sort(key=lambda cc: (cc.coupon.valid_to or "9999", -_est_save(cc)))

    plan: list[dict] = []
    used_slots: set[tuple[str, str]] = set()   # (date, slot) 已占用
    for cc in pool:
        if len(plan) >= meals:
            give_up.append(_give_up_reason(cc, "plan_full"))
            continue
        days = _eligible_dates(cc, today)
        if not days:
            give_up.append(_give_up_reason(cc, "no_slot"))
            continue
        # 为该券找第一个空位：any 券优先午餐，其次晚餐/早餐
        candidates = [cc.slot] if cc.slot != "any" else ["lunch", "dinner", "breakfast"]
        placed = None
        for d in days:
            for slot in candidates:
                if (d.isoformat(), slot) not in used_slots:
                    placed = (d, slot)
                    break
            if placed:
                break
        if not placed:
            give_up.append(_give_up_reason(cc, "plan_full"))
            continue
        d, slot = placed
        used_slots.add((d.isoformat(), slot))
        plan.append({
            "date": d.isoformat(),
            "weekday": f"周{'一二三四五六日'[d.isoweekday() - 1]}",
            "slot": _SLOT_LABELS[slot],
            "coupon": cc.coupon.name,
            "ctype": cc.ctype_label,
            "coupon_price": cc.coupon.price,
            "est_save": round(_est_save(cc), 1),
            "channels": cc.coupon.channels,
        })

    plan.sort(key=lambda p: (p["date"], SLOTS_PER_DAY.index(
        {v: k for k, v in _SLOT_LABELS.items() if k != "any"}[p["slot"]]
    )))
    return {
        "plan": plan,
        "give_up": give_up,
        "total": {
            "meals": len(plan),
            "est_save": round(sum(p["est_save"] for p in plan), 1),
            "est_pay": round(sum(p["coupon_price"] or 0 for p in plan), 1),
        },
    }


@dataclass
class MenuItem:
    """凑单候选商品。

    --- @ty.aicoding@1791776602135 ---
    """

    name: str
    price: float
    category: str = "snack"   # main=主食 / snack / drink / dessert


def optimize_threshold(
    items: list[MenuItem], threshold: float, minus: float,
) -> dict | None:
    """满减凑单 DP：达标前提下最小化溢出，平局取件数少；至少一件主食。

    --- @ty.aicoding@1791776602135 ---
    """
    t = round(threshold * 100)
    units = [(round(i.price * 100), i) for i in items]
    best: dict[int, tuple[int, list[int]]] = {0: (0, [])}  # sum -> (count, 商品下标)
    cap = t + max(u for u, _ in units)
    for idx, (u, it) in enumerate(units):
        for s in sorted([s for s in best if s + u <= cap], reverse=True):
            ns = s + u
            cand = (best[s][0] + 1, best[s][1] + [idx])
            if ns not in best or cand[0] < best[ns][0]:
                best[ns] = cand
    for s in sorted(k for k in best if k >= t):
        _, idxs = best[s]
        chosen = [units[i][1] for i in idxs]
        if any(i.category == "main" for i in chosen) or not any(
            i.category == "main" for i in items
        ):
            total = s / 100
            return {
                "items": [{"name": i.name, "price": i.price} for i in chosen],
                "total": total,
                "pay": round(total - minus, 2),
                "overflow": round(total - threshold, 2),
            }
    return None


if __name__ == "__main__":
    src = open(sys.argv[1], encoding="utf-8").read()
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    result = plan_week(classify_all(parse_coupons(src)), meals=n)

    # 满减 DP 自测（合成菜单：满 39 减 5）
    menu = [
        MenuItem("麦辣鸡腿堡", 21.0, "main"), MenuItem("板烧鸡腿堡", 22.0, "main"),
        MenuItem("巨无霸", 25.5, "main"), MenuItem("中薯条", 13.5),
        MenuItem("麦乐鸡5块", 13.0), MenuItem("中杯可乐", 9.5, "drink"),
        MenuItem("香芋派", 8.0, "dessert"),
    ]
    result["threshold_demo"] = optimize_threshold(menu, 39.0, 5.0)
    print(json.dumps(result, ensure_ascii=False, indent=2))
