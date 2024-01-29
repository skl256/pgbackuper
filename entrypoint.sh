#! /bin/sh

echo "${INTERVAL_CRON}"" cd /opt/app && python3 main.py >> /dev/stdout" | crontab -

crond -f
