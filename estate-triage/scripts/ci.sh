#!/usr/bin/env sh
set -eu

python3 -m pip install -e ".[test]"
python3 -m pytest -q
