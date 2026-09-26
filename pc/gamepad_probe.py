import time


def main():
    try:
        import pygame
    except ImportError:
        print("pygame is required for gamepad input.")
        print("Install it with: python3 -m pip install pygame")
        raise SystemExit(1)

    pygame.init()
    pygame.joystick.init()

    if pygame.joystick.get_count() == 0:
        print("No gamepad found.")
        raise SystemExit(1)

    joystick = pygame.joystick.Joystick(0)
    joystick.init()
    print("Controller:", joystick.get_name())
    print("Axes:", joystick.get_numaxes(), "Buttons:", joystick.get_numbuttons())
    print("Move sticks and press buttons. Ctrl+C to stop.")

    try:
        while True:
            pygame.event.pump()
            axes = []
            for index in range(joystick.get_numaxes()):
                axes.append("{}:{:+.2f}".format(index, joystick.get_axis(index)))
            buttons = []
            for index in range(joystick.get_numbuttons()):
                if joystick.get_button(index):
                    buttons.append(str(index))
            print("\raxes [{}] buttons [{}]".format(" ".join(axes), " ".join(buttons)), end="")
            time.sleep(0.05)
    except KeyboardInterrupt:
        print()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
