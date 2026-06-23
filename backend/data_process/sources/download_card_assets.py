from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from data_process.utils.io import load_json, write_text
from data_process.utils.paths import PROCESSED_ROOT, RAW_HEARTHSTONEJSON_ASSET_ROOT, RAW_HEARTHSTONEJSON_CARD_ASSET_ROOT

SCRIPT_VERSION = "2026-06-17-v1"
ART_URL_TEMPLATE = "https://art.hearthstonejson.com/v1/render/latest/{locale}/256x/{card_id}.png"
RESULT_FILE = "download_assets_result.txt"


def collect_card_ids(all_data: dict[str, Any]) -> list[str]:
    cards = all_data.get("cards")
    if not isinstance(cards, dict):
        raise TypeError("all.json must contain an object field named 'cards'")

    ids: set[str] = set()
    for card_id, card in cards.items():
        if isinstance(card_id, str) and card_id:
            ids.add(card_id)
        if not isinstance(card, dict):
            continue

        hero_power = card.get("heroPower")
        if isinstance(hero_power, dict) and isinstance(hero_power.get("id"), str):
            ids.add(hero_power["id"])

        golden = card.get("golden")
        if isinstance(golden, dict) and isinstance(golden.get("id"), str):
            ids.add(golden["id"])

    return sorted(ids)


def download_file(url: str, output_path: Path, retries: int = 3, timeout: int = 60) -> tuple[bool, str | None]:
    last_error: str | None = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "battleground-editor/0.1"},
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(response.read())
            return True, None
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}"
            if e.code == 404:
                print(f"[404] Missing image: {url}")
                return False, last_error
            if e.code == 429 and attempt < retries:
                print(f"[429] Rate limited; waiting 60s before retry {attempt + 1}/{retries}: {url}")
                time.sleep(60)
                continue
            print(f"[HTTP {e.code}] attempt {attempt}/{retries}: {url}")
        except Exception as e:
            last_error = str(e)
            print(f"[ERROR] attempt {attempt}/{retries}: {url} ({e})")

        if attempt < retries:
            time.sleep(2 * attempt)

    print(f"[FAILED] {url}: {last_error}")
    return False, last_error


def build_result_text(
    total: int,
    downloaded: int,
    skipped: int,
    failed: int,
    failed_items: list[tuple[str, str, str | None]],
) -> str:
    lines = [
        f"total: {total}",
        f"downloaded: {downloaded}",
        f"skipped: {skipped}",
        f"failed: {failed}",
    ]
    if failed_items:
        lines.append("")
        lines.append("failed images:")
        for card_id, url, error in failed_items:
            lines.append(f"{card_id}: {error or 'unknown error'} - {url}")
    return "\n".join(lines) + "\n"


def print_progress(current: int, total: int, downloaded: int, skipped: int, failed: int) -> None:
    width = 30
    filled = int(width * current / total) if total else width
    bar = "#" * filled + "-" * (width - filled)
    percent = int(100 * current / total) if total else 100
    sys.stdout.write(
        f"\r[{bar}] {percent:3d}% {current}/{total} "
        f"downloaded={downloaded} skipped={skipped} failed={failed}"
    )
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> None:
    default_input = PROCESSED_ROOT / "all.json"
    default_out = RAW_HEARTHSTONEJSON_CARD_ASSET_ROOT
    default_result = RAW_HEARTHSTONEJSON_ASSET_ROOT / RESULT_FILE

    parser = argparse.ArgumentParser(description="Download processed Battlegrounds card images.")
    parser.add_argument("--input", default=default_input, type=Path, help="Path to processed all.json")
    parser.add_argument("--out-dir", default=default_out, type=Path, help="Output folder for card images")
    parser.add_argument("--result", default=default_result, type=Path, help="Path to write download result summary")
    parser.add_argument("--locale", default="enUS", help="HearthstoneJSON art locale, e.g. enUS or zhCN")
    parser.add_argument("--force", action="store_true", help="Re-download images even when files already exist")
    parser.add_argument("--sleep", default=0.0, type=float, help="Delay between downloads in seconds")
    parser.add_argument("--timeout", default=30, type=int, help="Per-request timeout in seconds")
    args = parser.parse_args(argv)

    all_data = load_json(args.input)
    if not isinstance(all_data, dict):
        raise TypeError(f"Processed all.json must be an object: {args.input}")

    card_ids = collect_card_ids(all_data)
    downloaded = 0
    skipped = 0
    failed = 0
    failed_items: list[tuple[str, str, str | None]] = []

    print(f"download_card_assets.py version: {SCRIPT_VERSION}")
    print(f"Images to check: {len(card_ids)}")
    print(f"Input file: {args.input}")
    print(f"Output folder: {args.out_dir}")
    print(f"Result file: {args.result}")
    print(f"Locale: {args.locale}")
    print(f"Timeout: {args.timeout}s")

    total = len(card_ids)
    for index, card_id in enumerate(card_ids, start=1):
        output_path = args.out_dir / f"{card_id}.png"
        if output_path.exists() and not args.force:
            skipped += 1
            print_progress(index, total, downloaded, skipped, failed)
            continue

        url = ART_URL_TEMPLATE.format(locale=args.locale, card_id=card_id)
        success, error = download_file(url, output_path, timeout=args.timeout)
        if success:
            downloaded += 1
        else:
            failed += 1
            failed_items.append((card_id, url, error))
            print()
            print(f"[FAILED IMAGE] {card_id}: {error or 'unknown error'} - {url}")
        print_progress(index, total, downloaded, skipped, failed)
        if args.sleep > 0:
            time.sleep(args.sleep)

    print()
    print(f"Downloaded: {downloaded}")
    print(f"Skipped: {skipped}")
    print(f"Failed: {failed}")
    if failed_items:
        print("Failed images:")
        for card_id, url, error in failed_items:
            print(f"  {card_id}: {error or 'unknown error'} - {url}")
    write_text(
        args.result,
        build_result_text(
            total=len(card_ids),
            downloaded=downloaded,
            skipped=skipped,
            failed=failed,
            failed_items=failed_items,
        ),
    )
    print(f"Result file: {args.result}")


if __name__ == "__main__":
    main()
