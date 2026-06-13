import csv
import difflib
import hashlib
import io
import json
import re
import time
import zipfile
from xml.sax.saxutils import escape as xml_escape

from .ai_service import generate_pitch_package, pitch_package_text
from .config import SAMPLE_XLSX, SEED_DIR, UPLOAD_DIR
from .db import connect, init_db, insert_upload, reset_trade_data, rows_to_dicts
from .excel_reader import read_table, write_csv
from .normalization import (
    classify_product,
    convert_to_kg,
    display_company,
    matching_company_key,
    market_category,
    normalize_company,
    normalize_country,
    parse_month,
    parse_year,
    safe_float,
    simple_key,
)

STANDARD_PRODUCTS = [
    "Duloxetine API",
    "Duloxetine Pellets 17%",
    "Duloxetine Pellets 22.5%",
    "Duloxetine Pellets 25%",
    "Duloxetine Pellets",
    "Duloxetine Placebo Pellets",
    "Duloxetine Reference Standard / Impurity",
    "Other / Review Required",
]

REJECTED_COMPANY_ALIAS = "__REJECTED_COMPANY_ALIAS__"
REMAINING_MAPPING_VALUE = "Remaining / Create New Mapping"

COLUMN_ALIASES = {
    "shipment_date": ["date", "shipment date", "export date", "import date", "invoice date"],
    "hs_code": ["hs code", "hscode", "hs", "tariff code"],
    "product_description": ["product description", "product", "description", "commodity"],
    "quantity": ["quantity", "qty", "net weight", "weight"],
    "units": ["units", "unit", "uom", "quantity unit"],
    "value_usd": ["value fob $", "value fob usd", "fob value usd", "invoice value usd", "value usd", "total value usd"],
    "invoice_currency": ["invoice currency", "currency"],
    "importer_name": ["importer name", "importer", "buyer", "consignee", "receiver"],
    "importer_country": ["importer country", "import country", "destination country", "buyer country"],
    "importer_port": ["importer port", "import port", "destination port"],
    "exporter_name": ["exporter name", "exporter", "supplier", "shipper", "seller"],
    "exporter_country": ["exporter country", "export country", "origin country"],
    "exporter_port": ["exporter port", "export port", "origin port"],
}


def seed_files():
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    product = SEED_DIR / "product_mappings.csv"
    company = SEED_DIR / "company_mappings.csv"
    country = SEED_DIR / "country_mappings.csv"
    if not product.exists():
        product.write_text(
            "raw,standard,notes\n"
            "Duloxetine Hcl Usp,Duloxetine API,API variant\n"
            "Duloxetine Hydrochloride,Duloxetine API,API variant\n"
            "Duloxetine Hydrochloride Ph.Eur,Duloxetine API,API variant\n"
            "Duloxetine Hydrochloride Ph Eur,Duloxetine API,API variant\n"
            "Duloxetine Hcl Ec Pellets 17% W/W,Duloxetine Pellets 17%,17 percent pellet variant\n"
            "Duloxetine Ec Pellets 17% W/W,Duloxetine Pellets 17%,17 percent pellet variant\n"
            "Duloxetine Delayed Release Pellets 17.65% W/W,Duloxetine Pellets 17%,17 percent pellet variant\n"
            "Duloxetine Hcl 22.4% Dr Pellets,Duloxetine Pellets 22.5%,22.5 percent DR pellet variant\n"
            "Duloxetine Hcl 22.4% Dr Pallets,Duloxetine Pellets 22.5%,22.5 percent DR pellet typo variant\n"
            "Duloxetine Hcl Dr Pallets,Duloxetine Pellets,DR pellet typo variant\n"
            "Duloxetine Hcl Placebo Pellets,Duloxetine Placebo Pellets,Placebo pellet variant\n",
            encoding="utf-8",
        )
    if not company.exists():
        company.write_text(
            "raw,standard,notes\n"
            "SHODHANA LABS PVT LTD,SHODHANA LABORATORIES,Self supplier\n"
            "SHODHANA LABORATORIES PRIVATE LIMITED,SHODHANA LABORATORIES,Self supplier\n"
            "SHODHANA LABORATORIES P LTD,SHODHANA LABORATORIES,Self supplier\n"
            "SHODHANA LABORATORIES PVT LTD,SHODHANA LABORATORIES,Self supplier\n",
            encoding="utf-8",
        )
    if not country.exists():
        country.write_text(
            "raw,standard,notes\n"
            "USA,United States,Country alias\n"
            "US,United States,Country alias\n"
            "United States Of America,United States,Country alias\n"
            "UK,United Kingdom,Country alias\n"
            "UAE,United Arab Emirates,Country alias\n"
            "Republic Of Korea,South Korea,Country alias\n"
            "Korea,South Korea,Country alias\n"
            "Russian Federation,Russia,Country alias\n"
            "Turkiye,Turkey,Country alias\n",
            encoding="utf-8",
        )


def seed_database_mappings():
    seed_files()
    result = {}
    with connect() as conn:
        for config in _mapping_seed_configs():
            result[config["kind"]] = _seed_mapping_table(conn, config)
    return result


def sync_master_mappings_to_seed():
    seed_files()
    with connect() as conn:
        return _sync_master_mappings_to_seed_for_conn(conn)


def _sync_master_mappings_to_seed_for_conn(conn):
    result = {}
    for config in _mapping_seed_configs():
        result[config["kind"]] = _write_master_mappings_to_seed(conn, config)
    return result


def _mapping_seed_configs():
    return [
        {
            "kind": "products",
            "path": SEED_DIR / "product_mappings.csv",
            "table": "product_mappings",
            "raw_column": "raw_product_description",
            "suggested_column": "suggested_standard_product",
            "approved_column": "approved_standard_product",
        },
        {
            "kind": "companies",
            "path": SEED_DIR / "company_mappings.csv",
            "table": "company_mappings",
            "raw_column": "raw_company_name",
            "suggested_column": "suggested_standard_company_name",
            "approved_column": "approved_standard_company_name",
            "roles_column": "source_roles",
        },
        {
            "kind": "countries",
            "path": SEED_DIR / "country_mappings.csv",
            "table": "country_mappings",
            "raw_column": "raw_country_name",
            "suggested_column": "suggested_standard_country_name",
            "approved_column": "approved_standard_country_name",
            "roles_column": "source_roles",
        },
    ]


def _read_seed_mapping_rows(path):
    if not path.exists():
        return []
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            raw = (row.get("raw") or row.get("alias") or row.get("Raw") or "").strip()
            standard = (
                row.get("standard")
                or row.get("approved_standard")
                or row.get("canonical_name")
                or row.get("canonical")
                or ""
            ).strip()
            notes = (row.get("notes") or row.get("Notes") or "").strip()
            if raw and standard:
                rows.append({"raw": raw, "standard": standard, "notes": notes or "Seed master mapping"})
    return rows


def _seed_mapping_table(conn, config):
    rows = _read_seed_mapping_rows(config["path"])
    existing_by_key = _mapping_rows_by_key(conn, config["table"], config["raw_column"], simple_key)
    inserted = 0
    updated = 0
    skipped = 0
    now = int(time.time())
    for row in rows:
        key = simple_key(row["raw"])
        existing = existing_by_key.get(key)
        reason = "Default master mapping from seed configuration."
        if existing and int(existing.get("is_master") or 0):
            skipped += 1
            continue
        if existing:
            conn.execute(
                f"""
                update {config["table"]}
                set {config["suggested_column"]} = ?,
                    confidence_score = case when confidence_score < 1.0 then 1.0 else confidence_score end,
                    reason_for_suggestion = ?,
                    {config["approved_column"]} = ?,
                    status = 'Approved',
                    is_master = 1
                where id = ?
                """,
                (row["standard"], reason, row["standard"], existing["id"]),
            )
            updated += 1
            continue

        if config.get("roles_column"):
            conn.execute(
                f"""
                insert into {config["table"]}(
                    {config["raw_column"]}, {config["suggested_column"]}, confidence_score,
                    reason_for_suggestion, {config["roles_column"]}, {config["approved_column"]},
                    status, is_master, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (row["raw"], row["standard"], 1.0, reason, "Default", row["standard"], "Approved", 1, now),
            )
        else:
            conn.execute(
                f"""
                insert into {config["table"]}(
                    {config["raw_column"]}, {config["suggested_column"]}, confidence_score,
                    reason_for_suggestion, {config["approved_column"]}, status, is_master, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (row["raw"], row["standard"], 1.0, reason, row["standard"], "Approved", 1, now),
            )
        inserted += 1
    return {"inserted": inserted, "updated": updated, "skipped": skipped, "seed_rows": len(rows)}


def _write_master_mappings_to_seed(conn, config):
    existing_seed = {simple_key(row["raw"]): row for row in _read_seed_mapping_rows(config["path"])}
    rejected_rows = conn.execute(
        f"""
        select {config["raw_column"]} as raw_value
        from {config["table"]}
        where status = 'Rejected'
        """
    ).fetchall()
    for row in rejected_rows:
        existing_seed.pop(simple_key(row["raw_value"] or ""), None)

    rows = conn.execute(
        f"""
        select {config["raw_column"]} as raw_value,
               {config["approved_column"]} as approved_value
        from {config["table"]}
        where status = 'Approved'
          and coalesce(is_master, 0) = 1
          and coalesce({config["approved_column"]}, '') != ''
        order by {config["approved_column"]}, {config["raw_column"]}
        """
    ).fetchall()
    confirmed = 0
    for row in rows:
        raw = (row["raw_value"] or "").strip()
        approved = (row["approved_value"] or "").strip()
        key = simple_key(raw)
        if not key or not approved:
            continue
        existing_seed[key] = {
            "raw": raw,
            "standard": approved,
            "notes": "Confirmed master mapping from Cleaning Review",
        }
        confirmed += 1

    output_rows = sorted(existing_seed.values(), key=lambda row: (simple_key(row["standard"]), simple_key(row["raw"])))
    with config["path"].open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["raw", "standard", "notes"])
        writer.writeheader()
        writer.writerows(output_rows)
    return {"rows": len(output_rows), "confirmed_rows": confirmed, "path": str(config["path"])}


def detect_columns(headers):
    normalized = {header: _clean_header(header) for header in headers}
    detected = {}
    used = set()
    for canonical, aliases in COLUMN_ALIASES.items():
        best_header = ""
        best_score = 0.0
        for header, header_key in normalized.items():
            if header in used:
                continue
            for alias in aliases:
                alias_key = _clean_header(alias)
                if header_key == alias_key:
                    score = 1.0
                elif alias_key in header_key or header_key in alias_key:
                    score = 0.92
                else:
                    score = _similarity(header_key, alias_key)
                if score > best_score:
                    best_header = header
                    best_score = score
        if best_header and best_score >= 0.74:
            detected[canonical] = best_header
            used.add(best_header)
    return detected


def import_sample():
    if not SAMPLE_XLSX.exists():
        raise FileNotFoundError(f"Sample file not found: {SAMPLE_XLSX}")
    return import_trade_file(SAMPLE_XLSX, SAMPLE_XLSX.name, replace=True)


def import_trade_file(path, original_name, replace=True):
    init_db()
    seed_files()
    seed_database_mappings()
    rows = read_table(path)
    if not rows:
        raise ValueError("No rows found in uploaded file.")

    column_map = detect_columns(rows[0].keys())
    required = ["product_description", "quantity", "units", "value_usd", "importer_name", "exporter_name"]
    missing = [name for name in required if name not in column_map]
    if missing:
        raise ValueError(f"Could not detect required columns: {', '.join(missing)}")

    cleaned_rows = []
    product_mapping_rows = {}
    company_mapping_rows = {}
    country_mapping_rows = {}
    duplicate_keys = set()
    duplicate_count = 0
    raw_rows_to_insert = []
    with connect() as conn:
        approved_products = approved_product_map(conn)
        approved_companies = approved_company_map(conn)
        approved_countries = approved_country_map(conn)

    for index, row in enumerate(rows, start=1):
        raw_rows_to_insert.append((index, json.dumps(row)))
        cleaned = clean_row(
            row,
            column_map,
            approved_products=approved_products,
            approved_companies=approved_companies,
            approved_countries=approved_countries,
        )
        duplicate_key = cleaned["duplicate_key"]
        if duplicate_key in duplicate_keys:
            duplicate_count += 1
            continue
        duplicate_keys.add(duplicate_key)
        cleaned["row_number"] = index
        cleaned["raw_json"] = json.dumps(row)
        cleaned_rows.append(cleaned)

        product_mapping_rows.setdefault(
            simple_key(cleaned["raw_product_description"]),
            {
                "raw_product_description": cleaned["raw_product_description"],
                "suggested_standard_product": cleaned["standard_product"],
                "confidence_score": cleaned["product_confidence"],
                "reason_for_suggestion": cleaned["product_reason"],
                "approved_standard_product": cleaned["standard_product"] if cleaned["product_status"] == "Approved" else "",
                "status": cleaned["product_status"],
                "is_master": 1 if _is_trusted_product_mapping(cleaned["product_status"], cleaned["product_reason"]) else 0,
            },
        )
        for role, raw_name, standard_name, confidence, status, reason in [
            (
                "Importer",
                cleaned["raw_importer_name"],
                cleaned["standard_importer_name"],
                cleaned["importer_confidence"],
                cleaned["importer_status"],
                cleaned["importer_reason"],
            ),
            (
                "Exporter",
                cleaned["raw_exporter_name"],
                cleaned["standard_exporter_name"],
                cleaned["exporter_confidence"],
                cleaned["exporter_status"],
                cleaned["exporter_reason"],
            ),
        ]:
            _merge_company_mapping(company_mapping_rows, role, raw_name, standard_name, confidence, status, reason)
        for role, raw_country, standard_country, confidence, status, reason in [
            (
                "Importer",
                cleaned["raw_importer_country"],
                cleaned["importer_country"],
                cleaned["importer_country_confidence"],
                cleaned["importer_country_status"],
                cleaned["importer_country_reason"],
            ),
            (
                "Exporter",
                cleaned["raw_exporter_country"],
                cleaned["exporter_country"],
                cleaned["exporter_country_confidence"],
                cleaned["exporter_country_status"],
                cleaned["exporter_country_reason"],
            ),
        ]:
            _merge_country_mapping(country_mapping_rows, role, raw_country, standard_country, confidence, status, reason)

    quality = quality_summary(rows, cleaned_rows, duplicate_count)
    _cluster_company_mappings(company_mapping_rows)
    with connect() as conn:
        if replace:
            reset_trade_data(conn)
        upload_id = insert_upload(
            conn,
            original_name,
            str(path),
            "trade_data",
            len(rows),
            len(cleaned_rows),
            duplicate_count,
            quality,
            column_map,
        )
        raw_id_by_row_number = {}
        for row_number, raw_json in raw_rows_to_insert:
            cursor = conn.execute(
                "insert into raw_trade_records(upload_id, row_number, raw_json) values (?, ?, ?)",
                (upload_id, row_number, raw_json),
            )
            raw_id_by_row_number[row_number] = cursor.lastrowid
        for cleaned in cleaned_rows:
            raw_id = raw_id_by_row_number.get(cleaned["row_number"])
            conn.execute(
                """
                insert into clean_trade_records(
                    upload_id, raw_record_id, shipment_date, year, month_key, hs_code,
                    raw_product_description, standard_product, product_confidence, product_status,
                    raw_importer_name, standard_importer_name, importer_confidence, importer_status,
                    importer_country, importer_port, raw_exporter_name, standard_exporter_name,
                    exporter_confidence, exporter_status, exporter_country, exporter_port,
                    market_category, quantity, units, quantity_kg, quantity_status,
                    value_usd, price_per_kg, invoice_currency, duplicate_key, data_status, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    upload_id,
                    raw_id,
                    cleaned["shipment_date"],
                    cleaned["year"],
                    cleaned["month_key"],
                    cleaned["hs_code"],
                    cleaned["raw_product_description"],
                    cleaned["standard_product"],
                    cleaned["product_confidence"],
                    cleaned["product_status"],
                    cleaned["raw_importer_name"],
                    cleaned["standard_importer_name"],
                    cleaned["importer_confidence"],
                    cleaned["importer_status"],
                    cleaned["importer_country"],
                    cleaned["importer_port"],
                    cleaned["raw_exporter_name"],
                    cleaned["standard_exporter_name"],
                    cleaned["exporter_confidence"],
                    cleaned["exporter_status"],
                    cleaned["exporter_country"],
                    cleaned["exporter_port"],
                    cleaned["market_category"],
                    cleaned["quantity"],
                    cleaned["units"],
                    cleaned["quantity_kg"],
                    cleaned["quantity_status"],
                    cleaned["value_usd"],
                    cleaned["price_per_kg"],
                    cleaned["invoice_currency"],
                    cleaned["duplicate_key"],
                    cleaned["data_status"],
                    int(time.time()),
                ),
            )
        _replace_product_mappings(conn, product_mapping_rows.values())
        _replace_company_mappings(conn, company_mapping_rows.values())
        _replace_country_mappings(conn, country_mapping_rows.values())

    return {
        "upload_id": upload_id,
        "source_rows": len(rows),
        "clean_rows": len(cleaned_rows),
        "duplicates_removed": duplicate_count,
        "detected_columns": column_map,
        "quality": quality,
        "intake_summary": upload_intake_summary(),
        "mapping_readiness": mapping_review_status(),
    }


def save_uploaded_file(filename, data):
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename or "upload.xlsx").strip("._") or "upload.xlsx"
    stored = UPLOAD_DIR / f"{int(time.time())}_{safe_name}"
    stored.write_bytes(data)
    return stored


def import_mapping_file(kind, path):
    rows = read_table(path)
    if not rows:
        raise ValueError("No mapping rows found.")
    targets = {
        "product_mapping": "product_mappings.csv",
        "company_mapping": "company_mappings.csv",
        "country_mapping": "country_mappings.csv",
    }
    target = SEED_DIR / targets.get(kind, "company_mappings.csv")
    normalized_rows = []
    for row in rows:
        raw = _first_present(row, ["raw", "alias", "raw product description", "product description", "raw company name", "company name"])
        if not raw:
            raw = _first_present(row, ["raw country", "country", "country name"])
        standard = _first_present(
            row,
            [
                "standard",
                "canonical",
                "canonical_name",
                "approved_standard",
                "approved standard product",
                "approved standard company",
                "approved standard country",
                "standard product",
                "standard company",
                "standard country",
            ],
        )
        if raw and standard:
            normalized_rows.append({"raw": raw, "standard": standard, "notes": "Uploaded mapping"})
    if not normalized_rows:
        raise ValueError("Could not detect raw/standard mapping columns.")
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["raw", "standard", "notes"])
        writer.writeheader()
        writer.writerows(normalized_rows)
    seeded = seed_database_mappings()
    return {"rows": len(normalized_rows), "target": str(target), "seeded": seeded}


def dashboard(filters=None):
    filters = filters or {}
    with connect() as conn:
        stats = filtered_stats(conn, filters)
        product_split = grouped_metric(conn, "standard_product", filters, limit=20)
        country_demand = grouped_metric(conn, "importer_country", filters, limit=30)
        top_countries = grouped_metric(conn, "importer_country", filters, limit=10)
        top_importers = grouped_metric(conn, "standard_importer_name", filters, limit=10)
        top_exporters = grouped_metric(conn, "standard_exporter_name", filters, limit=10)
        month_trend = month_quantity_trend(conn, filters)
        price_trend = month_price_trend(conn, filters)
        price_range = price_range_by_product(conn, filters)
        competitors = competitor_intelligence(conn, filters)
        customers = customer_intelligence(conn, filters)
        options = dashboard_filter_options(conn)
        uploads = rows_to_dicts(
            conn.execute(
                "select id, original_name, row_count, clean_count, duplicate_count, imported_at from uploaded_files order by id desc limit 5"
            ).fetchall()
        )
    return {
        "stats": stats,
        "top_countries": top_countries,
        "top_importers": top_importers,
        "top_exporters": top_exporters,
        "product_split": product_split,
        "country_demand": country_demand,
        "month_trend": month_trend,
        "price_trend": price_trend,
        "price_range": price_range,
        "competitor_intelligence": competitors,
        "customer_intelligence": customers,
        "filter_options": options,
        "uploads": uploads,
    }


def latest_upload():
    with connect() as conn:
        row = conn.execute(
            "select * from uploaded_files order by id desc limit 1"
        ).fetchone()
    if not row:
        return {}
    result = dict(row)
    result["quality"] = json.loads(result.pop("quality_json") or "{}")
    result["column_map"] = json.loads(result.pop("column_map_json") or "{}")
    return result


def opportunities(filters=None, limit=100):
    filters = filters or {}
    where, params = analytics_where(filters)
    with connect() as conn:
        rows = conn.execute(
            f"""
            select
                standard_importer_name as importer,
                importer_country as country,
                standard_product as product,
                market_category,
                json_group_array(distinct raw_importer_name) as importer_aliases_text,
                json_group_array(distinct standard_exporter_name) as suppliers,
                json_group_array(distinct raw_exporter_name) as supplier_aliases_text,
                sum(coalesce(quantity_kg, 0)) as total_quantity_kg,
                sum(coalesce(value_usd, 0)) as total_value_usd,
                case
                  when sum(coalesce(quantity_kg, 0)) > 0 then sum(coalesce(value_usd, 0)) / sum(coalesce(quantity_kg, 0))
                  else null
                end as avg_price_per_kg,
                count(*) as shipment_count,
                group_concat(shipment_date) as shipment_dates,
                max(year) as latest_year,
                sum(case when quantity_kg is null then 1 else 0 end) as invalid_quantity_rows,
                sum(case when standard_product = 'Other / Review Required' then 1 else 0 end) as review_product_rows
            from clean_trade_records
            {where}
            group by standard_importer_name, importer_country, standard_product, market_category
            order by total_quantity_kg desc, total_value_usd desc
            """,
            params,
        ).fetchall()
        market_avgs = market_average_by_product(conn, filters)
    items = []
    base_items = []
    for row in rows:
        item = dict(row)
        suppliers = split_distinct_text(item.get("suppliers"))
        item["importer_aliases"] = split_distinct_text(item.pop("importer_aliases_text", ""))
        item["supplier_aliases"] = split_distinct_text(item.pop("supplier_aliases_text", ""))
        item["importer_alias_count"] = len(item["importer_aliases"])
        item["supplier_alias_count"] = len(item["supplier_aliases"])
        dates = [date for date in (item.pop("shipment_dates") or "").split(",") if date]
        dates.sort(key=_date_sort_key)
        item["first_shipment_date"] = dates[0] if dates else ""
        item["last_shipment_date"] = dates[-1] if dates else ""
        item["last_shipment_ordinal"] = _date_to_ordinal(item["last_shipment_date"])
        item["suppliers"] = suppliers
        item["exporter"] = ", ".join(suppliers[:3])
        if len(suppliers) > 3:
            item["exporter"] += f" +{len(suppliers) - 3}"
        item["current_supplier"] = item["exporter"]
        item["shodhana_status"] = shodhana_status_for_suppliers(suppliers)
        item["market_avg_price_per_kg"] = round(market_avgs.get(item["product"], 0), 2)
        item["avg_price_per_kg"] = round(item.get("avg_price_per_kg") or 0, 2)
        item["price_difference"] = round(item["avg_price_per_kg"] - item["market_avg_price_per_kg"], 2)
        item["total_quantity_kg"] = round(item.get("total_quantity_kg") or 0, 4)
        item["total_value_usd"] = round(item.get("total_value_usd") or 0, 2)
        item["opportunity_id"] = opportunity_id(item)
        base_items.append(item)

    quantity_threshold = percentile([item["total_quantity_kg"] for item in base_items], 0.8)
    ordinals = [item["last_shipment_ordinal"] for item in base_items if item["last_shipment_ordinal"]]
    min_ordinal = min(ordinals) if ordinals else 0
    max_ordinal = max(ordinals) if ordinals else 0
    recent_threshold = min_ordinal + ((max_ordinal - min_ordinal) * 0.8) if max_ordinal > min_ordinal else max_ordinal

    for item in base_items:
        score, tier, action, reasons = score_opportunity(item, quantity_threshold, recent_threshold)
        item["score"] = score
        item["tier"] = tier
        item["opportunity_category"] = tier
        item["recommended_action"] = action
        item["reasons"] = reasons
        item["opportunity_key"] = "|".join([item["importer"], item["country"], item["product"]])
        items.append(item)
    items.sort(key=lambda value: (value["score"], value["total_quantity_kg"], value["total_value_usd"]), reverse=True)
    for index, item in enumerate(items, start=1):
        item["rank"] = index
    return items[:limit]


def mapping_review_status(groups=None):
    groups = groups or mapping_groups()
    result = {
        "requires_review": False,
        "total_groups": 0,
        "total_aliases": 0,
        "by_kind": {},
        "samples": [],
    }
    for key, rows in groups.items():
        review_groups = [
            group for group in rows
            if int(group.get("needs_review_count") or 0) > 0 and not _is_generic_review_group(group)
        ]
        alias_count = sum(int(group.get("needs_review_count") or 0) for group in review_groups)
        result["by_kind"][key] = {
            "groups": len(review_groups),
            "aliases": alias_count,
        }
        result["total_groups"] += len(review_groups)
        result["total_aliases"] += alias_count
        for group in review_groups[:4]:
            result["samples"].append(
                {
                    "kind": key,
                    "standard_value": group.get("standard_value", ""),
                    "aliases": int(group.get("alias_count") or 0),
                    "needs_review": int(group.get("needs_review_count") or 0),
                    "examples": group.get("samples", [])[:4],
                }
            )
    result["requires_review"] = result["total_groups"] > 0
    return result


def upload_intake_summary():
    groups = mapping_groups()
    summary = {
        "products": _intake_summary_for_groups(groups.get("products", [])),
        "companies": _intake_summary_for_groups(groups.get("companies", [])),
        "countries": _intake_summary_for_groups(groups.get("countries", [])),
    }
    sections = [summary["products"], summary["companies"], summary["countries"]]
    summary["total_groups"] = sum(item["groups"] for item in sections)
    summary["total_aliases"] = sum(item["aliases"] for item in sections)
    summary["needs_confirmation"] = sum(item["needs_confirmation"] for item in sections)
    summary["approved_aliases"] = sum(item["approved_aliases"] for item in sections)
    return summary


def _intake_summary_for_groups(groups):
    return {
        "groups": len(groups),
        "aliases": sum(int(group.get("alias_count") or 0) for group in groups),
        "needs_confirmation": sum(int(group.get("needs_review_count") or 0) for group in groups),
        "approved_aliases": sum(int(group.get("approved_count") or 0) for group in groups),
    }


def opportunity_detail(opportunity_id_value):
    all_opps = opportunities(limit=10000)
    selected = next((item for item in all_opps if item["opportunity_id"] == opportunity_id_value), None)
    if not selected:
        raise ValueError("Opportunity not found.")
    with connect() as conn:
        rows = conn.execute(
            """
            select *
            from clean_trade_records
            where standard_importer_name = ? and importer_country = ? and standard_product = ?
            order by year desc, id desc
            limit 250
            """,
            (selected["importer"], selected["country"], selected["product"]),
        ).fetchall()
        supplier_rows = conn.execute(
            """
            select
                standard_exporter_name as supplier,
                exporter_country,
                json_group_array(distinct raw_exporter_name) as supplier_aliases_text,
                count(*) as shipment_count,
                sum(coalesce(quantity_kg, 0)) as total_quantity_kg,
                sum(coalesce(value_usd, 0)) as total_value_usd,
                case
                  when sum(coalesce(quantity_kg, 0)) > 0 then sum(coalesce(value_usd, 0)) / sum(coalesce(quantity_kg, 0))
                  else null
                end as avg_price_per_kg,
                group_concat(shipment_date) as shipment_dates
            from clean_trade_records
            where standard_importer_name = ? and importer_country = ? and standard_product = ?
            group by standard_exporter_name, exporter_country
            order by total_quantity_kg desc, total_value_usd desc
            """,
            (selected["importer"], selected["country"], selected["product"]),
        ).fetchall()
        product_market = conn.execute(
            """
            select
                min(price_per_kg) as min_price,
                avg(price_per_kg) as simple_avg_price,
                max(price_per_kg) as max_price,
                case
                  when sum(coalesce(quantity_kg, 0)) > 0 then sum(coalesce(value_usd, 0)) / sum(coalesce(quantity_kg, 0))
                  else null
                end as weighted_avg_price
            from clean_trade_records
            where standard_product = ? and price_per_kg is not null
            """,
            (selected["product"],),
        ).fetchone()
    supplier_history = []
    for row in supplier_rows:
        item = dict(row)
        dates = [date for date in (item.pop("shipment_dates") or "").split(",") if date]
        dates.sort(key=_date_sort_key)
        item["supplier_aliases"] = split_distinct_text(item.pop("supplier_aliases_text", ""))
        item["supplier_alias_count"] = len(item["supplier_aliases"])
        item["last_shipment_date"] = dates[-1] if dates else ""
        item["avg_price_per_kg"] = round(item.get("avg_price_per_kg") or 0, 2)
        item["total_quantity_kg"] = round(item.get("total_quantity_kg") or 0, 4)
        item["total_value_usd"] = round(item.get("total_value_usd") or 0, 2)
        item["shodhana_status"] = "Existing Shodhana Supply" if "SHODHANA" in simple_key(item["supplier"]) else "Competitor Supply"
        supplier_history.append(item)

    shipment_history = []
    for row in rows:
        item = dict(row)
        item["shodhana_status"] = "Existing Shodhana Supply" if "SHODHANA" in simple_key(item["standard_exporter_name"]) else "Competitor Supply"
        shipment_history.append(item)

    market = dict(product_market) if product_market else {}
    price_analysis = {
        "customer_avg_price_per_kg": selected["avg_price_per_kg"],
        "market_avg_price_per_kg": round((market.get("weighted_avg_price") or 0), 2),
        "price_difference": round(selected["avg_price_per_kg"] - (market.get("weighted_avg_price") or 0), 2),
        "market_min_price_per_kg": round((market.get("min_price") or 0), 2),
        "market_max_price_per_kg": round((market.get("max_price") or 0), 2),
    }
    return {
        "opportunity": selected,
        "customer_summary": {
            "importer": selected["importer"],
            "country": selected["country"],
            "market_category": selected["market_category"],
            "shipment_count": selected["shipment_count"],
            "total_quantity_kg": selected["total_quantity_kg"],
            "total_value_usd": selected["total_value_usd"],
            "last_shipment_date": selected["last_shipment_date"],
            "importer_aliases": selected.get("importer_aliases", []),
            "supplier_aliases": selected.get("supplier_aliases", []),
        },
        "product_summary": {
            "product": selected["product"],
            "status": selected["shodhana_status"],
            "current_supplier": selected["current_supplier"],
        },
        "supplier_history": supplier_history,
        "shipment_history": shipment_history,
        "price_analysis": price_analysis,
        "why_important": selected["reasons"],
        "recommended_action": selected["recommended_action"],
    }


def generated_pitch(opportunity_id_value, regenerate=False):
    detail = opportunity_detail(opportunity_id_value)
    with connect() as conn:
        if not regenerate:
            row = conn.execute(
                """
                select *
                from generated_pitches
                where opportunity_id = ?
                order by created_at desc, id desc
                limit 1
                """,
                (opportunity_id_value,),
            ).fetchone()
            if row:
                return pitch_row_response(dict(row), detail)

        package = generate_pitch_package(detail)
        created_at = int(time.time())
        opportunity = detail["opportunity"]
        content = pitch_package_text(package)
        conn.execute(
            """
            insert into generated_pitches(
                opportunity_key,
                action_type,
                content,
                opportunity_id,
                customer_summary,
                buying_pattern,
                price_strategy,
                email_draft_formal,
                email_draft_short,
                email_draft_relationship,
                ppt_outline_json,
                follow_up_plan,
                created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opportunity.get("opportunity_key") or opportunity_id_value,
                "full_customer_pitch",
                content,
                opportunity_id_value,
                package["customer_summary"],
                package["buying_pattern"],
                package["price_strategy"],
                package["email_drafts"]["formal"],
                package["email_drafts"]["short"],
                package["email_drafts"]["relationship"],
                json.dumps(package["ppt_outline"]),
                package["follow_up_plan"],
                created_at,
            ),
        )
        row = conn.execute(
            "select * from generated_pitches where opportunity_id = ? order by created_at desc, id desc limit 1",
            (opportunity_id_value,),
        ).fetchone()
    return pitch_row_response(dict(row), detail)


def pitch_row_response(row, detail):
    computed = generate_pitch_package(detail)
    ppt_outline = []
    if row.get("ppt_outline_json"):
        try:
            ppt_outline = json.loads(row["ppt_outline_json"])
        except json.JSONDecodeError:
            ppt_outline = []
    package = {
        "customer_summary": row.get("customer_summary") or "",
        "buying_pattern": row.get("buying_pattern") or "",
        "current_supplier": computed["current_supplier"],
        "price_analysis": computed["price_analysis"],
        "why_target": computed["why_target"],
        "commercial_strategy": row.get("price_strategy") or "",
        "price_strategy": row.get("price_strategy") or "",
        "email_drafts": {
            "formal": row.get("email_draft_formal") or "",
            "short": row.get("email_draft_short") or "",
            "relationship": row.get("email_draft_relationship") or "",
        },
        "ppt_outline": ppt_outline,
        "follow_up_plan": row.get("follow_up_plan") or "",
        "human_approval_note": "AI-generated output is a draft. Sales/business team must review before sending externally.",
    }
    return {
        "id": row.get("id"),
        "opportunity_id": row.get("opportunity_id"),
        "created_at": row.get("created_at"),
        "content": row.get("content") or pitch_package_text(package),
        "pitch": package,
        "detail": detail,
    }


def mappings(kind, limit=5000):
    table_by_kind = {
        "products": "product_mappings",
        "companies": "company_mappings",
        "countries": "country_mappings",
    }
    table = table_by_kind.get(kind, "company_mappings")
    with connect() as conn:
        rows = conn.execute(f"select * from {table} order by confidence_score asc, id asc limit ?", (limit,)).fetchall()
    return rows_to_dicts(rows)


def mapping_groups():
    with connect() as conn:
        products = rows_to_dicts(conn.execute("select * from product_mappings order by id asc").fetchall())
        companies = rows_to_dicts(conn.execute("select * from company_mappings order by id asc").fetchall())
        countries = rows_to_dicts(conn.execute("select * from country_mappings order by id asc").fetchall())
    return {
        "products": _mapping_groups_for_rows(
            products,
            "product",
            "raw_product_description",
            "suggested_standard_product",
            "approved_standard_product",
        ),
        "companies": _mapping_groups_for_rows(
            companies,
            "company",
            "raw_company_name",
            "suggested_standard_company_name",
            "approved_standard_company_name",
            "source_roles",
        ),
        "countries": _mapping_groups_for_rows(
            countries,
            "country",
            "raw_country_name",
            "suggested_standard_country_name",
            "approved_standard_country_name",
            "source_roles",
        ),
    }


def _mapping_groups_for_rows(rows, kind, raw_column, suggested_column, approved_column, roles_column=""):
    groups = {}
    for row in rows:
        raw_value = row.get(raw_column, "")
        approved_value = (row.get(approved_column) or "").strip()
        suggested_value = (row.get(suggested_column) or "").strip()
        standard = (approved_value or suggested_value).strip()
        if not standard:
            standard = "Review Required"
        if kind == "company" and simple_key(standard) in {"TO THE ORDER OF", "UNKNOWN"}:
            group_key = simple_key(standard)
        elif kind == "company" and not approved_value:
            group_key = simple_key(suggested_value) or matching_company_key(raw_value) or simple_key(standard)
        else:
            group_key = simple_key(standard)
        group = groups.setdefault(
            group_key,
            {
                "kind": kind,
                "standard_value": standard,
                "ids": [],
                "samples": [],
                "alias_count": 0,
                "pending_count": 0,
                "approved_count": 0,
                "rejected_count": 0,
                "min_confidence": 1.0,
                "max_confidence": 0.0,
                "source_roles": set(),
                "suggested_values": set(),
                "master_count": 0,
                "active_alias_count": 0,
                "needs_review_count": 0,
                "items": [],
            },
        )
        group["ids"].append(row["id"])
        group["items"].append(
            {
                "id": row["id"],
                "raw": raw_value,
                "suggested": suggested_value,
                "approved": approved_value,
                "status": row.get("status", ""),
                "confidence": float(row.get("confidence_score") or 0),
                "is_master": int(row.get("is_master") or 0),
            }
        )
        if raw_value and raw_value not in group["samples"] and len(group["samples"]) < 6:
            group["samples"].append(raw_value)
        if suggested_value:
            group["suggested_values"].add(suggested_value)
        group["alias_count"] += 1
        if row.get("status") != "Rejected":
            group["active_alias_count"] += 1
        if int(row.get("is_master") or 0):
            group["master_count"] += 1
        status = row.get("status", "")
        if status == "Approved":
            group["approved_count"] += 1
        elif status == "Rejected":
            group["rejected_count"] += 1
        else:
            group["pending_count"] += 1
        confidence = float(row.get("confidence_score") or 0)
        group["min_confidence"] = min(group["min_confidence"], confidence)
        group["max_confidence"] = max(group["max_confidence"], confidence)
        if roles_column:
            group["source_roles"].update(part.strip() for part in str(row.get(roles_column) or "").split(",") if part.strip())

    result = []
    for group in groups.values():
        if (
            kind == "company"
            and not group["master_count"]
            and simple_key(group["standard_value"]) != simple_key(REMAINING_MAPPING_VALUE)
        ):
            group["standard_value"] = _best_text_canonical(group["suggested_values"] or group["samples"])
        group["needs_review_count"] = _mapping_group_needs_review_count(group)
        group["source_roles"] = ", ".join(sorted(group["source_roles"]))
        group["suggested_values"] = sorted(group["suggested_values"])
        group["items"].sort(
            key=lambda item: (
                int(item.get("is_master") or 0),
                -float(item.get("confidence") or 0),
                simple_key(item.get("raw") or ""),
            )
        )
        result.append(group)
    return sorted(
        result,
        key=lambda group: (
            0 if group["needs_review_count"] else 1,
            group["min_confidence"],
            group["standard_value"],
        ),
    )


def _mapping_group_needs_review_count(group):
    unconfirmed = [
        item for item in group.get("items", [])
        if item.get("status") != "Rejected" and not int(item.get("is_master") or 0)
    ]
    if simple_key(group.get("standard_value")) == simple_key(REMAINING_MAPPING_VALUE):
        return len(unconfirmed)
    active_alias_count = int(group.get("active_alias_count") or 0)
    if active_alias_count < 2:
        return 0
    return len(unconfirmed)


def _is_generic_review_group(group):
    value = simple_key(group.get("standard_value", ""))
    return value in {"", "N A", "NA", "UNKNOWN", "TO THE ORDER", "TO THE ORDER OF", "OTHER REVIEW REQUIRED"}


def _best_text_canonical(values):
    values = [simple_key(value) for value in values if simple_key(value)]
    if not values:
        return "UNKNOWN"
    return max(values, key=_company_name_quality)


def cleaning_review():
    with connect() as conn:
        summary = cleaning_summary(conn)
        product_rows = rows_to_dicts(
            conn.execute(
                """
                select * from product_mappings
                order by
                  case status when 'Pending' then 0 when 'Rejected' then 1 else 2 end,
                  confidence_score asc,
                  id asc
                limit 5000
                """
            ).fetchall()
        )
        company_rows = rows_to_dicts(
            conn.execute(
                """
                select * from company_mappings
                order by
                  case status when 'Pending' then 0 when 'Rejected' then 1 else 2 end,
                  confidence_score asc,
                  id asc
                limit 5000
                """
            ).fetchall()
        )
        country_rows = rows_to_dicts(
            conn.execute(
                """
                select * from country_mappings
                order by
                  case status when 'Pending' then 0 when 'Rejected' then 1 else 2 end,
                  confidence_score asc,
                  id asc
                limit 5000
                """
            ).fetchall()
        )
        issue_rows = review_records_for_conn(conn, "pending", limit=150)
    return {"summary": summary, "products": product_rows, "companies": company_rows, "countries": country_rows, "issue_rows": issue_rows}


def update_mapping(kind, mapping_id, action, value=""):
    if action not in {"approve", "edit", "reject"}:
        raise ValueError("Mapping action must be approve, edit, or reject.")
    config = {
        "product": ("product_mappings", "suggested_standard_product", "approved_standard_product"),
        "company": ("company_mappings", "suggested_standard_company_name", "approved_standard_company_name"),
        "country": ("country_mappings", "suggested_standard_country_name", "approved_standard_country_name"),
    }
    if kind not in config:
        raise ValueError("Mapping kind must be product, company, or country.")
    table, suggested_column, approved_column = config[kind]
    id_column = "id"
    with connect() as conn:
        row = conn.execute(f"select * from {table} where {id_column} = ?", (mapping_id,)).fetchone()
        if not row:
            raise ValueError(f"Mapping not found: {mapping_id}")
        row = dict(row)
        if action == "reject":
            conn.execute(
                f"update {table} set status = 'Rejected', {approved_column} = '', is_master = 0 where id = ?",
                (mapping_id,),
            )
            status = "Rejected"
            approved = ""
            defaults = _sync_master_mappings_to_seed_for_conn(conn)
        else:
            approved = (value or row.get(suggested_column) or "").strip()
            if not approved:
                raise ValueError("Approved value cannot be blank.")
            conn.execute(
                f"""
                update {table}
                set status = 'Approved',
                    {suggested_column} = ?,
                    {approved_column} = ?,
                    reason_for_suggestion = ?,
                    is_master = 1
                where id = ?
                """,
                (
                    approved,
                    approved,
                    "Manually approved in Cleaning Review." if action == "approve" else "Manually edited and approved in Cleaning Review.",
                    mapping_id,
                ),
            )
            status = "Approved"
            defaults = _sync_master_mappings_to_seed_for_conn(conn)
        return {"id": mapping_id, "kind": kind, "status": status, "approved": approved, "defaults": defaults}


def update_mapping_group(kind, ids, action, value="", excluded_ids=None):
    if action not in {"approve", "edit", "reject"}:
        raise ValueError("Group action must be approve, edit, or reject.")
    if not ids:
        raise ValueError("Choose at least one mapping row.")
    ids = sorted({int(mapping_id) for mapping_id in ids if int(mapping_id)})
    excluded_ids = sorted({int(mapping_id) for mapping_id in (excluded_ids or []) if int(mapping_id)} - set(ids))
    config = {
        "product": ("product_mappings", "suggested_standard_product", "approved_standard_product"),
        "company": ("company_mappings", "suggested_standard_company_name", "approved_standard_company_name"),
        "country": ("country_mappings", "suggested_standard_country_name", "approved_standard_country_name"),
    }
    if kind not in config:
        raise ValueError("Mapping kind must be product, company, or country.")
    table, suggested_column, approved_column = config[kind]
    placeholders = ",".join("?" for _ in ids)
    with connect() as conn:
        rows = rows_to_dicts(conn.execute(f"select * from {table} where id in ({placeholders})", ids).fetchall())
        if not rows:
            raise ValueError("No mapping rows found for this group.")
        if action == "reject":
            conn.execute(
                f"update {table} set status = 'Rejected', {approved_column} = '', reason_for_suggestion = ?, is_master = 0 where id in ({placeholders})",
                ["Group rejected in Smart Confirm Review.", *ids],
            )
            defaults = _sync_master_mappings_to_seed_for_conn(conn)
            return {"kind": kind, "status": "Rejected", "updated": len(rows), "approved": "", "defaults": defaults}

        approved = (value or rows[0].get(approved_column) or rows[0].get(suggested_column) or "").strip()
        if not approved:
            raise ValueError("Approved group value cannot be blank.")
        if simple_key(approved) == simple_key(REMAINING_MAPPING_VALUE):
            raise ValueError("Enter the new master mapping name before saving aliases from Remaining / Create New Mapping.")
        conn.execute(
            f"""
            update {table}
            set status = 'Approved',
                {suggested_column} = ?,
                {approved_column} = ?,
                confidence_score = case when confidence_score < 0.96 then 0.96 else confidence_score end,
                reason_for_suggestion = ?,
                is_master = 1
            where id in ({placeholders})
            """,
            [approved, approved, "Group approved in Smart Confirm Review. This master mapping will be reused in future uploads.", *ids],
        )
        excluded_count = 0
        if excluded_ids:
            excluded_placeholders = ",".join("?" for _ in excluded_ids)
            conn.execute(
                f"""
                update {table}
                set status = 'Pending',
                    {suggested_column} = ?,
                    {approved_column} = '',
                    confidence_score = case when confidence_score > 0.65 then 0.65 else confidence_score end,
                    reason_for_suggestion = ?,
                    is_master = 0
                where id in ({excluded_placeholders})
                """,
                [
                    REMAINING_MAPPING_VALUE,
                    "Removed from the previous Smart Confirm group. Select it with other remaining aliases and save a new master mapping.",
                    *excluded_ids,
                ],
            )
            excluded_count = conn.execute(
                f"select changes() as changed"
            ).fetchone()["changed"]
        defaults = _sync_master_mappings_to_seed_for_conn(conn)
    return {
        "kind": kind,
        "status": "Approved",
        "updated": len(rows),
        "excluded": excluded_count,
        "approved": approved,
        "defaults": defaults,
    }


def rerun_cleaning():
    init_db()
    with connect() as conn:
        upload = conn.execute("select * from uploaded_files order by id desc limit 1").fetchone()
        if not upload:
            raise ValueError("Upload data first before re-running cleaning.")
        upload = dict(upload)
        column_map = json.loads(upload.get("column_map_json") or "{}")
        raw_records = conn.execute(
            "select id, row_number, raw_json from raw_trade_records where upload_id = ? order by row_number",
            (upload["id"],),
        ).fetchall()
        if not raw_records:
            raise ValueError("No raw records available to reprocess.")

        approved_products = approved_product_map(conn)
        approved_companies = approved_company_map(conn)
        approved_countries = approved_country_map(conn)
        conn.execute("delete from clean_trade_records where upload_id = ?", (upload["id"],))
        conn.execute("delete from generated_pitches")
        duplicate_keys = set()
        duplicate_count = 0
        cleaned_rows = []
        for raw in raw_records:
            row = json.loads(raw["raw_json"])
            cleaned = clean_row(
                row,
                column_map,
                approved_products=approved_products,
                approved_companies=approved_companies,
                approved_countries=approved_countries,
            )
            duplicate_key = cleaned["duplicate_key"]
            if duplicate_key in duplicate_keys:
                duplicate_count += 1
                continue
            duplicate_keys.add(duplicate_key)
            insert_clean_record(conn, upload["id"], raw["id"], cleaned)
            cleaned_rows.append(cleaned)
        quality = quality_summary([json.loads(raw["raw_json"]) for raw in raw_records], cleaned_rows, duplicate_count)
        conn.execute(
            """
            update uploaded_files
            set clean_count = ?, duplicate_count = ?, quality_json = ?
            where id = ?
            """,
            (len(cleaned_rows), duplicate_count, json.dumps(quality), upload["id"]),
        )
        summary = cleaning_summary(conn)
    return {"clean_rows": len(cleaned_rows), "duplicates_removed": duplicate_count, "quality": quality, "summary": summary}


def review_records(filter_name="", limit=150):
    with connect() as conn:
        return review_records_for_conn(conn, filter_name, limit)


def review_records_for_conn(conn, filter_name="", limit=150):
    filter_name = filter_name or "pending"
    clauses = []
    if filter_name == "review_products":
        clauses.append("standard_product = 'Other / Review Required'")
    elif filter_name == "invalid_units":
        clauses.append("quantity_kg is null")
    elif filter_name == "missing_price":
        clauses.append("(price_per_kg is null or value_usd = 0 or quantity_kg is null)")
    elif filter_name == "low_confidence":
        clauses.append("(product_confidence < 0.8 or importer_confidence < 0.8 or exporter_confidence < 0.8)")
    else:
        clauses.append("(product_status = 'Pending' or importer_status = 'Pending' or exporter_status = 'Pending' or data_status != 'Clean')")
    where = "where " + " and ".join(clauses)
    rows = conn.execute(
        f"""
        select
            id, raw_product_description, standard_product, product_confidence, product_status,
            raw_importer_name, standard_importer_name, importer_confidence, importer_status,
            raw_exporter_name, standard_exporter_name, exporter_confidence, exporter_status,
            quantity, units, quantity_kg, quantity_status, value_usd, price_per_kg, data_status
        from clean_trade_records
        {where}
        order by id asc
        limit ?
        """,
        (limit,),
    ).fetchall()
    return rows_to_dicts(rows)


def export_clean_csv(path):
    with connect() as conn:
        rows = rows_to_dicts(conn.execute("select * from clean_trade_records order by id").fetchall())
    return write_csv(path, rows)


def clean_row(row, column_map, approved_products=None, approved_companies=None, approved_countries=None):
    approved_products = approved_products or {}
    approved_companies = approved_companies or {}
    approved_countries = approved_countries or {}

    def value(name):
        header = column_map.get(name)
        return row.get(header, "") if header else ""

    product_raw = str(value("product_description")).strip()
    product_key = simple_key(product_raw)
    if product_key in approved_products:
        standard_product = approved_products[product_key]
        product_confidence = 1.0
        product_status = "Approved"
        product_reason = "Approved product master reused from prior Cleaning Review."
    else:
        standard_product, product_confidence, product_status, product_reason = classify_product(product_raw)
    importer_raw = str(value("importer_name")).strip()
    exporter_raw = str(value("exporter_name")).strip()
    importer_standard, importer_confidence, importer_status, importer_reason = clean_company_name(importer_raw, approved_companies)
    exporter_standard, exporter_confidence, exporter_status, exporter_reason = clean_company_name(exporter_raw, approved_companies)
    importer_country_raw = str(value("importer_country")).strip()
    exporter_country_raw = str(value("exporter_country")).strip()
    importer_country, importer_country_confidence, importer_country_status, importer_country_reason = clean_country_name(
        importer_country_raw,
        approved_countries,
    )
    exporter_country, exporter_country_confidence, exporter_country_status, exporter_country_reason = clean_country_name(
        exporter_country_raw,
        approved_countries,
    )
    quantity = safe_float(value("quantity"))
    units = str(value("units")).strip()
    quantity_kg, quantity_status = convert_to_kg(quantity, units)
    value_usd = safe_float(value("value_usd"))
    price = value_usd / quantity_kg if quantity_kg and value_usd else None
    shipment_date = str(value("shipment_date")).strip()
    year = parse_year(shipment_date)
    data_status = "Clean"
    if (
        product_status != "Approved"
        or standard_product == "Other / Review Required"
        or quantity_status != "Valid KG"
        or not price
        or importer_country in {"", "N/A"}
    ):
        data_status = "Needs Manual Review"
    duplicate_product = standard_product if product_status == "Approved" else product_raw
    duplicate_importer = importer_standard if importer_status == "Approved" else importer_raw
    duplicate_exporter = exporter_standard if exporter_status == "Approved" else exporter_raw
    duplicate_importer_country = importer_country if importer_country_status == "Approved" else importer_country_raw
    duplicate_exporter_country = exporter_country if exporter_country_status == "Approved" else exporter_country_raw
    duplicate_key = "|".join(
        [
            shipment_date.lower(),
            simple_key(duplicate_product),
            simple_key(duplicate_importer),
            simple_key(duplicate_exporter),
            simple_key(duplicate_importer_country),
            simple_key(duplicate_exporter_country),
            str(round(quantity_kg or 0, 6)),
            str(round(value_usd, 4)),
        ]
    )
    return {
        "shipment_date": shipment_date,
        "year": year,
        "month_key": parse_month(shipment_date),
        "hs_code": str(value("hs_code")).strip(),
        "raw_product_description": product_raw,
        "standard_product": standard_product,
        "product_confidence": product_confidence,
        "product_status": product_status,
        "product_reason": product_reason,
        "raw_importer_name": importer_raw,
        "standard_importer_name": importer_standard,
        "importer_confidence": importer_confidence,
        "importer_status": importer_status,
        "importer_reason": importer_reason,
        "raw_importer_country": importer_country_raw,
        "importer_country": importer_country,
        "importer_country_confidence": importer_country_confidence,
        "importer_country_status": importer_country_status,
        "importer_country_reason": importer_country_reason,
        "importer_port": str(value("importer_port")).strip(),
        "raw_exporter_name": exporter_raw,
        "standard_exporter_name": exporter_standard,
        "exporter_confidence": exporter_confidence,
        "exporter_status": exporter_status,
        "exporter_reason": exporter_reason,
        "raw_exporter_country": exporter_country_raw,
        "exporter_country": exporter_country,
        "exporter_country_confidence": exporter_country_confidence,
        "exporter_country_status": exporter_country_status,
        "exporter_country_reason": exporter_country_reason,
        "exporter_port": str(value("exporter_port")).strip(),
        "market_category": market_category(importer_country),
        "quantity": quantity,
        "units": units,
        "quantity_kg": quantity_kg,
        "quantity_status": quantity_status,
        "value_usd": value_usd,
        "price_per_kg": price,
        "invoice_currency": str(value("invoice_currency")).strip(),
        "duplicate_key": duplicate_key,
        "data_status": data_status,
    }


def clean_company_name(raw_name, approved_companies):
    direct, match_reason = _approved_company_lookup(raw_name, approved_companies)
    if direct == REJECTED_COMPANY_ALIAS:
        return display_company(raw_name), 0.5, "Pending", match_reason
    if match_reason.startswith("Pending"):
        return direct, 0.9, "Pending", match_reason
    if direct:
        return direct, 1.0, "Approved", match_reason
    return normalize_company(raw_name)


def _approved_company_lookup(raw_name, approved_companies):
    raw_simple = simple_key(raw_name)
    raw_match = matching_company_key(raw_name)
    if approved_companies.get(raw_simple) == REJECTED_COMPANY_ALIAS:
        return REJECTED_COMPANY_ALIAS, "Alias was manually removed from a company master group."
    direct = approved_companies.get(raw_simple) or approved_companies.get(raw_match)
    if direct:
        return direct, "Approved company master reused from prior Cleaning Review."

    if len(raw_match) < 5:
        return "", ""

    best_value = ""
    best_score = 0.0
    for candidate_key, candidate_value in approved_companies.items():
        if candidate_value == REJECTED_COMPANY_ALIAS:
            continue
        candidate = candidate_key.strip()
        if len(candidate) < 5:
            continue
        candidate_match = matching_company_key(candidate)
        if not candidate_match:
            candidate_match = candidate
        contains_match = (
            len(raw_match) >= 7
            and len(candidate_match) >= 7
            and (raw_match in candidate_match or candidate_match in raw_match)
        )
        score = 1.0 if contains_match else difflib.SequenceMatcher(None, raw_match, candidate_match).ratio()
        if score > best_score:
            best_score = score
            best_value = candidate_value

    if best_value and best_score >= 0.92:
        return best_value, "Pending similar company master match from prior configuration; confirm this new alias before using it in opportunities."
    return "", ""


def clean_country_name(raw_country, approved_countries):
    direct = approved_countries.get(simple_key(raw_country))
    if direct:
        return direct, 1.0, "Approved", "Approved country master reused from prior Cleaning Review."
    return normalize_country(raw_country)


def approved_product_map(conn):
    rows = conn.execute(
        """
        select raw_product_description, approved_standard_product
        from product_mappings
        where status = 'Approved'
          and coalesce(approved_standard_product, '') != ''
          and (
              coalesce(is_master, 0) = 1
              or reason_for_suggestion like 'Manually%'
              or reason_for_suggestion like 'Group approved%'
          )
        """
    ).fetchall()
    return {simple_key(row["raw_product_description"]): row["approved_standard_product"] for row in rows}


def approved_company_map(conn):
    rows = conn.execute(
        """
        select raw_company_name, approved_standard_company_name
        from company_mappings
        where status = 'Approved' and coalesce(approved_standard_company_name, '') != ''
        """
    ).fetchall()
    mapping = {}
    for row in rows:
        mapping[simple_key(row["raw_company_name"])] = row["approved_standard_company_name"]
        mapping[matching_company_key(row["raw_company_name"])] = row["approved_standard_company_name"]
    rejected_rows = conn.execute(
        """
        select raw_company_name
        from company_mappings
        where status = 'Rejected'
          and (
              reason_for_suggestion like 'Removed from this Smart Confirm group%'
              or reason_for_suggestion like 'Removed from the previous Smart Confirm group%'
          )
        """
    ).fetchall()
    for row in rejected_rows:
        mapping[simple_key(row["raw_company_name"])] = REJECTED_COMPANY_ALIAS
    return mapping


def approved_country_map(conn):
    rows = conn.execute(
        """
        select raw_country_name, approved_standard_country_name
        from country_mappings
        where status = 'Approved' and coalesce(approved_standard_country_name, '') != ''
        """
    ).fetchall()
    return {simple_key(row["raw_country_name"]): row["approved_standard_country_name"] for row in rows}


def insert_clean_record(conn, upload_id, raw_id, cleaned):
    conn.execute(
        """
        insert into clean_trade_records(
            upload_id, raw_record_id, shipment_date, year, month_key, hs_code,
            raw_product_description, standard_product, product_confidence, product_status,
            raw_importer_name, standard_importer_name, importer_confidence, importer_status,
            importer_country, importer_port, raw_exporter_name, standard_exporter_name,
            exporter_confidence, exporter_status, exporter_country, exporter_port,
            market_category, quantity, units, quantity_kg, quantity_status,
            value_usd, price_per_kg, invoice_currency, duplicate_key, data_status, created_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            upload_id,
            raw_id,
            cleaned["shipment_date"],
            cleaned["year"],
            cleaned["month_key"],
            cleaned["hs_code"],
            cleaned["raw_product_description"],
            cleaned["standard_product"],
            cleaned["product_confidence"],
            cleaned["product_status"],
            cleaned["raw_importer_name"],
            cleaned["standard_importer_name"],
            cleaned["importer_confidence"],
            cleaned["importer_status"],
            cleaned["importer_country"],
            cleaned["importer_port"],
            cleaned["raw_exporter_name"],
            cleaned["standard_exporter_name"],
            cleaned["exporter_confidence"],
            cleaned["exporter_status"],
            cleaned["exporter_country"],
            cleaned["exporter_port"],
            cleaned["market_category"],
            cleaned["quantity"],
            cleaned["units"],
            cleaned["quantity_kg"],
            cleaned["quantity_status"],
            cleaned["value_usd"],
            cleaned["price_per_kg"],
            cleaned["invoice_currency"],
            cleaned["duplicate_key"],
            cleaned["data_status"],
            int(time.time()),
        ),
    )


def quality_summary(raw_rows, clean_rows, duplicate_count):
    unique_products = {row["raw_product_description"] for row in clean_rows if row["raw_product_description"]}
    unique_importers = {row["standard_importer_name"] for row in clean_rows if row["standard_importer_name"]}
    unique_exporters = {row["standard_exporter_name"] for row in clean_rows if row["standard_exporter_name"]}
    return {
        "total_records": len(raw_rows),
        "clean_records": len(clean_rows),
        "duplicates_removed": duplicate_count,
        "clean_product_records": sum(1 for row in clean_rows if row["standard_product"] != "Other / Review Required"),
        "review_required_product_records": sum(1 for row in clean_rows if row["standard_product"] == "Other / Review Required"),
        "unique_raw_product_descriptions": len(unique_products),
        "unique_importers": len(unique_importers),
        "unique_exporters": len(unique_exporters),
        "valid_kg_quantity_records": sum(1 for row in clean_rows if row["quantity_kg"] is not None),
        "invalid_quantity_records": sum(1 for row in clean_rows if row["quantity_kg"] is None),
        "price_per_kg_records": sum(1 for row in clean_rows if row["price_per_kg"] is not None),
        "missing_value_or_quantity_records": sum(1 for row in clean_rows if not row["value_usd"] or row["quantity_kg"] is None),
        "manual_review_records": sum(1 for row in clean_rows if row["data_status"] != "Clean"),
    }


def cleaning_summary(conn):
    stats = _stats(conn)
    latest_upload_row = conn.execute("select * from uploaded_files order by id desc limit 1").fetchone()
    latest_upload_data = dict(latest_upload_row) if latest_upload_row else {}
    product_mappings_applied = conn.execute(
        "select count(*) from product_mappings where status = 'Approved' and coalesce(approved_standard_product, '') != ''"
    ).fetchone()[0]
    company_mappings_applied = conn.execute(
        "select count(*) from company_mappings where status = 'Approved' and coalesce(approved_standard_company_name, '') != ''"
    ).fetchone()[0]
    country_mappings_applied = conn.execute(
        "select count(*) from country_mappings where status = 'Approved' and coalesce(approved_standard_country_name, '') != ''"
    ).fetchone()[0]
    pending_product_mappings = conn.execute(
        "select count(*) from product_mappings where status = 'Pending'"
    ).fetchone()[0]
    pending_company_mappings = conn.execute(
        "select count(*) from company_mappings where status = 'Pending'"
    ).fetchone()[0]
    pending_country_mappings = conn.execute(
        "select count(*) from country_mappings where status = 'Pending'"
    ).fetchone()[0]
    stats.update(
        {
            "total_raw_records": latest_upload_data.get("row_count", 0),
            "cleaned_records": latest_upload_data.get("clean_count", stats.get("total_records", 0)),
            "product_mappings_applied": product_mappings_applied,
            "company_mappings_applied": company_mappings_applied,
            "country_mappings_applied": country_mappings_applied,
            "pending_product_mappings": pending_product_mappings,
            "pending_company_mappings": pending_company_mappings,
            "pending_country_mappings": pending_country_mappings,
            "records_missing_value_or_quantity": stats.get("missing_value_or_quantity_records", 0),
        }
    )
    return stats


def filtered_stats(conn, filters):
    where, params = analytics_where(filters)
    row = conn.execute(
        f"""
        select
            count(*) as total_records,
            sum(case when data_status = 'Clean' then 1 else 0 end) as clean_records,
            sum(case when standard_product = 'Other / Review Required' then 1 else 0 end) as review_required_records,
            count(distinct standard_importer_name) as unique_importers,
            count(distinct standard_exporter_name) as unique_exporters,
            count(distinct importer_country) as unique_countries,
            sum(case when upper(standard_exporter_name) like '%SHODHANA%' then 1 else 0 end) as shodhana_supplied_records,
            sum(case when upper(standard_exporter_name) not like '%SHODHANA%' then 1 else 0 end) as competitor_supplied_records,
            sum(case when quantity_kg is not null then 1 else 0 end) as valid_kg_records,
            sum(case when quantity_kg is null then 1 else 0 end) as invalid_qty_records,
            sum(case when price_per_kg is not null then 1 else 0 end) as price_records,
            sum(case when value_usd = 0 or quantity_kg is null then 1 else 0 end) as missing_value_or_quantity_records,
            sum(coalesce(quantity_kg, 0)) as total_quantity_kg,
            sum(coalesce(value_usd, 0)) as total_value_usd
        from clean_trade_records
        {where}
        """,
        params,
    ).fetchone()
    stats = dict(row)
    total_qty = stats.get("total_quantity_kg") or 0
    total_value = stats.get("total_value_usd") or 0
    stats["avg_price_per_kg"] = round(total_value / total_qty, 2) if total_qty else 0
    stats["total_quantity_kg"] = round(total_qty, 4)
    stats["total_value_usd"] = round(total_value, 2)
    latest_upload = conn.execute("select row_count, clean_count from uploaded_files order by id desc limit 1").fetchone()
    stats["total_raw_records"] = latest_upload["row_count"] if latest_upload else 0
    return stats


def grouped_metric(conn, column, filters, limit=10):
    allowed = {
        "standard_product",
        "importer_country",
        "exporter_country",
        "standard_importer_name",
        "standard_exporter_name",
    }
    if column not in allowed:
        raise ValueError("Unsupported group column.")
    where, params = analytics_where(filters)
    rows = conn.execute(
        f"""
        select {column} as label,
               sum(coalesce(quantity_kg, 0)) as quantity_kg,
               sum(coalesce(value_usd, 0)) as value_usd,
               count(*) as records,
               case
                 when sum(coalesce(quantity_kg, 0)) > 0 then sum(coalesce(value_usd, 0)) / sum(coalesce(quantity_kg, 0))
                 else null
               end as avg_price_per_kg
        from clean_trade_records
        {where}
        group by {column}
        order by quantity_kg desc, value_usd desc
        limit ?
        """,
        (*params, limit),
    ).fetchall()
    return [round_metric_row(dict(row)) for row in rows]


def month_quantity_trend(conn, filters):
    where, params = analytics_where(filters)
    rows = conn.execute(
        f"""
        select month_key as label,
               sum(coalesce(quantity_kg, 0)) as quantity_kg,
               sum(coalesce(value_usd, 0)) as value_usd,
               count(*) as records
        from clean_trade_records
        {where}
        group by month_key
        order by label
        """
        ,
        params,
    ).fetchall()
    return [round_metric_row(dict(row)) for row in rows]


def month_price_trend(conn, filters):
    where, params = analytics_where(filters)
    rows = conn.execute(
        f"""
        select month_key as label,
               case
                 when sum(coalesce(quantity_kg, 0)) > 0 then sum(coalesce(value_usd, 0)) / sum(coalesce(quantity_kg, 0))
                 else null
               end as avg_price_per_kg,
               count(price_per_kg) as priced_rows
        from clean_trade_records
        {where}
        group by month_key
        order by label
        """,
        params,
    ).fetchall()
    return [round_metric_row(dict(row)) for row in rows]


def price_range_by_product(conn, filters):
    where, params = analytics_where(filters, extra_clauses=["price_per_kg is not null"])
    rows = conn.execute(
        f"""
        select standard_product as product,
               min(price_per_kg) as min_price,
               case
                 when sum(coalesce(quantity_kg, 0)) > 0 then sum(coalesce(value_usd, 0)) / sum(coalesce(quantity_kg, 0))
                 else avg(price_per_kg)
               end as avg_price,
               max(price_per_kg) as max_price,
               count(price_per_kg) as priced_rows
        from clean_trade_records
        {where}
        group by standard_product
        order by avg_price desc
        """,
        params,
    ).fetchall()
    return [round_metric_row(dict(row)) for row in rows]


def competitor_intelligence(conn, filters, limit=30):
    where, params = analytics_where(filters, extra_clauses=["upper(standard_exporter_name) not like '%SHODHANA%'"])
    rows = conn.execute(
        f"""
        select
            standard_exporter_name as exporter_name,
            standard_product as product_category,
            group_concat(distinct importer_country) as countries_supplied,
            sum(coalesce(quantity_kg, 0)) as total_quantity_kg,
            sum(coalesce(value_usd, 0)) as total_value_usd,
            case
              when sum(coalesce(quantity_kg, 0)) > 0 then sum(coalesce(value_usd, 0)) / sum(coalesce(quantity_kg, 0))
              else null
            end as avg_price_per_kg,
            count(*) as shipment_count,
            group_concat(shipment_date) as shipment_dates
        from clean_trade_records
        {where}
        group by standard_exporter_name, standard_product
        order by total_quantity_kg desc, total_value_usd desc
        limit ?
        """,
        (*params, limit),
    ).fetchall()
    result = []
    for row in rows:
        item = round_metric_row(dict(row))
        dates = [date for date in (item.pop("shipment_dates") or "").split(",") if date]
        dates.sort(key=_date_sort_key)
        item["last_shipment_date"] = dates[-1] if dates else ""
        result.append(item)
    return result


def customer_intelligence(conn, filters, limit=30):
    return opportunities(filters=filters, limit=limit)


def dashboard_filter_options(conn):
    def distinct(column):
        rows = conn.execute(
            f"select distinct {column} as value from clean_trade_records where coalesce({column}, '') != '' order by value limit 500"
        ).fetchall()
        return [row["value"] for row in rows]

    return {
        "product_categories": distinct("standard_product"),
        "importer_countries": distinct("importer_country"),
        "exporter_countries": distinct("exporter_country"),
        "years": [row["value"] for row in conn.execute("select distinct year as value from clean_trade_records where year > 0 order by year desc").fetchall()],
        "months": distinct("month_key"),
        "shodhana_statuses": ["Existing Shodhana Supply", "Competitor Supply"],
    }


def market_average_by_product(conn, filters):
    where, params = analytics_where(filters, extra_clauses=["quantity_kg is not null", "quantity_kg > 0"])
    rows = conn.execute(
        f"""
        select standard_product,
               sum(coalesce(value_usd, 0)) as total_value_usd,
               sum(coalesce(quantity_kg, 0)) as total_quantity_kg
        from clean_trade_records
        {where}
        group by standard_product
        """,
        params,
    ).fetchall()
    result = {}
    for row in rows:
        qty = row["total_quantity_kg"] or 0
        result[row["standard_product"]] = (row["total_value_usd"] or 0) / qty if qty else 0
    return result


def score_opportunity(item, quantity_threshold=0, recent_threshold=0):
    score = 0
    reasons = []
    qty = item.get("total_quantity_kg") or 0
    last_ordinal = item.get("last_shipment_ordinal") or 0
    invalid_qty = item.get("invalid_quantity_rows") or 0
    review_product = item.get("review_product_rows") or 0

    if quantity_threshold and qty >= quantity_threshold:
        score += 30
        reasons.append("High quantity buyer")

    if recent_threshold and last_ordinal >= recent_threshold:
        score += 25
        reasons.append("Recent purchase activity")

    if item.get("shodhana_status") == "Competitor Supply":
        score += 20
        reasons.append("Buying from competitor")

    if (item.get("shipment_count") or 0) >= 3:
        score += 15
        reasons.append("Repeated shipments")
    elif (item.get("shipment_count") or 0) >= 2:
        score += 15
        reasons.append("Repeated shipments")

    if item.get("market_category") in {"Regulated", "Semi-regulated"}:
        score += 10
        reasons.append("Regulated/semi-regulated market")

    if (item.get("avg_price_per_kg") or 0) > (item.get("market_avg_price_per_kg") or 0) > 0:
        score += 10
        reasons.append("Price above market average")

    if invalid_qty:
        score -= 20
        reasons.append("Quantity KG missing or invalid")

    if review_product:
        score -= 10
        reasons.append("Requires manual product review")

    score = max(0, min(100, int(score)))
    if score >= 75:
        tier = "High Opportunity"
    elif score >= 45:
        tier = "Medium Opportunity"
    else:
        tier = "Low Opportunity"

    if item.get("shodhana_status") == "Existing Shodhana Supply":
        action = "Protect the account, check if the customer is also buying from competitors, and pitch continuity or expansion."
    elif invalid_qty or review_product:
        action = "Review product/quantity quality first, then validate buyer fit before outreach."
    elif tier == "High Opportunity":
        action = "Prioritize for Shodhana BD outreach with product-specific price benchmark and technical/regulatory positioning."
    elif tier == "Medium Opportunity":
        action = "Validate buyer fit, decision maker, and grade requirement before preparing a focused commercial pitch."
    else:
        action = "Keep in monitoring list until volume, recency, or price signal improves."
    return score, tier, action, reasons


def _stats(conn):
    row = conn.execute(
        """
        select
            count(*) as total_records,
                sum(case when standard_product != 'Other / Review Required' then 1 else 0 end) as clean_product_records,
                sum(case when standard_product = 'Other / Review Required' then 1 else 0 end) as review_required_records,
            count(distinct raw_product_description) as unique_raw_products,
            count(distinct standard_importer_name) as unique_importers,
            count(distinct standard_exporter_name) as unique_exporters,
            count(distinct importer_country) as unique_countries,
            sum(case when quantity_kg is not null then 1 else 0 end) as valid_kg_records,
            sum(case when quantity_kg is null then 1 else 0 end) as invalid_qty_records,
            sum(case when price_per_kg is not null then 1 else 0 end) as price_records,
            sum(case when value_usd = 0 or quantity_kg is null then 1 else 0 end) as missing_value_or_quantity_records,
            sum(case when data_status != 'Clean' then 1 else 0 end) as manual_review_records,
            sum(coalesce(quantity_kg, 0)) as total_quantity_kg,
            sum(coalesce(value_usd, 0)) as total_value_usd
        from clean_trade_records
        """
    ).fetchone()
    stats = dict(row)
    total_qty = stats.get("total_quantity_kg") or 0
    total_value = stats.get("total_value_usd") or 0
    stats["avg_price_per_kg"] = round(total_value / total_qty, 2) if total_qty else 0
    stats["total_quantity_kg"] = round(total_qty, 4)
    stats["total_value_usd"] = round(total_value, 2)
    upload = conn.execute(
        "select coalesce(sum(duplicate_count), 0) as duplicates_removed, count(*) as uploads from uploaded_files"
    ).fetchone()
    stats["duplicates_removed"] = upload["duplicates_removed"]
    stats["uploads"] = upload["uploads"]
    return stats


def _group_rows(conn, column, limit=10):
    rows = conn.execute(
        f"""
        select {column} as label,
               sum(coalesce(quantity_kg, 0)) as quantity_kg,
               sum(coalesce(value_usd, 0)) as value_usd,
               count(*) as records
        from clean_trade_records
        group by {column}
        order by quantity_kg desc, value_usd desc
        limit ?
        """,
        (limit,),
    ).fetchall()
    return rows_to_dicts(rows)


def _product_split(conn):
    rows = conn.execute(
        """
        select standard_product as label, count(*) as records, sum(coalesce(quantity_kg, 0)) as quantity_kg
        from clean_trade_records
        group by standard_product
        order by records desc
        """
    ).fetchall()
    return rows_to_dicts(rows)


def _month_trend(conn):
    rows = conn.execute(
        """
        select month_key as label, sum(coalesce(quantity_kg, 0)) as quantity_kg, count(*) as records
        from clean_trade_records
        group by month_key
        order by label
        limit 36
        """
    ).fetchall()
    return rows_to_dicts(rows)


def _price_range(conn):
    rows = conn.execute(
        """
        select standard_product as product,
               min(price_per_kg) as min_price,
               avg(price_per_kg) as avg_price,
               max(price_per_kg) as max_price,
               count(price_per_kg) as priced_rows
        from clean_trade_records
        where price_per_kg is not null
        group by standard_product
        order by avg_price desc
        """
    ).fetchall()
    return rows_to_dicts(rows)


def _replace_product_mappings(conn, rows):
    existing_by_key = _mapping_rows_by_key(conn, "product_mappings", "raw_product_description", simple_key)
    for row in rows:
        existing = existing_by_key.get(simple_key(row["raw_product_description"]))
        if existing:
            suggested = row["suggested_standard_product"]
            approved = row["approved_standard_product"]
            status = row["status"]
            confidence = row["confidence_score"]
            reason = row.get("reason_for_suggestion", "")
            is_master = max(int(existing.get("is_master") or 0), int(row.get("is_master") or 0))
            if is_master and existing.get("status") == "Approved" and existing.get("approved_standard_product"):
                suggested = existing["approved_standard_product"]
                approved = existing["approved_standard_product"]
                status = "Approved"
                confidence = max(float(existing.get("confidence_score") or 0), float(confidence or 0), 0.96)
                reason = "Approved product master retained and reused for this upload."
            elif existing.get("status") == "Rejected":
                approved = ""
                status = "Rejected"
                reason = existing.get("reason_for_suggestion") or "Rejected product mapping retained."
            elif (
                existing.get("status") == "Pending"
                and simple_key(existing.get("suggested_standard_product")) == simple_key(REMAINING_MAPPING_VALUE)
            ):
                suggested = REMAINING_MAPPING_VALUE
                approved = ""
                status = "Pending"
                confidence = min(float(confidence or 0), 0.65)
                reason = existing.get("reason_for_suggestion") or "Alias is waiting in Remaining / Create New Mapping."
            conn.execute(
                """
                update product_mappings
                set suggested_standard_product = ?,
                    confidence_score = ?,
                    reason_for_suggestion = ?,
                    approved_standard_product = ?,
                    status = ?,
                    is_master = ?
                where id = ?
                """,
                (suggested, confidence, reason, approved, status, is_master, existing["id"]),
            )
            continue
        conn.execute(
            """
            insert into product_mappings(
                raw_product_description, suggested_standard_product, confidence_score,
                reason_for_suggestion, approved_standard_product, status, is_master, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["raw_product_description"],
                row["suggested_standard_product"],
                row["confidence_score"],
                row.get("reason_for_suggestion", ""),
                row["approved_standard_product"],
                row["status"],
                int(row.get("is_master") or 0),
                int(time.time()),
            ),
        )


def _replace_company_mappings(conn, rows):
    existing_by_key = _mapping_rows_by_key(conn, "company_mappings", "raw_company_name", simple_key)
    for row in rows:
        existing = existing_by_key.get(simple_key(row["raw_company_name"]))
        if existing:
            suggested = row["suggested_standard_company_name"]
            approved = row["approved_standard_company_name"]
            status = row["status"]
            confidence = row["confidence_score"]
            reason = row.get("reason_for_suggestion", "")
            source_roles = _merge_roles(existing.get("source_roles", ""), row.get("source_roles", ""))
            is_master = max(int(existing.get("is_master") or 0), int(row.get("is_master") or 0))
            if existing.get("status") == "Approved" and existing.get("approved_standard_company_name"):
                suggested = existing["approved_standard_company_name"]
                approved = existing["approved_standard_company_name"]
                status = "Approved"
                is_master = max(is_master, int(row.get("is_master") or 0))
                confidence = max(float(existing.get("confidence_score") or 0), float(confidence or 0), 0.96)
                reason = "Approved company master retained and reused for this upload."
            elif existing.get("status") == "Rejected":
                approved = ""
                status = "Rejected"
                reason = existing.get("reason_for_suggestion") or "Rejected company mapping retained."
            elif (
                existing.get("status") == "Pending"
                and simple_key(existing.get("suggested_standard_company_name")) == simple_key(REMAINING_MAPPING_VALUE)
            ):
                suggested = REMAINING_MAPPING_VALUE
                approved = ""
                status = "Pending"
                confidence = min(float(confidence or 0), 0.65)
                reason = existing.get("reason_for_suggestion") or "Alias is waiting in Remaining / Create New Mapping."
            conn.execute(
                """
                update company_mappings
                set suggested_standard_company_name = ?,
                    confidence_score = ?,
                    reason_for_suggestion = ?,
                    source_roles = ?,
                    approved_standard_company_name = ?,
                    status = ?,
                    is_master = ?
                where id = ?
                """,
                (suggested, confidence, reason, source_roles, approved, status, is_master, existing["id"]),
            )
            continue
        conn.execute(
            """
            insert into company_mappings(
                raw_company_name, suggested_standard_company_name, confidence_score,
                reason_for_suggestion, source_roles, approved_standard_company_name, status, is_master, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["raw_company_name"],
                row["suggested_standard_company_name"],
                row["confidence_score"],
                row.get("reason_for_suggestion", ""),
                row.get("source_roles", ""),
                row["approved_standard_company_name"],
                row["status"],
                int(row.get("is_master") or 0),
                int(time.time()),
            ),
        )


def _replace_country_mappings(conn, rows):
    existing_by_key = _mapping_rows_by_key(conn, "country_mappings", "raw_country_name", simple_key)
    for row in rows:
        existing = existing_by_key.get(simple_key(row["raw_country_name"]))
        if existing:
            suggested = row["suggested_standard_country_name"]
            approved = row["approved_standard_country_name"]
            status = row["status"]
            confidence = row["confidence_score"]
            reason = row.get("reason_for_suggestion", "")
            source_roles = _merge_roles(existing.get("source_roles", ""), row.get("source_roles", ""))
            is_master = max(int(existing.get("is_master") or 0), int(row.get("is_master") or 0))
            existing_approved = existing.get("approved_standard_country_name") or ""
            trusted_real_country = (
                int(row.get("is_master") or 0) == 1
                and not _is_generic_country_value(row.get("approved_standard_country_name"))
            )
            existing_is_generic = _is_generic_country_value(existing_approved)
            if (
                existing.get("status") == "Approved"
                and existing_approved
                and not (trusted_real_country and existing_is_generic)
            ):
                suggested = existing["approved_standard_country_name"]
                approved = existing["approved_standard_country_name"]
                status = "Approved"
                confidence = max(float(existing.get("confidence_score") or 0), float(confidence or 0), 0.96)
                reason = "Approved country master retained and reused for this upload."
            elif existing.get("status") == "Rejected":
                approved = ""
                status = "Rejected"
                reason = existing.get("reason_for_suggestion") or "Rejected country mapping retained."
            elif (
                existing.get("status") == "Pending"
                and simple_key(existing.get("suggested_standard_country_name")) == simple_key(REMAINING_MAPPING_VALUE)
            ):
                suggested = REMAINING_MAPPING_VALUE
                approved = ""
                status = "Pending"
                confidence = min(float(confidence or 0), 0.65)
                reason = existing.get("reason_for_suggestion") or "Alias is waiting in Remaining / Create New Mapping."
            conn.execute(
                """
                update country_mappings
                set suggested_standard_country_name = ?,
                    confidence_score = ?,
                    reason_for_suggestion = ?,
                    source_roles = ?,
                    approved_standard_country_name = ?,
                    status = ?,
                    is_master = ?
                where id = ?
                """,
                (suggested, confidence, reason, source_roles, approved, status, is_master, existing["id"]),
            )
            continue
        conn.execute(
            """
            insert into country_mappings(
                raw_country_name, suggested_standard_country_name, confidence_score,
                reason_for_suggestion, source_roles, approved_standard_country_name, status, is_master, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["raw_country_name"],
                row["suggested_standard_country_name"],
                row["confidence_score"],
                row.get("reason_for_suggestion", ""),
                row.get("source_roles", ""),
                row["approved_standard_country_name"],
                row["status"],
                int(row.get("is_master") or 0),
                int(time.time()),
            ),
        )


def _mapping_rows_by_key(conn, table, raw_column, key_func):
    rows = conn.execute(f"select * from {table} order by id asc").fetchall()
    by_key = {}
    for row in rows:
        row = dict(row)
        key = key_func(row.get(raw_column, ""))
        if not key:
            continue
        current = by_key.get(key)
        if not current or _mapping_row_priority(row) > _mapping_row_priority(current):
            by_key[key] = row
    return by_key


def _mapping_row_priority(row):
    status_score = {"Approved": 3, "Pending": 2, "Rejected": 1}.get(row.get("status"), 0)
    return (int(row.get("is_master") or 0), status_score, int(row.get("id") or 0))


def _merge_roles(left, right):
    roles = set()
    for value in [left, right]:
        roles.update(part.strip() for part in str(value or "").split(",") if part.strip())
    return ", ".join(sorted(roles))


def _merge_company_mapping(mapping_rows, role, raw_name, standard_name, confidence, status, reason):
    key = simple_key(raw_name)
    if key not in mapping_rows:
        mapping_rows[key] = {
            "raw_company_name": raw_name,
            "suggested_standard_company_name": standard_name,
            "confidence_score": confidence,
            "reason_for_suggestion": reason,
            "source_roles": role,
            "approved_standard_company_name": standard_name if status == "Approved" else "",
            "status": status,
        }
        return
    current = mapping_rows[key]
    roles = set(filter(None, [part.strip() for part in current.get("source_roles", "").split(",")]))
    roles.add(role)
    current["source_roles"] = ", ".join(sorted(roles))
    if confidence > current.get("confidence_score", 0):
        current["suggested_standard_company_name"] = standard_name
        current["confidence_score"] = confidence
        current["reason_for_suggestion"] = reason
        current["approved_standard_company_name"] = standard_name if status == "Approved" else current.get("approved_standard_company_name", "")
        current["status"] = status if current["status"] != "Approved" else current["status"]


def _merge_country_mapping(mapping_rows, role, raw_name, standard_name, confidence, status, reason):
    key = simple_key(raw_name)
    if not key or key in {"N A", "NA", "NONE", "UNKNOWN", "NOT AVAILABLE"}:
        key = "N/A"
    is_master = 1 if _is_trusted_country_mapping(status, reason) else 0
    if key not in mapping_rows:
        mapping_rows[key] = {
            "raw_country_name": raw_name or "N/A",
            "suggested_standard_country_name": standard_name,
            "confidence_score": confidence,
            "reason_for_suggestion": reason,
            "source_roles": role,
            "approved_standard_country_name": standard_name if status == "Approved" else "",
            "status": status,
            "is_master": is_master,
        }
        return
    current = mapping_rows[key]
    roles = set(filter(None, [part.strip() for part in current.get("source_roles", "").split(",")]))
    roles.add(role)
    current["source_roles"] = ", ".join(sorted(roles))
    current["is_master"] = max(int(current.get("is_master") or 0), is_master)
    if confidence > current.get("confidence_score", 0):
        current["suggested_standard_country_name"] = standard_name
        current["confidence_score"] = confidence
        current["reason_for_suggestion"] = reason
        current["approved_standard_country_name"] = standard_name if status == "Approved" else current.get("approved_standard_country_name", "")
        current["status"] = status if current["status"] != "Approved" else current["status"]


def _is_trusted_country_mapping(status, reason):
    if status != "Approved":
        return False
    reason = str(reason or "").lower()
    return "exact country alias" in reason or "trusted country master" in reason


def _is_trusted_product_mapping(status, reason):
    if status != "Approved":
        return False
    reason = str(reason or "").lower()
    return "exact rule match" in reason or "exact mapping from product synonym master" in reason


def _is_generic_country_value(value):
    return simple_key(value) in {"", "N A", "NA", "NONE", "UNKNOWN", "NOT AVAILABLE"}


def _cluster_company_mappings(mapping_rows):
    groups = {}
    for row in mapping_rows.values():
        cluster_key = _company_anchor_key(row.get("raw_company_name", ""))
        if not cluster_key:
            continue
        groups.setdefault(cluster_key, []).append(row)

    for rows in groups.values():
        suggested_values = {simple_key(row.get("suggested_standard_company_name", "")) for row in rows}
        raw_values = {simple_key(row.get("raw_company_name", "")) for row in rows}
        if len(rows) < 2 or (len(suggested_values) == 1 and len(raw_values) == 1):
            continue
        canonical = _best_company_canonical(rows)
        for row in rows:
            if row.get("status") == "Approved":
                continue
            row["suggested_standard_company_name"] = canonical
            row["confidence_score"] = max(float(row.get("confidence_score") or 0), 0.84)
            row["status"] = "Pending"
            row["approved_standard_company_name"] = ""
            row["reason_for_suggestion"] = (
                "Similar normalized company names found in the uploaded document. "
                "Approve to club these importer/exporter variants under one master company."
            )


def _best_company_canonical(rows):
    approved = [
        simple_key(row.get("approved_standard_company_name"))
        for row in rows
        if row.get("status") == "Approved" and simple_key(row.get("approved_standard_company_name"))
    ]
    if approved:
        return max(approved, key=_company_name_quality)
    names = [simple_key(row.get("suggested_standard_company_name") or row.get("raw_company_name")) for row in rows]
    return max(names, key=_company_name_quality) if names else "UNKNOWN"


def _company_anchor_key(value):
    core = matching_company_key(value)
    if not core:
        return ""
    first = core.split()[0]
    if (
        len(first) < 3
        or first.isdigit()
        or first in {"UNKNOWN", "ORDER", "INTERNATIONAL", "GLOBAL", "TRADING", "ENTERPRISES"}
    ):
        return core
    return first


def _company_name_quality(name):
    name = simple_key(name)
    address_terms = {
        "STREET", "ROAD", "AVENUE", "BUILDING", "FLOOR", "DISTRICT", "PYRAMIDS",
        "GIZA", "EGYPT", "PIN", "ZIP", "PO", "BOX",
    }
    words = name.split()
    noisy = sum(1 for word in words if word in address_terms or any(char.isdigit() for char in word))
    legal_strength = (
        2 if "PRIVATE LIMITED" in name else
        1 if any(word in words for word in {"LIMITED", "LTD", "SA", "SAE", "GMBH", "INC", "LLP"}) else
        0
    )
    useful_length = min(len(name), 100)
    return (-noisy, legal_strength, useful_length, -len(name))


def analytics_where(filters, extra_clauses=None):
    filters = filters or {}
    clauses = list(extra_clauses or [])
    params = []
    mapping = [
        ("product_category", "standard_product", "exact"),
        ("product", "standard_product", "exact"),
        ("importer_country", "importer_country", "exact"),
        ("country", "importer_country", "exact"),
        ("exporter_country", "exporter_country", "exact"),
        ("importer_name", "standard_importer_name", "like"),
        ("importer", "standard_importer_name", "like"),
        ("exporter_name", "standard_exporter_name", "like"),
        ("exporter", "standard_exporter_name", "like"),
        ("month", "month_key", "exact"),
    ]
    for key, column, mode in mapping:
        value = (filters.get(key) or "").strip()
        if not value:
            continue
        if mode == "like":
            clauses.append(f"lower({column}) like lower(?)")
            params.append(f"%{value}%")
        else:
            clauses.append(f"{column} = ?")
            params.append(value)

    year = (filters.get("year") or "").strip()
    if year:
        clauses.append("year = ?")
        params.append(int(year))

    status = (filters.get("shodhana_status") or "").strip()
    if status == "Existing Shodhana Supply":
        clauses.append("upper(standard_exporter_name) like '%SHODHANA%'")
    elif status == "Competitor Supply":
        clauses.append("upper(standard_exporter_name) not like '%SHODHANA%'")

    return ("where " + " and ".join(clauses), params) if clauses else ("", params)


def round_metric_row(row):
    for key in [
        "quantity_kg",
        "value_usd",
        "avg_price_per_kg",
        "total_quantity_kg",
        "total_value_usd",
        "min_price",
        "avg_price",
        "max_price",
    ]:
        if key in row and row[key] is not None:
            row[key] = round(row[key], 4 if "quantity" in key else 2)
    return row


def shodhana_status_for_suppliers(suppliers):
    has_shodhana = any("SHODHANA" in simple_key(supplier) for supplier in suppliers)
    has_competitor = any("SHODHANA" not in simple_key(supplier) for supplier in suppliers)
    if has_competitor:
        return "Competitor Supply"
    if has_shodhana:
        return "Existing Shodhana Supply"
    return "Competitor Supply"


def split_distinct_text(value):
    raw_values = []
    text_value = str(value or "").strip()
    if text_value.startswith("["):
        try:
            raw_values = json.loads(text_value)
        except (TypeError, ValueError):
            raw_values = []
    if not raw_values:
        raw_values = text_value.split(",")
    result = []
    seen = set()
    for part in raw_values:
        text = str(part or "").strip()
        key = simple_key(text)
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def opportunity_id(item):
    key = "|".join([item.get("importer", ""), item.get("country", ""), item.get("product", "")]).lower()
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def percentile(values, pct):
    values = sorted(value for value in values if value is not None)
    if not values:
        return 0
    index = min(len(values) - 1, max(0, int(round((len(values) - 1) * pct))))
    return values[index]


def _date_to_ordinal(value):
    year, month, day = _date_sort_key(value)
    if not year:
        return 0
    return (year * 372) + (month * 31) + day


def clean_records_for_export(filters=None):
    filters = filters or {}
    where, params = analytics_where(filters)
    with connect() as conn:
        rows = conn.execute(
            f"""
            select
                shipment_date,
                year,
                month_key,
                hs_code,
                raw_product_description,
                standard_product,
                raw_importer_name,
                standard_importer_name,
                importer_country,
                raw_exporter_name,
                standard_exporter_name,
                exporter_country,
                market_category,
                quantity,
                units,
                quantity_kg,
                value_usd,
                price_per_kg,
                data_status
            from clean_trade_records
            {where}
            order by id
            """,
            params,
        ).fetchall()
    return rows_to_dicts(rows)


def dashboard_summary_rows(filters=None):
    data = dashboard(filters or {})
    stats = data["stats"]
    return [{"metric": key, "value": value} for key, value in stats.items()]


def opportunities_for_export(filters=None):
    rows = opportunities(filters or {}, limit=10000)
    return [
        {
            "rank": row["rank"],
            "importer": row["importer"],
            "country": row["country"],
            "product": row["product"],
            "current_supplier": row["current_supplier"],
            "total_quantity_kg": row["total_quantity_kg"],
            "avg_price_per_kg": row["avg_price_per_kg"],
            "market_avg_price_per_kg": row["market_avg_price_per_kg"],
            "price_difference": row["price_difference"],
            "shipment_count": row["shipment_count"],
            "last_shipment_date": row["last_shipment_date"],
            "shodhana_status": row["shodhana_status"],
            "opportunity_score": row["score"],
            "opportunity_category": row["opportunity_category"],
            "reasons": "; ".join(row["reasons"]),
            "recommended_action": row["recommended_action"],
        }
        for row in rows
    ]


def rows_to_csv_bytes(rows):
    output = io.StringIO()
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    writer = csv.DictWriter(output, fieldnames=fields or ["empty"])
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue().encode("utf-8")


def rows_to_xlsx_bytes(sheet_name, rows):
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    fields = fields or ["empty"]
    matrix = [fields] + [[row.get(field, "") for field in fields] for row in rows]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", XLSX_CONTENT_TYPES)
        archive.writestr("_rels/.rels", XLSX_RELS)
        archive.writestr("xl/workbook.xml", f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="{xml_escape(sheet_name[:31])}" sheetId="1" r:id="rId1"/></sheets>
</workbook>""")
        archive.writestr("xl/_rels/workbook.xml.rels", XLSX_WORKBOOK_RELS)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet_xml(matrix))
    return output.getvalue()


def worksheet_xml(matrix):
    rows_xml = []
    for row_index, row in enumerate(matrix, start=1):
        cells = []
        for col_index, value in enumerate(row, start=1):
            ref = f"{column_letters(col_index)}{row_index}"
            if isinstance(value, (int, float)) and value is not None:
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{xml_escape(str(value or ""))}</t></is></c>')
        rows_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>{''.join(rows_xml)}</sheetData>
</worksheet>"""


def column_letters(index):
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


XLSX_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""

XLSX_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

XLSX_WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""


def _where(filters):
    clauses = []
    params = []
    for key, column in [
        ("product", "standard_product"),
        ("country", "importer_country"),
        ("importer", "standard_importer_name"),
        ("exporter", "standard_exporter_name"),
        ("year", "year"),
    ]:
        value = (filters.get(key) or "").strip()
        if not value:
            continue
        if key == "year":
            clauses.append(f"{column} = ?")
            params.append(int(value))
        else:
            clauses.append(f"lower({column}) like lower(?)")
            params.append(f"%{value}%")
    return ("where " + " and ".join(clauses), params) if clauses else ("", params)


def _clean_header(header):
    text = str(header or "").lower()
    text = text.replace("($)", " usd ")
    text = text.replace("$", " usd ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _similarity(left, right):
    import difflib

    return difflib.SequenceMatcher(None, left, right).ratio()


def _date_sort_key(value):
    text = str(value or "")
    dmy = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](20\d{2}|19\d{2})", text)
    if dmy:
        return (int(dmy.group(3)), int(dmy.group(2)), int(dmy.group(1)))
    ymd = re.search(r"(20\d{2}|19\d{2})[/-](\d{1,2})[/-](\d{1,2})", text)
    if ymd:
        return (int(ymd.group(1)), int(ymd.group(2)), int(ymd.group(3)))
    return (0, 0, 0)


def _first_present(row, names):
    normalized = {_clean_header(key): value for key, value in row.items()}
    for name in names:
        value = normalized.get(_clean_header(name))
        if str(value or "").strip():
            return str(value).strip()
    return ""
