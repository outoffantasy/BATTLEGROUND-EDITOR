from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "2026-06-17-v4-official-categories"

CATEGORY_FILES = {
    "heroes": "heroes.json",
    "minions": "minions.json",
    "quests": "quests.json",
    "rewards": "rewards.json",
    "anomalies": "anomalies.json",
    "spells": "spells.json",
    "trinkets": "trinkets.json",
    "timewarp": "timewarp.json",
}

STATS_FILE = "process_stats.txt"
OUTPUT_FILES = ["all.json", *CATEGORY_FILES.values(), "keywords.json", STATS_FILE]

KEYWORDS = [
    {"id": "battlecry", "label": "Battlecry", "tags": ["BATTLECRY"], "terms": ["Battlecry"]},
    {"id": "deathrattle", "label": "Deathrattle", "tags": ["DEATHRATTLE"], "terms": ["Deathrattle", "Deathrattles"]},
    {"id": "taunt", "label": "Taunt", "tags": ["TAUNT"], "terms": ["Taunt"]},
    {"id": "divine_shield", "label": "Divine Shield", "tags": ["DIVINE_SHIELD"], "terms": ["Divine Shield"]},
    {"id": "reborn", "label": "Reborn", "tags": ["REBORN"], "terms": ["Reborn"]},
    {"id": "magnetic", "label": "Magnetic", "tags": ["MAGNETIC"], "terms": ["Magnetic"]},
    {"id": "discover", "label": "Discover", "tags": ["DISCOVER"], "terms": ["Discover"]},
    {"id": "avenge", "label": "Avenge", "tags": ["AVENGE"], "terms": ["Avenge"]},
    {"id": "blood_gem", "label": "Blood Gem", "tags": ["BACON_BLOOD_GEM_TOOLTIP"], "terms": ["Blood Gem", "Blood Gems"]},
    {"id": "spellcraft", "label": "Spellcraft", "tags": ["BACON_SPELLCRAFT_ID"], "terms": ["Spellcraft"]},
    {"id": "rally", "label": "Rally", "tags": ["BACON_RALLY"], "terms": ["Rally"]},
    {"id": "buddy", "label": "Buddy", "tags": [], "terms": ["Buddy", "Buddies"]},
    {"id": "pass", "label": "Pass", "tags": ["BACON_PASS_TOOLTIP"], "terms": ["Pass"]},
    {"id": "refresh", "label": "Refresh", "tags": ["BACON_REFRESH_TOOLTIP"], "terms": ["Refresh", "Refreshed"]},
    {"id": "stealth", "label": "Stealth", "tags": ["STEALTH"], "terms": ["Stealth"]},
    {"id": "venomous", "label": "Venomous", "tags": ["VENOMOUS"], "terms": ["Venomous"]},
    {"id": "windfury", "label": "Windfury", "tags": ["WINDFURY"], "terms": ["Windfury"]},
]

TRIBE_DISPLAY = {
    "BEAST": "Beast",
    "DEMON": "Demon",
    "DRAGON": "Dragon",
    "ELEMENTAL": "Elemental",
    "MECHANICAL": "Mech",
    "MURLOC": "Murloc",
    "NAGA": "Naga",
    "PIRATE": "Pirate",
    "QUILBOAR": "Quilboar",
    "UNDEAD": "Undead",
    "TOTEM": "Totem",
    "DRAENEI": "Draenei",
    "ALL": "All",
}


def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def clear_outputs(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for filename in OUTPUT_FILES:
        path = out_dir / filename
        if path.exists():
            path.unlink()


def index_by_dbf(cards: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for card in cards:
        dbf_id = card.get("dbfId")
        if isinstance(dbf_id, int):
            result[dbf_id] = card
    return result


def loc(en_card: dict[str, Any], zh_card: dict[str, Any] | None, field: str) -> dict[str, str]:
    return {
        "enUS": en_card.get(field) or "",
        "zhCN": (zh_card or {}).get(field) or "",
    }


def image_path(card_id: Any) -> str:
    return f"../asset/cards/{card_id}.png"


def is_golden_variant(card: dict[str, Any]) -> bool:
    return isinstance(card.get("battlegroundsNormalDbfId"), int)


def is_timewarp(card: dict[str, Any]) -> bool:
    return card.get("battlegroundsTimewarpCard") is not None


def is_quest(card: dict[str, Any]) -> bool:
    card_id = str(card.get("id") or "")
    return card.get("type") == "SPELL" and re.search(r"(^|_)Quest_\d+", card_id) is not None


def is_internal(card: dict[str, Any]) -> bool:
    name = str(card.get("name") or "")
    card_id = str(card.get("id") or "")
    return (
        "[DNT]" in name
        or "Dummy FX" in name
        or "VFX Dummy" in name
        or "FX Dummy" in name
        or card_id.endswith("_FX")
    )


def get_tribes(card: dict[str, Any]) -> list[str]:
    races = card.get("races")
    if isinstance(races, list):
        return [str(r) for r in races]
    race = card.get("race")
    if isinstance(race, str):
        return [race]
    return []


def keyword_ids(card: dict[str, Any]) -> list[str]:
    raw_tags = set()
    for field in ("mechanics", "referencedTags"):
        values = card.get(field)
        if isinstance(values, list):
            raw_tags.update(str(v) for v in values)

    text_blob = " ".join(
        str(card.get(field) or "")
        for field in ("name", "text", "collectionText")
    )

    result: list[str] = []
    for keyword in KEYWORDS:
        tags = set(keyword["tags"])
        terms = keyword["terms"]
        matched = bool(raw_tags & tags)
        if not matched:
            matched = any(re.search(rf"\b{re.escape(term)}\b", text_blob, re.IGNORECASE) for term in terms)
        if keyword["id"] == "buddy" and card.get("isBattlegroundsBuddy") is True:
            matched = True
        if matched:
            result.append(str(keyword["id"]))
    return result


def add_if_present(target: dict[str, Any], key: str, value: Any) -> None:
    if value is not None and value != "":
        target[key] = value


def build_golden(
    card: dict[str, Any],
    zh_by_dbf: dict[int, dict[str, Any]],
    en_by_dbf: dict[int, dict[str, Any]],
) -> dict[str, Any] | None:
    golden_dbf_id = card.get("battlegroundsPremiumDbfId")
    if not isinstance(golden_dbf_id, int):
        return None

    golden_en = en_by_dbf.get(golden_dbf_id)
    if golden_en is None:
        return None

    golden_id = golden_en.get("id")
    golden_zh = zh_by_dbf.get(golden_dbf_id)
    result: dict[str, Any] = {
        "id": golden_id,
        "name": loc(golden_en, golden_zh, "name"),
        "text": loc(golden_en, golden_zh, "text"),
        "image": image_path(golden_id),
    }
    add_if_present(result, "attack", golden_en.get("attack"))
    add_if_present(result, "health", golden_en.get("health"))
    return result


def base_card(card: dict[str, Any], zh_by_dbf: dict[int, dict[str, Any]], category: str) -> dict[str, Any]:
    card_id = card.get("id")
    dbf_id = card.get("dbfId")
    zh_card = zh_by_dbf.get(dbf_id) if isinstance(dbf_id, int) else None

    result: dict[str, Any] = {
        "id": card_id,
        "category": category,
        "name": loc(card, zh_card, "name"),
        "text": loc(card, zh_card, "text"),
        "image": image_path(card_id),
    }
    keywords = keyword_ids(card)
    if keywords:
        result["keywords"] = keywords
    return result


def build_minion(
    card: dict[str, Any],
    zh_by_dbf: dict[int, dict[str, Any]],
    en_by_dbf: dict[int, dict[str, Any]],
    category: str,
) -> dict[str, Any]:
    result = base_card(card, zh_by_dbf, category)
    add_if_present(result, "tier", card.get("techLevel"))
    if category == "timewarp":
        add_if_present(result, "chronumCost", card.get("cost"))
    else:
        result["cost"] = 3
    add_if_present(result, "attack", card.get("attack"))
    add_if_present(result, "health", card.get("health"))
    tribes = get_tribes(card)
    if tribes:
        result["tribes"] = tribes
        result["tribesDisplay"] = [TRIBE_DISPLAY.get(t, t.title()) for t in tribes]
    golden = build_golden(card, zh_by_dbf, en_by_dbf)
    if golden is not None:
        result["golden"] = golden
    return result


def build_spell_like(card: dict[str, Any], zh_by_dbf: dict[int, dict[str, Any]], category: str) -> dict[str, Any]:
    result = base_card(card, zh_by_dbf, category)
    add_if_present(result, "tier", card.get("techLevel"))
    if category == "timewarp":
        add_if_present(result, "chronumCost", card.get("cost"))
    else:
        add_if_present(result, "cost", card.get("cost"))
    return result


def build_hero(
    card: dict[str, Any],
    zh_by_dbf: dict[int, dict[str, Any]],
    en_by_dbf: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    result = base_card(card, zh_by_dbf, "heroes")
    add_if_present(result, "health", card.get("health"))

    buddy_dbf_id = card.get("battlegroundsBuddyDbfId")
    if isinstance(buddy_dbf_id, int):
        buddy = en_by_dbf.get(buddy_dbf_id)
        if buddy is not None and buddy.get("id"):
            result["buddyId"] = buddy["id"]

    hero_power_dbf_id = card.get("heroPowerDbfId")
    if isinstance(hero_power_dbf_id, int):
        hero_power = en_by_dbf.get(hero_power_dbf_id)
        if hero_power is not None:
            hero_power_id = hero_power.get("id")
            hp_zh = zh_by_dbf.get(hero_power_dbf_id)
            embedded: dict[str, Any] = {
                "id": hero_power_id,
                "name": loc(hero_power, hp_zh, "name"),
                "text": loc(hero_power, hp_zh, "text"),
                "image": image_path(hero_power_id),
            }
            add_if_present(embedded, "cost", hero_power.get("cost"))
            result["heroPower"] = embedded
    return result


def card_sort_key(card: dict[str, Any]) -> tuple[Any, ...]:
    category = card.get("category")
    if category == "timewarp":
        price = card.get("chronumCost")
    else:
        price = card.get("cost")

    return (
        card.get("tier") if isinstance(card.get("tier"), int) else 999,
        price if isinstance(price, int) else 999,
        card.get("name", {}).get("enUS") or "",
        card.get("id") or "",
    )


def sorted_ids(cards_by_id: dict[str, dict[str, Any]], ids: list[str]) -> list[str]:
    return sorted(ids, key=lambda card_id: card_sort_key(cards_by_id[card_id]))


def build_stats_text(stats: dict[str, int]) -> str:
    lines = [f"all.json: {stats['all']}"]
    lines.extend(
        f"{CATEGORY_FILES[category]}: {stats[category]}"
        for category in CATEGORY_FILES
    )
    lines.append(f"keywords.json: {stats['keywords']}")
    return "\n".join(lines) + "\n"


def process(en_cards: list[dict[str, Any]], zh_cards: list[dict[str, Any]]) -> dict[str, Any]:
    en_by_dbf = index_by_dbf(en_cards)
    zh_by_dbf = index_by_dbf(zh_cards)
    generated_at = datetime.now(timezone.utc).isoformat()

    cards_by_id: dict[str, dict[str, Any]] = {}
    categories: dict[str, list[str]] = {category: [] for category in CATEGORY_FILES}
    timewarp_groups: dict[str, list[str]] = {"minions": [], "spells": []}

    def add_card(card_data: dict[str, Any]) -> None:
        card_id = card_data.get("id")
        if not isinstance(card_id, str) or not card_id:
            return
        cards_by_id[card_id] = card_data
        categories[card_data["category"]].append(card_id)

    for card in en_cards:
        if is_golden_variant(card) or is_internal(card):
            continue

        card_type = card.get("type")
        if is_timewarp(card):
            if card_type == "MINION":
                built = build_minion(card, zh_by_dbf, en_by_dbf, "timewarp")
                built["timewarpKind"] = "minion"
                add_card(built)
                timewarp_groups["minions"].append(built["id"])
            elif card_type == "BATTLEGROUND_SPELL":
                built = build_spell_like(card, zh_by_dbf, "timewarp")
                built["timewarpKind"] = "spell"
                add_card(built)
                timewarp_groups["spells"].append(built["id"])
            continue

        if card_type == "HERO" and card.get("battlegroundsHero") is True:
            add_card(build_hero(card, zh_by_dbf, en_by_dbf))
        elif card_type == "MINION" and card.get("isBattlegroundsPoolMinion") is True:
            add_card(build_minion(card, zh_by_dbf, en_by_dbf, "minions"))
        elif is_quest(card):
            add_card(build_spell_like(card, zh_by_dbf, "quests"))
        elif card_type == "BATTLEGROUND_QUEST_REWARD":
            add_card(build_spell_like(card, zh_by_dbf, "rewards"))
        elif card_type == "BATTLEGROUND_ANOMALY":
            add_card(build_spell_like(card, zh_by_dbf, "anomalies"))
        elif card_type == "BATTLEGROUND_SPELL" and card.get("isBattlegroundsPoolSpell") is True:
            add_card(build_spell_like(card, zh_by_dbf, "spells"))
        elif card_type == "BATTLEGROUND_TRINKET":
            add_card(build_spell_like(card, zh_by_dbf, "trinkets"))

    for category in categories:
        categories[category] = sorted_ids(cards_by_id, categories[category])
    for group in timewarp_groups:
        timewarp_groups[group] = sorted_ids(cards_by_id, timewarp_groups[group])

    cards_by_id = {
        card_id: cards_by_id[card_id]
        for card_id in sorted(cards_by_id, key=lambda id_: (cards_by_id[id_]["category"], *card_sort_key(cards_by_id[id_])))
    }

    stats = {
        **{category: len(categories[category]) for category in CATEGORY_FILES},
        "all": len(cards_by_id),
        "keywords": len(KEYWORDS),
    }

    files: dict[str, Any] = {
        "all": {
            "source": "hearthstonejson",
            "build": "latest",
            "generatedAt": generated_at,
            "cards": cards_by_id,
        },
        "statsText": build_stats_text(stats),
        "keywords": {
            "keywords": [
                {"id": keyword["id"], "label": keyword["label"]}
                for keyword in KEYWORDS
            ],
        },
    }

    for category in CATEGORY_FILES:
        files[category] = {
            "category": category,
            "ids": categories[category],
        }
    files["timewarp"]["groups"] = timewarp_groups

    return files


def main() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    raw_root = backend_root / "data" / "raw" / "hearthstonejson" / "latest"

    parser = argparse.ArgumentParser(description="Process HearthstoneJSON cards into Battleground Editor data.")
    parser.add_argument("--en", default=raw_root / "enUS" / "cards.json", type=Path, help="Path to enUS cards.json")
    parser.add_argument("--zh", default=raw_root / "zhCN" / "cards.json", type=Path, help="Path to zhCN cards.json")
    parser.add_argument("--out-dir", default=backend_root / "data" / "processed", type=Path, help="Output folder")
    args = parser.parse_args()

    en_cards = load_json(args.en)
    zh_cards = load_json(args.zh)
    if not isinstance(en_cards, list):
        raise TypeError(f"enUS cards file must be a JSON list: {args.en}")
    if not isinstance(zh_cards, list):
        raise TypeError(f"zhCN cards file must be a JSON list: {args.zh}")

    files = process(en_cards, zh_cards)

    clear_outputs(args.out_dir)
    write_json(args.out_dir / "all.json", files["all"])
    for category, filename in CATEGORY_FILES.items():
        write_json(args.out_dir / filename, files[category])
    write_json(args.out_dir / "keywords.json", files["keywords"])
    write_text(args.out_dir / STATS_FILE, files["statsText"])

    print(f"process_hearthstonejson.py version: {SCRIPT_VERSION}")
    print(f"Wrote output folder: {args.out_dir}")
    for category, filename in CATEGORY_FILES.items():
        print(f"  {filename}: {len(files[category]['ids'])}")
    print(f"  all.json: {len(files['all']['cards'])}")
    print(f"  keywords.json: {len(files['keywords']['keywords'])}")


if __name__ == "__main__":
    main()
