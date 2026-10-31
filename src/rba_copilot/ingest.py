"""Download the public snapshot used by every later step.

The committed files under ``data/snapshot`` are what CI builds from. Re-running
this module needs the network and a polite delay between RBA pages.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from rba_copilot.paths import ABS_DIR, DOC_HTML, DOC_TEXT, DOCS, MANIFEST, TABLES

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 "
    "rba-rate-shock-copilot/0.1 (research; contact: github.com/LuciferDataEngineer)"
)
RBA = "https://www.rba.gov.au"
ABS = "https://data.api.abs.gov.au"
PAUSE_SECONDS = 0.45

RBA_TABLES = {
    "f1-data.csv": "F1 Interest rates and yields, money market, daily",
    "f1.1-data.csv": "F1.1 Interest rates and yields, money market, monthly",
    "f5-data.csv": "F5 Indicator lending rates",
    "f6-data.csv": "F6 Housing lending rates",
    "g1-data.csv": "G1 Consumer price inflation",
    "h5-data.csv": "H5 Labour force",
    "e13-data.csv": "E13 Housing loan payments",
}

DECISION_RELEASES = [
    "/media-releases/2025/mr-25-03.html",
    "/media-releases/2025/mr-25-10.html",
    "/media-releases/2025/mr-25-13.html",
    "/media-releases/2025/mr-25-17.html",
    "/media-releases/2025/mr-25-22.html",
    "/media-releases/2025/mr-25-27.html",
    "/media-releases/2025/mr-25-31.html",
    "/media-releases/2025/mr-25-33.html",
    "/media-releases/2026/mr-26-03.html",
    "/media-releases/2026/mr-26-08.html",
    "/media-releases/2026/mr-26-12.html",
    "/media-releases/2026/mr-26-15.html",
    "/media-releases/2026/mr-26-19.html",
    "/media-releases/2026/mr-26-27.html",
]

MINUTE_DATES = [
    "2025-02-18",
    "2025-04-01",
    "2025-05-20",
    "2025-07-08",
    "2025-08-12",
    "2025-09-30",
    "2025-11-04",
    "2025-12-09",
    "2026-02-03",
    "2026-03-17",
    "2026-05-05",
    "2026-06-16",
    "2026-08-11",
    "2026-09-29",
]

SMP_ISSUES = [
    "2025/feb",
    "2025/may",
    "2025/aug",
    "2025/nov",
    "2026/feb",
    "2026/may",
    "2026/aug",
]

# Meeting date of the Statement published with that issue.
SMP_DATES = {
    "2025-feb": "2025-02-18",
    "2025-may": "2025-05-20",
    "2025-aug": "2025-08-12",
    "2025-nov": "2025-11-04",
    "2026-feb": "2026-02-03",
    "2026-may": "2026-05-05",
    "2026-aug": "2026-08-11",
}

ABS_SERIES = {
    "cpi_headline_yoy.csv": (
        "ABS,CPI,2.0.0/3.10001.10.50.M?startPeriod=2024-01&endPeriod=2026-09",
        "Monthly CPI, all groups, percentage change from previous year, Australia, original",
    ),
    "cpi_trimmed_mean_yoy.csv": (
        "ABS,CPI,2.0.0/3.999902.20.50.M?startPeriod=2024-01&endPeriod=2026-09",
        "Monthly CPI trimmed mean, percentage change from previous year, Australia, seasonally adjusted",
    ),
    "cpi_headline_index.csv": (
        "ABS,CPI,2.0.0/1.10001.10.50.M?startPeriod=2024-01&endPeriod=2026-09",
        "Monthly CPI, all groups index, Australia, original",
    ),
    "awe_ordinary_time.csv": (
        "ABS,AWE,1.0.0/3.1.3.7.TOT.20.AUS.S?startPeriod=2023-S1",
        "Full-time adult average weekly ordinary time earnings, persons, Australia, seasonally adjusted",
    ),
}


def _request(url: str, accept: str | None = None) -> bytes:
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def _count_rows(path: Path) -> int | None:
    if path.suffix.lower() not in {".csv", ".txt", ".html"}:
        return None
    if path.suffix.lower() == ".html":
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    return max(text.count("\n"), 1)


def extract_article(html: str) -> dict:
    """Pull the article body out of an RBA HTML page."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    for tag in soup.select(
        "nav, .nav-publication-contents, .content-tools, footer, #mp-related-links, .aside-component"
    ):
        tag.decompose()
    content = (
        soup.select_one(".rss-mr-content")
        or soup.select_one("#content")
        or soup.select_one("main")
        or soup.body
    )
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = og["content"].split("|")[0].strip()
    elif content and content.find("h1"):
        title = content.find("h1").get_text(" ", strip=True)
    elif soup.title:
        title = soup.title.get_text(" ", strip=True)
    else:
        title = ""
    title = re.sub(r"\s+", " ", title).strip()
    published = None
    time_tag = soup.find("time")
    if time_tag and time_tag.get("datetime"):
        published = time_tag["datetime"][:10]
    sections: list[dict[str, str]] = []
    heading = "Document"
    buffer: list[str] = []

    def flush() -> None:
        text = " ".join(part.strip() for part in buffer if part.strip())
        if text:
            sections.append({"heading": heading, "text": text})

    if content:
        for element in content.find_all(["h2", "h3", "p", "li"]):
            if element.name in {"h2", "h3"}:
                flush()
                buffer = []
                heading = element.get_text(" ", strip=True) or heading
            else:
                text = re.sub(r"\s+", " ", element.get_text(" ", strip=True)).strip()
                if text and len(text) > 1:
                    buffer.append(text)
        flush()
    full = "\n\n".join(f"{section['heading']}\n{section['text']}" for section in sections)
    return {"title": title, "published": published, "sections": sections, "text": full}


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def download_tables(manifest_files: list[dict]) -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    for name, title in RBA_TABLES.items():
        url = f"{RBA}/statistics/tables/csv/{name}"
        destination = TABLES / name
        print(f"table {name}")
        _write(destination, _request(url))
        time.sleep(PAUSE_SECONDS)
        manifest_files.append(
            {
                "path": str(destination.relative_to(MANIFEST.parents[1])),
                "source_url": url,
                "publisher": "Reserve Bank of Australia",
                "licence": "CC BY 4.0",
                "title": title,
                "sha256": _sha256(destination),
                "bytes": destination.stat().st_size,
                "rows": _count_rows(destination),
            }
        )


def download_abs(manifest_files: list[dict]) -> None:
    ABS_DIR.mkdir(parents=True, exist_ok=True)
    for name, (key, title) in ABS_SERIES.items():
        url = f"{ABS}/rest/data/{key}"
        destination = ABS_DIR / name
        print(f"abs {name}")
        payload = _request(url, accept="application/vnd.sdmx.data+csv;labels=both")
        _write(destination, payload)
        time.sleep(PAUSE_SECONDS)
        manifest_files.append(
            {
                "path": str(destination.relative_to(MANIFEST.parents[1])),
                "source_url": url,
                "publisher": "Australian Bureau of Statistics",
                "licence": "CC BY 4.0",
                "title": title,
                "sha256": _sha256(destination),
                "bytes": destination.stat().st_size,
                "rows": _count_rows(destination),
            }
        )


def _save_document(url_path: str, doc_type: str, doc_id: str, catalogue: list[dict], manifest_files: list[dict]) -> None:
    url = url_path if url_path.startswith("http") else f"{RBA}{url_path}"
    try:
        raw = _request(url)
    except urllib.error.HTTPError as exc:
        print(f"skip {url} ({exc.code})")
        return
    html_path = DOC_HTML / f"{doc_id}.html"
    text_path = DOC_TEXT / f"{doc_id}.txt"
    _write(html_path, raw)
    parsed = extract_article(raw.decode("utf-8", errors="replace"))
    if doc_type == "minutes" and doc_id.startswith("minutes-"):
        parsed["published"] = doc_id.removeprefix("minutes-")
    if doc_type == "smp" and not parsed["published"]:
        issue_key = "-".join(doc_id.split("-")[1:3])
        parsed["published"] = SMP_DATES.get(issue_key)
    if len(parsed["text"]) < 400:
        print(f"skip short {doc_id} ({len(parsed['text'])} chars)")
        html_path.unlink(missing_ok=True)
        return
    text_path.write_text(parsed["text"], encoding="utf-8")
    sections_path = DOC_TEXT / f"{doc_id}.sections.json"
    sections_path.write_text(json.dumps(parsed["sections"], ensure_ascii=False), encoding="utf-8")
    catalogue.append(
        {
            "doc_id": doc_id,
            "doc_type": doc_type,
            "title": parsed["title"],
            "doc_date": parsed["published"],
            "url": url,
            "text_path": str(text_path.relative_to(MANIFEST.parents[1])),
            "html_path": str(html_path.relative_to(MANIFEST.parents[1])),
            "sections_path": str(sections_path.relative_to(MANIFEST.parents[1])),
            "n_chars": len(parsed["text"]),
        }
    )
    for path in (html_path, text_path):
        manifest_files.append(
            {
                "path": str(path.relative_to(MANIFEST.parents[1])),
                "source_url": url,
                "publisher": "Reserve Bank of Australia",
                "licence": "CC BY 4.0",
                "title": parsed["title"],
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
                "rows": None if path.suffix == ".html" else parsed["text"].count("\n") + 1,
            }
        )
    time.sleep(PAUSE_SECONDS)


def _smp_chapters(issue: str) -> list[str]:
    contents_url = f"{RBA}/publications/smp/{issue}/contents.html"
    try:
        html = _request(contents_url).decode("utf-8", errors="replace")
    except urllib.error.HTTPError:
        return []
    time.sleep(PAUSE_SECONDS)
    soup = BeautifulSoup(html, "lxml")
    found: list[str] = []
    prefix = f"/publications/smp/{issue}/"
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].split("#")[0]
        if not href.startswith(prefix) or not href.endswith(".html"):
            continue
        name = href.removeprefix(prefix)
        if "/" in name or name in {"contents.html"}:
            continue
        if name not in found:
            found.append(name)
    preferred = [
        "overview.html",
        "economic-conditions.html",
        "financial-conditions.html",
        "outlook.html",
        "inflation.html",
        "domestic-economic-conditions.html",
        "international-economic-conditions.html",
    ]
    ordered = [name for name in preferred if name in found]
    for name in found:
        if name.startswith("box-") and name not in ordered:
            ordered.append(name)
        if len(ordered) >= 5:
            break
    return ordered


def download_documents(manifest_files: list[dict]) -> list[dict]:
    DOC_HTML.mkdir(parents=True, exist_ok=True)
    DOC_TEXT.mkdir(parents=True, exist_ok=True)
    catalogue: list[dict] = []
    for path in DECISION_RELEASES:
        doc_id = Path(path).stem
        print(f"decision {doc_id}")
        _save_document(path, "decision", doc_id, catalogue, manifest_files)
    for day in MINUTE_DATES:
        year = day[:4]
        path = f"/monetary-policy/rba-board-minutes/{year}/{day}.html"
        doc_id = f"minutes-{day}"
        print(f"minutes {doc_id}")
        _save_document(path, "minutes", doc_id, catalogue, manifest_files)
    for issue in SMP_ISSUES:
        for chapter in _smp_chapters(issue):
            slug = chapter.removesuffix(".html")
            doc_id = f"smp-{issue.replace('/', '-')}-{slug}"
            path = f"/publications/smp/{issue}/{chapter}"
            print(f"smp {doc_id}")
            _save_document(path, "smp", doc_id, catalogue, manifest_files)
    catalogue_path = DOCS / "catalogue.json"
    catalogue_path.write_text(json.dumps(catalogue, indent=2), encoding="utf-8")
    manifest_files.append(
        {
            "path": str(catalogue_path.relative_to(MANIFEST.parents[1])),
            "source_url": f"{RBA}/monetary-policy/",
            "publisher": "Reserve Bank of Australia",
            "licence": "CC BY 4.0",
            "title": "Catalogue of snapshotted RBA documents",
            "sha256": _sha256(catalogue_path),
            "bytes": catalogue_path.stat().st_size,
            "rows": len(catalogue),
        }
    )
    return catalogue


def rebuild_texts_from_html() -> None:
    """Re-extract text from the committed HTML. No network."""
    catalogue_path = DOCS / "catalogue.json"
    catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
    for item in catalogue:
        html_path = MANIFEST.parents[1] / item["html_path"]
        parsed = extract_article(html_path.read_text(encoding="utf-8", errors="replace"))
        if item["doc_type"] == "minutes":
            parsed["published"] = item["doc_id"].removeprefix("minutes-")
        if item["doc_type"] == "smp":
            issue_key = "-".join(item["doc_id"].split("-")[1:3])
            parsed["published"] = parsed["published"] or SMP_DATES.get(issue_key)
        item["title"] = parsed["title"] or item["title"]
        item["doc_date"] = parsed["published"] or item.get("doc_date")
        item["n_chars"] = len(parsed["text"])
        text_path = MANIFEST.parents[1] / item["text_path"]
        sections_path = MANIFEST.parents[1] / item["sections_path"]
        text_path.write_text(parsed["text"], encoding="utf-8")
        sections_path.write_text(json.dumps(parsed["sections"], ensure_ascii=False), encoding="utf-8")
    catalogue_path.write_text(json.dumps(catalogue, indent=2), encoding="utf-8")
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        by_path = {entry["path"]: entry for entry in manifest["files"]}
        refreshed = [catalogue_path.relative_to(MANIFEST.parents[1]).as_posix()]
        for item in catalogue:
            refreshed.extend([item["text_path"], item["sections_path"]])
        for relative in refreshed:
            path = MANIFEST.parents[1] / relative
            entry = by_path.get(relative)
            if entry is None or not path.exists():
                continue
            entry["sha256"] = _sha256(path)
            entry["bytes"] = path.stat().st_size
            if path.suffix == ".txt":
                entry["rows"] = path.read_text(encoding="utf-8").count("\n") + 1
            if path.name == "catalogue.json":
                entry["rows"] = len(catalogue)
        MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"rebuilt text for {len(catalogue)} documents")


def build_snapshot() -> None:
    accessed = datetime.now(timezone.utc)
    melbourne = accessed.astimezone(ZoneInfo("Australia/Melbourne"))
    files: list[dict] = []
    download_tables(files)
    download_abs(files)
    catalogue = download_documents(files)
    manifest = {
        "project": "rba-rate-shock-copilot",
        "access_timestamp_utc": accessed.isoformat(),
        "access_timestamp_melbourne": melbourne.isoformat(),
        "attribution": "Source: RBA; Australian Bureau of Statistics",
        "licence": "CC BY 4.0",
        "document_count": len(catalogue),
        "notes": [
            "Raw RBA CSVs include some third-party series (Canstar, ASX, FENICS). Downstream code keeps only series whose Source is RBA, ABS, or APRA.",
            "ABS monthly CPI and average weekly earnings were read from the ABS Data API because table G1 is the quarterly CPI.",
            "CI reads this snapshot and does not scrape the live sites.",
        ],
        "files": files,
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {MANIFEST} documents={len(catalogue)} files={len(files)}")


def main() -> None:
    build_snapshot()


if __name__ == "__main__":
    main()
