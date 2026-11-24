#!/bin/bash
# run_all.sh — daily orchestration for Germany monitors
set -uo pipefail

PARENT="$(cd "$(dirname "$0")" && pwd)"
DASHBOARD="$PARENT/germany-monitor"
GOVDOCS="$PARENT/govdocs"
LOGS="$PARENT/logs"
LOG="$LOGS/$(date +%Y-%m-%d_%H%M).log"

mkdir -p "$LOGS" "$DASHBOARD/docs/govdocs"
exec > >(tee -a "$LOG") 2>&1

echo "=== Run started $(date) ==="

if [ -f "$HOME/.govdocs_de.env" ]; then
  set -a; source "$HOME/.govdocs_de.env"; set +a
  echo "  API key loaded from ~/.govdocs_de.env"
else
  echo "  WARNING: ~/.govdocs_de.env not found — govdocs translate step will fail"
fi

echo "--- Pull germany-monitor ---"
cd "$DASHBOARD"
git pull && echo "  up to date" || echo "  git pull failed, continuing"

echo "--- govdocs morning ---"
cd "$GOVDOCS"
./venv/bin/python govdocs.py morning \
  && echo "  govdocs done" \
  || echo "  govdocs morning failed, continuing"

echo "--- Build search.json ---"
python3 << PYEOF || echo "  search.json step failed"
import json
try:
    with open("$GOVDOCS/site/docs.json") as f:
        docs = json.load(f)
    slim = [
        {"u": d["url"], "t": d.get("title_en") or d.get("title", ""),
         "a": d.get("agency", ""), "d": d.get("date", ""),
         "y": d.get("type") or "",
         "s": (d.get("summary_en") or d.get("summary") or "")[:150]}
        for d in docs if d.get("url")
    ]
    slim.sort(key=lambda x: x["d"], reverse=True)
    out = "$DASHBOARD/docs/govdocs/search.json"
    with open(out, "w") as f:
        json.dump(slim, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  {len(slim)} docs written to search.json")
except Exception as e:
    print(f"  search.json failed: {e}")
PYEOF

echo "--- Commit and push ---"
cd "$DASHBOARD"
git add docs/govdocs
if git diff --cached --quiet; then
  echo "  nothing to commit"
else
  git commit -m "Update govdocs ($(date +%Y-%m-%d))"
  git pull --rebase && git push && echo "  pushed — Netlify will redeploy in ~1 minute" \
            || echo "  git push failed"
fi

echo "=== Done $(date) ==="
