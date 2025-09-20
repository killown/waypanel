import requests
from gi.repository import Gtk, GLib
from wayfire import WayfireSocket

sock = WayfireSocket()


class MullvadStatusDialog(Gtk.Dialog):
    def __init__(self, parent=None):
        super().__init__(title="Mullvad VPN Status", transient_for=parent)

        self.set_default_size(0, 0)
        self.set_resizable(False)
        self.hide()
        GLib.timeout_add(100, self.configure_view)

        header = Gtk.HeaderBar()
        self.set_titlebar(header)

        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda w: self.close())
        header.pack_end(close_btn)

        self.box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            margin_start=15,
            margin_end=15,
            margin_top=15,
            margin_bottom=15,
        )
        self.set_child(self.box)

        self.spinner = Gtk.Spinner(spinning=True)
        self.loading_label = Gtk.Label(label="Connecting to Mullvad...")
        loading_box = Gtk.Box(spacing=10)
        loading_box.append(self.spinner)
        loading_box.append(self.loading_label)
        self.box.append(loading_box)

        GLib.timeout_add(500, self.init_fetch)

    def init_fetch(self):
        GLib.Thread.new(None, self.fetch_in_thread, None)
        return False

    def fetch_in_thread(self, *args):
        data = self.get_mullvad_vpn_status()
        GLib.idle_add(self.update_ui, data)

    def configure_view(self):
        view = [
            view for view in sock.list_views() if "Mullvad VPN Status" in view["title"]
        ][0]
        output = sock.get_focused_output()
        workarea = output["workarea"]
        view_width = view["base-geometry"]["width"]
        position_x = (workarea["x"] + workarea["width"]) - (view_width + 100)
        print(position_x)
        position_y = workarea["y"] + 10
        sock.configure_view(view["id"], position_x, position_y, 0, 0)
        self.show()
        # finish timeout_add_seconds
        return False

    def get_mullvad_vpn_status(self):
        try:
            response = requests.get("https://am.i.mullvad.net/json", timeout=3)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"API Error: {e}")
            return None

    def update_ui(self, data):
        for child in list(self.box):
            self.box.remove(child)

        if not data:
            error_label = Gtk.Label(label="Failed to fetch VPN data")
            self.box.append(error_label)
            return

        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        self.box.append(grid)

        status_icon = Gtk.Image.new_from_icon_name(
            "network-vpn-acquired-symbolic"
            if data["mullvad_exit_ip"]
            else "network-vpn-disabled-symbolic"
        )
        status_label = Gtk.Label(
            label=f"<b>Status:</b> {'Active' if data['mullvad_exit_ip'] else 'Inactive'}",
            use_markup=True,
        )
        grid.attach(status_icon, 0, 0, 1, 1)
        grid.attach(status_label, 1, 0, 1, 1)

        info_rows = [
            ("IP Address", data["ip"], "network-transmit-receive-symbolic"),
            (
                "Location",
                f"{data['city']}, {data['country']}",
                "mark-location-on-map-symbolic",
            ),
            ("Server", data["mullvad_exit_ip_hostname"], "server-symbolic"),
            (
                "Type",
                data["mullvad_server_type"],
                "preferences-system-network-symbolic",
            ),
            ("ISP", data["organization"], "computer-symbolic"),
            (
                "Blacklisted",
                "Yes" if data["blacklisted"]["blacklisted"] else "No",
                "dialog-warning-symbolic",
            ),
        ]

        for i, (label, value, icon_name) in enumerate(info_rows, 1):
            icon = Gtk.Image.new_from_icon_name(icon_name)
            lbl = Gtk.Label(label=f"<b>{label}:</b>", use_markup=True, xalign=0)
            val = Gtk.Label(label=value, xalign=0, selectable=True)

            grid.attach(icon, 0, i, 1, 1)
            grid.attach(lbl, 1, i, 1, 1)
            grid.attach(val, 2, i, 1, 1)

    def about(self):
        """
        This class is a Gtk.Dialog window that displays detailed Mullvad VPN
        status. It fetches information from the official Mullvad API to show
        the user's IP address, server location, and connection status in a
        formatted pop-up window.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        The `MullvadStatusDialog` class is a Gtk window that fetches and
        displays real-time VPN status. Its key features are:

        1. **Threaded Data Fetching**: To prevent the user interface from
           freezing, the `get_mullvad_vpn_status` method, which makes a
           blocking HTTP request using the `requests` library, is executed in
           a separate thread. The `GLib.Thread.new` function starts this
           thread, and `GLib.idle_add` is used to safely update the UI with
           the fetched data once the thread completes.

        2. **Dynamic UI Generation**: The `update_ui` method dynamically
           constructs the dialog's content. It clears the existing widgets
           and then populates a `Gtk.Grid` with new labels, icons, and text
           based on the JSON data received from the Mullvad API.

        3. **Wayfire Integration**: The `configure_view` method uses the
           `WayfireSocket` to position the dialog window precisely on the
           screen. It calculates the correct X and Y coordinates to place the
           pop-up in a consistent location, typically near the top-right
           corner of the desktop.
        """
        return self.code_explanation.__doc__
