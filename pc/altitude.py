"""Optional Pi altitude protocol extensions; shared Pico payload stays unchanged."""
import time


class AltitudeClient:
    def __init__(self):
        self.hold = False
        self.offset = 0.0
        self.seq = 0
        self.token = ""
        self.status = None
        self.received_at = None

    def receive(self, status):
        if not isinstance(status, dict):
            return
        self.status = status.get("altitude")
        self.token = status.get("control_token", "")
        self.seq = max(self.seq, status.get("control_seq_floor", -1))
        self.received_at = time.monotonic()

    def decorate(self, payload):
        self.seq += 1
        if not payload["arm"]:
            self.hold = False
        return dict(payload, alt_hold=self.hold, alt_offset_m=self.offset,
                    control_token=self.token, control_seq=self.seq)

    def step(self, metres):
        self.offset = max(-10.0, min(10.0, self.offset+metres))

    def lines(self):
        if self.received_at is None or time.monotonic()-self.received_at > 1:
            return ["Altitude: NO FRESH ACK", "", "", ""]
        s = self.status or {}
        def fmt(key):
            value = s.get(key)
            return "?" if value is None else f"{value:.3f}"
        return [f"{s.get('mode', '?')} {s.get('state', '?')} hold requested={self.hold}",
                f"height={fmt('height_m')}m target={fmt('target_m')}m vz={fmt('velocity_m_s')}m/s",
                f"quality={s.get('quality', '?')} age={fmt('age_s')}s "
                f"thr manual/auto/out={s.get('manual_throttle','?')}/{s.get('auto_throttle','?')}/{s.get('output_throttle','?')}",
                f"fault={s.get('fault', '')}"]
