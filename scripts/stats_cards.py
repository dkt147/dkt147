"""Generate self-hosted GitHub stats + top-languages SVG cards.

Runs in GitHub Actions with the built-in GITHUB_TOKEN, so it never hits the
rate limits of public shared card services.
Usage: python scripts/stats_cards.py <username> <out_dir>
"""
import json
import os
import sys
import urllib.request
from html import escape

USER = sys.argv[1]
OUT = sys.argv[2]
TOKEN = os.environ["GITHUB_TOKEN"]

BG, BORDER, TITLE, TEXT, ICON, MUTED = "#1a1b27", "#2a2e45", "#70a5fd", "#c0caf5", "#bf91f3", "#565f89"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif"


def gql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if "errors" in data:
        raise SystemExit(f"GraphQL error: {data['errors']}")
    return data["data"]


REPOS_Q = """
query($login:String!, $after:String) {
  user(login:$login) {
    name
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    contributionsCollection { totalCommitContributions restrictedContributionsCount }
    repositoriesContributedTo(contributionTypes:[COMMIT, PULL_REQUEST, ISSUE]) { totalCount }
    repositories(first:100, after:$after, ownerAffiliations:OWNER, isFork:false) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first:10, orderBy:{field:SIZE, direction:DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}"""


def collect():
    after, stars, langs, base = None, 0, {}, None
    while True:
        u = gql(REPOS_Q, {"login": USER, "after": after})["user"]
        base = base or u
        repos = u["repositories"]
        for n in repos["nodes"]:
            stars += n["stargazerCount"]
            for e in n["languages"]["edges"]:
                name = e["node"]["name"]
                size, color = langs.get(name, (0, e["node"]["color"] or "#888"))
                langs[name] = (size + e["size"], color)
        if not repos["pageInfo"]["hasNextPage"]:
            break
        after = repos["pageInfo"]["endCursor"]
    cc = base["contributionsCollection"]
    return {
        "name": base["name"] or USER,
        "stars": stars,
        "commits": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
        "prs": base["pullRequests"]["totalCount"],
        "issues": base["issues"]["totalCount"],
        "contributed": base["repositoriesContributedTo"]["totalCount"],
        "repos": base["repositories"]["totalCount"],
        "followers": base["followers"]["totalCount"],
    }, langs


def fmt(n):
    return f"{n/1000:.1f}k" if n >= 1000 else str(n)


def card(w, h, title, body):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
<style>
.t{{font:600 18px {FONT};fill:{TITLE}}} .l{{font:400 14px {FONT};fill:{TEXT}}} .v{{font:700 14px {FONT};fill:{TEXT}}}
.s{{font:400 12px {FONT};fill:{MUTED}}}
.row{{opacity:0;animation:in .5s ease-out forwards}}
@keyframes in{{from{{opacity:0;transform:translateX(-8px)}}to{{opacity:1;transform:translateX(0)}}}}
.bar{{transform-origin:left;transform:scaleX(0);animation:grow 1s ease-out forwards}}
@keyframes grow{{to{{transform:scaleX(1)}}}}
</style>
<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="10" fill="{BG}" stroke="{BORDER}"/>
<text class="t" x="25" y="35">{escape(title)}</text>
{body}
</svg>"""


def stats_svg(s):
    rows = [
        ("★", "Total stars earned", s["stars"]),
        ("⎇", "Commits (this year)", s["commits"]),
        ("⇄", "Pull requests", s["prs"]),
        ("◎", "Issues", s["issues"]),
        ("⌂", "Public repositories", s["repos"]),
        ("✦", "Contributed to", s["contributed"]),
    ]
    body = ""
    for i, (icon, label, val) in enumerate(rows):
        y = 70 + i * 26
        body += (f'<g class="row" style="animation-delay:{0.15*i:.2f}s">'
                 f'<text x="25" y="{y}" style="font:700 15px {FONT};fill:{ICON}">{icon}</text>'
                 f'<text class="l" x="50" y="{y}">{label}:</text>'
                 f'<text class="v" x="330" y="{y}" text-anchor="end">{fmt(val)}</text></g>')
    return card(360, 235, f"{s['name']}'s GitHub Stats", body)


def langs_svg(langs, top=8):
    items = sorted(langs.items(), key=lambda kv: kv[1][0], reverse=True)[:top]
    total = sum(v[0] for _, v in items) or 1
    # stacked bar
    x, bar = 25.0, ""
    for name, (size, color) in items:
        w = 310 * size / total
        bar += f'<rect x="{x:.2f}" y="52" width="{w:.2f}" height="10" fill="{color}"/>'
        x += w
    body = (f'<clipPath id="r"><rect x="25" y="52" width="310" height="10" rx="5"/></clipPath>'
            f'<g class="bar" clip-path="url(#r)">{bar}</g>')
    for i, (name, (size, color)) in enumerate(items):
        col, row = i % 2, i // 2
        cx, cy = 30 + col * 160, 92 + row * 26
        body += (f'<g class="row" style="animation-delay:{0.1*i+0.4:.2f}s">'
                 f'<circle cx="{cx}" cy="{cy-4}" r="5" fill="{color}"/>'
                 f'<text class="l" x="{cx+12}" y="{cy}">{escape(name)}</text>'
                 f'<text class="s" x="{cx+140}" y="{cy}" text-anchor="end">{100*size/total:.1f}%</text></g>')
    return card(360, 235, "Most Used Languages", body)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    s, langs = collect()
    with open(os.path.join(OUT, "stats.svg"), "w", encoding="utf-8") as f:
        f.write(stats_svg(s))
    with open(os.path.join(OUT, "top-langs.svg"), "w", encoding="utf-8") as f:
        f.write(langs_svg(langs))
    print(json.dumps(s), len(langs), "languages")
