#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$project_root/src${PYTHONPATH:+:$PYTHONPATH}"
python3 -m compileall -q "$project_root/src" "$project_root/tests"
python3 -m unittest discover -s "$project_root/tests" -v

