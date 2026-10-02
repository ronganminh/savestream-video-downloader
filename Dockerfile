FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install .

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8787
CMD ["uvicorn", "savestream_downloader.main:app", "--host", "0.0.0.0", "--port", "8787"]
