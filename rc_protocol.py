ROLL_MIN = 1000
ROLL_MAX = 2000
PITCH_MIN = 1000
PITCH_MAX = 2000
THROTTLE_MIN = 1000
THROTTLE_MAX = 1200
YAW_MIN = 1000
YAW_MAX = 2000


def clamp(value, min_value, max_value):
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def safe_bool(value):
    return True if value is True else False


def default_rc():
    return {
        "roll": 1500,
        "pitch": 1500,
        "throttle": 1000,
        "yaw": 1500,
        "arm": False,
        "angle": True,
    }


def sanitize_rc(data, force_throttle_low=True):
    rc = default_rc()
    rc["roll"] = clamp(int(data.get("roll", rc["roll"])), ROLL_MIN, ROLL_MAX)
    rc["pitch"] = clamp(int(data.get("pitch", rc["pitch"])), PITCH_MIN, PITCH_MAX)
    rc["throttle"] = clamp(
        int(data.get("throttle", rc["throttle"])),
        THROTTLE_MIN,
        THROTTLE_MAX,
    )
    rc["yaw"] = clamp(int(data.get("yaw", rc["yaw"])), YAW_MIN, YAW_MAX)
    rc["arm"] = safe_bool(data.get("arm", rc["arm"]))
    rc["angle"] = safe_bool(data.get("angle", rc["angle"]))

    if force_throttle_low and not rc["arm"]:
        rc["throttle"] = THROTTLE_MIN

    return rc


def rc_to_channels(rc):
    ch = [1500] * 16
    ch[0] = rc["roll"]
    ch[1] = rc["pitch"]
    ch[2] = rc["throttle"]
    ch[3] = rc["yaw"]
    ch[4] = 2000 if rc["arm"] else 1000
    ch[5] = 2000 if rc["angle"] else 1000
    return ch
