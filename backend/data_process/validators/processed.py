from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ValidationError

from data_process.schemas.processed import AllCardsPayload, CategoryPayload, KeywordsPayload
from data_process.transforms.process_hearthstonejson import CATEGORY_FILES
from data_process.utils.io import load_json, write_text
from data_process.utils.paths import PROCESSED_ROOT


class ValidationReport(BaseModel):
    ok: bool
    errors: list[str]

    def to_text(self) -> str:
        if self.ok:
            return "ok: true\n"
        return "ok: false\n" + "\n".join(f"- {error}" for error in self.errors) + "\n"


def validate_processed_files(processed_dir: Path = PROCESSED_ROOT) -> ValidationReport:
    errors: list[str] = []

    try:
        all_cards = AllCardsPayload.model_validate(load_json(processed_dir / "all.json"))
    except (FileNotFoundError, ValidationError, TypeError) as e:
        return ValidationReport(ok=False, errors=[f"all.json: {e}"])

    try:
        KeywordsPayload.model_validate(load_json(processed_dir / "keywords.json"))
    except (FileNotFoundError, ValidationError, TypeError) as e:
        errors.append(f"keywords.json: {e}")

    for card_id, card in all_cards.cards.items():
        if card.id != card_id:
            errors.append(f"all.json: key {card_id} does not match card.id {card.id}")
        if not card.image.startswith("../raw/hearthstonejson/asset/cards/"):
            errors.append(f"all.json: {card_id} image path is outside HearthstoneJSON raw assets")

    for category, filename in CATEGORY_FILES.items():
        try:
            payload = CategoryPayload.model_validate(load_json(processed_dir / filename))
        except (FileNotFoundError, ValidationError, TypeError) as e:
            errors.append(f"{filename}: {e}")
            continue

        if payload.category != category:
            errors.append(f"{filename}: category is {payload.category}, expected {category}")

        for card_id in payload.ids:
            card = all_cards.cards.get(card_id)
            if card is None:
                errors.append(f"{filename}: missing card id {card_id} in all.json")
            elif card.category != category:
                errors.append(f"{filename}: {card_id} has category {card.category}")

    return ValidationReport(ok=not errors, errors=errors)


def write_validation_report(processed_dir: Path = PROCESSED_ROOT) -> ValidationReport:
    report = validate_processed_files(processed_dir)
    write_text(processed_dir / "validation_report.txt", report.to_text())
    return report


def assert_valid_processed_files(processed_dir: Path = PROCESSED_ROOT) -> None:
    report = validate_processed_files(processed_dir)
    if not report.ok:
        raise ValueError(report.to_text())
