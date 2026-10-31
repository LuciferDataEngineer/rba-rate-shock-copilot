"""Repository paths."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SNAPSHOT = DATA / "snapshot"
TABLES = SNAPSHOT / "tables"
ABS_DIR = SNAPSHOT / "abs"
DOCS = SNAPSHOT / "documents"
DOC_HTML = DOCS / "html"
DOC_TEXT = DOCS / "text"
MANIFEST = DATA / "manifest.json"
WAREHOUSE = DATA / "warehouse"
TIDY = WAREHOUSE / "tidy"
REPORTS = ROOT / "reports"
SITE = ROOT / "site"
CONTRACTS = ROOT / "contracts"
EVAL_DIR = ROOT / "eval"
