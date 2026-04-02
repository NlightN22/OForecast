FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt ./
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir --no-compile -r requirements.txt && \
    find /usr/local -type d -name "__pycache__" -prune -exec rm -rf {} + && \
    find /usr/local -type f -name "*.pyc" -delete

COPY . .

EXPOSE 8000

CMD ["uvicorn", "ts_forecast.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
