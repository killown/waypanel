#!/usr/bin/env python3
from subprocess import check_output as o
from notifypy import Notify

status = o("mullvad status".split()).decode()

# Create a notification object
notification = Notify()

# Set the title and message for the notification
notification.title = "Mullvad Status"
notification.message = status

# Display the notificationication
notification.send()
