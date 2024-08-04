import subprocess


class KDEConnectCLI:
    def list_devices(self, id_only=False, name_only=False, id_name_only=False):
        args = ["kdeconnect-cli", "--list-devices"]
        if id_only:
            args.append("--id-only")
        if name_only:
            args.append("--name-only")
        if id_name_only:
            args.append("--id-name-only")
        return self._execute_command(args)

    def list_available_devices(
        self, id_only=False, name_only=False, id_name_only=False
    ):
        args = ["kdeconnect-cli", "--list-available"]
        if id_only:
            args.append("--id-only")
        if name_only:
            args.append("--name-only")
        if id_name_only:
            args.append("--id-name-only")
        return self._execute_command(args)

    def refresh_devices(self):
        return self._execute_command(["kdeconnect-cli", "--refresh"])

    def pair_device(self, device_id):
        return self._execute_command(
            ["kdeconnect-cli", "--pair", "--device", device_id]
        )

    def unpair_device(self, device_id):
        return self._execute_command(
            ["kdeconnect-cli", "--unpair", "--device", device_id]
        )

    def ring_device(self, device_id):
        return self._execute_command(
            ["kdeconnect-cli", "--ring", "--device", device_id]
        )

    def ping_device(self, device_id):
        return self._execute_command(
            ["kdeconnect-cli", "--ping", "--device", device_id]
        )

    def send_clipboard(self, device_id):
        return self._execute_command(
            ["kdeconnect-cli", "--send-clipboard", "--device", device_id]
        )

    def share_file(self, file_path, device_id):
        return self._execute_command(
            ["kdeconnect-cli", "--share", file_path, "--device", device_id]
        )

    def share_text(self, text, device_id):
        return self._execute_command(
            ["kdeconnect-cli", "--share-text", text, "--device", device_id]
        )

    def list_notifications(self, device_id):
        return self._execute_command(
            ["kdeconnect-cli", "--list-notifications", "--device", device_id]
        )

    def lock_device(self, device_id):
        return self._execute_command(
            ["kdeconnect-cli", "--lock", "--device", device_id]
        )

    def unlock_device(self, device_id):
        return self._execute_command(
            ["kdeconnect-cli", "--unlock", "--device", device_id]
        )

    def send_sms(self, message, destination):
        return self._execute_command(
            ["kdeconnect-cli", "--send-sms", message, "--destination", destination]
        )

    def get_encryption_info(self, device_id):
        return self._execute_command(
            ["kdeconnect-cli", "--encryption-info", "--device", device_id]
        )

    def list_commands(self, device_id):
        return self._execute_command(
            ["kdeconnect-cli", "--list-commands", "--device", device_id]
        )

    def execute_command(self, command_id, device_id):
        return self._execute_command(
            ["kdeconnect-cli", "--execute-command", command_id, "--device", device_id]
        )

    def send_keys(self, keys, device_id):
        return self._execute_command(
            ["kdeconnect-cli", "--send-keys", keys, "--device", device_id]
        )

    def take_photo(self, device_id, photo_path):
        return self._execute_command(
            ["kdeconnect-cli", "--photo", photo_path, "--device", device_id]
        )

    def my_id(self):
        return self._execute_command(["kdeconnect-cli", "--my-id"])

    def _execute_command(self, args):
        try:
            result = subprocess.run(args, capture_output=True, text=True, check=True)
            return result.stdout
        except subprocess.CalledProcessError as e:
            return f"Error: {e}"


kdeconnect = KDEConnectCLI()
