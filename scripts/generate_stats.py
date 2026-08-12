import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

GRAPHQL_URL = "https://api.github.com/graphql"
ASCII_RAMP = " .`:-=+*cs#%@"

def fetch_graphql(query, variables, token):
    headers = {
        "Authorization": f"bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "GitHub-Profile-Stats-Generator"
    }
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(GRAPHQL_URL, data=payload, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "errors" in data:
                print("GraphQL Errors:", data["errors"])
                return None
            return data.get("data")
    except Exception as e:
        print("HTTP Error during GraphQL request:", e)
        return None

def get_stats_data(username, token):
    # Pin window to whole UTC days (today - 364 days 00:00:00Z to today 23:59:59Z)
    now_utc = datetime.now(timezone.utc)
    to_dt = datetime(now_utc.year, now_utc.month, now_utc.day, 23, 59, 59, tzinfo=timezone.utc)
    from_dt = (to_dt - timedelta(days=364)).replace(hour=0, minute=0, second=0)

    from_iso = from_dt.isoformat()
    to_iso = to_dt.isoformat()

    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          totalIssueContributions
          totalPullRequestContributions
          totalPullRequestReviewContributions
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                contributionCount
                date
              }
            }
          }
        }
        repositories(first: 100, privacy: PUBLIC, isFork: false, orderBy: {field: UPDATED_AT, direction: DESC}) {
          nodes {
            name
            languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
              edges {
                size
                node {
                  name
                  color
                }
              }
            }
          }
        }
      }
    }
    """
    
    variables = {"login": username, "from": from_iso, "to": to_iso}
    return fetch_graphql(query, variables, token)

def generate_mock_data():
    """Fallback mock data for local generation when no token is present."""
    weeks = []
    start_date = datetime.now(timezone.utc) - timedelta(days=364)
    curr = start_date
    for w in range(53):
        days = []
        for d in range(7):
            cnt = (w * 3 + d * 5) % 17
            days.append({"contributionCount": cnt, "date": curr.strftime("%Y-%m-%d")})
            curr += timedelta(days=1)
        weeks.append({"contributionDays": days})
    
    return {
        "user": {
            "contributionsCollection": {
                "totalCommitContributions": 412,
                "totalIssueContributions": 28,
                "totalPullRequestContributions": 64,
                "totalPullRequestReviewContributions": 19,
                "contributionCalendar": {
                    "totalContributions": 523,
                    "weeks": weeks
                }
            },
            "repositories": {
                "nodes": [
                    {
                        "name": "sample-repo-1",
                        "languages": {
                            "edges": [
                                {"size": 45000, "node": {"name": "Python", "color": "#3572A5"}},
                                {"size": 15000, "node": {"name": "TypeScript", "color": "#3178c6"}}
                            ]
                        }
                    },
                    {
                        "name": "sample-repo-2",
                        "languages": {
                            "edges": [
                                {"size": 30000, "node": {"name": "Rust", "color": "#dea584"}},
                                {"size": 10000, "node": {"name": "Python", "color": "#3572A5"}}
                            ]
                        }
                    }
                ]
            }
        }
    }

def render_stats_svg(total_contribs, commits, prs, issues, reviews):
    w, h = 420, 180
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <style>
    .bg {{ fill: #0d1117; rx: 8px; stroke: #30363d; stroke-width: 1px; }}
    .title {{ font-family: monospace; font-size: 14px; fill: #58a6ff; font-weight: bold; }}
    .label {{ font-family: monospace; font-size: 12px; fill: #8b949e; }}
    .val {{ font-family: monospace; font-size: 14px; fill: #c9d1d9; font-weight: bold; }}
  </style>
  <rect width="{w}" height="{h}" class="bg"/>
  <text x="20" y="35" class="title">KEY METRICS &amp; ACTIVITY</text>
  <line x1="20" y1="45" x2="{w-20}" y2="45" stroke="#30363d" stroke-width="1"/>
  
  <text x="20" y="75" class="label">Total Contributions:</text>
  <text x="220" y="75" class="val">{total_contribs}</text>

  <text x="20" y="100" class="label">Commits:</text>
  <text x="220" y="100" class="val">{commits}</text>

  <text x="20" y="125" class="label">Pull Requests / Reviews:</text>
  <text x="220" y="125" class="val">{prs} / {reviews}</text>

  <text x="20" y="150" class="label">Issues Logged:</text>
  <text x="220" y="150" class="val">{issues}</text>
</svg>"""
    return svg

def render_streak_svg(weeks):
    # Calculate current and longest streak
    all_days = []
    for w in weeks:
        for d in w["contributionDays"]:
            all_days.append(d)
    
    current_streak = 0
    longest_streak = 0
    temp_streak = 0

    for d in all_days:
        if d["contributionCount"] > 0:
            temp_streak += 1
            if temp_streak > longest_streak:
                longest_streak = temp_streak
        else:
            temp_streak = 0

    # Current streak looking backwards from today
    for d in reversed(all_days):
        if d["contributionCount"] > 0:
            current_streak += 1
        else:
            break

    w, h = 420, 140
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <style>
    .bg {{ fill: #0d1117; rx: 8px; stroke: #30363d; stroke-width: 1px; }}
    .title {{ font-family: monospace; font-size: 14px; fill: #58a6ff; font-weight: bold; }}
    .label {{ font-family: monospace; font-size: 12px; fill: #8b949e; }}
    .val {{ font-family: monospace; font-size: 20px; fill: #3fb950; font-weight: bold; }}
  </style>
  <rect width="{w}" height="{h}" class="bg"/>
  <text x="20" y="35" class="title">COMMIT STREAKS</text>
  <line x1="20" y1="45" x2="{w-20}" y2="45" stroke="#30363d" stroke-width="1"/>
  
  <text x="30" y="75" class="label">Current Streak</text>
  <text x="30" y="105" class="val">{current_streak} days</text>

  <text x="230" y="75" class="label">Longest Streak</text>
  <text x="230" y="105" class="val">{longest_streak} days</text>
</svg>"""
    return svg

def render_langs_svg(repos):
    lang_bytes = {}
    lang_colors = {}
    for repo in repos:
        for edge in repo.get("languages", {}).get("edges", []):
            name = edge["node"]["name"]
            color = edge["node"].get("color") or "#58a6ff"
            size = edge["size"]
            lang_bytes[name] = lang_bytes.get(name, 0) + size
            lang_colors[name] = color

    total_bytes = sum(lang_bytes.values()) or 1
    sorted_langs = sorted(lang_bytes.items(), key=lambda x: x[1], reverse=True)[:5]

    w, h = 420, 180
    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '  <style>',
        '    .bg { fill: #0d1117; rx: 8px; stroke: #30363d; stroke-width: 1px; }',
        '    .title { font-family: monospace; font-size: 14px; fill: #58a6ff; font-weight: bold; }',
        '    .label { font-family: monospace; font-size: 12px; fill: #c9d1d9; }',
        '    .pct { font-family: monospace; font-size: 12px; fill: #8b949e; }',
        '  </style>',
        f'  <rect width="{w}" height="{h}" class="bg"/>',
        '  <text x="20" y="35" class="title">TOP LANGUAGES</text>',
        f'  <line x1="20" y1="45" x2="{w-20}" y2="45" stroke="#30363d" stroke-width="1"/>'
    ]

    y_off = 70
    for name, b_count in sorted_langs:
        pct = (b_count / total_bytes) * 100
        color = lang_colors.get(name, "#58a6ff")
        bar_w = int((w - 200) * (pct / 100))
        svg_lines.append(f'  <circle cx="30" cy="{y_off-4}" r="5" fill="{color}"/>')
        svg_lines.append(f'  <text x="45" y="{y_off}" class="label">{name}</text>')
        svg_lines.append(f'  <rect x="150" y="{y_off-12}" width="{bar_w}" height="10" fill="{color}" rx="3"/>')
        svg_lines.append(f'  <text x="{160+bar_w}" y="{y_off}" class="pct">{pct:.1f}%</text>')
        y_off += 22

    svg_lines.append('</svg>')
    return "\n".join(svg_lines)

def render_year_svg(weeks):
    # Represent the full year activity as ASCII characters grid in an SVG
    ramp_len = len(ASCII_RAMP)
    max_count = 1
    for w in weeks:
        for d in w["contributionDays"]:
            if d["contributionCount"] > max_count:
                max_count = d["contributionCount"]

    w, h = 640, 150
    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '  <style>',
        '    .bg { fill: #0d1117; rx: 8px; stroke: #30363d; stroke-width: 1px; }',
        '    .title { font-family: monospace; font-size: 14px; fill: #58a6ff; font-weight: bold; }',
        '    .ascii-grid { font-family: monospace; font-size: 11px; fill: #3fb950; xml:space: preserve; white-space: pre; }',
        '  </style>',
        f'  <rect width="{w}" height="{h}" class="bg"/>',
        '  <text x="20" y="30" class="title">YEAR ACTIVITY MATRIX (ASCII GRID)</text>',
        f'  <line x1="20" y1="40" x2="{w-20}" y2="40" stroke="#30363d" stroke-width="1"/>'
    ]

    # Convert 52/53 weeks x 7 days to ASCII rows
    # 7 rows (Sunday to Saturday)
    for day_idx in range(7):
        row_str = ""
        for week in weeks:
            days = week["contributionDays"]
            if day_idx < len(days):
                cnt = days[day_idx]["contributionCount"]
                idx = int((cnt / max_count) * (ramp_len - 1)) if max_count > 0 else 0
                idx = max(0, min(ramp_len - 1, idx))
                row_str += ASCII_RAMP[idx]
            else:
                row_str += " "
        
        escaped_row = row_str.replace(" ", "&#160;")
        y_pos = 60 + day_idx * 12
        svg_lines.append(f'  <text x="20" y="{y_pos}" class="ascii-grid">{escaped_row}</text>')

    svg_lines.append('</svg>')
    return "\n".join(svg_lines)

def main():
    token = os.environ.get("GITHUB_TOKEN")
    username = os.environ.get("GH_LOGIN", "octocat")

    data = None
    if token:
        print(f"Fetching GitHub GraphQL stats for user '{username}'...")
        data = get_stats_data(username, token)
    
    if not data or "user" not in data or not data["user"]:
        print("Using fallback mock data for SVG generation...")
        data = generate_mock_data()

    user = data["user"]
    contribs = user["contributionsCollection"]
    calendar = contribs["contributionCalendar"]
    weeks = calendar["weeks"]

    # Write SVGs
    stats_svg = render_stats_svg(
        calendar["totalContributions"],
        contribs["totalCommitContributions"],
        contribs["totalPullRequestContributions"],
        contribs["totalIssueContributions"],
        contribs["totalPullRequestReviewContributions"]
    )
    with open("stats.svg", "w", encoding="utf-8") as f:
        f.write(stats_svg)

    streak_svg = render_streak_svg(weeks)
    with open("streak.svg", "w", encoding="utf-8") as f:
        f.write(streak_svg)

    repos = user.get("repositories", {}).get("nodes", [])
    langs_svg = render_langs_svg(repos)
    with open("langs.svg", "w", encoding="utf-8") as f:
        f.write(langs_svg)

    year_svg = render_year_svg(weeks)
    with open("year.svg", "w", encoding="utf-8") as f:
        f.write(year_svg)

    print("Generated stat graphics: stats.svg, streak.svg, langs.svg, year.svg")

if __name__ == "__main__":
    main()
