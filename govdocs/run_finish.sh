#!/bin/sh
echo "=== START $(date) ==="
./venv/bin/python govdocs.py enrich --limit 40000 &&
echo "=== ENRICH DONE $(date) ===" &&
./venv/bin/python govdocs.py translate --limit 40000 &&
echo "=== TRANSLATE DONE $(date) ===" &&
./venv/bin/python govdocs.py publish &&
echo "=== ALL DONE $(date) ==="
