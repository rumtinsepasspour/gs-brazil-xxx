# Germany monitor

Each morning this reads your Google Alerts feeds, has a Claude model translate
and score each new German item against `relevance.md`, and rebuilds the
dashboard page at `docs/index.html`, which GitHub Pages serves.

## Files you edit

| File | What it controls |
|---|---|
| `feeds.txt` | Which Google Alerts feeds are read. One address per line. |
| `relevance.md` | How items are scored and tagged. Plain English. |

Everything else runs on its own.

## Set-up (once)

Replace `YOUR-USERNAME` and `REPO-NAME` throughout. Pick a repo name that is
hard to guess (for example `gm-4k7q2x`), because it forms part of the
dashboard's address.

**1. Create the repo and push these files**

Create an empty private repo at https://github.com/new (no README, no
.gitignore). Then, in a terminal:

```
cd ~/Downloads
unzip germany-monitor.zip
cd germany-monitor
git init -b main
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR-USERNAME/REPO-NAME.git
git push -u origin main
```

**2. Add the Anthropic API key**

On GitHub: repo → Settings → Secrets and variables → Actions → New repository
secret. Name it exactly `ANTHROPIC_API_KEY` and paste the key as the value.

Or from the terminal, if you have the GitHub CLI (it prompts for the key):

```
gh secret set ANTHROPIC_API_KEY --repo YOUR-USERNAME/REPO-NAME
```

**3. Turn on GitHub Pages**

Repo → Settings → Pages → Source: "Deploy from a branch" → Branch: `main`,
folder: `/docs` → Save.

The dashboard is then at `https://YOUR-USERNAME.github.io/REPO-NAME/`.

**4. Add your feeds**

Edit `feeds.txt` on GitHub (open the file, click the pencil, paste the
addresses, commit), or locally:

```
cd ~/Downloads/germany-monitor
open -e feeds.txt
git add feeds.txt
git commit -m "Add feeds"
git push
```

**5. Run it once by hand**

Repo → Actions → Daily update → Run workflow. Or:

```
gh workflow run daily.yml --repo YOUR-USERNAME/REPO-NAME
```

After that it runs daily at 19:00 UTC (06:00 in Canberra during daylight
saving, 05:00 otherwise). To change the time, edit the `cron` line in
`.github/workflows/daily.yml`.

## Changing the relevance criteria

Edit `relevance.md` and commit. The next run uses it. Items already on the
dashboard keep their old scores.

## Running it on your own machine (optional)

```
cd ~/Downloads/germany-monitor
pip3 install -r requirements.txt
export ANTHROPIC_API_KEY="paste-your-key-here"
python3 pipeline.py
open docs/index.html
```

## Settings

Set these as environment variables in `.github/workflows/daily.yml`, next to
`ANTHROPIC_API_KEY`:

- `MODEL`: the Claude model used for scoring. Default `claude-haiku-5-5`.
- `KEEP_DAYS`: how many days of items stay on the dashboard. Default `30`.

## If something goes wrong

- **Items show a "?" and German text:** scoring failed for them (missing or
  invalid key, wrong model name, or an API error). They are retried on the
  next run. The run's log under Actions shows the error.
- **"nothing from ..." in the log:** that feed returned no entries. Open the
  feed address in a browser to check it still works.
- **The page does not update:** check the latest run under Actions for a red
  cross and open it to read the log.
