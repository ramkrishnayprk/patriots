from __future__ import annotations

import argparse
import json
import sys

from imdb_scraper.config import Settings
from imdb_scraper.pipeline import run_pipeline
from imdb_scraper.urls import load_seed_urls


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Standalone, seed-driven IMDb metadata extraction pipeline."
    )
    parser.add_argument(
        "--run-id",
        help="Resume or create a named output run directory.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate configuration and seed URLs without network requests.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
        seeds = load_seed_urls(settings.seeds_path, settings.max_titles)
        if args.validate_only:
            print(
                json.dumps(
                    {
                        "valid": True,
                        "seed_count": len(seeds),
                        "network_request_made": False,
                    },
                    indent=2,
                )
            )
            return 0
        manifest = run_pipeline(settings, run_id=args.run_id)
        print(json.dumps(manifest, indent=2))
        return 0
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
