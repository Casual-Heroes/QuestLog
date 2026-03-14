#!/bin/bash
# Auto-set sticker picker widget for new Matrix users
# Runs from cron as root - no token or password needed
python3 /srv/ch-webserver/set_widget_all_users.py >> /var/log/matrix_widget_setup.log 2>&1
