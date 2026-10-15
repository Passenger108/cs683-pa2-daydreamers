#!/bin/bash
# Build Summary_Task3.pdf from the Task 3 logs. Task 1/2a/2b summaries untouched.
set -eu
cd "$(dirname "$0")/.."
python3 scripts/build_summary_task3.py
pandoc docs/summary/task3.md -o Summary_Task3.pdf --pdf-engine=pdflatex \
  --toc --toc-depth=2 -V geometry:a4paper -V geometry:margin=2.2cm \
  -V fontsize=10pt -V colorlinks=true -V linkcolor=black -V urlcolor=black \
  --metadata title="" 2>&1 | grep -vE "^\[WARNING\]" || true
[ -f Summary_Task3.pdf ] || { echo "BUILD FAILED"; exit 1; }
echo "Summary_Task3.pdf  $(pdfinfo Summary_Task3.pdf | grep -oP '(?<=Pages:)\s*\d+' | tr -d ' ') pages, $(du -h Summary_Task3.pdf | cut -f1)"
