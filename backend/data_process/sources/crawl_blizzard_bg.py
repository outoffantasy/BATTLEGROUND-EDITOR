from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from data_process.utils.io import write_json, write_text
from data_process.utils.paths import RAW_ROOT


DEFAULT_LOCALE = "en-us"
DEFAULT_URL = "https://hearthstone.blizzard.com/en-us/battlegrounds"
DEFAULT_OUT_ROOT = RAW_ROOT / "crawl" / "blizzard_bg"
USER_AGENT = "battleground-editor/0.1"
RATE_LIMIT_STATUSES = {403, 429}
CARD_HREF_RE = re.compile(r"/battlegrounds/(?P<card_id>\d+)-(?P<slug>[^/?#]+)")
CARD_COUNT_RE = re.compile(r"(\d[\d,]*)\s+cards?\s+found\s+for\s+\"Battlegrounds\"", re.IGNORECASE)


class FatalCrawlError(Exception):
    pass


class RecoverableCrawlError(Exception):
    pass


class RateLimitError(Exception):
    pass


@dataclass
class CardRecord:
    list_index: int
    card_id: str
    slug: str
    name: str
    detail_url: str
    list_href: str
    image_url: str | None
    image_path: str | None = None
    image_status: str = "pending"
    detail_text_path: str | None = None
    detail_html_path: str | None = None
    detail_status: str = "pending"
    errors: list[str] = field(default_factory=list)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse_card_href(href: str) -> tuple[str, str]:
    match = CARD_HREF_RE.search(href)
    if not match:
        raise ValueError(f"Not a Battlegrounds card href: {href}")
    return match.group("card_id"), match.group("slug")


def normalize_detail_url(href: str, locale: str, base_url: str) -> str:
    card_id, slug = parse_card_href(href)
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}/{locale}/battlegrounds/{card_id}-{slug}"


def safe_file_stem(card_id: str, slug: str) -> str:
    clean_slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", slug).strip("-")
    return f"{card_id}-{clean_slug or 'card'}"


def infer_image_extension(url: str, content_type: str | None = None) -> str:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    by_type = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/avif": ".avif",
        "image/gif": ".gif",
    }
    if media_type in by_type:
        return by_type[media_type]

    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif"}:
        return suffix
    return ".img"


def extract_detail_text(body_text: str, card_name: str) -> str | None:
    normalized = body_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    starts = [index for index, line in enumerate(lines) if line.strip() == card_name]
    if not starts:
        return None

    for offset, start in enumerate(starts):
        end = starts[offset + 1] if offset + 1 < len(starts) else len(lines)
        candidate = "\n".join(lines[start:end]).strip()
        if "Set: Battlegrounds" in candidate:
            return candidate

    return "\n".join(lines[starts[-1] :]).strip()


def extract_displayed_card_count(body_text: str) -> int | None:
    match = CARD_COUNT_RE.search(body_text)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def is_valid_detail_text(detail_text: str | None, card_name: str) -> bool:
    if not detail_text:
        return False
    lines = [line.strip() for line in detail_text.splitlines() if line.strip()]
    return bool(lines and lines[0] == card_name and "Set: Battlegrounds" in detail_text)


def relative_to(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False, sort_keys=True))
        f.write("\n")


def print_step(message: str) -> None:
    print(message, flush=True)


def print_progress(label: str, current: int, total: int, status: str = "") -> None:
    width = 28
    filled = int(width * current / total) if total else width
    bar = "#" * filled + "-" * (width - filled)
    percent = int(100 * current / total) if total else 100
    suffix = f" {status}" if status else ""
    sys.stdout.write(f"\r{label} [{bar}] {percent:3d}% {current}/{total}{suffix}")
    sys.stdout.flush()
    if current >= total:
        sys.stdout.write("\n")
        sys.stdout.flush()


def run_retryable(operation, label: str, normal_delay: float = 1.0):
    saw_rate_limit = False
    last_error: Exception | None = None
    for attempt in range(1, 3):
        try:
            return operation()
        except RateLimitError as e:
            saw_rate_limit = True
            last_error = e
            if attempt == 1:
                print(f"[RATE LIMITED] {label}: {e}. Waiting 60s before retry.")
                time.sleep(60)
                continue
            raise FatalCrawlError(f"{label} failed after 403/429 retry: {e}") from e
        except RecoverableCrawlError as e:
            last_error = e
            if saw_rate_limit:
                raise FatalCrawlError(f"{label} failed after 403/429 retry: {e}") from e
            if attempt == 1:
                print(f"[RETRY] {label}: {e}")
                time.sleep(normal_delay)
                continue
            raise
        except (PlaywrightError, PlaywrightTimeoutError) as e:
            last_error = e
            if saw_rate_limit:
                raise FatalCrawlError(f"{label} failed after 403/429 retry: {e}") from e
            if attempt == 1:
                print(f"[RETRY] {label}: {e}")
                time.sleep(normal_delay)
                continue
            raise RecoverableCrawlError(str(e)) from e

    raise RecoverableCrawlError(f"{label} failed") from last_error


class BlizzardBgCrawler:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.run_dir = self._make_run_dir(Path(args.out_root) / args.locale)
        self.list_dir = self.run_dir / "list"
        self.details_dir = self.run_dir / "details"
        self.images_dir = self.run_dir / "images"
        self.network_path = self.run_dir / "network.jsonl"
        self.cards: list[CardRecord] = []
        self.resume_root = self.resolve_resume_root(args.resume_from)
        self.resume_cards: dict[str, dict[str, Any]] = {}
        self.errors: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []
        self.phase = "init"
        self.started_at = utc_now()
        self.displayed_card_count: int | None = None
        self.unique_card_links = 0

    def _make_run_dir(self, root: Path) -> Path:
        base = root / run_id()
        if not base.exists():
            return base
        for index in range(2, 100):
            candidate = Path(f"{base}-{index}")
            if not candidate.exists():
                return candidate
        raise RuntimeError(f"Could not create unique crawl folder under {root}")

    def resolve_resume_root(self, value: str | None) -> Path | None:
        if not value:
            return None

        path = Path(value)
        if path.exists():
            return path

        if not path.is_absolute():
            backend_relative = RAW_ROOT.parent.parent / path
            if backend_relative.exists():
                return backend_relative

        return path

    def load_resume_index(self) -> None:
        if self.resume_root is None:
            return

        index_path = self.resume_root / "cards_index.json"
        if not index_path.exists():
            raise FatalCrawlError(f"resume cards_index.json not found: {index_path}")

        with index_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise FatalCrawlError(f"resume cards_index.json must be a list: {index_path}")

        self.resume_cards = {
            str(item["card_id"]): item
            for item in data
            if isinstance(item, dict) and item.get("card_id")
        }
        print_step(f"[RESUME] Loaded {len(self.resume_cards)} cards from {self.resume_root}")

    def log_error(self, kind: str, message: str, card_id: str | None = None) -> None:
        self.errors.append(
            {
                "at": utc_now(),
                "kind": kind,
                "card_id": card_id,
                "message": message,
            }
        )

    def log_warning(self, kind: str, message: str) -> None:
        self.warnings.append(
            {
                "at": utc_now(),
                "kind": kind,
                "message": message,
            }
        )

    def attach_network_logger(self, page: Page) -> None:
        def on_response(response) -> None:
            try:
                append_jsonl(
                    self.network_path,
                    {
                        "at": utc_now(),
                        "phase": self.phase,
                        "url": response.url,
                        "status": response.status,
                        "content_type": response.headers.get("content-type"),
                        "resource_type": response.request.resource_type,
                        "method": response.request.method,
                    },
                )
            except Exception as e:
                print(f"[NETWORK LOG ERROR] {e}")

        page.on("response", on_response)

    def goto_page(self, page: Page, url: str) -> None:
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=self.args.timeout_ms)
        except (PlaywrightError, PlaywrightTimeoutError) as e:
            raise RecoverableCrawlError(f"page load failed: {e}") from e

        if response is None:
            return
        if response.status in RATE_LIMIT_STATUSES:
            raise RateLimitError(f"HTTP {response.status} {url}")
        if response.status >= 400:
            raise RecoverableCrawlError(f"HTTP {response.status} {url}")

    def run(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.details_dir.mkdir(parents=True, exist_ok=True)
        self.load_resume_index()
        print_step(f"[START] Blizzard BG crawl: {self.args.url}")
        print_step(f"[OUTPUT] {self.run_dir}")
        print_step(
            "[OPTIONS] "
            f"locale={self.args.locale} "
            f"limit_details={self.args.limit_details} "
            f"detail_sleep={self.args.detail_sleep}s "
            f"resume_from={self.resume_root} "
            f"timeout_ms={self.args.timeout_ms}"
        )

        with sync_playwright() as playwright:
            print_step("[BROWSER] Starting Chromium")
            browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(user_agent=USER_AGENT)
            try:
                list_page = context.new_page()
                self.attach_network_logger(list_page)
                self.cards = self.crawl_list_page(list_page)
                if not self.cards:
                    raise FatalCrawlError("List page returned zero cards.")
                self.reuse_previous_files()

                detail_cards = (
                    self.cards[: self.args.limit_details]
                    if self.args.limit_details is not None
                    else self.cards
                )
                self.download_images(context)
                self.crawl_details(context, detail_cards)
            finally:
                print_step("[BROWSER] Closing Chromium")
                context.close()
                browser.close()

    def crawl_list_page(self, page: Page) -> list[CardRecord]:
        def operation() -> list[CardRecord]:
            self.phase = "list"
            print_step(f"[LIST] Opening {self.args.url}")
            self.goto_page(page, self.args.url)
            print_step("[LIST] Waiting for card grid")
            page.wait_for_function(
                """
                () => document.querySelectorAll(
                  'a[href*="/battlegrounds/"] img[alt]'
                ).length > 10
                """,
                timeout=self.args.timeout_ms,
            )
            page.wait_for_timeout(1000)
            print_step("[LIST] Scrolling to bottom to trigger lazy loading")
            self.scroll_list_once(page)

            print_step("[LIST] Extracting card links and image URLs")
            raw_cards = page.evaluate(
                """
                () => [...document.querySelectorAll('a[href]')].map((anchor, index) => {
                  const href = anchor.getAttribute('href') || '';
                  if (!/\\/battlegrounds\\/\\d+-/.test(href)) return null;
                  const img = anchor.querySelector('img');
                  const name = ((img && img.alt) || anchor.textContent || '').trim();
                  const imageUrl = img ? (img.currentSrc || img.src || img.getAttribute('src')) : null;
                  return { list_index: index, href, name, image_url: imageUrl };
                }).filter(Boolean)
                """
            )

            cards: list[CardRecord] = []
            seen: set[str] = set()
            for raw in raw_cards:
                try:
                    card_id, slug = parse_card_href(raw["href"])
                except ValueError:
                    continue
                if card_id in seen or not raw.get("name"):
                    continue
                seen.add(card_id)
                cards.append(
                    CardRecord(
                        list_index=len(cards),
                        card_id=card_id,
                        slug=slug,
                        name=raw["name"],
                        detail_url=normalize_detail_url(raw["href"], self.args.locale, self.args.url),
                        list_href=raw["href"],
                        image_url=raw.get("image_url"),
                    )
                )

            if not cards:
                raise RecoverableCrawlError("no cards found")
            self.record_list_counts(page, len(cards))
            return cards

        cards = run_retryable(operation, "list page")
        print_step("[LIST] Writing rendered HTML and visible text")
        write_text(self.list_dir / "page.html", page.content())
        write_text(
            self.list_dir / "page.txt",
            page.locator("body").inner_text(timeout=self.args.timeout_ms),
        )
        print_step("[LIST] Taking full-page screenshot; this can be slow on a large card page")
        page.screenshot(path=self.list_dir / "screenshot.png", full_page=True)
        print_step(f"[LIST] Cards found: {len(cards)}")
        return cards

    def scroll_list_once(self, page: Page) -> None:
        viewport = page.viewport_size or {"width": 1280, "height": 720}
        page.mouse.move(viewport["width"] / 2, viewport["height"] / 2)

        scroll_step = int(viewport["height"] * 1.2)
        last_y = -1
        stuck_rounds = 0

        for _ in range(120):
            page.mouse.wheel(0, scroll_step)
            page.wait_for_timeout(100)
            scroll_y = page.evaluate("window.scrollY")
            max_y = page.evaluate("document.documentElement.scrollHeight - window.innerHeight")

            if abs(scroll_y - last_y) < 5 or scroll_y >= max_y - 5:
                stuck_rounds += 1
            else:
                stuck_rounds = 0

            last_y = scroll_y
            if stuck_rounds >= 5:
                break

        page.wait_for_timeout(1000)
        page.keyboard.press("Home")
        print_step("[LIST] Waiting 10s after returning to top")
        page.wait_for_timeout(10000)

    def record_list_counts(self, page: Page, extracted_cards: int) -> None:
        body_text = page.locator("body").inner_text(timeout=self.args.timeout_ms)
        self.displayed_card_count = extract_displayed_card_count(body_text)
        self.unique_card_links = extracted_cards
        print_step(
            "[LIST] Count info: "
            f"displayed={self.displayed_card_count}, extracted={extracted_cards}"
        )
        if self.displayed_card_count is not None and self.displayed_card_count != extracted_cards:
            self.log_warning(
                "list_count_mismatch",
                f"displayed_count={self.displayed_card_count}, extracted_cards={extracted_cards}",
            )

    def reuse_previous_files(self) -> None:
        if self.resume_root is None or not self.resume_cards:
            return

        image_count = 0
        detail_count = 0
        for card in self.cards:
            old_card = self.resume_cards.get(card.card_id)
            if not old_card:
                continue

            if old_card.get("image_status") in {"downloaded", "reused"}:
                image_path = self.copy_resume_file(old_card.get("image_path"))
                if image_path is not None:
                    card.image_path = image_path
                    card.image_status = "reused"
                    image_count += 1

            if old_card.get("detail_status") in {"downloaded", "reused"}:
                detail_text_path = self.copy_resume_file(old_card.get("detail_text_path"))
                detail_html_path = self.copy_resume_file(old_card.get("detail_html_path"))
                if detail_text_path is not None and detail_html_path is not None:
                    card.detail_text_path = detail_text_path
                    card.detail_html_path = detail_html_path
                    card.detail_status = "reused"
                    detail_count += 1

        print_step(f"[RESUME] Reused images={image_count}, details={detail_count}")

    def copy_resume_file(self, relative_path: str | None) -> str | None:
        if self.resume_root is None or not relative_path:
            return None

        old_path = self.resume_root / relative_path
        if not old_path.exists() or not old_path.is_file():
            return None

        new_path = self.run_dir / relative_path
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_path, new_path)
        return relative_path

    def download_images(self, context) -> None:
        downloaded_by_url: dict[str, str] = {}
        total = len(self.cards)
        downloaded = 0
        reused = 0
        failed = 0
        print_step(f"[IMAGES] Downloading card images for {total} cards")
        for index, card in enumerate(self.cards, start=1):
            if card.image_status == "reused" and card.image_path:
                if card.image_url:
                    downloaded_by_url[card.image_url] = card.image_path
                reused += 1
                print_progress("Images", index, total, f"downloaded={downloaded} reused={reused} failed={failed}")
                continue

            if not card.image_url:
                card.image_status = "failed"
                card.errors.append("missing image URL")
                self.log_error("image", "missing image URL", card.card_id)
                failed += 1
                print_progress("Images", index, total, f"downloaded={downloaded} reused={reused} failed={failed}")
                continue

            if card.image_url in downloaded_by_url:
                card.image_path = downloaded_by_url[card.image_url]
                card.image_status = "downloaded"
                reused += 1
                print_progress("Images", index, total, f"downloaded={downloaded} reused={reused} failed={failed}")
                continue

            stem = safe_file_stem(card.card_id, card.slug)

            def operation() -> Path:
                self.phase = f"image:{card.card_id}"
                try:
                    response = context.request.get(card.image_url, timeout=self.args.timeout_ms)
                except PlaywrightError as e:
                    raise RecoverableCrawlError(f"image request failed: {e}") from e

                content_type = response.headers.get("content-type")
                append_jsonl(
                    self.network_path,
                    {
                        "at": utc_now(),
                        "phase": self.phase,
                        "url": card.image_url,
                        "status": response.status,
                        "content_type": content_type,
                        "resource_type": "image-download",
                        "method": "GET",
                    },
                )

                if response.status in RATE_LIMIT_STATUSES:
                    raise RateLimitError(f"HTTP {response.status} {card.image_url}")
                if response.status >= 400:
                    raise RecoverableCrawlError(f"HTTP {response.status} {card.image_url}")

                output_path = self.images_dir / f"{stem}{infer_image_extension(card.image_url, content_type)}"
                output_path.write_bytes(response.body())
                return output_path

            try:
                image_path = run_retryable(operation, f"image {card.card_id}")
            except RecoverableCrawlError as e:
                card.image_status = "failed"
                card.errors.append(str(e))
                self.log_error("image", str(e), card.card_id)
                print(f"[SKIP IMAGE] {card.card_id}: {e}")
                failed += 1
                print_progress("Images", index, total, f"downloaded={downloaded} reused={reused} failed={failed}")
                continue

            rel_path = relative_to(image_path, self.run_dir)
            downloaded_by_url[card.image_url] = rel_path
            card.image_path = rel_path
            card.image_status = "downloaded"
            downloaded += 1
            print_progress("Images", index, total, f"downloaded={downloaded} reused={reused} failed={failed}")

    def crawl_details(self, context, cards: list[CardRecord]) -> None:
        detail_page = context.new_page()
        detail_page.route("**/*", self._block_heavy_detail_assets)
        self.attach_network_logger(detail_page)

        total = len(cards)
        downloaded = 0
        failed = 0
        print_step(f"[DETAILS] Crawling detail text for {total} cards")
        for index, card in enumerate(cards, start=1):
            if card.detail_status == "reused":
                downloaded += 1
                print_progress(
                    "Details",
                    index,
                    total,
                    f"downloaded={downloaded} failed={failed} current={card.card_id}",
                )
                continue

            try:
                self.crawl_one_detail(detail_page, card)
                downloaded += 1
            except RecoverableCrawlError as e:
                card.detail_status = "failed"
                card.errors.append(str(e))
                self.log_error("detail", str(e), card.card_id)
                failed += 1
                print(f"\n[SKIP DETAIL] {card.card_id}: {e}")
            print_progress(
                "Details",
                index,
                total,
                f"downloaded={downloaded} failed={failed} current={card.card_id}",
            )

        detail_page.close()

        if self.args.limit_details is not None and self.args.limit_details < len(self.cards):
            for card in self.cards[self.args.limit_details :]:
                card.detail_status = "not_requested"

    def _block_heavy_detail_assets(self, route) -> None:
        if route.request.resource_type in {"image", "font", "media"}:
            route.abort()
            return
        route.continue_()

    def crawl_one_detail(self, page: Page, card: CardRecord) -> None:
        def operation() -> tuple[str, str]:
            self.phase = f"detail:{card.card_id}"
            page.goto("about:blank", wait_until="domcontentloaded", timeout=self.args.timeout_ms)
            self.goto_page(page, card.detail_url)
            page.wait_for_function(
                """
                (name) => {
                  const text = document.body.innerText || '';
                  return text.includes(name) && text.includes('Set: Battlegrounds');
                }
                """,
                arg=card.name,
                timeout=self.args.timeout_ms,
            )
            if self.args.detail_sleep > 0:
                page.wait_for_timeout(int(self.args.detail_sleep * 1000))

            body_text = page.locator("body").inner_text(timeout=self.args.timeout_ms)
            detail_text = extract_detail_text(body_text, card.name)
            if not is_valid_detail_text(detail_text, card.name):
                raise RecoverableCrawlError("detail fragment not found")

            detail_html = self.extract_detail_html(page, card.name)
            if not detail_html:
                detail_html = f"<pre>{html.escape(detail_text)}</pre>\n"
            return detail_text, detail_html

        detail_text, detail_html = run_retryable(operation, f"detail {card.card_id}")
        stem = safe_file_stem(card.card_id, card.slug)
        text_path = self.details_dir / f"{stem}.txt"
        html_path = self.details_dir / f"{stem}.html"
        write_text(text_path, detail_text + "\n")
        write_text(html_path, detail_html)
        card.detail_text_path = relative_to(text_path, self.run_dir)
        card.detail_html_path = relative_to(html_path, self.run_dir)
        card.detail_status = "downloaded"

    def extract_detail_html(self, page: Page, card_name: str) -> str:
        try:
            return page.evaluate(
                """
                (name) => {
                  const nodes = [...document.querySelectorAll('article, section, aside, div')];
                  const matches = nodes
                    .filter((node) => {
                      const text = node.innerText || '';
                      return text.includes(name) && text.includes('Set: Battlegrounds');
                    })
                    .map((node) => ({ html: node.outerHTML, length: (node.innerText || '').length }))
                    .sort((a, b) => a.length - b.length);
                  return matches.length ? matches[0].html : '';
                }
                """,
                card_name,
            )
        except PlaywrightError:
            return ""

    def write_manifest(self, status: str) -> None:
        downloaded_images = sum(1 for card in self.cards if card.image_status == "downloaded")
        reused_images = sum(1 for card in self.cards if card.image_status == "reused")
        failed_images = sum(1 for card in self.cards if card.image_status == "failed")
        downloaded_details = sum(1 for card in self.cards if card.detail_status == "downloaded")
        reused_details = sum(1 for card in self.cards if card.detail_status == "reused")
        failed_details = sum(1 for card in self.cards if card.detail_status == "failed")
        payload = {
            "source": "hearthstone.blizzard.com",
            "kind": "blizzard_bg_raw_crawl",
            "status": status,
            "locale": self.args.locale,
            "url": self.args.url,
            "resumeFrom": str(self.resume_root) if self.resume_root is not None else None,
            "startedAt": self.started_at,
            "finishedAt": utc_now(),
            "runDir": str(self.run_dir),
            "counts": {
                "cards": len(self.cards),
                "imagesDownloaded": downloaded_images,
                "imagesReused": reused_images,
                "imagesFailed": failed_images,
                "detailsDownloaded": downloaded_details,
                "detailsReused": reused_details,
                "detailsFailed": failed_details,
                "errors": len(self.errors),
                "warnings": len(self.warnings),
            },
            "listCounts": {
                "displayedCardCount": self.displayed_card_count,
                "uniqueCardLinks": self.unique_card_links,
            },
            "options": {
                "limitDetails": self.args.limit_details,
                "detailSleep": self.args.detail_sleep,
                "timeoutMs": self.args.timeout_ms,
            },
            "files": {
                "cardsIndex": "cards_index.json",
                "network": "network.jsonl",
                "listHtml": "list/page.html",
                "listText": "list/page.txt",
                "listScreenshot": "list/screenshot.png",
            },
            "errors": self.errors,
            "warnings": self.warnings,
        }
        write_json(self.run_dir / "cards_index.json", [card.__dict__ for card in self.cards])
        write_json(self.run_dir / "manifest.json", payload)
        print_step(
            "[SUMMARY] "
            f"status={status} cards={len(self.cards)} "
            f"images={downloaded_images} reused_images={reused_images} "
            f"details={downloaded_details} reused_details={reused_details} "
            f"errors={len(self.errors)}"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl raw Blizzard Battlegrounds card data.")
    parser.add_argument("--locale", default=DEFAULT_LOCALE)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--out-root", default=DEFAULT_OUT_ROOT, type=Path)
    parser.add_argument("--limit-details", default=None, type=int)
    parser.add_argument("--detail-sleep", default=3, type=float)
    parser.add_argument("--resume-from", default=None)
    parser.add_argument("--timeout-ms", default=60000, type=int)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    crawler = BlizzardBgCrawler(args)
    status = "ok"
    try:
        crawler.run()
    except FatalCrawlError as e:
        status = "failed"
        crawler.log_error("fatal", str(e))
        print(f"[FATAL] {e}")
    except Exception as e:
        status = "failed"
        crawler.log_error("fatal", str(e))
        print(f"[FATAL] {e}")
    finally:
        crawler.write_manifest(status)
        print(f"Output: {crawler.run_dir}")

    if status != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
