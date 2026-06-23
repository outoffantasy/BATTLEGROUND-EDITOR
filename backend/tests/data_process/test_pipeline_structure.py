from __future__ import annotations

import json
from pathlib import Path

from data_process.schemas.processed import AllCardsPayload
from data_process.transforms.process_hearthstonejson import CATEGORY_FILES
from data_process.utils.paths import RAW_HEARTHSTONEJSON_CARD_ASSET_ROOT, hearthstonejson_cards_path
from data_process.validators.processed import validate_processed_files


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def minimal_all_payload() -> dict:
    return {
        "source": "hearthstonejson",
        "build": "latest",
        "generatedAt": "2026-06-23T00:00:00+00:00",
        "cards": {
            "CARD_001": {
                "id": "CARD_001",
                "category": "heroes",
                "name": {"enUS": "Test", "zhCN": "测试"},
                "text": {"enUS": "Text", "zhCN": "文本"},
                "image": "../raw/hearthstonejson/asset/cards/CARD_001.png",
            }
        },
    }


def write_minimal_processed_dir(path: Path) -> None:
    write_json(path / "all.json", minimal_all_payload())
    write_json(path / "keywords.json", {"keywords": [{"id": "battlecry", "label": "Battlecry"}]})
    for category, filename in CATEGORY_FILES.items():
        ids = ["CARD_001"] if category == "heroes" else []
        write_json(path / filename, {"category": category, "ids": ids})


def test_hearthstonejson_paths_do_not_use_latest() -> None:
    assert "latest" not in hearthstonejson_cards_path("enUS").parts
    assert hearthstonejson_cards_path("enUS").as_posix().endswith("raw/hearthstonejson/enUS/cards.json")
    assert RAW_HEARTHSTONEJSON_CARD_ASSET_ROOT.as_posix().endswith("raw/hearthstonejson/asset/cards")


def test_minimal_all_payload_matches_schema() -> None:
    payload = AllCardsPayload.model_validate(minimal_all_payload())
    assert payload.cards["CARD_001"].category == "heroes"


def test_validator_fails_when_category_references_missing_card(tmp_path: Path) -> None:
    write_minimal_processed_dir(tmp_path)
    write_json(tmp_path / "heroes.json", {"category": "heroes", "ids": ["MISSING_CARD"]})

    report = validate_processed_files(tmp_path)

    assert not report.ok
    assert any("MISSING_CARD" in error for error in report.errors)
