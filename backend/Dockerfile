FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    MODEL_DIR=/app/models/bias_correction \
    OPERATIONAL_MODEL_PATH=/app/models/operational_forecast/model_bundle.joblib \
    BMD_STATIONS_JSON=/app/data/processed/bmd_station_coordinates_35.json \
    BMD_TIMESERIES_DIR=/app/data/processed/bmd_stations_3hourly \
    NASA_STATION_TIMESERIES_DIR=/app/data/processed/nasa_station_data/3h_picked

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY app ./app
COPY data ./data
COPY models ./models

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).read()"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
