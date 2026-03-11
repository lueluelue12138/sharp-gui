#!/usr/bin/env python3
"""
commit-stats.py — Sharp GUI 项目 Commit 时间统计分析工具

统计 git 提交记录中的时间分布规律，输出：
  - 时间段分布（凌晨 / 上午 / 下午 / 晚上）
  - 各小时提交频率热力图
  - 星期分布
  - 高峰时段摘要

用法:
    python3 tools/commit-stats.py
"""

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from collections import defaultdict


BJT = timezone(timedelta(hours=8))

WEEKDAY_NAMES = ["周一(Mon)", "周二(Tue)", "周三(Wed)", "周四(Thu)", "周五(Fri)", "周六(Sat)", "周日(Sun)"]

TIME_PERIODS = [
    ("深夜/凌晨 (22:00–02:59)", [22, 23, 0, 1, 2]),
    ("傍晚/晚上 (18:00–21:59)", list(range(18, 22))),
    ("下午     (12:00–17:59)", list(range(12, 18))),
    ("上午     (06:00–11:59)", list(range(6, 12))),
    ("清晨     (03:00–05:59)", list(range(3, 6))),
]


def fetch_commits() -> list[dict]:
    result = subprocess.run(
        ["git", "log", "--format=%ai %s"],
        capture_output=True,
        text=True,
        check=True,
    )
    commits = []
    for line in result.stdout.strip().splitlines():
        # git %ai format: "2026-01-09 23:23:46 +0800 subject..."
        # Split on the first 3 whitespace tokens for date, time, tz
        parts = line.split(" ", 3)
        if len(parts) < 3:
            continue
        dt_str = f"{parts[0]} {parts[1]} {parts[2]}"
        try:
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S %z").astimezone(BJT)
        except ValueError:
            continue
        commits.append(
            {
                "datetime": dt,
                "hour": dt.hour,
                "minute": dt.minute,
                "weekday": dt.weekday(),
                "date": dt.date(),
                "subject": " ".join(parts[3:]),
            }
        )
    return commits


def bar(n: int, width: int = 1) -> str:
    return "█" * (n * width)


def print_section(title: str) -> None:
    print(f"\n{'=' * 50}")
    print(f"  {title}")
    print(f"{'=' * 50}")


def analyze(commits: list[dict]) -> None:
    if not commits:
        print("未找到任何 commit 记录。", file=sys.stderr)
        sys.exit(1)

    dates = [c["date"] for c in commits]
    total = len(commits)

    print(f"\n📊 Sharp GUI — Commit 时间统计分析")
    print(f"   时间范围 : {min(dates)}  →  {max(dates)}")
    print(f"   总提交数 : {total} 次  |  跨越 {(max(dates) - min(dates)).days} 天")

    # ── 时间段分布 ──────────────────────────────────────────
    print_section("时间段分布（北京时间）")
    hour_counts: dict[int, int] = defaultdict(int)
    for c in commits:
        hour_counts[c["hour"]] += 1

    period_rows = []
    for name, hours in TIME_PERIODS:
        count = sum(hour_counts.get(h, 0) for h in hours)
        period_rows.append((count, name))
    period_rows.sort(reverse=True)

    for count, name in period_rows:
        pct = count / total * 100
        filled = bar(count)
        print(f"  {name}  {filled:<20s}  {count:>2} 次 ({pct:4.1f}%)")

    # ── 各小时热力图 ─────────────────────────────────────────
    print_section("各小时提交热力图（北京时间）")
    max_h = max(hour_counts.values()) if hour_counts else 1
    for h in range(24):
        count = hour_counts.get(h, 0)
        scale = round(count / max_h * 20)
        pct = count / total * 100
        marker = " ◀ 高峰" if count == max_h else ""
        print(f"  {h:02d}:xx  {'█' * scale:<20s}  {count:>2} ({pct:4.1f}%){marker}")

    # ── 高频时段 TOP 5 ───────────────────────────────────────
    print_section("高频提交时段 TOP 5")
    sorted_hours = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)
    for rank, (h, count) in enumerate(sorted_hours[:5], 1):
        pct = count / total * 100
        print(f"  #{rank}  {h:02d}:00–{h:02d}:59  →  {count} 次 ({pct:.1f}%)")

    # ── 平均 / 中位数 ────────────────────────────────────────
    print_section("统计摘要")
    all_minutes = sorted(c["hour"] * 60 + c["minute"] for c in commits)
    avg_min = sum(all_minutes) / len(all_minutes)
    median_min = all_minutes[len(all_minutes) // 2]

    def fmt(m: float) -> str:
        return f"{int(m) // 60:02d}:{int(m) % 60:02d}"

    print(f"  平均提交时刻（算术均值）: {fmt(avg_min)} BJT")
    print(f"  中位数提交时刻          : {fmt(median_min)} BJT")
    print(f"  注：若提交时间分布不均匀，中位数通常比均值更能代表典型提交时刻。")

    # ── 星期分布 ─────────────────────────────────────────────
    print_section("星期分布")
    weekday_counts: dict[int, int] = defaultdict(int)
    for c in commits:
        weekday_counts[c["weekday"]] += 1

    for i, name in enumerate(WEEKDAY_NAMES):
        count = weekday_counts.get(i, 0)
        pct = count / total * 100
        weekend = "（周末）" if i >= 5 else "        "
        print(f"  {name} {weekend}  {bar(count):<20s}  {count:>2} 次 ({pct:4.1f}%)")

    weekday_total = sum(weekday_counts.get(i, 0) for i in range(5))
    weekend_total = sum(weekday_counts.get(i, 0) for i in range(5, 7))
    print(f"\n  工作日合计: {weekday_total} 次 ({weekday_total / total * 100:.1f}%)")
    print(f"  周末合计  : {weekend_total} 次 ({weekend_total / total * 100:.1f}%)")

    # ── 结论 ─────────────────────────────────────────────────
    top_period = period_rows[0][1].strip()
    top_hour, top_hour_count = sorted_hours[0]
    top_weekday = max(weekday_counts, key=lambda k: weekday_counts[k]) if weekday_counts else 0
    print_section("🔍 结论")
    print(f"  ① 最活跃时间段 : {top_period} ({period_rows[0][0]} 次, {period_rows[0][0]/total*100:.1f}%)")
    print(f"  ② 最高峰单小时 : {top_hour:02d}:00–{top_hour:02d}:59 ({top_hour_count} 次, {top_hour_count/total*100:.1f}%)")
    print(f"  ③ 最活跃星期   : {WEEKDAY_NAMES[top_weekday]} ({weekday_counts[top_weekday]} 次)")
    print(f"  ④ 工作日偏好   : {weekday_total / total * 100:.1f}% 提交发生在工作日")
    print()


def main() -> None:
    commits = fetch_commits()
    analyze(commits)


if __name__ == "__main__":
    main()
