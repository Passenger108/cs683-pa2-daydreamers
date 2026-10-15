#!/bin/bash
# Build Summary_Task2b.pdf from the run logs.
#   1. build_summary_task2b.py regenerates docs/summary/task2b.md, computing
#      every figure from results/task2b/*.txt -- so the document cannot
#      disagree with the logs it describes.
#   2. pandoc renders it with pdflatex.
# Task 1's Summary.pdf and Task 2a's Summary_Task2a.pdf are never touched.
set -eu
cd "$(dirname "$0")/.."

python3 scripts/build_summary_task2b.py

pandoc docs/summary/task2b.md \
  -o Summary_Task2b.pdf \
  --pdf-engine=pdflatex \
  --toc --toc-depth=2 \
  -V geometry:a4paper -V geometry:margin=2.2cm \
  -V fontsize=10pt -V colorlinks=true -V linkcolor=black -V urlcolor=black \
  --metadata title="" \
  2>&1 | grep -vE "^\[WARNING\] (Could not convert|Missing)" || true

[ -f Summary_Task2b.pdf ] || { echo "BUILD FAILED"; exit 1; }
echo "Summary_Task2b.pdf  $(pdfinfo Summary_Task2b.pdf | grep -oP '(?<=Pages:)\s*\d+' | tr -d ' ') pages, $(du -h Summary_Task2b.pdf | cut -f1)"
