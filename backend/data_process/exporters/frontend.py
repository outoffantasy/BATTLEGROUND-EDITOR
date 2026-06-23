from __future__ import annotations

from pathlib import Path
from typing import Any

from data_process.transforms.process_hearthstonejson import CATEGORY_FILES
from data_process.utils.io import load_json
from data_process.utils.paths import PROCESSED_ROOT
from data_process.validators.processed import assert_valid_processed_files


def load_frontend_payload(processed_dir: Path = PROCESSED_ROOT) -> dict[str, Any]:
    assert_valid_processed_files(processed_dir)
    return {
        "all": load_json(processed_dir / "all.json"),
        "keywords": load_json(processed_dir / "keywords.json"),
        "categories": {
            category: load_json(processed_dir / filename)
            for category, filename in CATEGORY_FILES.items()
        },
    }
