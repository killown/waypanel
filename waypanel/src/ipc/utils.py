def current_compositor(client_instance):
    """Determine the active compositor by inspecting the socket connection name.
    Identifies whether the connected compositor is Wayfire or Sway based on
    the peer name of the socket connection.

    Args:
        client_instance: An object containing the socket connection information.

    Returns:
        str: The name of the detected compositor ("wayfire" or "sway"), or None if neither is detected.
    """
    if "wayfire" in client_instance.sock.client.getpeername():
        return "wayfire"

    if "sway" in client_instance.sock.client.getpeername():
        return "sway"


def translate_ipc(ev, ipc_server_instance):
    """Translate Sway IPC events into standardized event names for internal handling.
    Converts raw Sway IPC events into a unified format used by the application,
    allowing consistent processing across different compositors like Wayfire and Sway.

    Args:
        ev (dict): Raw event data from Sway IPC.
        ipc_server_instance: Reference to the IPC server instance for compositor context.

    Returns:
        dict: A translated event dictionary with standardized event names and associated data,
              or None if the event could not be translated.
    """
    translated_signal = None
    event = None
    client = ipc_server_instance.ipc

    if current_compositor(client) == "sway":
        ipc_server_instance.compositor = "sway"
        if "container" in ev:
            if (
                ev["container"]["type"] == "con"
                or ev["container"]["type"] == "floating_con"
            ):
                if ev["change"] == "focus":
                    translated_signal = "view-focused"
                    event = {"event": translated_signal, "view": ev["container"]}
                if ev["change"] == "new":
                    translated_signal = "view-mapped"
                    event = {"event": translated_signal, "view": ev["container"]}
                if ev["change"] == "title":
                    translated_signal = "view-title-changed"
                    event = {"event": translated_signal, "view": ev["container"]}
                if ev["change"] == "close":
                    translated_signal = "view-closed"
                    event = {"event": translated_signal, "view": ev["container"]}

        if "old" in ev:
            if ev["change"] == "focus" and ev["old"] is not None:
                if ev["old"]["type"] == "workspace":
                    translated_signal = "workspace-lose-focus"
                    event = {"event": translated_signal, "workspace": ev["old"]}
        return event

    if current_compositor(client) == "wayfire":
        ipc_server_instance.compositor = "wayfire"
        return ev  # no translation needed
