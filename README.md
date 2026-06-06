# Raspberry Pico Drone Control

Minimal split:

- `pc_keyboard_ui.py`: PC keyboard UI. Sends RC commands to Pico W over UDP.
- `main.py`: Pico W entry point. Receives UDP commands and sends CRSF RC frames to FC.
- `pico_udp.py`: Pico WiFi/UDP receiver.
- `crsf.py`: CRSF frame packing and UART sender.
- `rc_protocol.py`: Shared RC command defaults, clamps, and channel mapping.

## Pico W Setup

Copy these files to the Pico W:

- `main.py`
- `crsf.py`
- `pico_udp.py`
- `rc_protocol.py`
- `wifi_config.py`

Create `wifi_config.py` from `wifi_config.example.py`:

```python
SSID = "your-ssid"
PASSWORD = "your-password"
```

UART wiring for the default setup:

- Pico GP0 / UART0 TX -> FC RX
- Pico GP1 / UART0 RX <- FC TX, optional
- GND shared between Pico and FC

The FC receiver protocol should be set to CRSF.

## PC Control

Run from this repo:

```bash
python3 pc_keyboard_ui.py --ip 192.168.0.112
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
