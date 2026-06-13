import csv
import difflib
import re
from pathlib import Path

from .config import SEED_DIR

PRODUCT_MAP = SEED_DIR / "product_mappings.csv"
COMPANY_MAP = SEED_DIR / "company_mappings.csv"
COUNTRY_MAP = SEED_DIR / "country_mappings.csv"

LEGAL_WORDS = {
    "PVT", "PRIVATE", "LTD", "LIMITED", "LLP", "INC", "CORP", "CORPORATION",
    "COMPANY", "CO", "GMBH", "SA", "S A", "BV", "PLC", "PHARMA",
    "PHARMACEUTICAL", "PHARMACEUTICALS", "LAB", "LABS", "LABORATORY", "LABORATORIES",
    "INDUSTRY", "INDUSTRIES", "MEDICAL", "APPLIANCE", "APPLIANCES",
    "FOR", "THE", "AND", "DRUG", "DRUGS",
}

INVALID_KG_UNITS = {"NOS", "NO", "PCS", "PC", "UNT", "UNITS", "VLS", "LOT", "CTN", "DRM"}

COUNTRY_ALIASES = {
    "ARGENTINA": "Argentina",
    "BANGLADESH": "Bangladesh",
    "BELGIUM": "Belgium",
    "BRAZIL": "Brazil",
    "CANADA": "Canada",
    "CHILE": "Chile",
    "CHINA": "China",
    "COLOMBIA": "Colombia",
    "CZECHIA": "Czech Republic",
    "CZECH REPUBLIC": "Czech Republic",
    "EGYPT": "Egypt",
    "FRANCE": "France",
    "GERMANY": "Germany",
    "INDIA": "India",
    "IRAN": "Iran",
    "IRAQ": "Iraq",
    "ISRAEL": "Israel",
    "ITALY": "Italy",
    "JAPAN": "Japan",
    "KOREA": "South Korea",
    "REPUBLIC OF KOREA": "South Korea",
    "SOUTH KOREA": "South Korea",
    "MEXICO": "Mexico",
    "NETHERLANDS": "Netherlands",
    "PAKISTAN": "Pakistan",
    "RUSSIA": "Russia",
    "RUSSIAN FEDERATION": "Russia",
    "SPAIN": "Spain",
    "SWITZERLAND": "Switzerland",
    "TAIWAN": "Taiwan",
    "TURKEY": "Turkey",
    "TURKIYE": "Turkey",
    "UAE": "United Arab Emirates",
    "U A E": "United Arab Emirates",
    "UNITED ARAB EMIRATES": "United Arab Emirates",
    "UK": "United Kingdom",
    "U K": "United Kingdom",
    "UNITED KINGDOM": "United Kingdom",
    "USA": "United States",
    "U S A": "United States",
    "US": "United States",
    "UNITED STATES": "United States",
    "UNITED STATES OF AMERICA": "United States",
    "URUGUAY": "Uruguay",
}


def simple_key(value):
    value = str(value or "").upper().replace("&", " AND ")
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def matching_company_key(value):
    cleaned = simple_key(value)
    cleaned = cleaned.replace("PHARMACEUTICALSAND", "PHARMACEUTICALS AND")
    words = [word for word in cleaned.split() if word not in LEGAL_WORDS]
    return " ".join(words)


def display_company(value):
    cleaned = simple_key(value)
    if not cleaned:
        return "UNKNOWN"
    if cleaned.startswith("TO THE ORDER OF"):
        return "TO THE ORDER OF"
    return cleaned


def display_country(value):
    key = simple_key(value)
    if not key or key in {"N A", "NA", "NONE", "UNKNOWN", "NOT AVAILABLE"}:
        return "N/A"
    if key in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[key]
    return " ".join(word.capitalize() for word in key.split())


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


def pellet_strength_product(text):
    matches = re.findall(r"\b(\d+(?:\.\d+)?)\s*(?:%|percent)", str(text or "").lower())
    for match in matches:
        strength = safe_float(match)
        if 16 <= strength <= 18.5:
            return "Duloxetine Pellets 17%"
        if 21.5 <= strength <= 23.5:
            return "Duloxetine Pellets 22.5%"
        if 24 <= strength <= 26:
            return "Duloxetine Pellets 25%"
    return ""


def is_reference_or_impurity(simple):
    return any(
        term in simple
        for term in [
            "reference standard",
            "ref standard",
            "working standard",
            "related compound",
            "compound h",
            "compound f",
            "impurity",
            "rac duloxetine",
            "rc h",
            "rc f",
            " rs ",
        ]
    )


def classify_product(description):
    text = str(description or "").lower()
    simple = re.sub(r"[^a-z0-9]+", " ", text)
    mapping = load_mapping(PRODUCT_MAP)
    direct = mapping.get(simple_key(description))
    if direct:
        return direct, 1.0, "Approved", "Exact mapping from product synonym master."

    has_placebo = "placebo" in simple
    has_pellet = (
        re.search(r"\bpellets?\b", simple)
        or re.search(r"\bpallets?\b", simple)
        or re.search(r"\bpel\b", simple)
        or "delayed release" in simple
        or "ec pellet" in simple
        or "e c pellet" in simple
    )

    if "duloxetine" in simple and is_reference_or_impurity(f" {simple} "):
        return (
            "Duloxetine Reference Standard / Impurity",
            0.78,
            "Pending",
            "Reference standard, related compound, or impurity material; review before using in sales market analysis.",
        )

    if has_placebo and has_pellet:
        return "Duloxetine Placebo Pellets", 0.99, "Approved", "Exact rule match: contains placebo and pellet."

    if has_pellet:
        strength_product = pellet_strength_product(text)
        if strength_product:
            return strength_product, 0.97, "Approved", "Exact rule match: pellet product with strength detected."
        return "Duloxetine Pellets", 0.95, "Approved", "Exact rule match: product description contains pellet/pallet terms."

    if (
        "duloxetine hcl" in simple
        or "duloxetine hydrochloride" in simple
        or re.search(r"\bapi\b", simple)
        or "active pharmaceutical" in simple
    ):
        return "Duloxetine API", 0.95, "Approved", "Exact rule match: product description contains API/Duloxetine HCL terms."

    fuzzy_value, fuzzy_score = best_mapping_match(description, mapping)
    if fuzzy_value == "Duloxetine Placebo Pellets" and not has_placebo:
        fuzzy_value = None
    if fuzzy_value and fuzzy_score >= 0.88:
        return fuzzy_value, round(fuzzy_score, 2), "Pending", "Strong fuzzy match to product synonym master."
    if fuzzy_value and fuzzy_score >= 0.72:
        return fuzzy_value, round(fuzzy_score, 2), "Pending", "Weak fuzzy match to product synonym master; review before approval."

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


def normalize_country(raw_country):
    mapping = load_mapping(COUNTRY_MAP)
    key = simple_key(raw_country)
    if not key or key in {"N A", "NA", "NONE", "UNKNOWN", "NOT AVAILABLE"}:
        return "N/A", 0.35, "Pending", "Country is missing or generic."

    direct = mapping.get(key) or COUNTRY_ALIASES.get(key)
    if direct:
        confidence = 1.0 if simple_key(direct) == key else 0.97
        return direct, confidence, "Approved", "Exact country alias match."

    alias_map = {**{simple_key(k): v for k, v in COUNTRY_ALIASES.items()}, **mapping}
    fuzzy_value, fuzzy_score = best_mapping_match(raw_country, alias_map)
    if fuzzy_value and fuzzy_score >= 0.88:
        return fuzzy_value, round(fuzzy_score, 2), "Pending", "Strong fuzzy country match; review before approval."
    if fuzzy_value and fuzzy_score >= 0.72:
        return fuzzy_value, round(fuzzy_score, 2), "Pending", "Weak fuzzy country match; review before approval."

    return display_country(raw_country), 0.7, "Pending", "Standardized country text; no approved country alias found."


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
    if unit_key in INVALID_KG_UNITS:
        return None, "Needs Manual Review"
    return None, "Needs Manual Review"


def parse_year(value):
    match = re.search(r"(20\d{2}|19\d{2})", str(value or ""))
    return int(match.group(1)) if match else 0


def parse_month(value):
    text = str(value or "").strip()
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
