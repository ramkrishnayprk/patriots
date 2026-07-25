FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        poppler-utils \
        texlive-latex-base \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /docs
