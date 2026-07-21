# HumO Square UI v2 — 실시간 레이어 합성 버전

기존의 흑백·모노스페이스 1:1 UI를 유지하면서, USB 마이크로 녹음한 10초 소리를 분석해 새로운 정사각형 PNG를 만드는 Raspberry Pi용 PySide6 앱입니다.

## 동작 흐름

1. 부팅 화면
2. 메인 화면
3. 녹음 화면에서 녹음 시작
4. USB 마이크로 10초 녹음
5. 처리 중 화면
6. 소리 분석 및 레이어 합성
7. 생성한 PNG를 결과 화면에 크게 표시
8. `LISTEN`으로 녹음 소리 재생

결과 화면의 하단 볼륨 슬라이더는 실제 재생 중에만 나타납니다. 일시정지하거나 재생이 끝나면 즉시 숨겨집니다.

## 이미지 생성 규칙

`core/analyzer.py`가 아래 네 가지 0~1 값을 계산합니다.

- `loudness`: RMS를 dBFS로 바꾼 뒤 -55~-10 dB 범위를 정규화합니다.
- `brightness`: 스펙트럼 중심과 고·중·저 주파수 에너지 비율을 함께 사용합니다.
- `roughness`: spectral flatness와 zero crossing rate를 함께 사용합니다.
- `variability`: 50ms 프레임별 RMS의 시간 변화량을 사용합니다.

주파수 대역의 기본 경계는 다음과 같으며 `config.json`에서 바꿀 수 있습니다.

- `c`(저음): 20~300Hz
- `b`(중음): 300~2,000Hz
- `a`(고음): 2,000~10,000Hz

선택 규칙은 다음과 같습니다.

- `brightness >= 0.52`: 낮(`D`, Day)
- `brightness < 0.52`: 밤(`N`, Night)
- 형태 점수: `0.25 × loudness + 0.35 × roughness + 0.40 × variability`가 낮으면 `1`, 높으면 `2`의 점수가 커집니다. 여기에 각 고·중·저음 에너지를 곱해 `a1, a2, b1, b2, c1, c2`의 우선순위를 만듭니다.
- 레이어 수: loudness가 `0~0.25`면 1개, `0.25~0.50`이면 2개, `0.50~0.75`면 3개, `0.75~0.88`이면 4개, `0.88~0.96`이면 5개, `0.96~1.0`이면 6개를 선택합니다.
- 따라서 항상 같은 수를 쓰지 않고, 소리 크기에 따라 상위 1~6개 PNG만 합성합니다.

그래픽 조합 수는 6개 레이어의 비어 있지 않은 모든 부분집합이므로 `2⁶-1 = 63`가지입니다. 낮/밤을 포함하면 126가지이고, 그라데이션 210개까지 포함한 최종 이론상 조합은 `126 × 210 = 26,460`가지입니다.

`core/gradient_selector.py`는 210개 그라데이션의 실제 평균색·대표 hue·밝기·채도·대비·차가운 정도를 기록한 `gradient_manifest.json`을 사용합니다. 각 항목은 전체 에셋 범위 안에서 0~1로 다시 정규화해 비교합니다.

- 밝고 높은 소리: 밝고 차가운 후보
- 부드럽고 안정적인 소리: 밝고 대비가 낮은 파스텔 후보
- 거칠고 변화가 큰 소리: 채도와 대비가 높은 후보
- 낮고 어두운 소리: 비교적 어둡고 따뜻한 후보

먼저 소리 특성으로 목표 hue·밝기·채도·대비·색온도를 만든 뒤 가장 가까운 후보 6개를 구합니다. 최종 후보는 loudness·brightness·roughness·variability의 32단계 구간 조합으로 정하므로 랜덤이나 파일명에 의존하지 않으며, 같은 분석값은 같은 결과를 만들고 서로 다른 소리는 같은 계열 안에서도 다른 그라데이션을 선택할 수 있습니다.

## 합성 순서

`core/image_composer.py`가 Pillow로 다음 순서를 처리합니다.

1. 720×720 검정 RGBA 캔버스
2. loudness와 대역·형태 점수로 선택된 1~6개의 그래픽 레이어
3. 선택 레이어를 `c → b → a` 순서로 합성
5. 약한 glow
6. 선택한 그라데이션을 그래픽의 투명도 영역에만 multiply 방식으로 적용
7. `assets/generated_results/<녹음파일명>_artwork.png`로 저장

분석에서 선택된 1~6개 레이어만 사용하므로 작은 소리는 단순하고, 큰 소리는 더 복잡한 결과가 됩니다. 소리가 클수록 전체 그래픽 크기도 커지고, 각 대역 에너지가 높을수록 해당 레이어의 opacity가 높아집니다. 그라데이션은 그래픽에만 입혀지므로 검정 배경에 사각형 경계가 생기지 않습니다. UI는 생성된 이미지의 색을 다시 덮어쓰지 않습니다.

## 에셋 위치

모든 경로는 `/Users/...` 같은 절대경로가 아니라 프로젝트 루트 기준 상대경로입니다.

```text
assets/
└── device_graphics/
    ├── gradients/
    │   ├── 1.png
    │   ├── 2.png
    │   ├── ...
    │   ├── 210.png
    │   └── gradient_manifest.json
    ├── layers/                    # Windows 권장 영문 경로
    │   └── A/
    │       ├── day/
    │       └── night/
    └── 0_디바이스그래픽/
        ├── A/
        │   ├── 낮_background_W/
        │   └── 밤_background_B/
        ├── B/                       # 제공되는 경우 같은 규칙
        │   ├── 낮_background_W/
        │   └── 밤_background_B/
        └── C/                       # 제공되는 경우 같은 규칙
            ├── 낮_background_W/
            └── 밤_background_B/
```

현재 전달된 ZIP에는 `A` 패밀리의 `Aa1_D.png`~`Ac2_D.png`, `Aa1_N.png`~`Ac2_N.png` 12개가 들어 있습니다. 코드는 한글 폴더명을 직접 비교하지 않고 파일명 끝의 `a1_D`, `b2_N` 같은 규칙을 재귀 검색하므로 macOS의 한글 유니코드 형식과 A/B/C 분리 구조를 모두 처리합니다. `composer_graphic_family`의 기본값은 `A`입니다.

Windows 전달본은 한글 폴더명의 ZIP 인코딩 문제를 막기 위해 동일한 12개 파일을 `layers/A/day`, `layers/A/night`에 배치하며, 합성기는 이 영문 경로를 가장 먼저 확인합니다.

에셋을 교체하거나 추가한 뒤 그라데이션 매니페스트를 다시 만들려면 다음을 실행합니다.

```bash
./.venv/bin/python tools/build_gradient_manifest.py
```

## Raspberry Pi 설치 및 실행

Raspberry Pi OS 64-bit와 Python 3.10 이상을 권장합니다.

```bash
cd hum_square_ui_v2
chmod +x install.sh run.sh
./install.sh
./.venv/bin/python check_devices.py
./run.sh
```

USB 마이크 입력 번호와 출력 장치는 `config.json`에서 지정합니다.

```json
"audio_input_device": 2,
"audio_output_device": 3
```

마이크 없이 전체 흐름을 시험할 수 있습니다.

```bash
HUM_MOCK_RECORDING=1 ./run.sh
```

자동 테스트는 아래 명령으로 실행합니다.

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

## 주요 설정

`config.json`에서 아래 값을 조정할 수 있습니다.

- `record_seconds`: 녹음 길이, 기본 10초
- `processing_minimum_seconds`: 처리 중 화면의 최소 표시 시간
- `device_graphics_dir`: 그래픽과 gradients의 루트
- `gradient_manifest`: 그라데이션 색 통계 파일
- `generated_results_dir`: 생성 PNG 저장 폴더
- `composer_canvas_size`: 출력 한 변 크기
- `composer_graphic_family`: A/B/C 중 우선 사용할 패밀리
- `composer_gradient_opacity`: 전면 그라데이션 기본 투명도
- `analysis.day_brightness_threshold`: 낮/밤 기준
- `analysis.layer_count_thresholds`: 1~6개 레이어 수를 나누는 loudness 기준
- `developer_mode`: `true`일 때 오늘의 Hum을 남긴 뒤에도 개발 테스트용 추가 녹음을 허용
- `analysis.low_band_hz`, `analysis.high_band_hz`: 저·중·고음 경계

## 코드 구조

```text
hum_square_ui_v2/
├── main.py
├── config.json
├── core/
│   ├── analyzer.py              # 소리 특성·대역·레이어 선택
│   ├── gradient_selector.py     # 그라데이션 목표 색감 매칭
│   ├── image_composer.py        # 실제 PNG 합성 및 저장
│   ├── library.py               # 분석값·생성 PNG 경로 보관
│   ├── recorder.py
│   └── player.py
├── ui/
├── assets/
│   ├── device_graphics/
│   └── generated_results/
├── recordings/
├── tests/
└── tools/build_gradient_manifest.py
```

기존 `image_mapping.csv`와 `assets/results/result_*.png`는 이전 데이터 확인용으로 남겨 두었지만 새 실행 흐름에서는 사용하지 않습니다. 새 녹음과 예전 목록 항목 중 생성 PNG가 없는 항목은 모두 새 분석·합성 파이프라인을 사용합니다.

## 녹음 목록과 오늘의 Hum

- 녹음 목록은 `FAVORITES`와 `TIME` 정렬을 선택할 수 있습니다.
- `FAVORITES`에서는 하트 표시된 항목이 먼저 나오고, 각 그룹 안에서는 최신순입니다.
- `TIME`에서는 전체 항목이 최신순으로 표시됩니다.
- 오늘의 Hum을 저장하면 선택한 녹음만 남고 같은 날짜의 다른 녹음과 생성 결과는 즉시 삭제됩니다.
- 운영 모드에서는 오늘의 Hum을 저장한 뒤 같은 날 추가 녹음이 차단됩니다.
- 현재 전달본은 테스트를 위해 `developer_mode: true`이며, 운영 시 `false`로 바꿉니다.
