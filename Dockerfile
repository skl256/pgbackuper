FROM python:3.12.1-alpine3.19

ENV INTERVAL_CRON="45 23 * * *"

WORKDIR /opt/app

COPY requirements.txt .

RUN apk add git postgresql16-client && \
    pip install --requirement requirements.txt && \
    rm -rf /var/cache/apk/*

RUN git clone https://code.nikolay1.ru/nikolays_libs/getenv2.git

RUN mkdir -m 700 -p /var/pgbackup

COPY --chmod=764 entrypoint.sh .

COPY *.py .

ENTRYPOINT ["./entrypoint.sh"]
