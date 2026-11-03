"""Refreshes the dynamic parts of the profile README.

Fills two marked sections:
  <!-- TERMINAL:START --> ... <!-- TERMINAL:END -->
  <!-- PROJECTS:START --> ... <!-- PROJECTS:END -->

and draws the stats cards into assets/ (stats.svg, langs.svg, streak.svg),
so the README doesn't depend on third-party stats services staying up.
"""
import json
import os
import re
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import escape

USER = os.environ.get("GH_USER", "bloogrty")
TOKEN = os.environ.get("GITHUB_TOKEN")
START = datetime(2023, 1, 1, tzinfo=timezone.utc)
MAX_PROJECTS = 8

# repos that should not show up in "recently worked on"
SKIP = {
    USER.lower(),
    "leetcode__python",
    "codewars__python",
    "leetcode-30-days",
    "codewars-s2",
}


def api(path):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(f"https://api.github.com{path}", headers=headers)
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def graphql(query, **variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    headers = {"Authorization": f"Bearer {TOKEN}", "User-Agent": USER,
               "Content-Type": "application/json"}
    req = urllib.request.Request("https://api.github.com/graphql", data=body, headers=headers)
    with urllib.request.urlopen(req) as r:
        out = json.load(r)
    if "errors" in out:
        raise RuntimeError(out["errors"])
    return out["data"]


STATS_QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    contributionsCollection {
      contributionYears
      totalCommitContributions
      restrictedContributionsCount
    }
    pullRequests { totalCount }
    issues { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

CALENDAR_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
  }
}
"""


def fetch_stats():
    u = graphql(STATS_QUERY, login=USER)["user"]
    cc = u["contributionsCollection"]

    langs = {}
    for repo in u["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            name = e["node"]["name"]
            size, _ = langs.get(name, (0, None))
            langs[name] = (size + e["size"], e["node"]["color"] or "#8b949e")

    days = {}
    for year in cc["contributionYears"]:
        cal = graphql(CALENDAR_QUERY, login=USER,
                      **{"from": f"{year}-01-01T00:00:00Z", "to": f"{year}-12-31T23:59:59Z"})
        for week in cal["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]:
            for d in week["contributionDays"]:
                days[date.fromisoformat(d["date"])] = d["contributionCount"]

    return {
        "stars": sum(r["stargazerCount"] for r in u["repositories"]["nodes"]),
        "commits": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
        "prs": u["pullRequests"]["totalCount"],
        "issues": u["issues"]["totalCount"],
        "repos": u["repositories"]["totalCount"],
        "followers": u["followers"]["totalCount"],
        "langs": sorted(langs.items(), key=lambda kv: -kv[1][0]),
        "days": days,
    }


def streaks(days):
    today = datetime.now(timezone.utc).date()
    active = sorted(d for d, n in days.items() if n and d <= today)
    longest, run, prev = 0, 0, None
    for d in active:
        run = run + 1 if prev and d - prev == timedelta(days=1) else 1
        longest = max(longest, run)
        prev = d
    # today not having a contribution yet doesn't break the streak
    current, d = 0, today if days.get(today) else today - timedelta(days=1)
    while days.get(d):
        current += 1
        d -= timedelta(days=1)
    return {
        "total": sum(n for d, n in days.items() if d <= today),
        "since": active[0] if active else today,
        "current": current,
        "longest": longest,
    }


# colors follow GitHub's own palette so the cards blend into both themes
CARD_STYLE = """<style>
  .title { font: 600 16px 'Segoe UI', Ubuntu, sans-serif; fill: #0969da; }
  .label { font: 400 13px 'Segoe UI', Ubuntu, sans-serif; fill: #57606a; }
  .value { font: 600 13px 'Segoe UI', Ubuntu, sans-serif; fill: #1f2328; }
  .big   { font: 700 26px 'Segoe UI', Ubuntu, sans-serif; fill: #1f2328; }
  .rule  { stroke: #d0d7de; }
  @media (prefers-color-scheme: dark) {
    .title { fill: #58a6ff; }
    .label { fill: #8b949e; }
    .value, .big { fill: #e6edf3; }
    .rule  { stroke: #30363d; }
  }
</style>"""


def svg(width, height, body, label):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(label)}">\n'
            f"{CARD_STYLE}\n{body}\n</svg>\n")


def stats_card(s):
    rows = [("total stars", s["stars"]), ("commits", s["commits"]),
            ("pull requests", s["prs"]), ("issues", s["issues"]),
            ("public repos", s["repos"])]
    body = [f'<text x="20" y="32" class="title">{escape(USER)}\'s github stats</text>']
    for i, (label, value) in enumerate(rows):
        y = 62 + i * 22
        body.append(f'<text x="20" y="{y}" class="label">{label}</text>')
        body.append(f'<text x="300" y="{y}" class="value" text-anchor="end">{value:,}</text>')
    return svg(320, 165, "\n".join(body), "github stats")


def langs_card(s, top=6):
    langs = s["langs"][:top]
    total = sum(size for _, (size, _) in langs) or 1
    body = ['<text x="20" y="32" class="title">top languages</text>',
            '<clipPath id="bar"><rect x="20" y="46" width="260" height="8" rx="4"/></clipPath>',
            '<g clip-path="url(#bar)">']
    x = 20.0
    for name, (size, color) in langs:
        w = 260 * size / total
        body.append(f'<rect x="{x:.2f}" y="46" width="{w:.2f}" height="8" fill="{color}"/>')
        x += w
    body.append("</g>")
    for i, (name, (size, color)) in enumerate(langs):
        cx, cy = 20 + (i % 2) * 135, 80 + (i // 2) * 24
        body.append(f'<circle cx="{cx + 5}" cy="{cy - 4}" r="5" fill="{color}"/>')
        body.append(f'<text x="{cx + 16}" y="{cy}" class="label">{escape(name)} '
                    f'<tspan class="value">{size / total:.1%}</tspan></text>')
    return svg(300, 165, "\n".join(body), "top languages")


def streak_card(st):
    cols = [
        (f"{st['total']:,}", "total contributions", f"since {st['since']:%b %d, %Y}"),
        (str(st["current"]), "current streak", f"{st['current']} day{'s' if st['current'] != 1 else ''}"),
        (str(st["longest"]), "longest streak", f"{st['longest']} day{'s' if st['longest'] != 1 else ''}"),
    ]
    body = []
    for i, (big, label, sub) in enumerate(cols):
        cx = 82 + i * 165
        body.append(f'<text x="{cx}" y="70" class="big" text-anchor="middle">{big}</text>')
        body.append(f'<text x="{cx}" y="100" class="title" text-anchor="middle">{label}</text>')
        body.append(f'<text x="{cx}" y="124" class="label" text-anchor="middle">{sub}</text>')
        if i:
            body.append(f'<line x1="{cx - 82}" y1="35" x2="{cx - 82}" y2="135" class="rule"/>')
    return svg(495, 165, "\n".join(body), "contribution streak")


def write_cards():
    if not TOKEN:
        print("no GITHUB_TOKEN, skipping stats cards")
        return
    s = fetch_stats()
    os.makedirs("assets", exist_ok=True)
    cards = {"stats.svg": stats_card(s), "langs.svg": langs_card(s),
             "streak.svg": streak_card(streaks(s["days"]))}
    for name, content in cards.items():
        with open(os.path.join("assets", name), "w", encoding="utf-8") as f:
            f.write(content)


def ago(iso):
    then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    secs = int((datetime.now(timezone.utc) - then).total_seconds())
    for unit, size in (("year", 31536000), ("month", 2592000), ("day", 86400),
                       ("hour", 3600), ("minute", 60)):
        if secs >= size:
            n = secs // size
            return f"{n} {unit}{'s' if n > 1 else ''} ago"
    return "just now"


def uptime():
    now = datetime.now(timezone.utc)
    months = (now.year - START.year) * 12 + now.month - START.month
    y, m = divmod(months, 12)
    parts = []
    if y:
        parts.append(f"{y} year{'s' if y > 1 else ''}")
    if m:
        parts.append(f"{m} month{'s' if m > 1 else ''}")
    return ", ".join(parts) or "a few days"


def replace(text, tag, body):
    pattern = re.compile(rf"(<!-- {tag}:START -->).*?(<!-- {tag}:END -->)", re.S)
    return pattern.sub(lambda m: f"{m.group(1)}\n{body}\n{m.group(2)}", text)


def main():
    repos = api(f"/users/{USER}/repos?per_page=100&sort=pushed")
    repos = [r for r in repos if not r["fork"] and not r["archived"]]
    projects = [r for r in repos if r["name"].lower() not in SKIP]
    latest = projects[0] if projects else None

    terminal = [
        "```console",
        "$ whoami",
        USER,
        "",
        "$ uptime",
        f"up {uptime()}, still building...",
        "",
        "$ ls projects/ | wc -l",
        str(len(projects)),
        "",
        "$ cat motivation.txt",
        "if it works, don't touch it.",
        "if it doesn't, git blame.",
        "",
        "$ echo $MOOD",
        "coffee && code",
    ]
    if latest:
        terminal += [
            "",
            "$ git log -1 --oneline",
            f"last push: {latest['name']} ({ago(latest['pushed_at'])})",
        ]
    terminal.append("```")

    rows = ["| project | what it is | lang | updated |", "| --- | --- | --- | --- |"]
    for r in projects[:MAX_PROJECTS]:
        desc = (r["description"] or "_no description yet_").replace("|", "\\|")
        lang = r["language"] or "-"
        rows.append(f"| [{r['name']}]({r['html_url']}) | {desc} | {lang} | {ago(r['pushed_at'])} |")
    rows.append("")
    rows.append(f"<sub>last refreshed {datetime.now(timezone.utc):%Y-%m-%d} · "
                f"[see all repos](https://github.com/{USER}?tab=repositories)</sub>")

    with open("README.md", encoding="utf-8") as f:
        text = f.read()
    new = replace(text, "TERMINAL", "\n".join(terminal))
    new = replace(new, "PROJECTS", "\n".join(rows))
    if new != text:
        with open("README.md", "w", encoding="utf-8") as f:
            f.write(new)
        print("README updated")
    else:
        print("no changes")
    write_cards()


if __name__ == "__main__":
    main()
