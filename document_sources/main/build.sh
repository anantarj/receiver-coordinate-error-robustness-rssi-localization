#!/bin/sh
set -eu
cd "$(dirname "$0")"
pdflatex -interaction=nonstopmode -halt-on-error paper_b_sensors.tex
pdflatex -interaction=nonstopmode -halt-on-error paper_b_sensors.tex
pdflatex -interaction=nonstopmode -halt-on-error paper_b_sensors.tex
