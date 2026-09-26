"""Compatibility entry point; implementation lives in pc/hid_probe.py."""

from pc.hid_probe import *  # noqa: F401,F403 - preserve existing imports


if __name__ == "__main__":
    main()
