from __future__ import annotations

from data_process.sources.crawl_blizzard_bg import (
    extract_detail_text,
    infer_image_extension,
    parse_card_href,
)


def test_parse_card_href() -> None:
    assert parse_card_href("/battlegrounds/57944-a-f-kay") == ("57944", "a-f-kay")
    assert parse_card_href("https://hearthstone.blizzard.com/en-us/battlegrounds/57944-a-f-kay") == (
        "57944",
        "a-f-kay",
    )


def test_infer_image_extension() -> None:
    assert infer_image_extension("https://example.test/card", "image/png") == ".png"
    assert infer_image_extension("https://example.test/card.webp?x=1", None) == ".webp"
    assert infer_image_extension("https://example.test/card", "application/octet-stream") == ".img"


def test_extract_detail_text_uses_last_card_name() -> None:
    body_text = """Heroes
A. F. Kay
Stay Connected
Close
A. F. Kay

Skip your first two turns, then Discover a minion from Tier 3 and Tier 4.

Type: Hero
Set: Battlegrounds
Artist: Adam Byrne
"""

    detail = extract_detail_text(body_text, "A. F. Kay")

    assert detail is not None
    assert detail.startswith("A. F. Kay\n\nSkip your first two turns")
    assert "Set: Battlegrounds" in detail
