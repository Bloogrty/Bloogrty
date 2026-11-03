"""Refreshes the dynamic parts of the profile README.

Fills two marked sections:
  <!-- TERMINAL:START --> ... <!-- TERMINAL:END -->
  <!-- PROJECTS:START --> ... <!-- PROJECTS:END -->
"""
import json
import os
import re
import urllib.request
from datetime import datetime, timezone

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


if __name__ == "__main__":
    main()
