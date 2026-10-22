FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# GDAL/GEOS/PROJ for django.contrib.gis; SpatiaLite for the in-memory test DB
RUN apt-get update \
    && apt-get install -y --no-install-recommends gdal-bin libgdal-dev libgeos-dev libproj-dev binutils libsqlite3-mod-spatialite \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.lock requirements.txt requirements-test.txt ./
RUN pip install -r requirements.lock

COPY . .

EXPOSE 8000

CMD ["gunicorn", "picadailys.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--worker-class", "gevent", "--timeout", "120"]
