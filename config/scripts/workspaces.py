import subprocess
import json
import sys

w = subprocess.check_output(["hyprctl", "-j", "workspaces"]).decode()
data = json.loads(w)
workspaces = []
activeworkspace = subprocess.check_output(["hyprctl", "-j", "activeworkspace"]).decode()
activeworkspace = json.loads(activeworkspace)
activeworkspace = activeworkspace["name"]
exclude = ["9"]
for i in data:
    if i["name"] in exclude:
        continue
    workspaces.append(i["name"])

workspace_jump = workspaces.index(activeworkspace)
wlen = len(workspaces) - 1

if wlen == workspace_jump:
    workspace_jump = 0

workspace_name = workspaces[workspace_jump]
if workspace_name == activeworkspace:
    try:
        workspace_name = workspaces[workspace_jump + 1]
    except IndexError:
        print("create a new workspace to switch, there is only one")
        sys.exit()


print(workspace_name, workspaces, workspace_jump)
subprocess.call(["hyprctl", "dispatch", "workspace", "{0}".format(workspace_name)])
