from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from data_process.utils.io import write_json
from data_process.utils.paths import RAW_HEARTHSTONEJSON_ROOT


# 爬数据的网址
BASE_URL = "https://api.hearthstonejson.com/v1/latest"
DEFAULT_OUT = RAW_HEARTHSTONEJSON_ROOT

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def download_json(url: str, retries: int = 3, timeout: int = 60) -> tuple[list | dict, str]:
    """
    Download JSON from url.
    Returns:
      (parsed_json, final_url_after_redirect)
    """
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "bg-editor-mvp/0.1"
                },
            )

            with urllib.request.urlopen(request, timeout=timeout) as response:
                final_url = response.geturl()
                raw_bytes = response.read()
                data = json.loads(raw_bytes.decode("utf-8"))
                return data, final_url

        except urllib.error.HTTPError as e:
            last_error = e

            # If server says "too many requests", wait a bit.
            if e.code == 429:
                retry_after = e.headers.get("Retry-After")
                wait_seconds = int(retry_after) if retry_after and retry_after.isdigit() else 60
                print(f"[429] Too many requests. Waiting {wait_seconds}s...")
                time.sleep(wait_seconds)
            else:
                print(f"[HTTP {e.code}] {url}")

        except Exception as e:
            last_error = e
            print(f"[ERROR] attempt {attempt}/{retries}: {e}")

        if attempt < retries:
            time.sleep(2 * attempt)

    raise RuntimeError(f"Failed to download {url}") from last_error


def infer_hsbg_version_from_final_url(final_url: str) -> str | None:
    """
    返回爬下来的数据的 hearthstone battleground 的版本号
    Example final_url:
      https://api.hearthstonejson.com/v1/123456/zhCN/cards.json

    Return:
      123456
    """
    parts = final_url.split("/")
    try:
        v1_index = parts.index("v1")
        return parts[v1_index + 1]
    except Exception:
        return None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Download raw HearthstoneJSON card data."
    )

    parser.add_argument(
        "--locales",
        nargs="+",
        default=["zhCN", "enUS"],
        help="Locales to download, e.g. zhCN enUS",
    )

    parser.add_argument(
        "--file",
        default="cards.json",
        help="File to download, usually cards.json",
    )

    parser.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help="Output folder",
    )

    args = parser.parse_args(argv)

    out_root = Path(args.out)
    meta = {
        "source": "hearthstonejson",
        "file": args.file,
        "startedAt": utc_now(),
        "downloads": [],
    }

    for locale in args.locales:
        url = f"{BASE_URL}/{locale}/{args.file}"

        print(f"Downloading {url}")
        data, final_url = download_json(url)

        hsbg_version = infer_hsbg_version_from_final_url(final_url)
        output_path = out_root / locale / args.file

        write_json(output_path, data)

        item = {
            "locale": locale,
            "file": args.file,
            "url": url,
            "finalUrl": final_url,
            "hsbg_version": hsbg_version,
            "outputPath": str(output_path),
            "itemCount": len(data) if isinstance(data, list) else None,
            "downloadedAt": utc_now(),
        }

        meta["downloads"].append(item)

        print(f"Saved: {output_path}")
        print(f"Items: {item['itemCount']}")
        print(f"hsbg_version: {hsbg_version}")
        print()

        # Be polite. This is not urgent.
        time.sleep(1)

    meta["finishedAt"] = utc_now()

    meta_path = out_root / "meta.json"
    write_json(meta_path, meta)

    print(f"Meta saved: {meta_path}")


if __name__ == "__main__":
    main()
