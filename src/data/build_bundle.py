#!/usr/bin/env python3
"""Inline data/parcels.js + data/data.js into syracuse-reference.html to produce
a single self-contained file that opens by double-click (no server needed)."""
import os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "syracuse-reference.html")
# NOTE: macOS filesystem is case-insensitive, so the output MUST NOT differ from
# the source only by case (that would overwrite the source). Use a dist/ subdir.
os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
OUT = os.path.join(ROOT, "dist", "Syracuse-Reference.html")

html = open(SRC, encoding="utf-8").read()
for rel in ("data/parcels.js", "data/nhoods.js", "data/data.js"):
    js = open(os.path.join(ROOT, rel), encoding="utf-8").read()
    tag = f'<script src="{rel}"></script>'
    assert tag in html, f"tag not found: {tag}"
    html = html.replace(tag, "<script>\n" + js + "\n</script>")

with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)
print(f"wrote {OUT} ({os.path.getsize(OUT)/1024:.0f} KB, self-contained)")
