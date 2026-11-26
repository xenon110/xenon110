#!/usr/bin/env python3
"""
Profile README generator for @xenon110
--------------------------------------
Pulls REAL activity from the GitHub GraphQL API (every day of every year since
the account was created) and renders ONE unified dark dashboard per period:

  assets/dashboard-last-year.svg   rolling 12 months
  assets/dashboard-YYYY.svg        one per calendar year (month -> day detail)

Each dashboard combines KPI tiles, a day-level heatmap, a weekly trend line
aligned to the same time axis, and a language donut.

It also rewrites the <!--START_SECTION:x--> blocks inside README.md.

Usage:
  GH_USER=xenon110 GH_TOKEN=ghp_xxx python scripts/generate.py
  python scripts/generate.py --demo        # offline preview with fake data
"""
import html
import json
import math
import os
import random
import re
import sys
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

USER = os.environ.get("GH_USER", "xenon110")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
DEMO = "--demo" in sys.argv or not TOKEN

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ("assets_demo" if DEMO else "assets")
OUT.mkdir(exist_ok=True)

NOW = datetime.now(timezone.utc)
TODAY = NOW.date()

# ----------------------------------------------------------------- theme ----
TXT, MUTED = "#e2e8f0", "#94a3b8"
LEVELS = ["#151b2b", "#0b4f6c", "#0891b2", "#22d3ee", "#a5f3fc"]
FONT = "Segoe UI, Helvetica, Arial, sans-serif"
PALETTE = ["#22d3ee", "#a78bfa", "#f472b6", "#fbbf24", "#34d399", "#475569"]
esc = html.escape

# ------------------------------------------------------------ GraphQL -------
PROFILE_Q = """
query($login:String!){
  user(login:$login){
    createdAt
    followers{totalCount}
    following{totalCount}
    pullRequests{totalCount}
    issues{totalCount}
    repositories(ownerAffiliations:OWNER,isFork:false,first:100,
                 orderBy:{field:PUSHED_AT,direction:DESC}){
      totalCount
      nodes{
        name description url stargazerCount forkCount pushedAt isArchived
        primaryLanguage{name color}
        languages(first:8,orderBy:{field:SIZE,direction:DESC}){
          edges{size node{name color}}
        }
      }
    }
  }
}"""

YEAR_Q = """
query($login:String!,$from:DateTime!,$to:DateTime!){
  user(login:$login){
    contributionsCollection(from:$from,to:$to){
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      contributionCalendar{
        totalContributions
        weeks{contributionDays{date contributionCount}}
      }
    }
  }
}"""


def gql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "profile-readme-generator",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    if "errors" in data:
        raise SystemExit(json.dumps(data["errors"], indent=2))
    return data["data"]


def fetch_live():
    prof = gql(PROFILE_Q, {"login": USER})["user"]
    created = int(prof["createdAt"][:4])
    years = {}
    for y in range(created, TODAY.year + 1):
        frm = f"{y}-01-01T00:00:00Z"
        to = NOW.strftime("%Y-%m-%dT%H:%M:%SZ") if y == TODAY.year else f"{y}-12-31T23:59:59Z"
        years[y] = gql(YEAR_Q, {"login": USER, "from": frm, "to": to})["user"][
            "contributionsCollection"
        ]
        print(f"  fetched {y}: {years[y]['contributionCalendar']['totalContributions']}")
    return prof, years


def fetch_demo():
    random.seed(7)
    langs = [("Python", "#3572A5"), ("JavaScript", "#f1e05a"), ("Java", "#b07219"),
             ("TypeScript", "#3178c6"), ("Jupyter Notebook", "#DA5B0B"), ("HTML", "#e34c26")]
    nodes = []
    for n in ["Mediskin", "Veyra", "Scan2Eat", "Task-Management", "dsa-practice", "portfolio"]:
        edges = [{"size": random.randint(2000, 90000), "node": {"name": l, "color": c}}
                 for l, c in random.sample(langs, 3)]
        nodes.append({"name": n, "description": f"Demo repo {n}", "url": f"https://github.com/{USER}/{n}",
                      "stargazerCount": random.randint(0, 9), "forkCount": random.randint(0, 3),
                      "pushedAt": f"2026-0{random.randint(1, 9)}-1{random.randint(0, 9)}T10:00:00Z",
                      "isArchived": False,
                      "primaryLanguage": {"name": edges[0]["node"]["name"], "color": edges[0]["node"]["color"]},
                      "languages": {"edges": edges}})
    prof = {"createdAt": "2023-06-01T00:00:00Z", "followers": {"totalCount": 12},
            "following": {"totalCount": 20}, "pullRequests": {"totalCount": 31},
            "issues": {"totalCount": 9}, "repositories": {"totalCount": len(nodes), "nodes": nodes}}
    years = {}
    for y in range(2023, TODAY.year + 1):
        d, end, days = date(y, 1, 1), min(date(y, 12, 31), TODAY), []
        while d <= end:
            c = 0 if random.random() < 0.35 else int(random.expovariate(1 / 4))
            days.append({"date": d.isoformat(), "contributionCount": c})
            d += timedelta(days=1)
        weeks = [{"contributionDays": days[i:i + 7]} for i in range(0, len(days), 7)]
        years[y] = {"totalCommitContributions": sum(x["contributionCount"] for x in days) // 2,
                    "totalPullRequestContributions": 8, "totalIssueContributions": 3,
                    "totalPullRequestReviewContributions": 2,
                    "contributionCalendar": {"totalContributions": sum(x["contributionCount"] for x in days),
                                             "weeks": weeks}}
    return prof, years


# ------------------------------------------------------------ analytics -----
def build_days(years):
    days = {}
    for cc in years.values():
        for wk in cc["contributionCalendar"]["weeks"]:
            for d in wk["contributionDays"]:
                days[date.fromisoformat(d["date"])] = d["contributionCount"]
    return days


def streaks(days):
    run = longest = 0
    for d in sorted(days):
        run = run + 1 if days[d] > 0 else 0
        longest = max(longest, run)
    cur, d = 0, TODAY
    if days.get(d, 0) == 0:  # today not finished yet - don't break the streak
        d -= timedelta(days=1)
    while days.get(d, 0) > 0:
        cur += 1
        d -= timedelta(days=1)
    return cur, longest


# ------------------------------------------------------------- SVG kit ------
def level(c, mx):
    return 0 if c <= 0 else min(4, max(1, math.ceil(4 * c / mx)))


def smooth(pts, lo, hi):
    """Catmull-Rom -> cubic Bezier path through pts, clamped to [lo, hi] on y."""
    cl = lambda v: min(max(v, lo), hi)
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0, p1, p2 = pts[max(i - 1, 0)], pts[i], pts[i + 1]
        p3 = pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, cl(p1[1] + (p2[1] - p0[1]) / 6))
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, cl(p2[1] - (p3[1] - p1[1]) / 6))
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d


def dashboard(days, start, end, label, ctx, live):
    W, H = 960, 448
    cell, pitch, LX, HY = 10, 12, 56, 164
    first = start - timedelta(days=(start.weekday() + 1) % 7)
    nweeks = (end - first).days // 7 + 1
    last = min(end, TODAY)
    rng = [(d, days.get(d, 0)) for d in (start + timedelta(n) for n in range((last - start).days + 1))]
    total = sum(c for _, c in rng)
    active = sum(1 for _, c in rng if c > 0)
    best_d, best_n = max(rng, key=lambda kv: kv[1])
    run = lng = 0
    for _, c in rng:
        run = run + 1 if c > 0 else 0
        lng = max(lng, run)
    mt, wdt, wk = defaultdict(int), [0] * 7, [0] * nweeks
    for d, c in rng:
        mt[(d.year, d.month)] += c
        wdt[(d.weekday() + 1) % 7] += c
        wk[(d - first).days // 7] += c
    (by, bm), bmv = max(mt.items(), key=lambda kv: kv[1])
    top_wd = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][wdt.index(max(wdt))]
    nz = sorted(c for _, c in rng if c > 0)
    p90 = nz[int(0.9 * (len(nz) - 1))] if nz else 1

    o = ['<defs>'
         '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0b1020"/><stop offset="1" stop-color="#0d1117"/></linearGradient>'
         '<linearGradient id="acc" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#22d3ee"/><stop offset="1" stop-color="#a78bfa"/></linearGradient>'
         '<linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#22d3ee" stop-opacity=".45"/><stop offset="1" stop-color="#a78bfa" stop-opacity="0"/></linearGradient>'
         '<radialGradient id="g1"><stop offset="0" stop-color="#22d3ee" stop-opacity=".16"/><stop offset="1" stop-color="#22d3ee" stop-opacity="0"/></radialGradient>'
         '<radialGradient id="g2"><stop offset="0" stop-color="#a78bfa" stop-opacity=".18"/><stop offset="1" stop-color="#a78bfa" stop-opacity="0"/></radialGradient>'
         '<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
         '</defs>',
         f'<g font-family="{FONT}">',
         f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="18" fill="url(#bg)" stroke="#1e293b"/>',
         f'<circle cx="60" cy="40" r="220" fill="url(#g1)"/><circle cx="{W - 40}" cy="{H - 30}" r="240" fill="url(#g2)"/>']

    # header
    o.append(f'<text x="28" y="38" font-size="22" font-weight="800" fill="url(#acc)">@{esc(USER)}</text>')
    o.append(f'<text x="28" y="56" font-size="11" fill="{MUTED}">{esc(label)} · {start:%d %b %Y} → {last:%d %b %Y}</text>')
    if live:
        o.append(f'<circle cx="{W - 154}" cy="33" r="4" fill="#34d399" filter="url(#glow)"/>'
                 f'<text x="{W - 28}" y="38" font-size="12" font-weight="700" fill="#34d399" text-anchor="end">'
                 f'LIVE · {ctx["cur"]}-day streak</text>')
    o.append(f'<text x="{W - 28}" y="56" font-size="11" fill="{MUTED}" text-anchor="end">updated {NOW:%d %b %Y, %H:%M} UTC</text>')

    # KPI tiles
    tiles = [("Contributions", f"{total:,}"), ("Active days", f"{active} / {len(rng)}"),
             ("Best day", f"{best_n} · {best_d:%d %b}"), ("Longest streak", f"{lng} days"),
             ("Avg / active day", f"{total / active:.1f}" if active else "0"),
             ("Best month", f"{date(by, bm, 1):%b} · {bmv}")]
    tw, gp = 140, 14.4
    for i, (k, v) in enumerate(tiles):
        x = 28 + i * (tw + gp)
        col = PALETTE[i % 5]
        o.append(f'<rect x="{x:.1f}" y="72" width="{tw}" height="54" rx="12" fill="#ffffff" fill-opacity=".035" stroke="#ffffff" stroke-opacity=".08"/>'
                 f'<rect x="{x + 10:.1f}" y="84" width="3" height="30" rx="1.5" fill="{col}"/>'
                 f'<text x="{x + 22:.1f}" y="98" font-size="17" font-weight="700" fill="{TXT}">{esc(v)}</text>'
                 f'<text x="{x + 22:.1f}" y="115" font-size="10" fill="{MUTED}">{k}</text>')

    # heatmap
    ml, marks = None, []
    for col in range(nweeks):
        m = max(first + timedelta(days=7 * col), start).month
        if m != ml:
            marks.append((col, m))
            ml = m
    if len(marks) > 1 and marks[1][0] - marks[0][0] < 3:
        marks.pop(0)  # drop a cramped partial first month
    for col, m in marks:
        o.append(f'<text x="{LX + col * pitch}" y="{HY - 8}" font-size="10" fill="{MUTED}">{date(2000, m, 1):%b}</text>')
    for r, n in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        o.append(f'<text x="28" y="{HY + r * pitch + 9}" font-size="9" fill="{MUTED}">{n}</text>')
    for d, c in rng:
        col, row = (d - first).days // 7, (d.weekday() + 1) % 7
        lv = level(c, p90)
        glow = ' filter="url(#glow)"' if lv == 4 else ""
        plural = "s" if c != 1 else ""
        o.append(f'<rect x="{LX + col * pitch}" y="{HY + row * pitch}" width="{cell}" height="{cell}" rx="2.5" '
                 f'fill="{LEVELS[lv]}"{glow}><title>{d:%a, %d %b %Y}: {c} contribution{plural}</title></rect>')

    # weekly trend (same x-axis as the heatmap)
    top, base = 284, 366
    mx = max(wk) or 1
    o.append(f'<text x="28" y="274" font-size="10" font-weight="700" fill="{MUTED}" letter-spacing="1">WEEKLY PULSE</text>')
    for frac in (0.5, 1):
        y = base - (base - top) * frac
        o.append(f'<line x1="{LX}" y1="{y:.1f}" x2="{LX + nweeks * pitch - 2}" y2="{y:.1f}" stroke="#ffffff" stroke-opacity=".07" stroke-dasharray="3 4"/>'
                 f'<text x="{LX - 8}" y="{y + 3:.1f}" font-size="9" fill="{MUTED}" text-anchor="end">{round(mx * frac)}</text>')
    pts = [(LX + i * pitch + cell / 2, base - (base - top) * v / mx) for i, v in enumerate(wk)]
    if len(pts) > 1:
        line = smooth(pts, top, base)
        o.append(f'<path d="{line} L{pts[-1][0]:.1f},{base} L{pts[0][0]:.1f},{base} Z" fill="url(#area)"/>')
        o.append(f'<path d="{line}" fill="none" stroke="url(#acc)" stroke-width="2.4" stroke-linecap="round" filter="url(#glow)"/>')
    pk = wk.index(mx)
    px, py = pts[pk]
    o.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="#fff" stroke="#22d3ee" stroke-width="2" filter="url(#glow)"/>'
             f'<text x="{min(max(px, LX + 60), LX + nweeks * pitch - 60):.1f}" y="{max(py - 10, top - 2):.1f}" font-size="10" font-weight="700" '
             f'fill="{TXT}" text-anchor="middle">peak {mx}</text>')
    for i, (x, y) in enumerate(pts):
        ws = first + timedelta(days=7 * i)
        o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="transparent"><title>Week of {ws:%d %b %Y}: {wk[i]}</title></circle>')

    # languages donut
    rx0 = 724
    o.append(f'<rect x="{rx0 - 8}" y="138" width="224" height="248" rx="14" fill="#ffffff" fill-opacity=".035" stroke="#ffffff" stroke-opacity=".08"/>'
             f'<text x="{rx0 + 8}" y="162" font-size="10" font-weight="700" fill="{MUTED}" letter-spacing="1">LANGUAGES</text>')
    cx, cy, R = rx0 + 104, 216, 46
    C = 2 * math.pi * R
    o.append(f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="none" stroke="#151b2b" stroke-width="14"/>')
    off = 0.0
    for i, (n, p) in enumerate(ctx["langs"]):
        seg = C * p / 100
        dash = max(seg - 2, 0.5)
        o.append(f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="none" stroke="{PALETTE[i]}" stroke-width="14" '
                 f'stroke-dasharray="{dash:.2f} {C - dash:.2f}" stroke-dashoffset="{-off:.2f}" transform="rotate(-90 {cx} {cy})"><title>{esc(n)} {p:.1f}%</title></circle>')
        off += seg
    if ctx["langs"]:
        n0, p0 = ctx["langs"][0]
        o.append(f'<text x="{cx}" y="{cy + 3}" font-size="18" font-weight="800" fill="{TXT}" text-anchor="middle">{p0:.0f}%</text>'
                 f'<text x="{cx}" y="{cy + 18}" font-size="9" fill="{MUTED}" text-anchor="middle">{esc(n0[:12])}</text>')
    for i, (n, p) in enumerate(ctx["langs"]):
        y = 288 + i * 17
        o.append(f'<circle cx="{rx0 + 12}" cy="{y - 3}" r="4" fill="{PALETTE[i]}"/>'
                 f'<text x="{rx0 + 24}" y="{y}" font-size="11" fill="{TXT}">{esc(n[:16])}</text>'
                 f'<text x="{rx0 + 200}" y="{y}" font-size="11" fill="{MUTED}" text-anchor="end">{p:.1f}%</text>')

    # footer insights
    o.append(f'<line x1="28" y1="392" x2="{W - 28}" y2="392" stroke="#ffffff" stroke-opacity=".08"/>')
    o.append(f'<text x="28" y="414" font-size="11.5" fill="{MUTED}">Most active weekday <tspan fill="{TXT}" font-weight="700">{top_wd}</tspan>'
             f'   ·   Busiest month <tspan fill="{TXT}" font-weight="700">{date(by, bm, 1):%B %Y}</tspan></text>')
    o.append(f'<text x="28" y="432" font-size="11.5" fill="{MUTED}">All-time <tspan fill="{TXT}" font-weight="700">{ctx["total"]:,}</tspan> contributions   ·   '
             f'<tspan fill="{TXT}" font-weight="700">{ctx["commits"]:,}</tspan> commits   ·   <tspan fill="{TXT}" font-weight="700">{ctx["prs"]:,}</tspan> PRs   ·   '
             f'<tspan fill="{TXT}" font-weight="700">{ctx["stars"]}</tspan> stars   ·   since {ctx["since"]}</text>')
    o.append('</g>')
    body = "".join(o)
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{body}</svg>'


# ---------------------------------------------------------------- README ----
def inject(text, name, content):
    pat = re.compile(rf"(<!--START_SECTION:{name}-->)(.*?)(<!--END_SECTION:{name}-->)", re.S)
    return pat.sub(lambda m: f"{m.group(1)}\n{content}\n{m.group(3)}", text)


def main():
    print(f"{'DEMO' if DEMO else 'LIVE'} mode for @{USER}")
    prof, years = fetch_demo() if DEMO else fetch_live()
    days = build_days(years)
    cur, _ = streaks(days)
    repos = [r for r in prof["repositories"]["nodes"] if r["name"].lower() != USER.lower()]

    langs = defaultdict(int)
    for r in repos:
        if not r["isArchived"]:
            for e in r["languages"]["edges"]:
                langs[e["node"]["name"]] += e["size"]
    tot = sum(langs.values()) or 1
    ranked = sorted(langs.items(), key=lambda kv: -kv[1])
    lang_list = [(n, 100 * s / tot) for n, s in ranked[:5]]
    if len(ranked) > 5:
        lang_list.append(("Other", 100 * sum(s for _, s in ranked[5:]) / tot))

    ctx = {
        "cur": cur, "langs": lang_list, "since": prof["createdAt"][:4],
        "total": sum(c["contributionCalendar"]["totalContributions"] for c in years.values()),
        "commits": sum(c["totalCommitContributions"] for c in years.values()),
        "prs": sum(c["totalPullRequestContributions"] for c in years.values()),
        "stars": sum(r["stargazerCount"] for r in repos),
    }

    (OUT / "dashboard-last-year.svg").write_text(
        dashboard(days, TODAY - timedelta(days=364), TODAY, "Last 12 months", ctx, True))
    blocks = []
    for y in sorted(years, reverse=True):
        (OUT / f"dashboard-{y}.svg").write_text(
            dashboard(days, date(y, 1, 1), date(y, 12, 31), f"Year {y}", ctx, y == TODAY.year))
        yt = years[y]["contributionCalendar"]["totalContributions"]
        blocks.append(f'<details><summary><b>{y}</b> — {yt:,} contributions</summary><br/>'
                      f'<img src="assets/dashboard-{y}.svg" width="100%" alt="{y} dashboard"/></details>')

    if DEMO:
        print(f"Demo assets written to {OUT} (README untouched).")
        return

    rows = []
    for r in repos[:6]:
        lang = r["primaryLanguage"]["name"] if r["primaryLanguage"] else "—"
        rows.append(f'<tr><td><a href="{r["url"]}"><b>{esc(r["name"])}</b></a></td><td>{esc(r["description"] or "—")}</td>'
                    f'<td><code>{esc(lang)}</code></td><td>⭐ {r["stargazerCount"]}</td><td>{r["pushedAt"][:10]}</td></tr>')
    repo_html = ('<table><tr><th>Repository</th><th>About</th><th>Language</th><th>Stars</th><th>Last push</th></tr>'
                 + "".join(rows) + "</table>")
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    text = inject(text, "repos", repo_html)
    text = inject(text, "years", "\n".join(blocks))
    text = inject(text, "updated", f"<sub>🤖 auto-generated · last refresh {NOW:%d %b %Y, %H:%M} UTC</sub>")
    readme.write_text(text, encoding="utf-8")
    print("README + assets updated.")


if __name__ == "__main__":
    main()
