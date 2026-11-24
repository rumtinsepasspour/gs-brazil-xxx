# Germany monitor

A daily news dashboard for Rumtin Sepasspour (Global Shield). It reads Google
Alerts RSS feeds on German civil defence and critical infrastructure policy,
has a Claude model translate and score each item, and publishes one HTML page.

## How it runs

1. GitHub Actions runs `pipeline.py` on a schedule (`.github/workflows/daily.yml`,
   every 2 hours at :17 past the hour, plus manual runs).
2. `pipeline.py` reads `feeds.txt`, fetches new items, calls the Anthropic API,
   stores everything in `data/items.json`, and renders `docs/index.html` from
   `template.html`.
3. The workflow commits `data/` and `docs/` back to the repo.
4. Netlify watches the repo and publishes the `docs/` folder. GitHub Pages is
   not used (free plan, private repo).

Repo: `rumtinsepasspour/gs-gm-xxx` (private). Local copy: `~/Desktop/germany-monitor`.

## Files

| File | Purpose |
|---|---|
| `pipeline.py` | Fetch, translate, score, render, post to Slack |
| `template.html` | The whole dashboard: HTML, CSS and JavaScript in one file. Data is injected at `/*__DATA__*/null` |
| `feeds.txt` | Feed addresses, `address \| label`. Feeds under `[wider]` are the news-alert stream; everything else is core |
| `relevance.md` | Rumtin's scoring criteria for core items (score 3/2/1/0 and topic tags). He edits this himself |
| `relevance-news.md` | Rumtin's criteria for scoring news alerts High/Medium/Low. He edits this himself |
| `data/items.json` | Item store. Written by the workflow; do not hand-edit |
| `docs/index.html` | Generated page. Written by the workflow; do not hand-edit |

## Two streams

- **Core** ("Policy monitor" on the dashboard): scored 3/2/1/0, shown as
  High/Medium/Low/Ignored with coloured boxes, with an English headline,
  summary and tag. Kept 30 days. New score-3 items are posted to Slack.
- **Wider** ("News alerts"): general alerts. Headline translated and scored
  High/Medium/Low against `relevance-news.md`. No summary or tag. Kept 7 days.
  Never posted to Slack.

"Highlights" at the top shows the ten most recent core highs and high-level
news alerts together.

Each item is processed once. Changing a criteria file affects new items only.

## Deploying a change

The workflow commits to the repo on every run, so always pull first.

```
cd ~/Desktop/germany-monitor
git pull
git add <changed files>
git commit -m "<what changed>"
git push
gh workflow run daily.yml --repo rumtinsepasspour/gs-gm-xxx
```

The page only changes after a workflow run, because `docs/index.html` is
rebuilt from `template.html` during the run. Netlify republishes about a
minute later.

To see what a run did:

```
gh run view $(gh run list --repo rumtinsepasspour/gs-gm-xxx --workflow daily.yml --limit 1 --json databaseId --jq '.[0].databaseId') --repo rumtinsepasspour/gs-gm-xxx --log | grep -E "Reading|new|nothing|Scoring|scored|handled|Slack|failed|Done"
```

Do not push while a run is in progress; the run's own commit will collide.

## Testing a template change locally

There is no test suite. To preview `template.html`, render it with sample
items and open the result in a browser:

```
python3 -c "import json, pipeline; pipeline.OUT = pipeline.ROOT / 'preview.html'; items = json.load(open('data/items.json')); pipeline.render(items, set())"
open preview.html
```

Delete `preview.html` afterwards; do not commit it.

## Secrets

Stored as GitHub Actions secrets, never in files or chat:

- `ANTHROPIC_API_KEY` (set)
- `SLACK_WEBHOOK_URL` (not set yet; Slack posting stays dormant until it is)

## How Rumtin wants to work

- Propose a change and get his approval before building it. Do not add
  features he did not ask for.
- When he must run something himself, give the exact commands.
- Write plainly and briefly. No filler, no flattery.
- Give an English gloss for every German term.
- He is not a developer. Explain in terms of what he will see, not how the
  code works.

## Design decisions already made

- Warm cream page background (#f7f3ec); panels are white. No dark mode.
- Importance is shown by coloured boxes, not numbers.
- Topic tags in rounded pills; topics filtered by tickboxes.
- Summaries show on High items only; Medium and Low fold them away.
- Headlines open the page through Google Translate; "Open original source"
  opens the untranslated page.
- Opened items are dimmed (remembered per browser). There is no
  "mark read/unread" control; he asked for it to be removed.
- Days are collapsible; the newest day starts open.
- The page is unlisted, not password-protected: `noindex` and
  `no-referrer` meta tags must stay.

## Open items

- Scheduled runs: the scheduler was reset (disable/enable via API) in Nov 2026.
  Confirm runs with `schedule` event appear in `gh run list` after the next
  automatic firing.
- Slack: he needs to create an incoming webhook and set `SLACK_WEBHOOK_URL`.
- Proposed, not approved: fetching article text to write a 150-word English
  digest shown inside the dashboard, which would also improve scoring.
- Proposed, not built: grouping near-identical stories from different outlets.
- He has not yet created the extra KRITIS alerts (identification ordinance,
  criticality threshold, national risk analyses, resilience strategy, CER
  directive, AG KRITIS, DIHK).
- The GitHub workflow uses `actions/checkout@v4` and `actions/setup-python@v5`,
  which print a Node deprecation notice. Harmless; bump when convenient.
