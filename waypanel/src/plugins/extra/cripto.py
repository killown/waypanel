import requests
from gi.repository import Gtk, GLib


# set to False or remove the plugin file to disable it
ENABLE_PLUGIN = False


def position():
    """
    Define the plugin's position and order.
    """
    position = "right"  # Can be "left", "right", or "center"
    order = 3  # Lower numbers have higher priority
    return position, order


def initialize_plugin(obj, app):
    """
    Initialize the cripto plugin.
    Args:
        obj: The main panel object (Panel instance).
        app: The main application instance.
    """
    if ENABLE_PLUGIN:
        cripto_plugin = CriptoPlugin(obj, app)
        cripto_plugin.create_menu_popover_crypto()


class CriptoPlugin:
    def __init__(self, obj, app):
        self.obj = obj
        self.app = app
        self.popover_crypto = None
        self.crypto_labels = {}
        self.update_timeout_id = None
        self.update_time = 1800
        self.prices = {
            "XRPUSDT": None,
            "BTCUSDT": None,
            "HBARUSDT": None,
            "VETUSDT": None,
        }

    def create_menu_popover_crypto(self):
        """
        Create the crypto button and popover.
        """
        # Create the crypto button
        self.menubutton_crypto = Gtk.Button()
        self.menubutton_crypto.set_icon_name("taxes-finances")  # Default icon
        self.menubutton_crypto.connect("clicked", self.open_popover_crypto)

        # Add the button to the systray
        if hasattr(self.obj, "top_panel_box_right"):
            self.obj.top_panel_box_systray.append(self.menubutton_crypto)
        else:
            print("Error: top_panel_box_right not found in Panel object.")

        # Start fetching crypto data periodically
        self.start_crypto_updates()

    def start_crypto_updates(self):
        """
        Start periodic updates for cryptocurrency data.
        """
        # Fetch data immediately for the first time
        self.fetch_and_update_crypto_data()

        # Schedule periodic updates
        self.update_timeout_id = GLib.timeout_add_seconds(
            self.update_time, self.fetch_and_update_crypto_data
        )

    def fetch_and_update_crypto_data(self):
        """
        Fetch cryptocurrency data and update the labels.
        """
        fetched_prices = self.fetch_prices(
            ["XRPUSDT", "BTCUSDT", "HBARUSDT", "VETUSDT"]
        )
        self.prices.update(fetched_prices)  # Update stored prices
        self.update_labels()  # Update labels with the latest prices

        # Return True to keep the timeout active
        return True

    def fetch_prices(self, symbols):
        """
        Fetch the current prices of multiple cryptocurrencies using the Binance API.

        Args:
            symbols (list): List of trading pair symbols (e.g., ["XRPUSDT", "BTCUSDT"]).

        Returns:
            dict: A dictionary mapping symbols to their formatted prices.
        """
        url = "https://api.binance.com/api/v3/ticker/price"
        prices = {}

        for symbol in symbols:
            params = {"symbol": symbol}
            try:
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                price = float(data["price"])
                prices[symbol] = self.format_price(price, symbol)
            except requests.exceptions.RequestException as e:
                print(f"Error fetching {symbol} price: {e}")
                prices[symbol] = "Price not available"

        return prices

    def format_price(self, price, symbol):
        """
        Format the price to display an extra decimal place for small values.
        Larger values are rounded to two decimal places. Bitcoin is formatted as "K" for thousands.

        Args:
            price (float): The price to format.
            symbol (str): The symbol of the cryptocurrency (e.g., "BTCUSDT").

        Returns:
            str: The formatted price as a string.
        """
        if price is None:
            return "Price not available"

        # Special handling for Bitcoin
        if symbol == "BTCUSDT":
            if price >= 1000:
                return f"{price / 1000:.2f}K"  # Format as "K" for thousands
            else:
                return f"{price:.2f}"

        if price < 0.1:  # Add an extra decimal place for small values
            return f"{price:.3f}"
        else:  # Round to two decimal places for larger values
            return f"{price:.2f}"

    def update_labels(self):
        """
        Update the labels in the popover with the fetched prices.
        """
        icons = {
            "XRPUSDT": "XRP     ",
            "BTCUSDT": "₿itcoin ",
            "HBARUSDT": "Hbar    ",
            "VETUSDT": "Vchain  ",
        }

        for symbol, price in self.prices.items():
            label = self.crypto_labels.get(symbol)
            if label:
                if price is None:
                    label.set_label(f"{icons[symbol]}: Fetching...")
                    label.set_xalign(0.0)
                else:
                    label.set_label(f"{icons[symbol]}: ${price}")
                    label.set_xalign(0.0)

    def update_labels_run_once(self):
        self.update_labels()
        return False

    def open_popover_crypto(self, *_):
        """
        Handle opening the crypto popover.
        """
        if self.popover_crypto and self.popover_crypto.is_visible():
            self.popover_crypto.popdown()
        elif self.popover_crypto and not self.popover_crypto.is_visible():
            self.update_labels()
            self.popover_crypto.popup()
        else:
            # we need 100 ms to update labels
            # which is time enough to create popover for the first time
            GLib.timeout_add(100, self.update_labels_run_once)
            self.create_popover_crypto()

    def create_popover_crypto(self):
        """
        Create the crypto popover and populate it with labels.
        """
        # Create the popover
        self.popover_crypto = Gtk.Popover.new()
        self.popover_crypto.set_has_arrow(False)
        self.popover_crypto.connect("closed", self.popover_is_closed)
        self.popover_crypto.connect("notify::visible", self.popover_is_open)

        # Create a vertical box to hold the crypto data
        vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)

        # Add placeholder labels for each cryptocurrency
        cryptos = ["XRPUSDT", "BTCUSDT", "HBARUSDT", "VETUSDT"]
        icons = {"XRPUSDT": "X", "BTCUSDT": "₿", "HBARUSDT": "H", "VETUSDT": "V"}

        for crypto in cryptos:
            label = Gtk.Label(label=f"{icons[crypto]}: Fetching...")
            self.crypto_labels[crypto] = label
            vbox.append(label)

        # Set the box as the child of the popover
        self.popover_crypto.set_child(vbox)

        # Set the parent widget of the popover and display it
        self.popover_crypto.set_parent(self.menubutton_crypto)
        self.popover_crypto.popup()

    def popover_is_open(self, *_):
        """
        Callback when the popover is opened.
        """
        print("Crypto popover is open")

    def popover_is_closed(self, *_):
        """
        Callback when the popover is closed.
        """
        print("Crypto popover is closed")
