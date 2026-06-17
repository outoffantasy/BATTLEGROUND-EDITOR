from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "2026-06-17-v1"
ART_URL_TEMPLATE = "https://art.hearthstonejson.com/v1/render/latest/{locale}/256x/{card_id}.png"


def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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


def download_file(url: str, output_path: Path, retries: int = 3, timeout: int = 60) -> bool:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "battleground-editor/0.1"},
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(response.read())
            return True
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code == 404:
                print(f"[404] Missing image: {url}")
                return False
            print(f"[HTTP {e.code}] attempt {attempt}/{retries}: {url}")
        except Exception as e:
            last_error = e
            print(f"[ERROR] attempt {attempt}/{retries}: {url} ({e})")

        if attempt < retries:
            time.sleep(2 * attempt)

    print(f"[FAILED] {url}: {last_error}")
    return False


def main() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    default_input = backend_root / "data" / "processed" / "all.json"
    default_out = backend_root / "data" / "asset" / "cards"

    parser = argparse.ArgumentParser(description="Download processed Battlegrounds card images.")
    parser.add_argument("--input", default=default_input, type=Path, help="Path to processed all.json")
    parser.add_argument("--out-dir", default=default_out, type=Path, help="Output folder for card images")
    parser.add_argument("--locale", default="enUS", help="HearthstoneJSON art locale, e.g. enUS or zhCN")
    parser.add_argument("--force", action="store_true", help="Re-download images even when files already exist")
    parser.add_argument("--sleep", default=0.05, type=float, help="Delay between downloads in seconds")
    args = parser.parse_args()

    all_data = load_json(args.input)
    if not isinstance(all_data, dict):
        raise TypeError(f"Processed all.json must be an object: {args.input}")

    card_ids = collect_card_ids(all_data)
    downloaded = 0
    skipped = 0
    failed = 0

    print(f"download_card_assets.py version: {SCRIPT_VERSION}")
    print(f"Images to check: {len(card_ids)}")
    print(f"Output folder: {args.out_dir}")

    for card_id in card_ids:
        output_path = args.out_dir / f"{card_id}.png"
        if output_path.exists() and not args.force:
            skipped += 1
            continue

        url = ART_URL_TEMPLATE.format(locale=args.locale, card_id=card_id)
        if download_file(url, output_path):
            downloaded += 1
        else:
            failed += 1
        if args.sleep > 0:
            time.sleep(args.sleep)

    print(f"Downloaded: {downloaded}")
    print(f"Skipped: {skipped}")
    print(f"Failed: {failed}")


if __name__ == "__main__":
    main()
