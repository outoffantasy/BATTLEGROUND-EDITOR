from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from data_process.exporters.frontend import load_frontend_payload
from data_process.sources.download_card_assets import main as download_assets_main
from data_process.sources.sync_raw_hearthstonejson import main as sync_raw_main
from data_process.transforms.process_hearthstonejson import main as process_hearthstonejson_main
from data_process.validators.processed import write_validation_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Battleground Editor data pipeline.")
    parser.add_argument("--sync-raw", action="store_true", help="Download raw HearthstoneJSON cards first")
    parser.add_argument("--download-assets", action="store_true", help="Download card images after processing")
    args = parser.parse_args()

    if args.sync_raw:
        sync_raw_main([])

    process_hearthstonejson_main([])
    report = write_validation_report()
    if not report.ok:
        raise ValueError(report.to_text())

    load_frontend_payload()

    if args.download_assets:
        download_assets_main([])

    print("Pipeline finished.")


if __name__ == "__main__":
    main()
