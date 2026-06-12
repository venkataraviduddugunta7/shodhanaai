#!/usr/bin/env python3
import cgi
import csv
import difflib
import html
import json
import math
import os
import re
import sqlite3
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
IMPORTS_DIR = DATA_DIR / "imports"
UPLOADS_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "shodhana_ai.sqlite3"
PUBLIC_SITE_URL = "https://www.shodhana.com/"
PUBLIC_SITEMAP_URL = "https://www.shodhana.com/sitemap_index.xml"
PUBLIC_SITE_OUTPUT = KNOWLEDGE_DIR / "shodhana_public_website.md"
PRIORITY_PUBLIC_PATHS = [
    "/",
    "/about-us/",
    "/vision/",
    "/milestones/",
    "/infrastructure/",
    "/rd/",
    "/manufacturing/",
    "/quality-management/",
    "/regulatory-strengths/",
    "/commercial-apis/",
    "/commercialized-products/",
    "/duloxetine-hcl/",
    "/duloxetine-intermediates/",
    "/cas-no/cas-no-136434-34-9/",
]


def ensure_dirs():
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    ensure_dirs()
    with db() as conn:
        conn.executescript(
            """
            create table if not exists knowledge_chunks (
                id integer primary key autoincrement,
                source text not null,
                title text not null,
                content text not null,
                tokens text not null,
                created_at integer not null
            );

            create table if not exists market_rows (
                id integer primary key autoincrement,
                company text not null,
                region text,
                country text,
                product text,
                role text,
                estimated_volume_kg real,
                estimated_price_usd_kg real,
                competitor_supplier text,
                current_shodhana_customer text,
                last_purchase_date text,
                trend text,
                notes text,
                opportunity_score real,
                tier text,
                created_at integer not null
            );

            create table if not exists shipment_rows (
                id integer primary key autoincrement,
                source text,
                shipment_date text,
                year integer,
                product_raw text,
                product_canonical text,
                exporter_raw text,
                exporter_canonical text,
                importer_raw text,
                importer_canonical text,
                origin_country text,
                destination_country text,
                market_category text,
                quantity_kg real,
                total_value_usd real,
                unit_price_usd_kg real,
                dmf_grade text,
                shipment_id text,
                duplicate_key text,
                notes text,
                created_at integer not null
            );

            create table if not exists uploaded_files (
                id integer primary key autoincrement,
                original_name text not null,
                stored_path text not null,
                source_type text not null,
                source_rows integer not null,
                clean_rows integer not null,
                duplicate_rows integer not null,
                created_at integer not null
            );
            """
        )


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "in",
    "is", "it", "its", "of", "on", "or", "that", "the", "this", "to", "with",
    "will", "what", "why", "how", "who", "where", "can", "should", "into",
}

COMMON_QUERY_FIXES = {
    "abt": "about",
    "copany": "company",
    "compnay": "company",
    "compny": "company",
    "shodana": "shodhana",
    "shodhanaa": "shodhana",
    "duloxetin": "duloxetine",
    "duloxitine": "duloxetine",
}


def tokenize(text):
    text = normalize_query_text(text)
    words = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9\-]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def normalize_query_text(text):
    def replace_word(match):
        word = match.group(0).lower()
        return COMMON_QUERY_FIXES.get(word, word)

    return re.sub(r"[a-zA-Z0-9][a-zA-Z0-9\-]+", replace_word, text or "")


def expand_query(query):
    normalized = normalize_query_text(query)
    tokens = set(tokenize(normalized))
    additions = []
    if "company" in tokens or ({"about", "shodhana"} & tokens and len(tokens) <= 3):
        additions.append(
            "Shodhana Laboratories company profile leading manufacturer supplier "
            "Active Pharmaceutical Ingredients APIs Intermediates manufacturing sites "
            "Hyderabad Vizag regulatory bodies US FDA Japan PMDA KFDA cGMP R&D quality"
        )
    if "duloxetine" in tokens:
        additions.append(
            "Duloxetine HCL Hydrochloride API antidepressant CAS 136434-34-9 "
            "regulatory support CEP DMF submissions pellets intermediates"
        )
    return " ".join([normalized, *additions]).strip()


def chunk_text(text, max_words=180):
    words = text.split()
    chunks = []
    for i in range(0, len(words), max_words):
        chunk = " ".join(words[i : i + max_words]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def read_text_file(path):
    return path.read_text(encoding="utf-8", errors="ignore")


class WebsiteTextParser(HTMLParser):
    block_tags = {
        "address", "article", "aside", "blockquote", "br", "div", "footer", "h1",
        "h2", "h3", "h4", "h5", "h6", "header", "li", "main", "p", "section",
        "td", "th", "tr",
    }
    skip_tags = {"script", "style", "svg", "noscript"}

    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.skip_tags:
            self.skip_depth += 1
            return
        if tag == "meta":
            attr_map = dict(attrs)
            name = (attr_map.get("name") or attr_map.get("property") or "").lower()
            content = attr_map.get("content") or ""
            if name in {"description", "og:description"} and content:
                self.parts.append("\n" + content + "\n")
        if tag in self.block_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.skip_tags and self.skip_depth:
            self.skip_depth -= 1
            return
        if tag in self.block_tags:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)

    def text(self):
        return "".join(self.parts)


def clean_public_text(raw_text):
    skip_lines = {
        "about us", "expertise", "products", "gallery", "connect", "downloads",
        "menu", "home", "shopping cart", "image", "contact us", "follow us on",
    }
    cleaned = []
    seen = set()
    for line in raw_text.splitlines():
        line = html.unescape(re.sub(r"\s+", " ", line)).strip()
        lowered = line.lower()
        if len(line) < 3 or lowered in skip_lines:
            continue
        if line in seen:
            continue
        seen.add(line)
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def fetch_url_text(url, timeout=20):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ShodhanaAI-Pilot/0.1 (+https://www.shodhana.com/)",
            "Accept": "text/html,application/xml,text/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def is_public_site_url(url):
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.netloc == "www.shodhana.com"


def should_import_page(url):
    parsed = urlparse(url)
    path = parsed.path.lower()
    if not is_public_site_url(url):
        return False
    excluded_paths = [
        "/cartflows_step", "/author/", "/category/", "/store", "/cart", "/checkout",
        "/request-quote", "/thank-you", "/privacy-policy", "/terms-of-use",
        "__trashed",
    ]
    if any(part in path for part in excluded_paths):
        return False
    if re.search(r"\.(jpg|jpeg|png|gif|webp|svg|css|js|zip|xml)$", path):
        return False
    return True


def sitemap_urls(sitemap_url=PUBLIC_SITEMAP_URL, max_pages=60):
    urls = []
    seen_sitemaps = set()

    def visit(url):
        if url in seen_sitemaps:
            return
        seen_sitemaps.add(url)
        xml_text = fetch_url_text(url)
        root = ET.fromstring(xml_text)
        locs = [node.text.strip() for node in root.findall(".//{*}loc") if node.text]
        for loc in locs:
            if loc.endswith(".xml"):
                visit(loc)
            elif should_import_page(loc) and loc not in urls:
                urls.append(loc)

    visit(sitemap_url)
    urls.sort(key=public_page_priority)
    return urls[:max_pages]


def public_page_priority(url):
    path = urlparse(url).path or "/"
    try:
        return (0, PRIORITY_PUBLIC_PATHS.index(path), path)
    except ValueError:
        pass
    if "duloxetine" in path:
        return (1, 0, path)
    if any(word in path for word in ["manufacturing", "quality", "regulatory", "rd", "infrastructure"]):
        return (1, 1, path)
    if any(word in path for word in ["commercial", "api", "intermediate", "pipeline"]):
        return (1, 2, path)
    return (2, 0, path)


def html_to_text(markup):
    parser = WebsiteTextParser()
    parser.feed(markup)
    return clean_public_text(parser.text())


def import_public_website(max_pages=60):
    ensure_dirs()
    urls = sitemap_urls(max_pages=max_pages)
    pages = []
    for url in urls:
        try:
            text = html_to_text(fetch_url_text(url))
        except Exception as exc:
            text = f"Import failed for {url}: {exc}"
        if len(text.split()) < 20:
            continue
        title = text.splitlines()[0][:100]
        pages.append((url, title, text))
        time.sleep(0.15)

    lines = [
        "# Shodhana Public Website Knowledge",
        "",
        f"Source site: {PUBLIC_SITE_URL}",
        f"Imported at: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "This file contains public website text for retrieval by Shodhana AI. Verify critical facts before using them in external communication.",
        "",
    ]
    for url, title, text in pages:
        lines.extend([f"## {title}", "", f"Source URL: {url}", "", text, ""])
    PUBLIC_SITE_OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    return {
        "pages": len(pages),
        "output": str(PUBLIC_SITE_OUTPUT.relative_to(ROOT)),
        "chunks": ingest_knowledge(),
    }


def ingest_knowledge():
    init_db()
    loaded = 0
    with db() as conn:
        conn.execute("delete from knowledge_chunks")
        for path in sorted(KNOWLEDGE_DIR.glob("**/*")):
            if path.suffix.lower() not in {".txt", ".md", ".csv"} or not path.is_file():
                continue
            text = read_text_file(path)
            for index, chunk in enumerate(chunk_text(text)):
                title = f"{path.stem} #{index + 1}"
                conn.execute(
                    """
                    insert into knowledge_chunks(source, title, content, tokens, created_at)
                    values (?, ?, ?, ?, ?)
                    """,
                    (str(path.relative_to(ROOT)), title, chunk, " ".join(tokenize(chunk)), int(time.time())),
                )
                loaded += 1
    return loaded


def score_text(query_tokens, doc_tokens):
    if not query_tokens or not doc_tokens:
        return 0.0
    q = {}
    d = {}
    for token in query_tokens:
        q[token] = q.get(token, 0) + 1
    for token in doc_tokens:
        d[token] = d.get(token, 0) + 1
    overlap = set(q) & set(d)
    dot = sum(q[t] * d[t] for t in overlap)
    q_norm = math.sqrt(sum(v * v for v in q.values()))
    d_norm = math.sqrt(sum(v * v for v in d.values()))
    return dot / (q_norm * d_norm) if q_norm and d_norm else 0.0


def search_knowledge(query, limit=5):
    query_tokens = tokenize(expand_query(query))
    with db() as conn:
        rows = conn.execute("select * from knowledge_chunks").fetchall()
    ranked = []
    for row in rows:
        score = score_text(query_tokens, row["tokens"].split())
        if score > 0:
            ranked.append((score, dict(row)))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [{"score": round(score, 3), **row} for score, row in ranked[:limit]]


def normalize_bool(value):
    return str(value or "").strip().lower() in {"yes", "y", "true", "1", "existing"}


def calculate_opportunity(row):
    score = 0
    role = (row.get("role") or "").lower()
    trend = (row.get("trend") or "").lower()
    notes = (row.get("notes") or "").lower()
    volume = float(row.get("estimated_volume_kg") or 0)
    price = float(row.get("estimated_price_usd_kg") or 0)
    existing = normalize_bool(row.get("current_shodhana_customer"))

    if "buyer" in role or "formulation" in role:
        score += 25
    if "cdmo" in role:
        score += 18
    if "competitor" in role:
        score -= 35
    if existing:
        score += 12
    if "growing" in trend or "increase" in trend:
        score += 18
    if "declining" in trend or "reduce" in trend:
        score -= 5
    if volume >= 1000:
        score += 20
    elif volume >= 250:
        score += 12
    elif volume > 0:
        score += 5
    if price > 0:
        score += 6
    if "regulatory" in notes or "usdmf" in notes or "europe" in notes or "regulated" in notes:
        score += 8
    if "pellet" in (row.get("product") or "").lower():
        score += 5

    score = max(0, min(score, 100))
    if score >= 75:
        tier = "Tier 1 - Strategic high-volume customer"
    elif score >= 55:
        tier = "Tier 2 - High-potential growing customer"
    elif existing:
        tier = "Tier 3 - Existing customer expansion"
    elif score >= 30:
        tier = "Tier 4 - Low/medium priority"
    else:
        tier = "Tier 5 - Avoid or review carefully"
    return score, tier


def import_market_csv(csv_path):
    init_db()
    path = Path(csv_path)
    count = 0
    with path.open(newline="", encoding="utf-8-sig") as handle, db() as conn:
        reader = csv.DictReader(handle)
        conn.execute("delete from market_rows")
        for row in reader:
            score, tier = calculate_opportunity(row)
            conn.execute(
                """
                insert into market_rows(
                    company, region, country, product, role, estimated_volume_kg,
                    estimated_price_usd_kg, competitor_supplier, current_shodhana_customer,
                    last_purchase_date, trend, notes, opportunity_score, tier, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("company", "").strip(),
                    row.get("region", "").strip(),
                    row.get("country", "").strip(),
                    row.get("product", "").strip(),
                    row.get("role", "").strip(),
                    float(row.get("estimated_volume_kg") or 0),
                    float(row.get("estimated_price_usd_kg") or 0),
                    row.get("competitor_supplier", "").strip(),
                    row.get("current_shodhana_customer", "").strip(),
                    row.get("last_purchase_date", "").strip(),
                    row.get("trend", "").strip(),
                    row.get("notes", "").strip(),
                    score,
                    tier,
                    int(time.time()),
                ),
            )
            count += 1
    return count


def csv_rows(path):
    path = Path(path)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def column_index(cell_ref):
    letters = re.sub(r"[^A-Z]", "", str(cell_ref or "").upper())
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return max(index - 1, 0)


def xml_text(node):
    return "".join(node.itertext()) if node is not None else ""


def xlsx_rows(path):
    rows = []
    with zipfile.ZipFile(path) as archive:
        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(".//{*}si"):
                shared_strings.append(xml_text(item))
        sheet_name = "xl/worksheets/sheet1.xml"
        if sheet_name not in archive.namelist():
            sheet_candidates = sorted(name for name in archive.namelist() if name.startswith("xl/worksheets/sheet"))
            if not sheet_candidates:
                return []
            sheet_name = sheet_candidates[0]
        root = ET.fromstring(archive.read(sheet_name))
        matrix = []
        for row_node in root.findall(".//{*}row"):
            values = []
            for cell in row_node.findall("{*}c"):
                idx = column_index(cell.attrib.get("r", ""))
                while len(values) <= idx:
                    values.append("")
                cell_type = cell.attrib.get("t")
                value_node = cell.find("{*}v")
                if cell_type == "s" and value_node is not None:
                    raw = value_node.text or "0"
                    value = shared_strings[int(raw)] if raw.isdigit() and int(raw) < len(shared_strings) else ""
                elif cell_type == "inlineStr":
                    value = xml_text(cell)
                else:
                    value = value_node.text if value_node is not None else ""
                values[idx] = value or ""
            if any(str(v).strip() for v in values):
                matrix.append(values)
    if not matrix:
        return []
    headers = [str(h).strip() or f"column_{i + 1}" for i, h in enumerate(matrix[0])]
    for values in matrix[1:]:
        row = {}
        for i, header in enumerate(headers):
            row[header] = values[i] if i < len(values) else ""
        if any(str(v).strip() for v in row.values()):
            rows.append(row)
    return rows


def parse_table_file(path):
    suffix = Path(path).suffix.lower()
    if suffix == ".xlsx":
        return xlsx_rows(path)
    return csv_rows(path)


def write_rows_csv(path, rows):
    if not rows:
        return 0
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


COLUMN_ALIASES = {
    "product_name": [
        "product", "product name", "product description", "description", "commodity",
        "item", "api", "drug", "molecule", "material", "goods description",
    ],
    "exporter": ["exporter", "shipper", "supplier", "seller", "consignor", "exporter name"],
    "importer": ["importer", "buyer", "receiver", "consignee", "customer", "importer name"],
    "origin_country": ["origin country", "country of origin", "export country", "source country", "origin"],
    "destination_country": ["destination country", "import country", "country", "dest country", "buyer country", "destination"],
    "quantity": ["quantity", "qty", "net weight", "net wt", "weight", "volume"],
    "quantity_kg": ["quantity kg", "qty kg", "net weight kg", "weight kg", "kg"],
    "unit": ["unit", "uom", "quantity unit", "measure unit"],
    "total_value_usd": [
        "invoice value usd", "total value usd", "value usd", "usd value",
        "invoice value", "fob value", "assessable value", "total value",
    ],
    "unit_price_usd_kg": ["unit price", "price per kg", "usd/kg", "price/kg", "unit price usd kg"],
    "shipment_date": ["date", "shipment date", "export date", "import date", "invoice date", "be date"],
    "shipment_id": ["shipment id", "invoice no", "invoice number", "bill no", "be no", "sb no"],
    "dmf_grade": ["dmf", "grade", "dmf grade", "regulatory grade"],
    "currency": ["currency", "invoice currency"],
    "source": ["source", "platform", "data source"],
    "notes": ["notes", "remarks", "remark"],
}


def normalized_header(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def detect_columns(headers):
    normalized = {header: normalized_header(header) for header in headers}
    detected = {}
    used = set()
    for canonical, aliases in COLUMN_ALIASES.items():
        alias_keys = [normalized_header(alias) for alias in aliases]
        best_header = ""
        best_score = 0.0
        for header, header_key in normalized.items():
            if header in used:
                continue
            for alias in alias_keys:
                if header_key == alias or alias in header_key or header_key in alias:
                    score = 1.0
                else:
                    score = difflib.SequenceMatcher(None, header_key, alias).ratio()
                if score > best_score:
                    best_score = score
                    best_header = header
        if best_header and best_score >= 0.74:
            detected[canonical] = best_header
            used.add(best_header)
    return detected


def row_value(row, mapping, canonical):
    header = mapping.get(canonical)
    return row.get(header, "") if header else ""


def quantity_to_kg(quantity, unit):
    qty = safe_float(quantity)
    unit_key = simple_key(unit)
    if not qty:
        return 0.0
    if unit_key in {"g", "gm", "gram", "grams"}:
        return qty / 1000
    if unit_key in {"mg", "milligram", "milligrams"}:
        return qty / 1_000_000
    if unit_key in {"mt", "ton", "tons", "tonne", "tonnes", "metric ton"}:
        return qty * 1000
    return qty


def best_alias_match(value, aliases, threshold=0.88):
    key = simple_key(value)
    best_key = ""
    best_score = 0.0
    for alias_key in aliases:
        score = difflib.SequenceMatcher(None, key, alias_key).ratio()
        if score > best_score:
            best_score = score
            best_key = alias_key
    if best_key and best_score >= threshold:
        return aliases[best_key]
    return ""


def simple_key(value):
    value = str(value or "").lower()
    value = value.replace("&", " and ")
    value = re.sub(r"\b(private|pvt|limited|ltd|llc|inc|gmbh|sa|s\.a|co|company|pharma|pharmaceuticals)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def load_alias_map(path, alias_col="alias", canonical_col="canonical_name"):
    aliases = {}
    metadata = {}
    for row in csv_rows(path):
        canonical = (row.get(canonical_col) or "").strip()
        alias = (row.get(alias_col) or "").strip()
        if not canonical or not alias:
            continue
        aliases[simple_key(alias)] = canonical
        metadata.setdefault(canonical, {}).update({k: v for k, v in row.items() if v})
    return aliases, metadata


def canonicalize(value, aliases):
    key = simple_key(value)
    if key in aliases:
        return aliases[key]
    fuzzy = best_alias_match(value, aliases)
    if fuzzy:
        return fuzzy
    return str(value or "").strip() or "Unknown"


def safe_float(value):
    cleaned = re.sub(r"[^0-9.\-]", "", str(value or ""))
    if cleaned in {"", ".", "-", "-."}:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def shipment_year(shipment_date):
    match = re.search(r"(20\d{2}|19\d{2})", str(shipment_date or ""))
    return int(match.group(1)) if match else 0


def classify_market(country):
    country_key = simple_key(country)
    regulated = {
        "usa", "us", "united states", "germany", "france", "italy", "spain",
        "united kingdom", "uk", "japan", "korea", "south korea", "australia",
        "canada", "netherlands", "portugal",
    }
    semi_regulated = {
        "india", "egypt", "argentina", "bangladesh", "brazil", "indonesia",
        "malaysia", "tanzania", "kenya", "zimbabwe", "mexico", "south africa",
    }
    if country_key in regulated:
        return "Regulated"
    if country_key in semi_regulated:
        return "Semi-regulated"
    return "Non-regulated"


def normalize_trade_row(row, mapping, product_aliases, company_aliases, source_name=""):
    product_raw = row_value(row, mapping, "product_name") or row.get("product_name", "")
    exporter_raw = row_value(row, mapping, "exporter") or row.get("exporter", "")
    importer_raw = row_value(row, mapping, "importer") or row.get("importer", "")
    product = canonicalize(product_raw, product_aliases)
    exporter = canonicalize(exporter_raw, company_aliases)
    importer = canonicalize(importer_raw, company_aliases)
    quantity = safe_float(row_value(row, mapping, "quantity_kg") or row.get("quantity_kg"))
    if not quantity:
        quantity = quantity_to_kg(row_value(row, mapping, "quantity"), row_value(row, mapping, "unit"))
    total_value = safe_float(row_value(row, mapping, "total_value_usd") or row.get("total_value_usd"))
    unit_price = safe_float(row_value(row, mapping, "unit_price_usd_kg") or row.get("unit_price_usd_kg"))
    if not unit_price and quantity and total_value:
        unit_price = total_value / quantity
    if not total_value and quantity and unit_price:
        total_value = quantity * unit_price
    shipment_date = row_value(row, mapping, "shipment_date") or row.get("shipment_date", "")
    year = shipment_year(shipment_date)
    destination_country = row_value(row, mapping, "destination_country") or row.get("destination_country", "")
    origin_country = row_value(row, mapping, "origin_country") or row.get("origin_country", "")
    market_category = classify_market(destination_country)
    dmf_grade = row_value(row, mapping, "dmf_grade") or row.get("dmf_grade", "")
    shipment_id = row_value(row, mapping, "shipment_id") or row.get("shipment_id", "")
    source = row_value(row, mapping, "source") or row.get("source", "") or source_name
    notes = row_value(row, mapping, "notes") or row.get("notes", "")
    duplicate_key = "|".join(
        [
            str(year),
            product.lower(),
            exporter.lower(),
            importer.lower(),
            str(round(quantity, 4)),
            str(round(total_value, 2)),
            str(shipment_date).strip().lower(),
        ]
    )
    return {
        "source": str(source).strip(),
        "shipment_date": str(shipment_date).strip(),
        "year": year,
        "product_raw": str(product_raw).strip(),
        "product_canonical": product,
        "exporter_raw": str(exporter_raw).strip(),
        "exporter_canonical": exporter,
        "importer_raw": str(importer_raw).strip(),
        "importer_canonical": importer,
        "origin_country": str(origin_country).strip(),
        "destination_country": str(destination_country).strip(),
        "market_category": market_category,
        "quantity_kg": quantity,
        "total_value_usd": total_value,
        "unit_price_usd_kg": unit_price,
        "dmf_grade": str(dmf_grade).strip(),
        "shipment_id": str(shipment_id).strip(),
        "duplicate_key": duplicate_key,
        "notes": str(notes).strip(),
    }


def import_shipment_rows(rows, source_name="", replace=True, original_name="sample"):
    init_db()
    seed_files()
    product_aliases, _ = load_alias_map(IMPORTS_DIR / "product_aliases.csv")
    company_aliases, _ = load_alias_map(IMPORTS_DIR / "company_aliases.csv")
    mapping = detect_columns(rows[0].keys()) if rows else {}
    seen = set()
    inserted = 0
    duplicates = 0
    with db() as conn:
        if replace:
            conn.execute("delete from shipment_rows")
        for row in rows:
            cleaned = normalize_trade_row(row, mapping, product_aliases, company_aliases, source_name)
            duplicate_key = cleaned["duplicate_key"]
            if duplicate_key in seen:
                duplicates += 1
                continue
            seen.add(duplicate_key)
            conn.execute(
                """
                insert into shipment_rows(
                    source, shipment_date, year, product_raw, product_canonical,
                    exporter_raw, exporter_canonical, importer_raw, importer_canonical,
                    origin_country, destination_country, market_category, quantity_kg,
                    total_value_usd, unit_price_usd_kg, dmf_grade, shipment_id,
                    duplicate_key, notes, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cleaned["source"],
                    cleaned["shipment_date"],
                    cleaned["year"],
                    cleaned["product_raw"],
                    cleaned["product_canonical"],
                    cleaned["exporter_raw"],
                    cleaned["exporter_canonical"],
                    cleaned["importer_raw"],
                    cleaned["importer_canonical"],
                    cleaned["origin_country"],
                    cleaned["destination_country"],
                    cleaned["market_category"],
                    cleaned["quantity_kg"],
                    cleaned["total_value_usd"],
                    cleaned["unit_price_usd_kg"],
                    cleaned["dmf_grade"],
                    cleaned["shipment_id"],
                    cleaned["duplicate_key"],
                    cleaned["notes"],
                    int(time.time()),
                ),
            )
            inserted += 1
        conn.execute(
            """
            insert into uploaded_files(original_name, stored_path, source_type, source_rows, clean_rows, duplicate_rows, created_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (original_name, source_name, "trade_data", len(rows), inserted, duplicates, int(time.time())),
        )
    return {
        "inserted": inserted,
        "duplicates_removed": duplicates,
        "source_rows": len(rows),
        "detected_columns": mapping,
    }


def import_shipment_csv(csv_path):
    return import_shipment_rows(csv_rows(csv_path), source_name=str(csv_path), replace=True, original_name=Path(csv_path).name)


def import_shipment_file(path, original_name):
    return import_shipment_rows(parse_table_file(path), source_name=str(path), replace=True, original_name=original_name)


def list_shipment_insights(limit=25):
    with db() as conn:
        rows = conn.execute(
            """
            select
                importer_canonical,
                product_canonical,
                destination_country,
                market_category,
                sum(quantity_kg) as total_quantity_kg,
                sum(total_value_usd) as total_value_usd,
                count(*) as shipment_count,
                max(year) as latest_year,
                group_concat(distinct exporter_canonical) as suppliers,
                group_concat(distinct dmf_grade) as grades
            from shipment_rows
            group by importer_canonical, product_canonical, destination_country, market_category
            order by total_quantity_kg desc, total_value_usd desc
            limit ?
            """,
            (limit,),
        ).fetchall()
    insights = []
    for row in rows:
        item = dict(row)
        total_qty = item.get("total_quantity_kg") or 0
        total_value = item.get("total_value_usd") or 0
        avg_price = total_value / total_qty if total_qty else 0
        suppliers = [s for s in (item.get("suppliers") or "").split(",") if s]
        shodhana_present = any("shodhana" in simple_key(s) for s in suppliers)
        competitor_suppliers = [s for s in suppliers if "shodhana" not in simple_key(s)]
        if shodhana_present and competitor_suppliers:
            opportunity = "Defend / expand share"
            action = "Customer already knows Shodhana. Compare competitor price and pitch reliability, DMF support, and supply continuity."
        elif shodhana_present:
            opportunity = "Existing customer"
            action = "Check if the same customer buys other Shodhana products from competitors and prepare a cross-sell pitch."
        else:
            opportunity = "New target"
            action = "Approach with customer-specific Duloxetine pitch and benchmark offer below observed average competitor price if margin allows."
        if item.get("market_category") == "Regulated":
            action += " Lead with DMF/regulatory support and audit readiness."
        item.update(
            {
                "avg_price_usd_kg": round(avg_price, 2),
                "target_price_usd_kg": round(avg_price * 0.97, 2) if avg_price else 0,
                "suppliers": suppliers,
                "opportunity": opportunity,
                "recommended_action": action,
            }
        )
        insights.append(item)
    return insights


def list_opportunities(limit=25):
    with db() as conn:
        rows = conn.execute(
            "select * from market_rows order by opportunity_score desc, estimated_volume_kg desc limit ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def dashboard_stats():
    init_db()
    with db() as conn:
        knowledge_chunks = conn.execute("select count(*) from knowledge_chunks").fetchone()[0]
        market_rows = conn.execute("select count(*) from market_rows").fetchone()[0]
        shipment_rows = conn.execute("select count(*) from shipment_rows").fetchone()[0]
        tier_1 = conn.execute("select count(*) from market_rows where opportunity_score >= 75").fetchone()[0]
        tier_2 = conn.execute(
            "select count(*) from market_rows where opportunity_score >= 55 and opportunity_score < 75"
        ).fetchone()[0]
    return {
        "knowledge_chunks": knowledge_chunks,
        "market_rows": market_rows,
        "shipment_rows": shipment_rows,
        "tier_1": tier_1,
        "tier_2": tier_2,
        "ai_mode": "OpenAI" if os.environ.get("OPENAI_API_KEY") else "Local",
        "public_website_file": PUBLIC_SITE_OUTPUT.exists(),
    }


def call_openai(system, user):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        parts = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    parts.append(content.get("text", ""))
        return "\n".join(parts).strip() or None
    except Exception as exc:
        return f"AI request failed: {exc}"


def local_answer(question, matches):
    if not matches:
        return (
            "I do not have enough Shodhana knowledge loaded yet. Add company/product documents "
            "to data/knowledge, or click Import Public Website, then click Ingest Knowledge."
        )
    if is_company_question(question):
        return local_company_answer(matches)
    bullets = []
    for match in matches[:3]:
        bullets.append(f"- {match['title']}: {match['content'][:420].strip()}")
    return "Relevant Shodhana context found:\n\n" + "\n\n".join(bullets)


def is_company_question(question):
    tokens = set(tokenize(question))
    return "company" in tokens or ("shodhana" in tokens and len(tokens) <= 4)


def local_company_answer(matches):
    text = " ".join(match["content"] for match in matches).lower()
    facts = []

    def add(condition, sentence):
        if condition and sentence not in facts:
            facts.append(sentence)

    add(
        "leading manufacturer and supplier" in text and ("api" in text or "active pharmaceutical" in text),
        "Shodhana Laboratories Pvt. Ltd. is positioned publicly as a manufacturer and supplier of Active Pharmaceutical Ingredients (APIs) and intermediates.",
    )
    add(
        "hyderabad" in text and "vizag" in text,
        "The public website mentions manufacturing sites in Hyderabad and Vizag.",
    )
    add(
        "us fda" in text or "japan pmda" in text or "kfda" in text or "cgmp" in text,
        "The website says its API facilities have been inspected/approved by global regulatory bodies such as US FDA, Japan PMDA, and KFDA, and that they meet cGMP standards.",
    )
    add(
        "vertically integrated" in text,
        "A key strength described on the website is vertical integration, including support from subsidiary units for early/back-stage intermediates.",
    )
    add(
        "research & development" in text or "r&d" in text,
        "The company highlights centralized R&D, process development, scaling up, and new product development capability.",
    )
    add(
        "quality management" in text or "quality standards" in text,
        "The public positioning emphasizes quality management, regulatory readiness, and reliable supply.",
    )

    if not facts:
        bullets = [f"- {match['content'][:360].strip()}" for match in matches[:3]]
        return "I found company-related context, but it needs review:\n\n" + "\n\n".join(bullets)

    sources = []
    for match in matches:
        source_match = re.search(r"Source URL:\s*(https?://\S+)", match["content"])
        if source_match and source_match.group(1) not in sources:
            sources.append(source_match.group(1))

    answer = "About Shodhana:\n\n" + "\n".join(f"- {fact}" for fact in facts)
    if sources:
        answer += "\n\nSource pages:\n" + "\n".join(f"- {url}" for url in sources[:3])
    return answer


def answer_question(question):
    matches = search_knowledge(question, limit=6)
    context = "\n\n".join([f"{m['title']}:\n{m['content']}" for m in matches])
    system = (
        "You are Shodhana AI, a pharma sales intelligence assistant. Answer using only the "
        "provided Shodhana context. If the context is incomplete, say what data is missing."
    )
    user = f"Question: {question}\n\nShodhana context:\n{context}"
    ai = call_openai(system, user)
    return {"answer": ai or local_answer(question, matches), "matches": matches}


def pitch_for_company(company):
    with db() as conn:
        row = conn.execute(
            "select * from market_rows where lower(company)=lower(?) order by opportunity_score desc limit 1",
            (company,),
        ).fetchone()
    if not row:
        return {"pitch": f"No market row found for {company}. Import CSV data first."}
    row = dict(row)
    matches = search_knowledge(f"Shodhana strengths {row['product']} API pellets CDMO regulatory", limit=5)
    context = "\n\n".join([m["content"] for m in matches])
    system = (
        "You create concise pharma business development pitch drafts for Shodhana. "
        "Do not invent approvals, capacities, or customer names. Mark missing facts clearly."
    )
    user = f"""
Create a customer-specific pitch for this company.

Customer data:
{json.dumps(row, indent=2)}

Relevant Shodhana context:
{context}

Return:
1. Opportunity note
2. Recommended positioning
3. Email subject
4. Short email draft
5. Presentation slide outline
6. Next action
"""
    ai = call_openai(system, user)
    if ai:
        return {"pitch": ai, "customer": row, "matches": matches}

    product = row.get("product") or "Duloxetine"
    pitch = f"""Opportunity note
{row['company']} is classified as {row['tier']} with an opportunity score of {row['opportunity_score']}/100. The current product focus is {product}. Reported trend: {row.get('trend') or 'not available'}.

Recommended positioning
Position Shodhana around reliable {product} supply, regulatory readiness, quality systems, and a focused Duloxetine capability discussion. Validate exact approvals, capacity, and documentation before external use.

Email subject
Potential {product} supply and partnership discussion with Shodhana

Short email draft
Dear Team,

We would like to explore whether Shodhana can support your {product} requirements. Based on your market activity, we believe there may be a fit around reliable supply, quality documentation, and long-term business continuity.

Could we schedule a short discussion to understand your current sourcing priorities and share Shodhana's relevant capabilities?

Regards,
Shodhana Business Development

Presentation slide outline
1. Shodhana overview
2. {product} capability
3. Quality and regulatory readiness
4. Supply reliability and business continuity
5. Proposed next discussion

Next action
Review internal facts, confirm decision maker, then send a personalized first email."""
    return {"pitch": pitch, "customer": row, "matches": matches}


def seed_files():
    company = KNOWLEDGE_DIR / "shodhana_company_profile.md"
    market = IMPORTS_DIR / "duloxetine_market.csv"
    raw_shipments = IMPORTS_DIR / "raw_shipments_duloxetine.csv"
    product_aliases = IMPORTS_DIR / "product_aliases.csv"
    company_aliases = IMPORTS_DIR / "company_aliases.csv"
    if not company.exists():
        company.write_text(
            """# Shodhana Company Profile - Starter Knowledge

Shodhana AI should understand Shodhana as a pharma business before generating any pitch.

Core positioning:
Shodhana AI is a pharma sales intelligence and organizational knowledge platform for Shodhana. It is designed to support API, pellets, intermediates, and CDMO business development.

Pilot focus:
- Duloxetine Hydrochloride API
- Duloxetine Pellets

Business goal:
Improve growth and sales efficiency by helping the team identify customers, analyze competitor and market data, prioritize opportunities, generate customer-specific pitches, summarize communication, and reduce manual follow-up work.

Important principle:
The AI must not create generic presentations. It should adapt the pitch to the customer, product, region, and business model.

Data still needed:
- Confirmed regulatory approvals
- Manufacturing capacity
- Facility details
- Certifications
- Existing customers
- Known competitors
- Product documentation
- Approved corporate pitch language
""",
            encoding="utf-8",
        )
    if not market.exists():
        market.write_text(
            """company,region,country,product,role,estimated_volume_kg,estimated_price_usd_kg,competitor_supplier,current_shodhana_customer,last_purchase_date,trend,notes
Example Pharma GmbH,Europe,Germany,Duloxetine API,Buyer,1200,88,Competitor A,No,2026-02-15,Growing,Regulated market buyer; validate approvals needed
Sample Formulations Inc,North America,USA,Duloxetine Pellets,Formulation company,750,105,Competitor B,No,2026-01-10,Growing,Potential pellets opportunity
Existing Customer Ltd,Asia,India,Duloxetine API,Buyer,400,82,Competitor C,Yes,2026-03-01,Stable,Existing customer with expansion potential
Integrated Competitor SA,Latin America,Brazil,Duloxetine API,Competitor,1500,79,Own API,No,2026-04-12,Stable,May not be suitable as target
""",
            encoding="utf-8",
        )
    if not raw_shipments.exists():
        raw_shipments.write_text(
            """source,shipment_date,product_name,exporter,importer,origin_country,destination_country,quantity_kg,total_value_usd,unit_price_usd_kg,dmf_grade,shipment_id,notes
ChemDoss,2024-01-18,Duloxetine HCL,Megafide Pharma Pvt Ltd,Asher Pharma GmbH,India,Germany,400,146000,,DMF,CD-1001,Original shipment row
API-FDF,2024-01-18,Duloxetine Hydrochloride,Megafide Pharma Private Limited,Asher Pharma GMBH,India,Germany,400,146000,,DMF,AP-7781,Same shipment from another source; should be removed as duplicate
ChemDoss,2024-05-22,Duloxetin Hydrochloride,Olympic Pharma Ltd,Asher Pharma GmbH,India,Germany,500,181000,,Non-DMF,CD-1099,Name typo should map to Duloxetine HCL
ChemDoss,2025-02-12,Duloxetine Pellets 20%,Competitor B Pvt Ltd,Sample Formulations Inc,India,USA,250,28000,,DMF,CD-2011,Pellets opportunity in regulated market
ChemDoss,2025-07-04,Duloxetine HCl,Shodhana Laboratories Pvt Ltd,Existing Customer Ltd,India,India,150,12750,,DMF,SH-5555,Existing Shodhana sale
ChemDoss,2025-07-09,Duloxetine HCl,Competitor C Pvt Ltd,Existing Customer Limited,India,India,100,9000,,DMF,CD-3333,Same customer also buying from competitor
""",
            encoding="utf-8",
        )
    if not product_aliases.exists():
        product_aliases.write_text(
            """canonical_name,alias,product_type,shodhana_product,regulatory_position,pitch_angle
Duloxetine HCL,Duloxetine HCL,API,Yes,DMF/CEP where verified,Lead with Duloxetine API capability and regulatory support
Duloxetine HCL,Duloxetine Hydrochloride,API,Yes,DMF/CEP where verified,Lead with Duloxetine API capability and regulatory support
Duloxetine HCL,Duloxetin Hydrochloride,API,Yes,DMF/CEP where verified,Correct typo/variant and group under Duloxetine HCL
Duloxetine HCL,Duloxetine HCl,API,Yes,DMF/CEP where verified,Lead with Duloxetine API capability and regulatory support
Duloxetine Pellets,Duloxetine Pellets 20%,Pellets,Yes,Technical package where verified,Pitch semi-formulation/pellets capability
Duloxetine Pellets,Duloxetine Pellets,Pellets,Yes,Technical package where verified,Pitch semi-formulation/pellets capability
""",
            encoding="utf-8",
        )
    if not company_aliases.exists():
        company_aliases.write_text(
            """canonical_name,alias,company_type,relationship,notes
Megafide Pharma,Megafide Pharma Pvt Ltd,Exporter,Competitor/Supplier,Normalize private limited variants
Megafide Pharma,Megafide Pharma Private Limited,Exporter,Competitor/Supplier,Normalize private limited variants
Asher Pharma,Asher Pharma GmbH,Importer,Target customer,Regulated market buyer
Asher Pharma,Asher Pharma GMBH,Importer,Target customer,Same company casing variant
Olympic Pharma,Olympic Pharma Ltd,Exporter,Competitor/Supplier,Competitor supplier
Competitor B,Competitor B Pvt Ltd,Exporter,Competitor/Supplier,Competitor supplier
Competitor C,Competitor C Pvt Ltd,Exporter,Competitor/Supplier,Competitor supplier
Sample Formulations,Sample Formulations Inc,Importer,Target customer,Formulation company
Shodhana Laboratories,Shodhana Laboratories Pvt Ltd,Exporter,Self,Existing supplier
Existing Customer,Existing Customer Ltd,Importer,Existing customer,Normalize limited variants
Existing Customer,Existing Customer Limited,Importer,Existing customer,Normalize limited variants
""",
            encoding="utf-8",
        )


INDEX_HTML = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Shodhana AI Pilot</title>
  <style>
    :root {
      color-scheme: light;
      --bg:#f5f7f8;
      --surface:#ffffff;
      --surface-2:#f9fbfc;
      --ink:#172026;
      --muted:#62717d;
      --line:#d9e1e6;
      --brand:#0f766e;
      --brand-2:#155e75;
      --accent:#a16207;
      --danger:#b42318;
      --soft:#eaf6f4;
      --shadow:0 14px 35px rgba(30,43,52,.08);
    }
    * { box-sizing:border-box; }
    body { margin:0; font-family:Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:var(--bg); color:var(--ink); }
    header { height:68px; background:var(--surface); border-bottom:1px solid var(--line); padding:0 28px; display:flex; align-items:center; justify-content:space-between; gap:18px; position:sticky; top:0; z-index:20; }
    h1 { margin:0; font-size:21px; letter-spacing:0; }
    h2 { margin:0 0 14px; font-size:15px; letter-spacing:0; }
    h3 { margin:0; font-size:13px; letter-spacing:0; }
    main { display:grid; grid-template-columns:390px minmax(0,1fr); min-height:calc(100vh - 68px); }
    aside { background:var(--surface); border-right:1px solid var(--line); padding:20px; display:flex; flex-direction:column; gap:16px; }
    section { padding:22px; min-width:0; }
    label { display:block; font-size:12px; color:var(--muted); margin-bottom:7px; font-weight:700; }
    input, textarea { width:100%; border:1px solid var(--line); border-radius:7px; padding:11px 12px; font:inherit; background:#fff; color:var(--ink); outline:none; transition:border-color .15s, box-shadow .15s; }
    textarea { min-height:118px; resize:vertical; line-height:1.45; }
    input:focus, textarea:focus { border-color:var(--brand); box-shadow:0 0 0 3px rgba(15,118,110,.12); }
    button { border:0; background:var(--brand); color:#fff; padding:10px 13px; min-height:40px; border-radius:7px; cursor:pointer; font:inherit; font-size:13px; font-weight:750; line-height:1; display:inline-flex; align-items:center; justify-content:center; gap:8px; transition:transform .12s, box-shadow .12s, background .12s; white-space:nowrap; }
    button:hover { transform:translateY(-1px); box-shadow:0 8px 18px rgba(15,118,110,.18); }
    button:focus-visible { outline:3px solid rgba(15,118,110,.25); outline-offset:2px; }
    button:disabled { cursor:progress; opacity:.62; transform:none; box-shadow:none; }
    button.secondary { background:var(--brand-2); }
    button.ghost { background:#e8eef2; color:#20303a; }
    button.warning { background:var(--accent); }
    button.small { min-height:32px; padding:8px 10px; font-size:12px; border-radius:6px; }
    table { width:100%; border-collapse:separate; border-spacing:0; font-size:13px; }
    th, td { padding:12px 12px; border-bottom:1px solid var(--line); text-align:left; vertical-align:middle; }
    th { color:#40505c; font-size:11px; text-transform:uppercase; letter-spacing:.06em; background:#f7fafb; position:sticky; top:0; z-index:1; }
    tbody tr:hover { background:#fbfdfd; }
    pre { margin:0; white-space:pre-wrap; background:#0f1f2a; color:#edf7f7; border:1px solid #18303d; padding:16px; border-radius:8px; overflow:auto; min-height:300px; line-height:1.45; font-size:13px; }
    code { font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:.92em; }
    .muted { color:var(--muted); }
    .app-meta { display:flex; gap:10px; align-items:center; color:var(--muted); font-size:13px; }
    .badge { display:inline-flex; align-items:center; gap:6px; border:1px solid var(--line); background:#fff; color:#40505c; border-radius:999px; padding:6px 10px; font-size:12px; font-weight:700; }
    .panel { background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:16px; box-shadow:var(--shadow); }
    aside .panel { box-shadow:none; }
    .panel-head { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:14px; }
    .panel-title { display:flex; align-items:center; gap:9px; }
    .panel-title span { width:26px; height:26px; border-radius:7px; display:inline-flex; align-items:center; justify-content:center; background:var(--soft); color:var(--brand); font-weight:850; font-size:12px; }
    .control-stack { display:flex; flex-direction:column; gap:13px; }
    .button-row { display:flex; flex-wrap:wrap; gap:10px; align-items:center; }
    .button-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
    .field-row { display:grid; gap:8px; }
    .status-line { margin-top:12px; min-height:20px; color:var(--muted); font-size:13px; line-height:1.35; }
    .stats-grid { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:14px; margin-bottom:16px; }
    .stat { background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:14px; min-height:86px; box-shadow:var(--shadow); display:flex; flex-direction:column; justify-content:space-between; }
    .stat span { color:var(--muted); font-size:12px; font-weight:700; }
    .stat strong { display:block; font-size:24px; letter-spacing:0; margin-top:6px; }
    .workspace { display:grid; grid-template-columns:minmax(0, 1.08fr) minmax(360px, .92fr); gap:16px; align-items:start; }
    .table-wrap { overflow:auto; max-height:520px; border:1px solid var(--line); border-radius:8px; }
    .score { font-weight:850; color:var(--brand); }
    .tier { max-width:240px; color:#33434e; }
    .empty { padding:16px; color:var(--muted); }
    .quick-grid { display:grid; grid-template-columns:1fr; gap:8px; }
    .quick-grid button { justify-content:flex-start; background:#f0f5f7; color:#23343f; box-shadow:none; transform:none; white-space:normal; line-height:1.25; text-align:left; }
    .output-toolbar { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
    .tip { position:relative; }
    .tip::after { content:attr(data-tooltip); position:absolute; left:50%; bottom:calc(100% + 10px); transform:translateX(-50%) translateY(4px); min-width:220px; max-width:300px; background:#142530; color:#fff; padding:9px 10px; border-radius:7px; font-size:12px; font-weight:600; line-height:1.35; opacity:0; pointer-events:none; transition:opacity .12s, transform .12s; white-space:normal; z-index:50; box-shadow:0 14px 28px rgba(0,0,0,.18); }
    .tip::before { content:""; position:absolute; left:50%; bottom:calc(100% + 4px); transform:translateX(-50%); border:6px solid transparent; border-top-color:#142530; opacity:0; transition:opacity .12s; z-index:51; }
    .tip:hover::after, .tip:hover::before, .tip:focus-visible::after, .tip:focus-visible::before { opacity:1; transform:translateX(-50%) translateY(0); }
    aside .tip::after { left:0; transform:translateY(4px); }
    aside .tip::before { left:22px; transform:none; }
    aside .tip:hover::after, aside .tip:focus-visible::after { transform:translateY(0); }
    @media (max-width:1180px) {
      main { grid-template-columns:1fr; }
      aside { border-right:0; border-bottom:1px solid var(--line); }
      .workspace { grid-template-columns:1fr; }
    }
    @media (max-width:760px) {
      header { height:auto; padding:16px; align-items:flex-start; flex-direction:column; }
      section, aside { padding:14px; }
      .stats-grid { grid-template-columns:1fr 1fr; }
      .button-grid { grid-template-columns:1fr; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Shodhana AI Pilot</h1>
      <div class="muted">Duloxetine intelligence workspace</div>
    </div>
    <div class="app-meta">
      <span class="badge" id="modeBadge">Mode: Local</span>
      <span class="badge">RAG + scoring</span>
    </div>
  </header>
  <main>
    <aside>
      <div class="panel">
        <div class="panel-head">
          <div class="panel-title"><span>1</span><h2>Data</h2></div>
        </div>
        <div class="control-stack">
          <div class="button-grid">
            <button class="ghost tip" data-tooltip="Pull public Shodhana website pages into the knowledge base." onclick="importWebsite(this)">Import Website</button>
            <button class="tip" data-tooltip="Rebuild searchable chunks from files in data/knowledge." onclick="ingest(this)">Ingest Knowledge</button>
            <button class="secondary tip" data-tooltip="Load Duloxetine customer and market rows from the CSV file." onclick="importCsv(this)">Import CSV</button>
            <button class="secondary tip" data-tooltip="Clean raw shipment/export rows, remove duplicates, normalize names, and calculate price insights." onclick="importShipments(this)">Import Shipments</button>
            <button class="warning tip" data-tooltip="Reload dashboard counters and the opportunity table." onclick="refreshAll(this)">Refresh</button>
          </div>
          <div id="setupResult" class="status-line">Ready</div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <div class="panel-title"><span>2</span><h2>Knowledge</h2></div>
        </div>
        <div class="control-stack">
          <div class="field-row">
            <label for="question">Question</label>
            <textarea id="question">Tell me about Shodhana company</textarea>
          </div>
          <div class="button-row">
            <button class="tip" data-tooltip="Search Shodhana knowledge and generate an answer." onclick="ask(this)">Ask</button>
            <button class="ghost tip" data-tooltip="Replace the question with a blank field." onclick="clearQuestion()">Clear</button>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <div class="panel-title"><span>3</span><h2>Pitch</h2></div>
        </div>
        <div class="control-stack">
          <div class="field-row">
            <label for="company">Company</label>
            <input id="company" value="Example Pharma GmbH">
          </div>
          <div class="button-row">
            <button class="tip" data-tooltip="Create an opportunity note, email draft, slide outline, and next action." onclick="pitch(this)">Generate Pitch</button>
            <button class="ghost tip" data-tooltip="Use the first company from the opportunity table." onclick="useTopCompany()">Top Company</button>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <div class="panel-title"><span>Q</span><h2>Quick Prompts</h2></div>
        </div>
        <div class="quick-grid">
          <button class="tip" data-tooltip="Ask for a company overview from the public website knowledge." onclick="quickAsk('Tell me about Shodhana company')">Company overview</button>
          <button class="tip" data-tooltip="Ask for Duloxetine API details from the imported knowledge." onclick="quickAsk('What does Shodhana say about Duloxetine HCL?')">Duloxetine profile</button>
          <button class="tip" data-tooltip="Ask why this pilot differs from generic AI tools." onclick="quickAsk('Why is Shodhana AI different from generic ChatGPT?')">Why custom AI</button>
        </div>
      </div>
    </aside>

    <section>
      <div class="stats-grid">
        <div class="stat"><span>Knowledge Chunks</span><strong id="knowledgeCount">0</strong></div>
        <div class="stat"><span>Market Rows</span><strong id="marketCount">0</strong></div>
        <div class="stat"><span>Clean Shipments</span><strong id="shipmentCount">0</strong></div>
        <div class="stat"><span>Tier 1</span><strong id="tierOneCount">0</strong></div>
      </div>

      <div class="workspace">
        <div class="panel">
          <div class="panel-head">
            <div class="panel-title"><span>T</span><h2>Top Opportunities</h2></div>
            <button class="ghost small tip" data-tooltip="Reload customer scores from the current database." onclick="loadOpps()">Reload</button>
          </div>
          <div id="opportunities" class="table-wrap"></div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div class="panel-title"><span>S</span><h2>Shipment Insights</h2></div>
            <button class="ghost small tip" data-tooltip="Reload cleaned shipment/customer pricing insights." onclick="loadShipmentInsights()">Reload</button>
          </div>
          <div id="shipmentInsights" class="table-wrap"></div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div class="panel-title"><span>A</span><h2>AI Output</h2></div>
            <div class="output-toolbar">
              <button class="ghost small tip" data-tooltip="Copy the current AI output to clipboard." onclick="copyOutput()">Copy</button>
              <button class="ghost small tip" data-tooltip="Clear only this output area." onclick="clearOutput()">Clear</button>
            </div>
          </div>
          <pre id="output">Ready.</pre>
        </div>
      </div>
    </section>
  </main>
  <script>
    let latestRows = [];

    async function api(path, body) {
      const res = await fetch(path, { method: body ? 'POST' : 'GET', headers: {'Content-Type':'application/json'}, body: body ? JSON.stringify(body) : undefined });
      if (!res.ok) throw new Error(await res.text());
      return await res.json();
    }

    async function withBusy(button, label, task) {
      const original = button ? button.textContent : '';
      try {
        if (button) {
          button.disabled = true;
          button.textContent = label;
        }
        return await task();
      } catch (error) {
        setStatus(error.message || String(error), true);
        throw error;
      } finally {
        if (button) {
          button.disabled = false;
          button.textContent = original;
        }
      }
    }

    function setStatus(message, isError=false) {
      const el = document.getElementById('setupResult');
      el.textContent = message;
      el.style.color = isError ? 'var(--danger)' : 'var(--muted)';
    }

    async function refreshStats() {
      const data = await api('/api/stats');
      document.getElementById('knowledgeCount').textContent = data.knowledge_chunks;
      document.getElementById('marketCount').textContent = data.market_rows;
      document.getElementById('shipmentCount').textContent = data.shipment_rows;
      document.getElementById('tierOneCount').textContent = data.tier_1;
      document.getElementById('modeBadge').textContent = `Mode: ${data.ai_mode}`;
    }

    async function refreshAll(button) {
      await withBusy(button, 'Refreshing', async () => {
        await refreshStats();
        await loadOpps();
        await loadShipmentInsights();
        setStatus('Dashboard refreshed.');
      });
    }

    async function ingest(button) {
      await withBusy(button, 'Ingesting', async () => {
        const data = await api('/api/ingest', {});
        setStatus(`Loaded ${data.chunks} knowledge chunks.`);
        await refreshStats();
      });
    }

    async function importCsv(button) {
      await withBusy(button, 'Importing', async () => {
        const data = await api('/api/import-market', {});
        setStatus(`Imported ${data.rows} market rows.`);
        await refreshStats();
        await loadOpps();
      });
    }

    async function importShipments(button) {
      await withBusy(button, 'Cleaning', async () => {
        const data = await api('/api/import-shipments', {});
        setStatus(`Cleaned ${data.inserted} shipment rows. Removed ${data.duplicates_removed} duplicate rows from ${data.source_rows} source rows.`);
        await refreshStats();
        await loadShipmentInsights();
      });
    }

    async function importWebsite(button) {
      await withBusy(button, 'Importing', async () => {
        setStatus('Importing public website pages...');
        const data = await api('/api/import-website', {});
        setStatus(`Imported ${data.pages} website pages and loaded ${data.chunks} chunks.`);
        await refreshStats();
      });
    }

    async function ask(button) {
      const question = document.getElementById('question').value.trim();
      if (!question) {
        setOutput('Type a question first.');
        return;
      }
      await withBusy(button, 'Asking', async () => {
        const data = await api('/api/ask', {question});
        setOutput(data.answer);
      });
    }

    async function pitch(button) {
      const company = document.getElementById('company').value.trim();
      if (!company) {
        setOutput('Type a company name first.');
        return;
      }
      await withBusy(button, 'Generating', async () => {
        const data = await api('/api/pitch', {company});
        setOutput(data.pitch);
      });
    }

    async function generateFor(company) {
      document.getElementById('company').value = company;
      const data = await api('/api/pitch', {company});
      setOutput(data.pitch);
    }

    async function loadOpps() {
      const data = await api('/api/opportunities');
      latestRows = data.rows || [];
      const container = document.getElementById('opportunities');
      if (!latestRows.length) {
        container.innerHTML = '<div class="empty">No market data imported.</div>';
        return;
      }
      container.innerHTML = `<table><thead><tr><th>Company</th><th>Product</th><th>Region</th><th>Score</th><th>Tier</th><th>Action</th></tr></thead><tbody>${latestRows.map(row => `<tr><td><strong>${esc(row.company)}</strong></td><td>${esc(row.product)}</td><td>${esc(row.region)}</td><td class="score">${row.opportunity_score}</td><td class="tier">${esc(row.tier)}</td><td><button class="small tip" data-tooltip="Generate a tailored pitch for this company." onclick="generateFor('${jsEsc(row.company)}')">Pitch</button></td></tr>`).join('')}</tbody></table>`;
      setTooltipTitles();
    }

    async function loadShipmentInsights() {
      const data = await api('/api/shipment-insights');
      const rows = data.rows || [];
      const container = document.getElementById('shipmentInsights');
      if (!rows.length) {
        container.innerHTML = '<div class="empty">No shipment data imported. Click Import Shipments.</div>';
        return;
      }
      container.innerHTML = `<table><thead><tr><th>Importer</th><th>Product</th><th>Market</th><th>Qty KG</th><th>Avg $/KG</th><th>Suppliers</th><th>Opportunity</th></tr></thead><tbody>${rows.map(row => `<tr><td><strong>${esc(row.importer_canonical)}</strong></td><td>${esc(row.product_canonical)}</td><td>${esc(row.market_category)}<br><span class="muted">${esc(row.destination_country)}</span></td><td>${num(row.total_quantity_kg)}</td><td class="score">${num(row.avg_price_usd_kg)}</td><td>${esc((row.suppliers || []).join(', '))}</td><td class="tier">${esc(row.opportunity)}<br><span class="muted">${esc(row.recommended_action)}</span></td></tr>`).join('')}</tbody></table>`;
      setTooltipTitles();
    }

    function quickAsk(question) {
      document.getElementById('question').value = question;
      ask();
    }

    function useTopCompany() {
      if (!latestRows.length) {
        setOutput('Import the Duloxetine CSV first.');
        return;
      }
      document.getElementById('company').value = latestRows[0].company;
    }

    function clearQuestion() {
      document.getElementById('question').value = '';
    }

    function setOutput(text) {
      document.getElementById('output').textContent = text || '';
    }

    function clearOutput() {
      setOutput('');
    }

    async function copyOutput() {
      const text = document.getElementById('output').textContent;
      try {
        await navigator.clipboard.writeText(text);
        setStatus('Output copied.');
      } catch (error) {
        setStatus('Copy failed. Select the output text manually.', true);
      }
    }

    function esc(value) {
      return String(value ?? '').replace(/[&<>"']/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
    }

    function jsEsc(value) {
      return String(value ?? '').replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, ' ');
    }

    function num(value) {
      const n = Number(value || 0);
      return n.toLocaleString(undefined, {maximumFractionDigits: 2});
    }

    function setTooltipTitles() {
      document.querySelectorAll('[data-tooltip]').forEach(el => {
        el.setAttribute('title', el.getAttribute('data-tooltip'));
      });
    }

    setTooltipTitles();
    refreshStats();
    loadOpps();
    loadShipmentInsights();
  </script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def send_json(self, payload, status=200):
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/opportunities":
            limit = int(parse_qs(parsed.query).get("limit", ["25"])[0])
            self.send_json({"rows": list_opportunities(limit)})
            return
        if parsed.path == "/api/stats":
            self.send_json(dashboard_stats())
            return
        if parsed.path == "/api/shipment-insights":
            limit = int(parse_qs(parsed.query).get("limit", ["25"])[0])
            self.send_json({"rows": list_shipment_insights(limit)})
            return
        self.send_error(404)

    def do_HEAD(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return
        self.send_error(404)

    def read_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_POST(self):
        try:
            if self.path == "/api/ingest":
                seed_files()
                self.send_json({"chunks": ingest_knowledge()})
                return
            if self.path == "/api/import-market":
                seed_files()
                rows = import_market_csv(IMPORTS_DIR / "duloxetine_market.csv")
                self.send_json({"rows": rows})
                return
            if self.path == "/api/import-shipments":
                seed_files()
                self.send_json(import_shipment_csv(IMPORTS_DIR / "raw_shipments_duloxetine.csv"))
                return
            if self.path == "/api/import-website":
                seed_files()
                self.send_json(import_public_website(max_pages=30))
                return
            if self.path == "/api/ask":
                body = self.read_body()
                self.send_json(answer_question(body.get("question", "")))
                return
            if self.path == "/api/pitch":
                body = self.read_body()
                self.send_json(pitch_for_company(body.get("company", "")))
                return
            self.send_error(404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


def main():
    init_db()
    seed_files()
    host = "127.0.0.1"
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Shodhana AI Pilot running at http://{host}:{port}")
    print(f"Knowledge folder: {KNOWLEDGE_DIR}")
    print(f"Market CSV: {IMPORTS_DIR / 'duloxetine_market.csv'}")
    server.serve_forever()


if __name__ == "__main__":
    main()
