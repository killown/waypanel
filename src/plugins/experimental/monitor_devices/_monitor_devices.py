import pyudev
import sys


def main():
    """Isolated USB event monitor using the Process-Cycling pattern.

    This script exists to solve a specific persistence bug in `pyudev.Monitor`
    where the observer often hangs or stops responding after the first hardware
    handshake when running in a persistent Python thread.

    Architecture:
        1. The parent process (Waypanel) spawns this script as a subprocess.
        2. This script creates a fresh Netlink socket to listen for udev events.
        3. Upon catching a valid event (Joystick or USB device), it prints data
           to STDOUT and immediately terminates (sys.exit(0)).
        4. The parent reads the output, processes it, and spawns a brand-new
           instance of this script, ensuring a clean state for every event.

    Strict Output Protocol:
        - STDOUT: Reserved EXCLUSIVELY for event data. Any other prints to
          STDOUT will corrupt the pipe and crash the parent's parser.
        - STDERR: Used for debugging, logging, and error reporting.

    Data Format:
        action|device_id|clean_model_name|clean_vendor_name
    """
    try:
        context = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(context)

        # DEBUG: Sent to stderr so it doesn't pollute the data pipe
        print(
            "Child: Listener initialized. Waiting for hardware signal...",
            file=sys.stderr,
        )

        for action, device in monitor:
            # Detect joysticks (input subsystem) or generic USB hardware
            is_joy = device.properties.get("ID_INPUT_JOYSTICK") == "1"
            is_usb = device.device_type == "usb_device"

            if not (is_joy or is_usb):
                continue

            # Unique hardware identifier
            did = device.properties.get("ID_SERIAL") or device.sys_path

            # --- String Filtering & Normalization ---
            # Replace underscores/hyphens with spaces and collapse whitespace
            raw_name = (
                device.properties.get("ID_MODEL_FROM_DATABASE")
                or device.properties.get("ID_MODEL")
                or "Unknown Device"
            )
            name = " ".join(raw_name.replace("-", " ").replace("_", " ").split())

            raw_vendor = device.properties.get("ID_VENDOR", "Unknown")
            vendor = " ".join(raw_vendor.replace("-", " ").replace("_", " ").split())

            # ATOMIC DATA TRANSMISSION
            # This is the ONLY line allowed to write to stdout.
            print(f"{action}|{did}|{name}|{vendor}")
            sys.stdout.flush()

            # SELF-TERMINATION: Force parent to recycle the process
            sys.exit(0)

    except Exception as e:
        print(f"Subprocess Fatal Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
