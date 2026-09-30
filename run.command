#!/bin/zsh

cd "$(dirname "$0")"
.venv/bin/python create_report.py

echo
read "?Press Enter to close..."