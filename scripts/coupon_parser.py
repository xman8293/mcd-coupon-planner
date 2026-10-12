"""券 Markdown 解析器：query-my-coupons 返回的是 Markdown 而非 JSON，本模块负责结构化。

实测格式（2026-10-12，6 张真实券样本）：

    ## 中薯条买一送一
    - **优惠**: ¥13.5 (用券价格)
    - **有效期**: 2026-10-12 10:30-2026-10-16 23:59 周一、二、三、四、五 10:30-23:59
    - **领取时间**: 今日收到
    - **标签**: 到店专用、外送专用

    <img src="..." ...>

要点：
- 有效期行 = 起止日期时间 + 可选的"星期约束"+"当日时段约束"两段尾巴
- 优惠行 = 用券价格（部分券型未来可能出现"满X减Y"等其它形态，一律保留原文）

CLI 用法（联调）：
    py scripts/coupon_parser.py tests/fixtures/my_coupons.md

--- @ty.aicoding@1791776247197 ---
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field

sys.stdout.reconfigure(encoding="utf-8")

_WEEKDAY_MAP = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}

_RE_PRICE = re.compile(r"¥\s*([0-9]+(?:\.[0-9]+)?)\s*(?:\(([^)]*)\))?")
_RE_RANGE = re.compile(
    r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s*-\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})"
)
_RE_WEEKDAYS = re.compile(r"周([一二三四五六日天](?:、[一二三四五六日天])*)")
_RE_DAYTIME = re.compile(r"(?<!\d)(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})(?!\d)")


@dataclass
class Coupon:
    """一张券的结构化表示。

    --- @ty.aicoding@1791776247197 ---
    """

    name: str
    price: float | None = None          # 用券价格（¥ 后的数字）
    price_note: str | None = None       # 价格括号说明，如"用券价格"
    benefit_text: str | None = None     # 优惠行原文（兜底，供分类器判断券型）
    valid_from: str | None = None       # ISO 分钟级：2026-10-12T10:30
    valid_to: str | None = None
    weekdays: list[int] = field(default_factory=list)   # 1=周一 ... 7=周日；空=不限
    day_start: str | None = None        # 当日可用时段，如 "10:30"
    day_end: str | None = None
    channels: list[str] = field(default_factory=list)   # 到店专用/外送专用 ...
    raw: str = ""                       # 该券 Markdown 原文块


def parse_coupons(markdown: str) -> list[Coupon]:
    """把券列表 Markdown 解析为 Coupon 列表；解析不了的块原样进 raw 不丢弃。

    --- @ty.aicoding@1791776247197 ---
    """
    coupons: list[Coupon] = []
    # 按 "## " 标题切块，忽略文档头部（"# 您的优惠券列表" 与统计行）
    blocks = re.split(r"\n##\s+", markdown)
    for block in blocks[1:]:
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        c = Coupon(name=lines[0].strip(), raw=block)
        for line in lines[1:]:
            line = line.strip()
            if line.startswith("- **优惠**"):
                c.benefit_text = line.split(":", 1)[-1].strip()
                m = _RE_PRICE.search(c.benefit_text)
                if m:
                    c.price = float(m.group(1))
                    c.price_note = m.group(2)
            elif line.startswith("- **有效期**"):
                body = line.split(":", 1)[-1].strip()
                m = _RE_RANGE.search(body)
                if m:
                    c.valid_from = f"{m.group(1)}T{m.group(2)}"
                    c.valid_to = f"{m.group(3)}T{m.group(4)}"
                tail = body[m.end():].strip() if m else body
                wm = _RE_WEEKDAYS.search(tail)
                if wm:
                    c.weekdays = [_WEEKDAY_MAP[ch] for ch in re.split(r"[、,]", wm.group(1))]
                times = _RE_DAYTIME.findall(tail)
                if times:
                    c.day_start, c.day_end = times[-1]
            elif line.startswith("- **标签**"):
                c.channels = [t.strip() for t in line.split(":", 1)[-1].split("、") if t.strip()]
        coupons.append(c)
    return coupons


if __name__ == "__main__":
    src = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else sys.stdin.read()
    result = [asdict(c) for c in parse_coupons(src)]
    print(json.dumps(result, ensure_ascii=False, indent=2))
