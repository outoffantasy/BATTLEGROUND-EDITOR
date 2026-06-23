from __future__ import annotations

from pathlib import Path


DATA_PROCESS_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = DATA_PROCESS_ROOT.parent
DATA_ROOT = BACKEND_ROOT / "data"

RAW_ROOT = DATA_ROOT / "raw"
PROCESSED_ROOT = DATA_ROOT / "processed"

RAW_HEARTHSTONEJSON_ROOT = RAW_ROOT / "hearthstonejson"
RAW_HEARTHSTONEJSON_ASSET_ROOT = RAW_HEARTHSTONEJSON_ROOT / "asset"
RAW_HEARTHSTONEJSON_CARD_ASSET_ROOT = RAW_HEARTHSTONEJSON_ASSET_ROOT / "cards"


def hearthstonejson_cards_path(locale: str, filename: str = "cards.json") -> Path:
    return RAW_HEARTHSTONEJSON_ROOT / locale / filename
