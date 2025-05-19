def current_compositor(client_instance):
    if "wayfire" in client_instance.sock.client.getpeername():
        return "wayfire"

    if "sway" in client_instance.sock.client.getpeername():
        return "sway"


def translate_ipc(ev, ipc_server_instance):
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
