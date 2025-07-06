from wayfire import WayfireSocket
from wayfire.extra.ipc_utils import WayfireUtils

STATE_FILE = "/tmp/.toggle_maximized_state"

sock = WayfireSocket()
utils = WayfireUtils(sock)

view = sock.get_focused_view()
view_geometry = view["geometry"]
view_width = view_geometry["width"]
view_height = view_geometry["height"]

output = sock.get_focused_output()
workarea = output["workarea"]
screen_width = workarea["width"]
screen_height = workarea["height"]

# Check if already maximized (>90% of screen)
is_maximized = (view_width / screen_width) > 0.9 and (view_height / screen_height) > 0.9

try:
    with open(STATE_FILE, "r") as f:
        current_state = f.read().strip() == "True"
except FileNotFoundError:
    current_state = False

# Set new_state based on whether it's already maximized
new_state = False if is_maximized else not current_state

# save new state
with open(STATE_FILE, "w") as f:
    f.write(str(new_state))

utils.tile_maximize_all_from_active_workspace(new_state)
