#!/usr/bin/env python3
"""生成 GitHub 统计卡片 SVG（无第三方依赖，仅标准库）。

数据来源：GitHub GraphQL API（需要带 repo 读权限的 token）。
用法：
    GITHUB_TOKEN=xxx python scripts/generate_stats.py --login HH200606 --out assets/stats.svg
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com/graphql"

# GitHub 官方语言配色（取常用的一批，缺失时用中性灰）
LANG_COLORS = {
    "Python": "#3572A5",
    "Jupyter Notebook": "#DA5B0B",
    "TypeScript": "#3178c6",
    "JavaScript": "#f1e05a",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "C++": "#f34b7d",
    "C": "#555555",
    "Java": "#b07219",
    "Go": "#00ADD8",
    "Rust": "#dea584",
    "Shell": "#89e051",
    "MDX": "#fcb32c",
    "Vue": "#41b883",
}

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100) {
      totalCount
      nodes {
        stargazerCount
        primaryLanguage { name color }
      }
    }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount date } }
      }
    }
  }
}
"""


def gql(token: str, login: str) -> dict:
    payload = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        API,
        data=payload,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-stats-generator",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode())
    if "errors" in body:
        raise SystemExit(f"GraphQL error: {body['errors']}")
    return body["data"]["user"]


def streaks(days: list[dict]) -> tuple[int, int]:
    """返回 (当前连续天数, 历史最长连续天数)。days 按日期升序。"""
    parsed = sorted(
        ((dt.date.fromisoformat(d["date"]), d["contributionCount"]) for d in days),
        key=lambda x: x[0],
    )
    longest = current = 0
    last_date = None
    for day, count in parsed:
        if count > 0:
            if last_date is not None and (day - last_date).days == 1:
                current += 1
            else:
                current = 1
            longest = max(longest, current)
            last_date = day
        else:
            current = 0
            last_date = None

    # 当前连续：从今天（或昨天有贡献时）往回数
    today = dt.date.today()
    counts = {d: c for d, c in parsed}
    run = 0
    cursor = today
    if counts.get(cursor, 0) == 0:
        cursor = today - dt.timedelta(days=1)
    while counts.get(cursor, 0) > 0:
        run += 1
        cursor -= dt.timedelta(days=1)
    return run, longest


def fmt(n: int) -> str:
    return f"{n:,}"


def build_svg(user: dict, login: str) -> str:
    repos = user["repositories"]
    days = [d for w in user["contributionsCollection"]["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    total = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    stars = sum(r["stargazerCount"] for r in repos["nodes"])
    followers = user["followers"]["totalCount"]
    current, longest = streaks(days)

    lang_count: dict[str, int] = {}
    lang_color: dict[str, str] = {}
    for r in repos["nodes"]:
        lang = r.get("primaryLanguage")
        if not lang:
            continue
        name = lang["name"]
        lang_count[name] = lang_count.get(name, 0) + 1
        lang_color[name] = lang.get("color") or LANG_COLORS.get(name, "#8b949e")
    top = sorted(lang_count.items(), key=lambda kv: kv[1], reverse=True)[:3]

    metrics = [
        ("贡献总数", fmt(total)),
        ("公开仓库", fmt(repos["totalCount"])),
        ("Star", fmt(stars)),
        ("关注者", fmt(followers)),
        ("连续天数", fmt(current)),
    ]

    x = 56
    blocks = []
    for label, value in metrics:
        blocks.append(
            f'<text x="{x}" y="120" class="num">{value}</text>'
            f'<text x="{x}" y="150" class="lbl">{label}</text>'
        )
        x += 138

    if top:
        dots = []
        y = 104
        for name, count in top:
            dots.append(
                f'<circle cx="792" cy="{y - 5}" r="5" fill="{lang_color[name]}"/>'
                f'<text x="808" y="{y}" class="lang">{name}</text>'
            )
            y += 30
    else:
        dots = ['<text x="792" y="104" class="lang">还没有语言数据</text>']

    updated = dt.date.today().isoformat()
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1040" height="200" viewBox="0 0 1040 200" role="img" aria-label="GitHub stats for {login}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0b1220"/>
      <stop offset="1" stop-color="#111c33"/>
    </linearGradient>
    <linearGradient id="rule" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#818cf8"/>
      <stop offset="1" stop-color="#22d3ee"/>
    </linearGradient>
  </defs>
  <style>
    .num {{ font: 800 34px 'Segoe UI','Microsoft YaHei',sans-serif; fill: #f8fafc; }}
    .lbl {{ font: 400 13px 'Segoe UI','Microsoft YaHei',sans-serif; fill: #94a3b8; }}
    .hdr {{ font: 600 12px 'Segoe UI','Microsoft YaHei',sans-serif; fill: #38bdf8; letter-spacing: 3px; }}
    .lang {{ font: 400 14px 'Segoe UI','Microsoft YaHei',sans-serif; fill: #cbd5e1; }}
    .upd {{ font: 400 11px 'Segoe UI','Microsoft YaHei',sans-serif; fill: #64748b; }}
  </style>
  <rect x="0.5" y="0.5" width="1039" height="199" rx="16" fill="url(#bg)" stroke="#1f2a3a"/>
  <text x="56" y="56" class="hdr">GITHUB 数据</text>
  <rect x="56" y="68" width="56" height="3" rx="1.5" fill="url(#rule)"/>
  {''.join(blocks)}
  <line x1="752" y1="88" x2="752" y2="156" stroke="#1f2a3a"/>
  {''.join(dots)}
  <text x="968" y="182" text-anchor="end" class="upd">更新于 {updated}</text>
</svg>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", required=True)
    ap.add_argument("--out", default="assets/stats.svg")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("缺少 GITHUB_TOKEN", file=sys.stderr)
        return 1

    user = gql(token, args.login)
    svg = build_svg(user, args.login)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"written {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

