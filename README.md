# Raspberry Pico Drone Control

Minimal split:

- `pc_keyboard_ui.py`: PC keyboard UI. Sends RC commands to Pico W over UDP.
- `pc_gamepad_ui.py`: PC gamepad UI. Sends RC commands and shows Pico ACK/status.
- `pc_gamepad_probe.py`: Shows gamepad axis/button numbers for mapping.
- `pc_hid_probe.py`: Raw HID probe for controllers that pygame/SDL cannot see.
- `picomain.py`: Pico W entry point. Receives UDP commands and sends CRSF RC frames to FC.
- `pico_udp.py`: Pico WiFi/UDP receiver.
- `crsf.py`: CRSF frame packing and UART sender.
- `rc_protocol.py`: Shared RC command defaults, clamps, and channel mapping.

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
