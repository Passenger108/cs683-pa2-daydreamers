#!/bin/bash
# Build Summary_Task2a.pdf from the run logs.
#   1. scripts/build_summary_task2a.py regenerates docs/summary/task2a.md,
#      computing every figure from results/task2a/*.txt -- so the document
#      cannot disagree with the logs it describes.
#   2. pandoc renders it with pdflatex.
# Task 1's Summary.pdf is a separate, finished artifact and is never touched.
set -eu
cd "$(dirname "$0")/.."

python3 scripts/build_summary_task2a.py

pandoc docs/summary/task2a.md \
  -o Summary_Task2a.pdf \
  --pdf-engine=pdflatex \
  --toc --toc-depth=2 \
  -V geometry:a4paper -V geometry:margin=2.2cm \
  -V fontsize=10pt -V colorlinks=true -V linkcolor=black -V urlcolor=black \
  -V title="CS683 PA2 - Task 2a: Instruction-Conscious L2 Replacement (I-RRIP)" \
  --metadata title="" \
  2>&1 | grep -vE "^\[WARNING\] (Could not convert|Missing)" || true

[ -f Summary_Task2a.pdf ] || { echo "BUILD FAILED"; exit 1; }
echo "Summary_Task2a.pdf  $(pdfinfo Summary_Task2a.pdf | grep -oP '(?<=Pages:)\s*\d+' | tr -d ' ') pages, $(du -h Summary_Task2a.pdf | cut -f1)"
