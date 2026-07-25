FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN groupadd --system --gid 1001 scraper \
    && useradd --system --uid 1001 --gid scraper --create-home scraper

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --requirement requirements.txt

COPY --chown=scraper:scraper src ./src
COPY --chown=scraper:scraper config ./config

RUN mkdir -p /app/data && chown -R scraper:scraper /app/data

USER scraper

CMD ["python", "-m", "imdb_scraper"]

FROM python:3.12-slim AS test

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --requirement requirements.txt \
    && pip install --no-cache-dir --requirement requirements-dev.txt

COPY src ./src
COPY tests ./tests
COPY pyproject.toml ./

CMD ["pytest", "-q"]
