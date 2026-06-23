#!/usr/bin/env python3
"""조직 공개 저장소의 커밋을 모아 활동 대시보드 + 잔디 히트맵 SVG를 생성한다.

- 외부 패키지 의존 없음 (표준 라이브러리만 사용)
- 비공개 저장소까지 집계하려면 org repo 읽기 권한(Contents/Metadata: read)이 있는
  토큰을 GH_TOKEN 으로 넘긴다. 토큰이 없으면 공개 저장소만 집계된다.
- 사용:  GH_TOKEN=xxx python3 scripts/generate_activity.py
"""

from __future__ import annotations

import json
import os
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ORG = os.environ.get("ORG", "bricks8c")
API = "https://api.github.com"
OUT_DIR = Path(os.environ.get("OUT_DIR", "profile/assets"))

# 브랜드 컬러
BG = "#0a0a0a"
PANEL = "#111317"
ACCENT = "#FF4500"
FG = "#e6e6e6"
MUTED = "#8b8b8b"
GRID_EMPTY = "#1b1f24"
# 잔디 강도(낮음→높음)
HEAT = ["#1b1f24", "#5c1b00", "#8a2900", "#c23600", "#FF4500"]


def gh_get(url: str):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "bricks8c-activity",
    })
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def list_repos() -> list[str]:
    # type=all → 공개 + 비공개 모두 (비공개는 권한 있는 토큰 필요).
    # 포크 · 아카이브 저장소는 활동 집계에서 제외.
    repos, page = [], 1
    while True:
        batch = gh_get(f"{API}/orgs/{ORG}/repos?per_page=100&type=all&page={page}")
        if not batch:
            break
        repos += [r["name"] for r in batch
                  if not r.get("fork") and not r.get("archived")]
        if len(batch) < 100:
            break
        page += 1
    return repos


def list_commit_dates(repo: str) -> list[datetime]:
    dates, page = [], 1
    while page <= 5:  # 저장소당 최대 500커밋이면 충분
        try:
            batch = gh_get(f"{API}/repos/{ORG}/{repo}/commits?per_page=100&page={page}")
        except Exception:
            break
        if not batch:
            break
        for c in batch:
            iso = c["commit"]["author"]["date"]
            dates.append(datetime.fromisoformat(iso.replace("Z", "+00:00")))
        if len(batch) < 100:
            break
        page += 1
    return dates


def collect():
    all_dates: list[datetime] = []
    repos = list_repos()
    for r in repos:
        all_dates += list_commit_dates(r)
    return repos, all_dates


def compute_stats(dates: list[datetime]):
    by_day = defaultdict(int)
    for d in dates:
        by_day[d.astimezone(timezone.utc).date()] += 1

    total = len(dates)
    active_days = len(by_day)

    # 현재 연속일(오늘 또는 어제부터 역산)
    today = datetime.now(timezone.utc).date()
    streak = 0
    cur = today if by_day.get(today) else today - timedelta(days=1)
    while by_day.get(cur):
        streak += 1
        cur -= timedelta(days=1)

    return by_day, total, active_days, streak


def weekly_counts(by_day, weeks=12):
    today = datetime.now(timezone.utc).date()
    # 이번 주 월요일
    monday = today - timedelta(days=today.weekday())
    buckets = []
    for i in range(weeks - 1, -1, -1):
        start = monday - timedelta(weeks=i)
        c = sum(by_day.get(start + timedelta(days=d), 0) for d in range(7))
        buckets.append(c)
    return buckets


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_dashboard(repos, by_day, total, active_days, streak) -> str:
    W, H = 480, 210
    weeks = weekly_counts(by_day, 12)
    peak = max(weeks) or 1

    # 막대그래프 영역
    bx, by_, bw, bh = 28, 120, W - 56, 60
    gap = 6
    n = len(weeks)
    barw = (bw - gap * (n - 1)) / n
    bars = []
    for i, c in enumerate(weeks):
        h = round(bh * (c / peak)) if c else 2
        x = bx + i * (barw + gap)
        y = by_ + bh - h
        op = 0.35 + 0.65 * (c / peak) if peak else 0.35
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{barw:.1f}" height="{h}" '
            f'rx="2" fill="{ACCENT}" opacity="{op:.2f}"/>'
        )

    def stat(x, value, label):
        return (
            f'<text x="{x}" y="86" fill="{FG}" font-size="26" font-weight="700" '
            f'font-family="-apple-system,Segoe UI,sans-serif">{value}</text>'
            f'<text x="{x}" y="104" fill="{MUTED}" font-size="11" '
            f'font-family="-apple-system,Segoe UI,sans-serif" letter-spacing="1">{label}</text>'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img">
  <rect width="{W}" height="{H}" rx="12" fill="{BG}"/>
  <rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="12" fill="none" stroke="#222" />
  <text x="28" y="40" fill="{FG}" font-size="17" font-weight="700"
    font-family="-apple-system,Segoe UI,sans-serif">BRICKS8 <tspan fill="{ACCENT}">·</tspan> Building brick by brick 🧱</text>
  <text x="28" y="58" fill="{MUTED}" font-size="11"
    font-family="-apple-system,Segoe UI,sans-serif">조직 공개 저장소 활동 · 자동 갱신</text>
  {stat(28, total, "COMMITS")}
  {stat(150, active_days, "ACTIVE DAYS")}
  {stat(290, streak, "DAY STREAK")}
  {stat(400, len(repos), "REPOS")}
  <text x="28" y="116" fill="{MUTED}" font-size="10" letter-spacing="1"
    font-family="-apple-system,Segoe UI,sans-serif">COMMITS / WEEK · 최근 12주</text>
  {''.join(bars)}
</svg>'''


def render_heatmap(by_day) -> str:
    cell, gap = 11, 3
    step = cell + gap
    weeks = 53
    today = datetime.now(timezone.utc).date()
    # 그리드 끝(오른쪽) = 이번 주, 일요일 시작 기준
    end_sunday = today + timedelta(days=(6 - today.weekday()) % 7)
    start = end_sunday - timedelta(weeks=weeks - 1, days=6)

    counts = [by_day.get(start + timedelta(days=i), 0)
              for i in range((end_sunday - start).days + 1)]
    nonzero = [c for c in counts if c]
    hi = max(nonzero) if nonzero else 1

    def level(c):
        if not c:
            return 0
        if c >= hi:
            return 4
        return 1 + min(3, int(4 * c / hi))

    pad_l, pad_t = 30, 22
    cells, month_labels = [], []
    last_month = None
    for w in range(weeks):
        for d in range(7):
            day = start + timedelta(weeks=w, days=d)
            if day > today:
                continue
            c = by_day.get(day, 0)
            x = pad_l + w * step
            y = pad_t + d * step
            cells.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" '
                f'fill="{HEAT[level(c)]}"><title>{day.isoformat()} · {c} commits</title></rect>'
            )
        # 월 라벨
        first = start + timedelta(weeks=w)
        if first.month != last_month and first.day <= 7:
            month_labels.append(
                f'<text x="{pad_l + w*step}" y="{pad_t-7}" fill="{MUTED}" font-size="9" '
                f'font-family="-apple-system,Segoe UI,sans-serif">{first.strftime("%b")}</text>'
            )
            last_month = first.month

    days_lbl = ""
    for d, name in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
        days_lbl += (f'<text x="2" y="{pad_t + d*step + cell-1}" fill="{MUTED}" '
                     f'font-size="9" font-family="-apple-system,Segoe UI,sans-serif">{name}</text>')

    W = pad_l + weeks * step + 4
    H = pad_t + 7 * step + 24
    legend_x = W - 150
    legend = "".join(
        f'<rect x="{legend_x + 40 + i*(cell+2)}" y="{H-16}" width="{cell}" height="{cell}" rx="2" fill="{HEAT[i]}"/>'
        for i in range(5)
    )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img">
  <rect width="{W}" height="{H}" rx="12" fill="{BG}"/>
  <rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="12" fill="none" stroke="#222"/>
  {''.join(month_labels)}
  {days_lbl}
  {''.join(cells)}
  <text x="{legend_x}" y="{H-7}" fill="{MUTED}" font-size="9" font-family="-apple-system,Segoe UI,sans-serif">Less</text>
  {legend}
  <text x="{legend_x + 40 + 5*(cell+2) + 4}" y="{H-7}" fill="{MUTED}" font-size="9" font-family="-apple-system,Segoe UI,sans-serif">More</text>
</svg>'''


def main():
    repos, dates = collect()
    by_day, total, active_days, streak = compute_stats(dates)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "activity-dashboard.svg").write_text(
        render_dashboard(repos, by_day, total, active_days, streak), encoding="utf-8")
    (OUT_DIR / "contribution-heatmap.svg").write_text(
        render_heatmap(by_day), encoding="utf-8")
    print(f"repos={len(repos)} commits={total} active_days={active_days} streak={streak}")
    print(f"→ {OUT_DIR}/activity-dashboard.svg")
    print(f"→ {OUT_DIR}/contribution-heatmap.svg")


if __name__ == "__main__":
    main()
