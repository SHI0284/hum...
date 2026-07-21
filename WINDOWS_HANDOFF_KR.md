# HumO Square UI v2 — Windows 개발자 전달 안내

이 패키지는 현재까지 구현된 실시간 소리 분석 및 PNG 레이어 합성 버전입니다.
개인 테스트 녹음, 생성 결과, macOS 가상환경은 포함하지 않았습니다.

## 권장 환경

- Windows 10/11 64-bit
- Python 3.11 64-bit
- USB 마이크

Python 설치 시 `Add python.exe to PATH`를 선택하거나 Windows Python Launcher(`py`)를 설치해주세요.

## 처음 한 번 설치

프로젝트 폴더에서 `setup_windows.bat`을 실행합니다.

직접 명령을 실행하려면 PowerShell에서 다음을 사용합니다.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 실행

`run_windows.bat`을 실행합니다.

마이크 연결 전 UI와 합성 흐름만 확인하려면 `run_windows_mock.bat`을 실행합니다. 이 모드에서는 테스트용 가상 녹음을 생성합니다.

## USB 마이크 설정

연결된 장치 번호는 다음 명령으로 확인합니다.

```powershell
.\.venv\Scripts\python.exe check_devices.py
```

필요하면 `config.json`에서 장치 번호를 지정합니다.

```json
"audio_input_device": null,
"audio_output_device": null
```

`null`이면 운영체제 기본 장치를 사용합니다. 특정 장치를 사용할 경우 `null` 대신 확인한 숫자를 입력합니다.

## 핵심 구현 파일

- `core/analyzer.py`: loudness, brightness, roughness, variability 및 주파수 대역 분석
- `core/gradient_selector.py`: 소리 특성에 맞는 그라데이션 선택
- `core/image_composer.py`: 1~6개 그래픽 레이어와 그라데이션 합성
- `ui/main_window.py`: 녹음·처리·결과·재생 흐름 연결
- `config.json`: 분석 임계값과 에셋 경로 설정
- `README_KR.md`: 전체 알고리즘 및 폴더 구조 설명

## 현재 이미지 선택 규칙

- loudness 0~0.25: 레이어 1개
- loudness 0.25~0.50: 레이어 2개
- loudness 0.50~0.75: 레이어 3개
- loudness 0.75~0.88: 레이어 4개
- loudness 0.88~0.96: 레이어 5개
- loudness 0.96~1.00: 레이어 6개
- 선택 후보: `a1, a2, b1, b2, c1, c2`
- 그래픽 조합 63개, 낮/밤 포함 126개, 그라데이션 210개 포함 이론상 26,460개

윈도우 전달본의 그래픽 레이어는 한글 ZIP 경로 호환 문제를 방지하기 위해 아래 영문 경로에 들어 있습니다.

```text
assets/device_graphics/layers/A/day/Aa1_D.png ... Ac2_D.png
assets/device_graphics/layers/A/night/Aa1_N.png ... Ac2_N.png
```

## 테스트

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

현재 자동 테스트는 소리 크기에 따른 레이어 수, 낮/밤 선택, 이미지 생성, 그라데이션 특성 매핑을 확인합니다.

## 운영 전 개발자 모드 해제

현재 `config.json`의 `developer_mode`는 테스트 편의를 위해 `true`입니다. 운영본에서는 `false`로 바꿔야 오늘의 Hum 저장 후 같은 날 추가 녹음이 차단됩니다. 오늘의 Hum 저장 시 같은 날짜의 다른 녹음은 개발자 모드와 관계없이 삭제됩니다.
