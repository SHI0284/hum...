#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "가상환경이 없습니다. 먼저 ./install.sh을 실행해주세요."
  exit 1
fi

exec .venv/bin/python main.py
