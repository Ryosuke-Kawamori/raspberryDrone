# Raspberry Pico Drone Control

Raspberry Pi Zero W can also replace the Pico W without changing the PC UIs.
See [Pi Zero W setup, safety behavior, and tests](pi_zero/README.md).

Pi Zero Wを初めて使う場合は、[初期セットアップ手順](pi_zero/README.md#初めてセットアップする場合)を参照してください。
OS・Wi-Fi・SSH、未pushコードの転送、dry-run、UART設定、FC配線、自動起動の順に説明しています。
Pi Zero WではmicroSD上のRaspberry Pi OSを使用します。下記のPico W用MicroPython手順とは異なります。

BMP581 / VL53L4CDによる実験的な高度維持を追加しました。既定起動は非駆動です。
実行モード・配線確認・校正・検証手順は[高度維持ガイド](pi_zero/ALTITUDE.md)を参照してください。
同梱設定ではliveは無効です。

## Directory structure

```text
raspberryDrone/
├── pc/                         # PC操作・入力デバイス確認の実装
│   ├── README.md
│   ├── keyboard_ui.py
│   ├── gamepad_ui.py
│   ├── gamepad_probe.py
│   ├── hid_probe.py
│   └── altitude.py
├── pi_zero/                    # Raspberry Pi Zero W用CPython実装
│   ├── README.md               # 初期設定・UART・配線・自動起動
│   ├── ALTITUDE.md             # 高度維持の設定と検証
│   ├── main.py / config.py
│   ├── udp_receiver.py / serial_transport.py
│   ├── alt_config.py / alt_control.py / alt_runtime.py
│   ├── sensors.py / estimation.py / experiments.py
│   ├── altitude.example.json
│   ├── requirements.txt / requirements-sensors.txt
│   ├── raspberry-drone.service
│   └── tests/                  # ブリッジ・高度制御の自動テスト
├── examples/                   # 手動で実行する確認スクリプト
│   ├── README.md               # 旧ファイル名との対応と実行方法
│   ├── pico_w/                 # Pico Wで動かすUART・モーター確認
│   └── udp/send_rc.py           # PCから固定RC値を送信
├── tests/                      # PC起動方法・互換性の自動テスト
├── pytest.ini                  # 実機用examplesを自動収集しない設定
├── picomain.py                 # Pico Wへmain.pyとしてコピー
├── pico_udp.py                 # Pico WのWi-Fi・UDP受信
├── wifi_config.example.py      # Pico W用Wi-Fi設定テンプレート
├── crsf.py                     # Pico / Pi共通のCRSF生成
├── rc_protocol.py              # PC / Pico / Pi共通のRCプロトコル
└── pc_*.py                     # 既存コマンド・importを維持する互換ファイル
```

PC側の変更は[pc/](pc/README.md)、Pi Zero W側の変更は[pi_zero/](pi_zero/README.md)で行います。
ルートの `pc_*.py` は互換用で、実装は `pc/` に集約しています。
Pico Wへファイルを直接コピーする既存の運用とMicroPythonのimportを維持するため、
Pico W起動コードと共通モジュールはルートに残しています。
仮想環境・キャッシュ・ローカル調査用ファイルは上記の構成に含めません。

リポジトリ直下から、新しいモジュール形式でも起動できます。

```bash
python -m pc.keyboard_ui --ip <DEVICE_IP>
python -m pc.gamepad_ui --ip <DEVICE_IP> --receiver-test
python -m pi_zero.main --dry-run
python -m pytest
```

自動テストには `python -m pip install pytest` が必要です。従来のPC起動コマンドも引き続き使えます。

## Pico W Setup

Copy these files to the Pico W:

- `picomain.py` as `main.py`
- `crsf.py`
- `pico_udp.py`
- `rc_protocol.py`
- `wifi_config.py`

Create `wifi_config.py` from `wifi_config.example.py`:

```python
WIFI_MODE = "ap"

AP_SSID = "pico-drone"
AP_PASSWORD = "drone12345"

STA_SSID = "your-home-wifi"
STA_PASSWORD = "your-home-password"
```

`WIFI_MODE = "ap"` makes the Pico W the Wi-Fi access point. This is the flight-oriented setup because it does not require an outdoor router.

UART wiring for the default setup:

- Pico GP0 / UART0 TX -> FC RX
- Pico GP1 / UART0 RX <- FC TX, optional
- GND shared between Pico and FC

The FC receiver protocol should be set to CRSF.

## PC Control

Run from this repo:

```bash
python3 pc_keyboard_ui.py --ip 192.168.4.1
```

For gamepad control, install pygame first:

```bash
python3 -m pip install pygame
```

Check the controller mapping:

```bash
python3 pc_gamepad_probe.py
```

If the controller appears in macOS `hidutil` but pygame says `No gamepad found`, try raw HID probing:

```bash
python3 -m pip install hidapi
python3 pc_hid_probe.py --list
python3 pc_hid_probe.py
```

Run the gamepad controller:

```bash
python3 pc_gamepad_ui.py --ip 192.168.4.1
```

The gamepad UI prints `ACK packets=...` when Pico is receiving UDP commands and replying with status.
The default stick span is `+/-250us` around center. For first FC receiver checks or very gentle tests, use a smaller span:

```bash
python3 pc_gamepad_ui.py --ip 192.168.4.1 --stick-span 150
```

For Betaflight Receiver tab checks, use receiver test mode. It keeps AUX arm forced off while allowing the throttle channel to move:

```bash
python3 pc_gamepad_ui.py --ip 192.168.4.1 --stick-span 150 --receiver-test
```

Controls:

- `W/S`: pitch
- `A/D`: roll
- `Q/E`: yaw
- `R/F`: throttle up/down
- `M`: arm toggle
- `G`: angle mode toggle
- `Space`: center roll/pitch/yaw
- `P`: panic disarm and throttle low
- `X`: quit

For safety, throttle is clamped to `1000..1200` for now, and Pico disarms on UDP timeout.
