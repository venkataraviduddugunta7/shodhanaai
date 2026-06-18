import csv
import datetime as dt
import difflib
import re
from pathlib import Path

from .config import SEED_DIR

PRODUCT_MAP = SEED_DIR / "product_mappings.csv"
COMPANY_MAP = SEED_DIR / "company_mappings.csv"

LEGAL_WORDS = {
    "PVT", "PRIVATE", "LTD", "LIMITED", "LLP", "INC", "CORP", "CORPORATION",
    "CO", "GMBH", "SA", "S A", "BV", "PLC", "P", "M", "S",
}

INVALID_KG_UNITS = {"NOS", "NO", "PCS", "PC", "UNT", "UNITS", "VLS", "LOT", "CTN", "DRM"}

COUNTRY_ALIASES = {
    "AMERICA": "United States",
    "RUSSIAN FEDERATION": "Russia",
    "UAE": "United Arab Emirates",
    "U K": "United Kingdom",
    "UK": "United Kingdom",
    "UNI": "United Kingdom",
    "USA": "United States",
    "U S A": "United States",
    "UNITED STATES OF AMERICA": "United States",
    "VIET NAM": "Vietnam",
    "EG": "Egypt",
    "EGY": "Egypt",
    "EGYPT ARAB REPUBLIC": "Egypt",
    "ARAB REPUBLIC OF EGYPT": "Egypt",
    "US": "United States",
    "UNITED STATES": "United States",
    "GREAT BRITAIN": "United Kingdom",
    "GB": "United Kingdom",
    "ENGLAND": "United Kingdom",
    "REPUBLIC OF KOREA": "South Korea",
    "KOREA REPUBLIC OF": "South Korea",
    "KOREA": "South Korea",
    "KOREA REPUBLIC": "South Korea",
    "SOUTH KOREA": "South Korea",
    "PRC": "China",
    "PEOPLES REPUBLIC OF CHINA": "China",
    "PEOPLE S REPUBLIC OF CHINA": "China",
    "CN": "China",
    "IND": "India",
    "DEUTSCHLAND": "Germany",
    "GERMANY": "Germany",
    "HOLLAND": "Netherlands",
    "NETHERLANDS": "Netherlands",
    "KSA": "Saudi Arabia",
    "SAUDI ARAB": "Saudi Arabia",
    "SAUDI ARABIA": "Saudi Arabia",
    "ISLAMIC REPUBLIC OF IRAN": "Iran",
    "IRAN ISLAMIC REPUBLIC OF": "Iran",
    "PHILIPINES": "Philippines",
    "PHILLIPINES": "Philippines",
    "PHILIPPINES": "Philippines",
    "SYRIAN ARAB REPUBLIC": "Syria",
    "SRILANKA": "Sri Lanka",
    "SRI LANKA": "Sri Lanka",
    "BOLIVARIAN REPUBLIC OF VENEZUELA": "Venezuela",
    "VENEZUELA BOLIVARIAN REPUBLIC OF": "Venezuela",
    "VIETNAM": "Vietnam",
    "TANZANIA UNITED REPUBLIC OF": "Tanzania",
    "UNITED REPUBLIC OF TANZANIA": "Tanzania",
}

ADDRESS_MARKERS = {
    " BUILDING ", " REGISTRATION ", " TAX ID ", " STREET ", " ROAD ",
    " COLONY ", " PLOT ", " BEHIND ", " PINCODE ", " DISTRICT ",
}


def simple_key(value):
    value = str(value or "").upper().replace("&", " AND ")
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def matching_company_key(value):
    words = [word for word in simple_key(value).split() if word not in LEGAL_WORDS]
    return " ".join(words)


def display_company(value):
    cleaned = simple_key(value)
    if not cleaned:
        return "UNKNOWN"
    if cleaned.startswith("TO THE ORDER OF"):
        return "TO THE ORDER OF"
    padded = f" {cleaned} "
    cut_at = min([padded.find(marker) for marker in ADDRESS_MARKERS if marker in padded] or [-1])
    if cut_at > 0:
        cleaned = padded[:cut_at].strip()
    words = [word for word in cleaned.split() if word not in LEGAL_WORDS]
    cleaned = " ".join(words) or cleaned

    # Strip any suffix starting with FOR, AND, or ANDMEDICAL followed by generic text (handles typos and long tails)
    cleaned = re.sub(
        r"\b(FOR|AND|ANDMEDICAL|AND\s+MEDICAL|FOR\s+PHARMACEUTICALS|FOR\s+PHARMACEUTICAL|FOR\s+PHARMA|FOR\s+PHARM|FOR\s+DRUGS|FOR\s+IMPORT|FOR\s+EXPORT|FOR\s+TRADE|FOR\s+TRADING|FOR\s+INDUSTRY|FOR\s+INDUSTRIES|AND\s+MEDICAL\s+APPLIANCES|ANDMEDICAL\s+APPLIANCES)\b.*$",
        "",
        cleaned,
        flags=re.IGNORECASE
    ).strip()

    # Strip final dangling generic terms or legal designations (e.g. INDUSTRY, TRADING, LTD, etc.)
    cleaned = re.sub(
        r"\b(LTD|PVT|PRIVATE|LIMITED|LLP|INC|CORP|CORPORATION|CO|GMBH|SA|BV|PLC|FZCO|FZE|FZLLC|SPA|OY|AS|AG|TRADING|TRADERS|IMPORTS|EXPORTS|IMPORT|EXPORT|GLOBAL|INTERNATIONAL|WORLDWIDE|HOLDINGS|INDUSTRY|INDUSTRIES|PHARMACEUTICALS|PHARMACEUTICAL|LABORATORIES|LABS)\b\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE
    ).strip()

    # Strip final trailing conjunctions
    cleaned = re.sub(
        r"\s+(FOR|AND)\b\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE
    ).strip()

    return cleaned or "UNKNOWN"


def load_mapping(path):
    mapping = {}
    if not Path(path).exists():
        return mapping
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            raw = (row.get("raw") or row.get("alias") or row.get("Raw") or "").strip()
            approved = (
                row.get("approved_standard")
                or row.get("standard")
                or row.get("canonical_name")
                or row.get("canonical")
                or ""
            ).strip()
            if raw and approved:
                mapping[simple_key(raw)] = approved
                mapping[matching_company_key(raw)] = approved
    return mapping


def best_mapping_match(value, mapping, key_func=simple_key):
    key = key_func(value)
    best_value = ""
    best_score = 0.0
    for candidate_key, candidate_value in mapping.items():
        if not candidate_key:
            continue
        score = difflib.SequenceMatcher(None, key, candidate_key).ratio()
        if score > best_score:
            best_score = score
            best_value = candidate_value
    return best_value, best_score


def classify_product(description):
    text = str(description or "").lower()
    simple = re.sub(r"[^a-z0-9]+", " ", text)
    mapping = load_mapping(PRODUCT_MAP)
    direct = mapping.get(simple_key(description))
    if direct:
        return direct, 1.0, "Approved", "Exact mapping from product synonym master."

    fuzzy_value, fuzzy_score = best_mapping_match(description, mapping)
    if fuzzy_value and fuzzy_score >= 0.88:
        return fuzzy_value, round(fuzzy_score, 2), "Pending", "Strong fuzzy match to product synonym master."
    if fuzzy_value and fuzzy_score >= 0.72:
        return fuzzy_value, round(fuzzy_score, 2), "Pending", "Weak fuzzy match to product synonym master; review before approval."

    if "placebo" in simple and "pellet" in simple:
        return "Duloxetine Placebo Pellets", 0.99, "Approved", "Exact rule match: contains placebo and pellet."

    if (
        "pellet" in simple
        or "pellets" in simple
        or "delayed release" in simple
        or "ec pellet" in simple
        or "e c pellet" in simple
    ):
        return "Duloxetine Pellets", 0.95, "Approved", "Exact rule match: product description contains pellet terms."

    if (
        "duloxetine hcl" in simple
        or "duloxetine hydrochloride" in simple
        or re.search(r"\bapi\b", simple)
        or "active pharmaceutical" in simple
    ):
        return "Duloxetine API", 0.95, "Approved", "Exact rule match: product description contains API/Duloxetine HCL terms."

    if "duloxetine" in simple:
        return "Other / Review Required", 0.45, "Pending", "Duloxetine found, but API/pellet/placebo pattern is unclear."
    return "Other / Review Required", 0.25, "Pending", "Unknown product pattern below confidence threshold."


def normalize_company(raw_name):
    mapping = load_mapping(COMPANY_MAP)
    key = simple_key(raw_name)
    match_key = matching_company_key(raw_name)
    if key in mapping:
        return mapping[key], 1.0, "Approved", "Exact mapping from company synonym master."
    if match_key in mapping:
        return mapping[match_key], 0.96, "Approved", "Exact normalized company match after removing legal suffixes."

    best_value, best_score = best_mapping_match(raw_name, mapping, matching_company_key)
    if best_value and best_score >= 0.88:
        return best_value, round(best_score, 2), "Pending", "Strong fuzzy company match after normalization."
    if best_value and best_score >= 0.68:
        return best_value, round(best_score, 2), "Pending", "Weak fuzzy company match; review before approval."

    cleaned = display_company(raw_name)
    confidence = 0.72 if cleaned != "UNKNOWN" else 0.2
    if cleaned in {"UNKNOWN", "TO THE ORDER OF"}:
        return cleaned, 0.35, "Pending", "Importer/exporter name is generic or missing."
    return cleaned, confidence, "Pending", "Normalized company text; no approved synonym match found."


def safe_float(value):
    cleaned = re.sub(r"[^0-9.\-]", "", str(value or ""))
    if cleaned in {"", ".", "-", "-."}:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def convert_to_kg(quantity, unit):
    qty = safe_float(quantity)
    unit_key = simple_key(unit)
    if qty <= 0:
        return None, "Needs Manual Review"
    if unit_key in {"KG", "KGS", "KILOGRAM", "KILOGRAMS"}:
        return qty, "Valid KG"
    if unit_key in {"G", "GM", "GMS", "GRM", "GRAM", "GRAMS"}:
        return qty / 1000, "Valid KG"
    if unit_key in {"MG", "MGS", "MILLIGRAM", "MILLIGRAMS"}:
        return qty / 1_000_000, "Valid KG"
    if unit_key in {"LB", "LBS", "POUND", "POUNDS"}:
        return qty * 0.45359237, "Valid KG"
    if unit_key in {"MT", "TON", "TONS", "TONNE", "TONNES"}:
        return qty * 1000, "Valid KG"
    if unit_key in INVALID_KG_UNITS:
        return None, "Needs Manual Review"
    return None, "Needs Manual Review"


def normalize_country(country):
    key = simple_key(country)
    if not key or key in {"NA", "N A", "NOT SPECIFIED"}:
        return "Unknown"
    
    country_map_path = SEED_DIR / "country_mappings.csv"
    if country_map_path.exists():
        mapping = load_mapping(country_map_path)
        if key in mapping:
            return mapping[key]

    return COUNTRY_ALIASES.get(key, country.title())


def clean_country_name(raw_name, approved_countries):
    key = simple_key(raw_name)
    if not key or key in {"NA", "N A", "NOT SPECIFIED"}:
        return "Unknown", 1.0, "Approved", "Country name is missing or generic."
    
    direct = approved_countries.get(key) if approved_countries else None
    if direct:
        return direct, 1.0, "Approved", "Approved country mapping from Cleaning Review."
    
    country_map_path = SEED_DIR / "country_mappings.csv"
    if country_map_path.exists():
        mapping = load_mapping(country_map_path)
        if key in mapping:
            return mapping[key], 1.0, "Approved", "Exact mapping from country synonym master."
            
    if key in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[key], 1.0, "Approved", "Exact normalized country match from aliases."
        
    # Fuzzy alias match
    alias_keys = {simple_key(k): v for k, v in COUNTRY_ALIASES.items()}
    for v in COUNTRY_ALIASES.values():
        alias_keys[simple_key(v)] = v
        
    best_val = ""
    best_score = 0.0
    for cand_key, cand_val in alias_keys.items():
        if not cand_key:
            continue
        score = difflib.SequenceMatcher(None, key, cand_key).ratio()
        if score > best_score:
            best_score = score
            best_val = cand_val
            
    if best_val and best_score >= 0.82:
        return best_val, round(best_score, 2), "Approved", f"Strong fuzzy match ({round(best_score * 100)}%) to country dictionary."
        
    if best_val and best_score >= 0.68:
        return best_val, round(best_score, 2), "Pending", f"Fuzzy country match ({round(best_score * 100)}%); review before approval."

    normalized = raw_name.title()
    if key == simple_key(normalized):
        return normalized, 1.0, "Approved", "Standard country name classification."
        
    return normalized, 0.8, "Pending", "Normalized country text; review before approval."



def normalize_date_text(value):
    text = str(value or "").strip()
    if not text:
        return ""
    serial = safe_float(text)
    if serial and 20000 <= serial <= 70000 and re.fullmatch(r"\d+(\.0+)?", text):
        date = dt.date(1899, 12, 30) + dt.timedelta(days=int(serial))
        return date.isoformat()
    dmy = re.search(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$", text)
    if dmy:
        year = int(dmy.group(3))
        if year < 100:
            year += 2000
        try:
            return dt.date(year, int(dmy.group(2)), int(dmy.group(1))).isoformat()
        except ValueError:
            return text
    ymd = re.search(r"^(20\d{2}|19\d{2})[/-](\d{1,2})[/-](\d{1,2})$", text)
    if ymd:
        try:
            return dt.date(int(ymd.group(1)), int(ymd.group(2)), int(ymd.group(3))).isoformat()
        except ValueError:
            return text
    return text


def parse_year(value):
    value = normalize_date_text(value)
    match = re.search(r"(20\d{2}|19\d{2})", str(value or ""))
    return int(match.group(1)) if match else 0


def parse_month(value):
    text = normalize_date_text(value)
    dmy = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](20\d{2}|19\d{2})", text)
    if dmy:
        return f"{dmy.group(3)}-{int(dmy.group(2)):02d}"
    ymd = re.search(r"(20\d{2}|19\d{2})[/-](\d{1,2})[/-](\d{1,2})", text)
    if ymd:
        return f"{ymd.group(1)}-{int(ymd.group(2)):02d}"
    year = parse_year(text)
    return str(year) if year else "Unknown"


def market_category(country):
    key = simple_key(country)
    regulated = {
        "USA", "US", "UNITED STATES", "GERMANY", "FRANCE", "ITALY", "SPAIN",
        "UNITED KINGDOM", "UK", "JAPAN", "KOREA", "SOUTH KOREA", "AUSTRALIA",
        "CANADA", "NETHERLANDS", "PORTUGAL", "RUSSIA",
    }
    semi_regulated = {
        "INDIA", "EGYPT", "ARGENTINA", "BANGLADESH", "BRAZIL", "INDONESIA",
        "MALAYSIA", "TANZANIA", "KENYA", "ZIMBABWE", "MEXICO", "SOUTH AFRICA",
    }
    if key in regulated:
        return "Regulated"
    if key in semi_regulated:
        return "Semi-regulated"
    return "Non-regulated"
