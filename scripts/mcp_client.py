"""麦当劳 MCP 客户端：券驱动点餐 Skill 的基础设施层。

- 身份机制：Token 从环境变量 MCD_MCP_TOKEN 读取
  （用户在 https://open.mcd.cn/mcp 控制台手机号登录后免费领取，600 次/分限流）。
- 严禁将 Token 写入代码、配置或仓库；mcp-config.example.json 中仅使用
  ${MCD_MCP_TOKEN} 占位符。
- 通信：HTTP POST + JSON-RPC(tools/call)，无会话；curl 会被 WAF 拦截（202 空响应），
  本模块使用 urllib 直连（已实测可用）。

CLI 用法（联调）：
    py scripts/mcp_client.py <tool_name> [args_json]

--- @ty.aicoding@1791776046438 ---
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.stdout.reconfigure(encoding="utf-8")

URL = "https://mcp.mcd.cn/mcp-servers/mcd-mcp"
TIMEOUT = 30


class McpError(Exception):
    """MCP 调用失败的结构化错误，kind 供上层生成人话提示。

    kind 取值：
        no_token  - 环境变量未配置
        http      - HTTP 层错误（含 401/403 Token 失效）
        rpc       - MCP 服务端返回 JSON-RPC error
        network   - 网络/超时
    """


def _token() -> str:
    """读取 Token；未配置时抛 no_token，由 Skill 层提示用户去开放平台领取。

    --- @ty.aicoding@1791776046438 ---
    """
    token = os.environ.get("MCD_MCP_TOKEN", "").strip()
    if not token:
        raise McpError("no_token")
    return token


def list_tools() -> list[dict]:
    """拉取 tools/list，返回全部工具签名（联调与文档编写用）。

    --- @ty.aicoding@1791777283328 ---
    """
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    headers = {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "mcd-coupon-planner/0.1",
    }
    req = urllib.request.Request(
        URL, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    return data.get("result", {}).get("tools", [])


def call_tool(tool: str, args: dict | None = None, max_len: int | None = None) -> str:
    """调用一个 MCP 工具，返回其 text 内容（部分工具为 Markdown 文本）。

    --- @ty.aicoding@1791776046438 ---
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": args or {}},
    }
    headers = {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "mcd-coupon-planner/0.1",
    }
    req = urllib.request.Request(
        URL, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise McpError(f"http:{e.code}:{body}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise McpError(f"network:{e}") from e

    if "error" in data:
        raise McpError(f"rpc:{json.dumps(data['error'], ensure_ascii=False)[:300]}")

    result = data.get("result", {})
    content = result.get("content", [])
    if isinstance(content, list) and content:
        text = "\n".join(c.get("text", "") for c in content if c.get("type") == "text")
    else:
        text = json.dumps(result, ensure_ascii=False)
    if max_len and len(text) > max_len:
        text = text[:max_len] + "\n...[truncated]"
    return text


def fetch_user_context(city: str = "北京") -> dict:
    """流水线阶段①：并行拉取规划所需的四路数据。

    返回 {"coupons": str, "stores": str, "available": str, "account": str,
          "errors": {接口名: 错误信息}}；单接口失败不拖垮整体。

    --- @ty.aicoding@1791776046438 ---
    """
    jobs = {
        "coupons": ("query-my-coupons", {}),
        "stores": ("query-nearby-stores", {"city": city}),
        "available": ("available-coupons", {}),
        "account": ("query-my-account", {}),
    }
    out: dict = {"errors": {}}

    def _run(item):
        key, (tool, args) = item
        try:
            return key, call_tool(tool, args), None
        except McpError as e:
            return key, None, str(e)

    with ThreadPoolExecutor(max_workers=4) as pool:
        for key, text, err in pool.map(_run, jobs.items()):
            if err:
                out["errors"][key] = err
            else:
                out[key] = text
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    _tool = sys.argv[1]
    _args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    try:
        print(call_tool(_tool, _args, max_len=2500))
    except McpError as e:
        print(f"McpError: {e}")
        sys.exit(2)
