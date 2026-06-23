from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


Category = Literal[
    "heroes",
    "minions",
    "quests",
    "rewards",
    "anomalies",
    "spells",
    "trinkets",
    "timewarp",
]


class LocalizedText(BaseModel):
    enUS: str
    zhCN: str


class EmbeddedCard(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: LocalizedText
    text: LocalizedText
    image: str


class ProcessedCard(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    category: Category
    name: LocalizedText
    text: LocalizedText
    image: str
    keywords: list[str] | None = None
    tribes: list[str] | None = None
    tribesDisplay: list[str] | None = None
    golden: EmbeddedCard | None = None
    heroPower: EmbeddedCard | None = None
    buddyId: str | None = None
    timewarpKind: Literal["minion", "spell"] | None = None


class AllCardsPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str
    build: str
    generatedAt: str
    cards: dict[str, ProcessedCard]


class CategoryPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    category: Category
    ids: list[str]
    groups: dict[str, list[str]] | None = None


class KeywordPayload(BaseModel):
    id: str
    label: str


class KeywordsPayload(BaseModel):
    keywords: list[KeywordPayload]
