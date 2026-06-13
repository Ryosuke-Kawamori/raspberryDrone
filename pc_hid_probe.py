import argparse
import time


VENDOR_ID_8BITDO = 0x2DC8
PRODUCT_ID_ULTIMATE_2C_WIRED = 0x310A


def load_hid():
    try:
        import hid
    except ImportError:
        print("hidapi Python package is required for raw HID probing.")
        print("Install it with: python3 -m pip install hidapi")
        raise SystemExit(1)
    return hid


def list_devices(hid):
    devices = hid.enumerate()
    if not devices:
        print("No HID devices found.")
        return

    for index, device in enumerate(devices):
        vendor_id = device.get("vendor_id")
        product_id = device.get("product_id")
        product = device.get("product_string") or ""
        manufacturer = device.get("manufacturer_string") or ""
        path = device.get("path")
        if isinstance(path, bytes):
            path_text = path.decode(errors="replace")
        else:
            path_text = str(path)
        print(
            "{}: vid=0x{:04x} pid=0x{:04x} manufacturer={!r} product={!r} path={}".format(
                index,
                vendor_id or 0,
                product_id or 0,
                manufacturer,
                product,
                path_text,
            )
        )


def find_device(hid, vendor_id, product_id):
    matches = []
    for device in hid.enumerate(vendor_id, product_id):
        matches.append(device)
    return matches


def open_device(hid, device):
    path = device.get("path")
    handle = hid.device()
    handle.open_path(path)
    handle.set_nonblocking(True)
    return handle


def format_report(data):
    return " ".join("{:02x}".format(byte) for byte in data)


def main():
    parser = argparse.ArgumentParser(description="Raw HID probe for controllers.")
    parser.add_argument("--list", action="store_true", help="List HID devices and exit")
    parser.add_argument("--vid", type=lambda value: int(value, 0), default=VENDOR_ID_8BITDO)
    parser.add_argument("--pid", type=lambda value: int(value, 0), default=PRODUCT_ID_ULTIMATE_2C_WIRED)
    parser.add_argument("--index", type=int, default=0, help="Matching HID device index")
    parser.add_argument("--length", type=int, default=64, help="Read report length")
    args = parser.parse_args()

    hid = load_hid()

    if args.list:
        list_devices(hid)
        return

    matches = find_device(hid, args.vid, args.pid)
    if not matches:
        print("No matching HID device found for vid=0x{:04x} pid=0x{:04x}".format(args.vid, args.pid))
        print("Try: python3 pc_hid_probe.py --list")
        raise SystemExit(1)

    if args.index >= len(matches):
        print("Only {} matching HID device(s), index {} is out of range.".format(len(matches), args.index))
        raise SystemExit(1)

    device = matches[args.index]
    product = device.get("product_string") or "unknown"
    print("Opening:", product)
    print("Move sticks and press buttons. Ctrl+C to stop.")

    handle = open_device(hid, device)
    last = None
    try:
        while True:
            data = handle.read(args.length)
            if data and data != last:
                print(format_report(data))
                last = data
            time.sleep(0.005)
    except KeyboardInterrupt:
        print()
    finally:
        handle.close()


if __name__ == "__main__":
    main()
