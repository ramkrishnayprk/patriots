FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    COVERAGE_FILE=/tmp/.coverage

WORKDIR /app

RUN groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --create-home app

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --requirement requirements.txt

COPY --chown=app:app app ./app
COPY --chown=app:app config ./config
COPY --chown=app:app wsgi.py ./
RUN mkdir -p /app/data /models && chown -R app:app /app/data /models

FROM base AS runtime
USER app
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "120", "wsgi:app"]

FROM base AS test
COPY requirements-dev.txt .
RUN pip install --requirement requirements-dev.txt
COPY --chown=app:app tests ./tests
COPY --chown=app:app pyproject.toml ./
USER app
CMD ["pytest", "-q"]
