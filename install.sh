#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "[1/4] 라즈베리파이 시스템 패키지 설치"
sudo apt update
sudo apt install -y \
  python3-venv \
  python3-pip \
  portaudio19-dev \
  libportaudio2 \
  libsndfile1 \
  libasound2-dev \
  libegl1 \
  libgl1 \
  libxcb-cursor0 \
  fonts-noto-cjk \
  alsa-utils

echo "[2/4] 가상환경 생성"
python3 -m venv .venv

echo "[3/4] Python 패키지 설치"
.venv/bin/python -m pip install --upgrade pip wheel
.venv/bin/python -m pip install -r requirements.txt

echo "[4/4] 설치 확인"
.venv/bin/python - <<'PY'
import PySide6
import numpy
import sounddevice
import soundfile
from PIL import Image
print("HumO 설치 완료")
PY

echo
echo "장치 확인: ./.venv/bin/python check_devices.py"
echo "마이크 시험: ./.venv/bin/python mic_test.py"
echo "앱 실행: ./run.sh"
