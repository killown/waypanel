#!/usr/bin/env python3
from subprocess import call
from notifypy import Notify


# Create a notification object
notification = Notify()

# Set the title and message for the notification
notification.title = "Mullvad Connecting"
notification.message = "The VPN is connected now"

# Display the notificationication
notification.send()

call("mullvad connect".split())
