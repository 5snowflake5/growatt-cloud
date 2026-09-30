FROM ghcr.io/home-assistant/base:3.22

WORKDIR /app

RUN apk add --no-cache \
    python3 \
    py3-paho-mqtt \
    tzdata

COPY api.py /app/api.py
COPY sensors.py /app/sensors.py
COPY mqtt_ha.py /app/mqtt_ha.py
COPY discovery_purge.py /app/discovery_purge.py
COPY ha_env.py /app/ha_env.py
COPY growatt_cloud.py /app/growatt_cloud.py

ENV PYTHONUNBUFFERED=1

CMD ["python3", "-u", "/app/growatt_cloud.py"]
