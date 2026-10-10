"""抓上游資料表 (只給 CLI 用; 入口函式不碰網路)."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .errors import ToolError
from .pool import SOURCES, raw_url

_UA = {"User-Agent": "claude_autoClickV2-recruit-tags"}


def _get_json(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=_UA),
                                    timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # 網路、HTTP、JSON 格式
        raise ToolError(f"抓不到 {url}（{e}）") from None


def table(server, name):
    return _get_json(raw_url(server, name))


def upstream_updated(server):
    """上游 gacha_table 的最後提交時間 (GitHub API); 抓不到時回 None."""
    src = SOURCES[server]
    q = urllib.parse.urlencode({"path": f"{src['path']}gacha_table.json",
                                "sha": src["branch"], "per_page": 1})
    try:
        commits = _get_json(f"https://api.github.com/repos/{src['repo']}/commits?{q}")
        return commits[0]["commit"]["committer"]["date"]
    except (ToolError, LookupError, TypeError):
        return None
