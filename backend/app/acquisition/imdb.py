import csv
import gzip
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import Settings

DATASET_NAMES = (
    "title.basics.tsv.gz",
    "title.ratings.tsv.gz",
    "title.crew.tsv.gz",
    "title.principals.tsv.gz",
    "name.basics.tsv.gz",
    "title.akas.tsv.gz",
)


def create_download_session(user_agent: str) -> requests.Session:
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=2,
        status_forcelist=(408, 425, 429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount(
        "https://",
        HTTPAdapter(max_retries=retry, pool_connections=2, pool_maxsize=2),
    )
    session.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip"})
    return session


def download_datasets(
    settings: Settings,
    *,
    snapshot_date: str,
    session: requests.Session | None = None,
) -> dict[str, Path]:
    """Download one dated IMDb snapshot, reusing complete local files."""
    destination = settings.data_dir / "sources" / "imdb" / snapshot_date
    destination.mkdir(parents=True, exist_ok=True)
    session = session or create_download_session(settings.user_agent)
    paths = {}
    for name in DATASET_NAMES:
        path = destination / name
        if not path.is_file() or path.stat().st_size == 0:
            _download_file(
                session,
                f"{settings.imdb_dataset_base_url}/{name}",
                path,
                timeout=settings.request_timeout_seconds,
                chunk_bytes=settings.download_chunk_bytes,
            )
        paths[name] = path
    return paths


def assemble_imdb_records(
    paths: dict[str, Path],
    *,
    year: int,
    title_types: tuple[str, ...],
    include_adult: bool,
    region_preference: str,
    top_cast_limit: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Stream IMDb files and join only rows referenced by filtered movie IDs."""
    records: dict[str, dict[str, Any]] = {}
    for row in _rows(paths["title.basics.tsv.gz"]):
        if row.get("titleType") not in title_types:
            continue
        if row.get("startYear") != str(year):
            continue
        if not include_adult and row.get("isAdult") == "1":
            continue
        imdb_id = row["tconst"]
        records[imdb_id] = {
            "imdb_id": imdb_id,
            "title": _nullable(row.get("primaryTitle")) or imdb_id,
            "original_title": _nullable(row.get("originalTitle")),
            "year": year,
            "runtime": _integer_or_none(row.get("runtimeMinutes")),
            "genres": _split_ids(row.get("genres")),
            "imdb_rating": None,
            "imdb_votes": None,
            "directors": [],
            "writers": [],
            "top_cast": [],
            "_director_ids": [],
            "_writer_ids": [],
            "_cast": [],
        }

    kept_ids = set(records)
    for row in _rows(paths["title.ratings.tsv.gz"]):
        record = records.get(row.get("tconst", ""))
        if record is not None:
            record["imdb_rating"] = _float_or_none(row.get("averageRating"))
            record["imdb_votes"] = _integer_or_none(row.get("numVotes"))

    referenced_names: set[str] = set()
    for row in _rows(paths["title.crew.tsv.gz"]):
        record = records.get(row.get("tconst", ""))
        if record is None:
            continue
        record["_director_ids"] = _split_ids(row.get("directors"))
        record["_writer_ids"] = _split_ids(row.get("writers"))
        referenced_names.update(record["_director_ids"])
        referenced_names.update(record["_writer_ids"])

    cast_by_title: dict[str, list[tuple[int, str, str | None]]] = {}
    for row in _rows(paths["title.principals.tsv.gz"]):
        imdb_id = row.get("tconst", "")
        if imdb_id not in kept_ids or row.get("category") not in {
            "actor",
            "actress",
            "self",
        }:
            continue
        name_id = row.get("nconst", "")
        if not name_id:
            continue
        cast_by_title.setdefault(imdb_id, []).append(
            (
                _integer_or_none(row.get("ordering")) or 9999,
                name_id,
                _nullable(row.get("characters")),
            )
        )
        referenced_names.add(name_id)
    for imdb_id, values in cast_by_title.items():
        records[imdb_id]["_cast"] = sorted(values)[:top_cast_limit]

    regional_titles: dict[str, tuple[int, str]] = {}
    alternate_titles: dict[str, set[str]] = {}
    for row in _rows(paths["title.akas.tsv.gz"]):
        imdb_id = row.get("titleId", "")
        if imdb_id not in kept_ids:
            continue
        title = _nullable(row.get("title"))
        if not title:
            continue
        alternate_titles.setdefault(imdb_id, set()).add(title)
        region = row.get("region")
        language = row.get("language")
        score = 2 if region == region_preference else 1 if language == "en" else 0
        previous = regional_titles.get(imdb_id)
        if previous is None or score > previous[0]:
            regional_titles[imdb_id] = (score, title)

    names = {}
    if referenced_names:
        for row in _rows(paths["name.basics.tsv.gz"]):
            name_id = row.get("nconst", "")
            if name_id in referenced_names:
                names[name_id] = _nullable(row.get("primaryName")) or name_id

    for imdb_id, record in records.items():
        regional = regional_titles.get(imdb_id)
        if regional and regional[0] > 0:
            record["title"] = regional[1]
        excluded_titles = {
            value
            for value in (record.get("title"), record.get("original_title"))
            if value
        }
        record["akas"] = sorted(
            alternate_titles.get(imdb_id, set()) - excluded_titles
        )[:50]
        record["directors"] = [
            names.get(name_id, name_id) for name_id in record.pop("_director_ids")
        ]
        record["writers"] = [
            names.get(name_id, name_id) for name_id in record.pop("_writer_ids")
        ]
        record["top_cast"] = [
            {
                "name": names.get(name_id, name_id),
                "characters": characters,
            }
            for _ordering, name_id, characters in record.pop("_cast")
        ]

    return list(records.values()), {
        "imdb_candidates": len(records),
        "referenced_people": len(referenced_names),
        "resolved_people": len(names),
    }


def _download_file(
    session: requests.Session,
    url: str,
    destination: Path,
    *,
    timeout: float,
    chunk_bytes: int,
) -> None:
    temporary_path = None
    try:
        with (
            session.get(url, timeout=timeout, stream=True) as response,
            NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".part",
                delete=False,
            ) as temporary,
        ):
            temporary_path = Path(temporary.name)
            response.raise_for_status()
            for block in response.iter_content(chunk_size=chunk_bytes):
                if block:
                    temporary.write(block)
            temporary.flush()
            os.fsync(temporary.fileno())
        if not temporary_path.stat().st_size:
            raise ValueError(f"IMDb returned an empty dataset for {destination.name}.")
        temporary_path.replace(destination)
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)


def _rows(path: Path) -> Iterator[dict[str, str]]:
    _set_maximum_csv_field_size()
    with gzip.open(path, mode="rt", encoding="utf-8", errors="replace", newline="") as source:
        yield from csv.DictReader(source, delimiter="\t")


def _set_maximum_csv_field_size() -> None:
    """Use the largest field size supported by the current Python platform."""
    limit = sys.maxsize
    while limit:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10
    raise RuntimeError("Unable to configure a supported CSV field size limit.")


def _nullable(value: str | None) -> str | None:
    return None if value in {None, "", r"\N"} else value


def _split_ids(value: str | None) -> list[str]:
    normalized = _nullable(value)
    return normalized.split(",") if normalized else []


def _integer_or_none(value: str | None) -> int | None:
    normalized = _nullable(value)
    try:
        return int(normalized) if normalized is not None else None
    except ValueError:
        return None


def _float_or_none(value: str | None) -> float | None:
    normalized = _nullable(value)
    try:
        return float(normalized) if normalized is not None else None
    except ValueError:
        return None
