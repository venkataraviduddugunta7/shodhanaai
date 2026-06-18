import csv
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
    clean_country_name,
    convert_to_kg,
    matching_company_key,
    market_category,
    normalize_company,
    normalize_country,
    normalize_date_text,
    parse_month,
    parse_year,
    safe_float,
    simple_key,
)

STANDARD_PRODUCTS = [
    "Duloxetine API",
    "Duloxetine Pellets",
    "Duloxetine Placebo Pellets",
    "Other / Review Required",
]

SHODHANA_SUPPLIER_TERMS = ["SHODHANA", "JAI LARA"]
GENERIC_COMPANY_KEYS = {"", "UNKNOWN", "TO THE ORDER", "TO THE ORDER OF", "NA", "N A", "NOT SPECIFIED"}

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
    if not product.exists():
        product.write_text(
            "raw,standard,notes\n"
            "Duloxetine Hcl Usp,Duloxetine API,API variant\n"
            "Duloxetine Hydrochloride,Duloxetine API,API variant\n"
            "Duloxetine Hydrochloride Ph.Eur,Duloxetine API,API variant\n"
            "Duloxetine Hydrochloride Ph Eur,Duloxetine API,API variant\n"
            "Duloxetine Hcl Ec Pellets 17% W/W,Duloxetine Pellets,Pellet variant\n"
            "Duloxetine Ec Pellets 17% W/W,Duloxetine Pellets,Pellet variant\n"
            "Duloxetine Delayed Release Pellets 17.65% W/W,Duloxetine Pellets,Pellet variant\n"
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

    for index, row in enumerate(rows, start=1):
        raw_rows_to_insert.append((index, json.dumps(row)))
        cleaned = clean_row(row, column_map)
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

        for role, raw_name, standard_name, confidence, status, reason in [
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
            _merge_country_mapping(country_mapping_rows, role, raw_name, standard_name, confidence, status, reason)

    quality = quality_summary(rows, cleaned_rows, duplicate_count)
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
    if kind == "product_mapping":
        target = SEED_DIR / "product_mappings.csv"
    elif kind == "company_mapping":
        target = SEED_DIR / "company_mappings.csv"
    elif kind == "country_mapping":
        target = SEED_DIR / "country_mappings.csv"
    else:
        raise ValueError(f"Unknown mapping file kind: {kind}")
    normalized_rows = []
    for row in rows:
        raw = _first_present(row, ["raw", "alias", "raw product description", "product description", "raw company name", "company name"])
        standard = _first_present(
            row,
            [
                "standard",
                "canonical",
                "canonical_name",
                "approved_standard",
                "approved standard product",
                "approved standard company",
                "standard product",
                "standard company",
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
    return {"rows": len(normalized_rows), "target": str(target)}


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
                group_concat(distinct standard_exporter_name) as suppliers,
                group_concat(standard_exporter_name || '@@' || coalesce(shipment_date, '')) as supplier_dates,
                sum(coalesce(quantity_kg, 0)) as total_quantity_kg,
                sum(coalesce(value_usd, 0)) as total_value_usd,
                case
                  when sum(case when price_per_kg is not null then coalesce(quantity_kg, 0) else 0 end) > 0
                  then sum(case when price_per_kg is not null then coalesce(value_usd, 0) else 0 end) /
                       sum(case when price_per_kg is not null then coalesce(quantity_kg, 0) else 0 end)
                  else null
                end as avg_price_per_kg,
                count(*) as shipment_count,
                group_concat(shipment_date) as shipment_dates,
                max(year) as latest_year,
                sum(case when quantity_kg is null then 1 else 0 end) as invalid_quantity_rows,
                sum(case when standard_product = 'Other / Review Required' then 1 else 0 end) as review_product_rows,
                sum(case when data_status != 'Clean' then 1 else 0 end) as manual_review_rows
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
        suppliers = [supplier for supplier in (item.get("suppliers") or "").split(",") if supplier]
        supplier_dates = [part for part in (item.pop("supplier_dates") or "").split(",") if part]
        dates = [date for date in (item.pop("shipment_dates") or "").split(",") if date]
        dates.sort(key=_date_sort_key)
        item["first_shipment_date"] = dates[0] if dates else ""
        item["last_shipment_date"] = dates[-1] if dates else ""
        item["last_shipment_ordinal"] = _date_to_ordinal(item["last_shipment_date"])
        item["suppliers"] = suppliers
        item["current_supplier"] = current_supplier_from_pairs(supplier_dates, suppliers)
        item["exporter"] = item["current_supplier"]
        item["shodhana_status"] = shodhana_status_for_suppliers(suppliers)
        item["has_shodhana_supplier"] = any(is_shodhana_supplier(supplier) for supplier in suppliers)
        item["has_competitor_supplier"] = any(not is_shodhana_supplier(supplier) for supplier in suppliers)
        item["customer_identification_status"] = customer_identification_status(item["importer"])
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
                count(*) as shipment_count,
                sum(coalesce(quantity_kg, 0)) as total_quantity_kg,
                sum(coalesce(value_usd, 0)) as total_value_usd,
                case
                  when sum(case when price_per_kg is not null then coalesce(quantity_kg, 0) else 0 end) > 0
                  then sum(case when price_per_kg is not null then coalesce(value_usd, 0) else 0 end) /
                       sum(case when price_per_kg is not null then coalesce(quantity_kg, 0) else 0 end)
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
        item["last_shipment_date"] = dates[-1] if dates else ""
        item["avg_price_per_kg"] = round(item.get("avg_price_per_kg") or 0, 2)
        item["total_quantity_kg"] = round(item.get("total_quantity_kg") or 0, 4)
        item["total_value_usd"] = round(item.get("total_value_usd") or 0, 2)
        item["shodhana_status"] = "Existing Shodhana Supply" if is_shodhana_supplier(item["supplier"]) else "Competitor Supply"
        supplier_history.append(item)

    shipment_history = []
    for row in rows:
        item = dict(row)
        item["shodhana_status"] = (
            "Existing Shodhana Supply"
            if is_shodhana_supplier(item["standard_exporter_name"])
            else "Competitor Supply"
        )
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
    opportunity = detail["opportunity"]
    # Bypass constraints for POC demonstration
    # if opportunity.get("customer_identification_status") != "Identified Customer":
    #     raise ValueError("Identify the real buyer before generating a pitch for this opportunity.")
    # if opportunity.get("manual_review_rows"):
    #     raise ValueError("Approve mappings and re-run cleaning before generating a pitch for this opportunity.")
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
    if kind == "products":
        table = "product_mappings"
    elif kind == "companies":
        table = "company_mappings"
    elif kind == "countries":
        table = "country_mappings"
    else:
        raise ValueError(f"Unknown mappings kind: {kind}")
    with connect() as conn:
        rows = conn.execute(f"select * from {table} order by confidence_score asc, id asc limit ?", (limit,)).fetchall()
    return rows_to_dicts(rows)


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
        issue_rows = review_records_for_conn(conn, "pending", limit=150)
    return {"summary": summary, "products": product_rows, "companies": company_rows, "issue_rows": issue_rows}


def update_mapping(kind, mapping_id, action, value=""):
    if action not in {"approve", "edit", "reject"}:
        raise ValueError("Mapping action must be approve, edit, or reject.")
    if kind == "product":
        table = "product_mappings"
        suggested_column = "suggested_standard_product"
        approved_column = "approved_standard_product"
    elif kind == "company":
        table = "company_mappings"
        suggested_column = "suggested_standard_company_name"
        approved_column = "approved_standard_company_name"
    elif kind == "country":
        table = "country_mappings"
        suggested_column = "suggested_standard_country_name"
        approved_column = "approved_standard_country_name"
    else:
        raise ValueError(f"Unknown mapping kind: {kind}")
        
    id_column = "id"
    with connect() as conn:
        row = conn.execute(f"select * from {table} where {id_column} = ?", (mapping_id,)).fetchone()
        if not row:
            raise ValueError(f"Mapping not found: {mapping_id}")
        row = dict(row)
        if action == "reject":
            conn.execute(
                f"update {table} set status = 'Rejected', {approved_column} = '' where id = ?",
                (mapping_id,),
            )
            status = "Rejected"
            approved = ""
        else:
            approved = (value or row.get(suggested_column) or "").strip()
            if kind == "product" and approved not in STANDARD_PRODUCTS:
                raise ValueError("Choose a valid standard product.")
            if not approved:
                raise ValueError("Approved value cannot be blank.")
            conn.execute(
                f"""
                update {table}
                set status = 'Approved',
                    {suggested_column} = ?,
                    {approved_column} = ?,
                    reason_for_suggestion = ?
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
        return {"id": mapping_id, "kind": kind, "status": status, "approved": approved}


def bulk_update_mappings(kind, min_confidence=0.9):
    if kind not in {"product", "company", "country"}:
        raise ValueError("Mapping kind must be product, company, or country.")
    if kind == "product":
        table = "product_mappings"
        suggested_column = "suggested_standard_product"
        approved_column = "approved_standard_product"
    elif kind == "company":
        table = "company_mappings"
        suggested_column = "suggested_standard_company_name"
        approved_column = "approved_standard_company_name"
    elif kind == "country":
        table = "country_mappings"
        suggested_column = "suggested_standard_country_name"
        approved_column = "approved_standard_country_name"
        
    min_confidence = float(min_confidence or 0.9)
    approved_count = 0
    with connect() as conn:
        rows = conn.execute(
            f"""
            select id, {suggested_column} as suggested
            from {table}
            where status = 'Pending' and confidence_score >= ?
            """,
            (min_confidence,),
        ).fetchall()
        for row in rows:
            suggested = (row["suggested"] or "").strip()
            if kind == "product" and suggested not in STANDARD_PRODUCTS:
                continue
            if not suggested:
                continue
            conn.execute(
                f"""
                update {table}
                set status = 'Approved',
                    {approved_column} = ?,
                    reason_for_suggestion = ?
                where id = ?
                """,
                (
                    suggested,
                    f"Bulk approved at {min_confidence:.0%}+ confidence in Cleaning Review.",
                    row["id"],
                ),
            )
            approved_count += 1
    return {"kind": kind, "approved_count": approved_count, "min_confidence": min_confidence}


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
            cleaned = clean_row(row, column_map, approved_products=approved_products, approved_companies=approved_companies, approved_countries=approved_countries)
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
        product_reason = "Approved product mapping from Cleaning Review."
    else:
        standard_product, product_confidence, product_status, product_reason = classify_product(product_raw)
    importer_raw = str(value("importer_name")).strip()
    exporter_raw = str(value("exporter_name")).strip()
    importer_standard, importer_confidence, importer_status, importer_reason = clean_company_name(importer_raw, approved_companies)
    exporter_standard, exporter_confidence, exporter_status, exporter_reason = clean_company_name(exporter_raw, approved_companies)
    quantity = safe_float(value("quantity"))
    units = str(value("units")).strip()
    quantity_kg, quantity_status = convert_to_kg(quantity, units)
    value_usd = safe_float(value("value_usd"))
    price = value_usd / quantity_kg if quantity_kg and value_usd and value_usd > 0 else None
    shipment_date = normalize_date_text(value("shipment_date"))
    year = parse_year(shipment_date)
    
    # Country cleaning
    raw_importer_country = str(value("importer_country") or "").strip()
    raw_exporter_country = str(value("exporter_country") or "").strip()
    importer_country, importer_country_conf, importer_country_status, importer_country_reason = clean_country_name(raw_importer_country, approved_countries)
    exporter_country, exporter_country_conf, exporter_country_status, exporter_country_reason = clean_country_name(raw_exporter_country, approved_countries)
    
    data_status = "Clean"
    if (
        product_status != "Approved"
        or importer_status != "Approved"
        or exporter_status != "Approved"
        or importer_country_status != "Approved"
        or exporter_country_status != "Approved"
        or standard_product == "Other / Review Required"
        or quantity_status != "Valid KG"
        or not price
    ):
        data_status = "Needs Manual Review"
    duplicate_key = "|".join(
        [
            shipment_date.lower(),
            simple_key(product_raw),
            simple_key(importer_raw),
            simple_key(exporter_raw),
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
        "raw_importer_country": raw_importer_country,
        "importer_country": importer_country,
        "importer_country_confidence": importer_country_conf,
        "importer_country_status": importer_country_status,
        "importer_country_reason": importer_country_reason,
        "importer_port": str(value("importer_port")).strip(),
        "raw_exporter_name": exporter_raw,
        "standard_exporter_name": exporter_standard,
        "exporter_confidence": exporter_confidence,
        "exporter_status": exporter_status,
        "exporter_reason": exporter_reason,
        "raw_exporter_country": raw_exporter_country,
        "exporter_country": exporter_country,
        "exporter_country_confidence": exporter_country_conf,
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
    direct = approved_companies.get(simple_key(raw_name)) or approved_companies.get(matching_company_key(raw_name))
    if direct:
        return direct, 1.0, "Approved", "Approved company mapping from Cleaning Review."
    return normalize_company(raw_name)


def approved_product_map(conn):
    rows = conn.execute(
        """
        select raw_product_description, approved_standard_product
        from product_mappings
        where status = 'Approved' and coalesce(approved_standard_product, '') != ''
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
    return mapping


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
    pending_product_mappings = conn.execute(
        "select count(*) from product_mappings where status = 'Pending'"
    ).fetchone()[0]
    pending_company_mappings = conn.execute(
        "select count(*) from company_mappings where status = 'Pending'"
    ).fetchone()[0]
    country_mappings_applied = conn.execute(
        "select count(*) from country_mappings where status = 'Approved' and coalesce(approved_standard_country_name, '') != ''"
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
            sum(case when standard_product != 'Other / Review Required' then 1 else 0 end) as clean_product_records,
            sum(case when standard_product = 'Other / Review Required' then 1 else 0 end) as review_required_records,
            count(distinct raw_product_description) as unique_raw_products,
            count(distinct standard_importer_name) as unique_importers,
            count(distinct standard_exporter_name) as unique_exporters,
            count(distinct importer_country) as unique_countries,
            sum(case when (upper(standard_exporter_name) like '%SHODHANA%' or upper(standard_exporter_name) like '%JAI LARA%') then 1 else 0 end) as shodhana_supplied_records,
            sum(case when (upper(standard_exporter_name) not like '%SHODHANA%' and upper(standard_exporter_name) not like '%JAI LARA%') then 1 else 0 end) as competitor_supplied_records,
            sum(case when quantity_kg is not null then 1 else 0 end) as valid_kg_records,
            sum(case when quantity_kg is null then 1 else 0 end) as invalid_qty_records,
            sum(case when price_per_kg is not null then 1 else 0 end) as price_records,
            sum(case when value_usd = 0 or quantity_kg is null then 1 else 0 end) as missing_value_or_quantity_records,
            sum(case when data_status != 'Clean' then 1 else 0 end) as manual_review_records,
            sum(coalesce(quantity_kg, 0)) as total_quantity_kg,
            sum(coalesce(value_usd, 0)) as total_value_usd,
            sum(case when price_per_kg is not null then coalesce(quantity_kg, 0) else 0 end) as priced_quantity_kg,
            sum(case when price_per_kg is not null then coalesce(value_usd, 0) else 0 end) as priced_value_usd
        from clean_trade_records
        {where}
        """,
        params,
    ).fetchone()
    stats = dict(row)
    total_qty = stats.get("total_quantity_kg") or 0
    total_value = stats.get("total_value_usd") or 0
    priced_qty = stats.pop("priced_quantity_kg", 0) or 0
    priced_value = stats.pop("priced_value_usd", 0) or 0
    stats["avg_price_per_kg"] = round(priced_value / priced_qty, 2) if priced_qty else 0
    stats["total_quantity_kg"] = round(total_qty, 4)
    stats["total_value_usd"] = round(total_value, 2)
    latest_upload = conn.execute(
        "select row_count, clean_count, duplicate_count from uploaded_files order by id desc limit 1"
    ).fetchone()
    stats["total_raw_records"] = latest_upload["row_count"] if latest_upload else 0
    stats["duplicates_removed"] = latest_upload["duplicate_count"] if latest_upload else 0
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
                 when sum(case when price_per_kg is not null then coalesce(quantity_kg, 0) else 0 end) > 0
                 then sum(case when price_per_kg is not null then coalesce(value_usd, 0) else 0 end) /
                      sum(case when price_per_kg is not null then coalesce(quantity_kg, 0) else 0 end)
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
    where, params = analytics_where(filters, extra_clauses=["price_per_kg is not null"])
    rows = conn.execute(
        f"""
        select month_key as label,
               case
                 when sum(case when price_per_kg is not null then coalesce(quantity_kg, 0) else 0 end) > 0
                 then sum(case when price_per_kg is not null then coalesce(value_usd, 0) else 0 end) /
                      sum(case when price_per_kg is not null then coalesce(quantity_kg, 0) else 0 end)
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
    where, params = analytics_where(
        filters,
        extra_clauses=[
            "upper(standard_exporter_name) not like '%SHODHANA%'",
            "upper(standard_exporter_name) not like '%JAI LARA%'",
        ],
    )
    rows = conn.execute(
        f"""
        select
            standard_exporter_name as exporter_name,
            standard_product as product_category,
            group_concat(distinct importer_country) as countries_supplied,
            sum(coalesce(quantity_kg, 0)) as total_quantity_kg,
            sum(coalesce(value_usd, 0)) as total_value_usd,
            case
              when sum(case when price_per_kg is not null then coalesce(quantity_kg, 0) else 0 end) > 0
              then sum(case when price_per_kg is not null then coalesce(value_usd, 0) else 0 end) /
                   sum(case when price_per_kg is not null then coalesce(quantity_kg, 0) else 0 end)
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
    where, params = analytics_where(
        filters,
        extra_clauses=["quantity_kg is not null", "quantity_kg > 0", "value_usd > 0", "price_per_kg is not null"],
    )
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
    manual_review = item.get("manual_review_rows") or 0
    generic_customer = item.get("customer_identification_status") != "Identified Customer"

    if quantity_threshold and qty >= quantity_threshold:
        score += 30
        reasons.append("High quantity buyer")

    if recent_threshold and last_ordinal >= recent_threshold:
        score += 25
        reasons.append("Recent purchase activity")

    if item.get("has_competitor_supplier"):
        score += 20
        reasons.append("Buying from competitor")

    if item.get("has_shodhana_supplier") and item.get("has_competitor_supplier"):
        score += 10
        reasons.append("Customer also has Shodhana linkage")

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

    if manual_review:
        score -= min(20, manual_review * 2)
        reasons.append("Golden data needs approval")

    if generic_customer:
        score = min(score, 35)
        reasons.append("Actual buyer must be identified")

    score = max(0, min(100, int(score)))
    if score >= 75:
        tier = "High Opportunity"
    elif score >= 45:
        tier = "Medium Opportunity"
    else:
        tier = "Low Opportunity"

    if generic_customer:
        action = "Identify the real buyer before outreach; keep this row for market sizing but do not pitch the generic consignee."
    elif item.get("has_shodhana_supplier") and item.get("has_competitor_supplier"):
        action = "Cross-sell or defend the account: customer has Shodhana linkage but also buys from competitors."
    elif item.get("has_shodhana_supplier"):
        action = "Retention and expansion: protect the account and check for adjacent Duloxetine needs."
    elif invalid_qty or review_product or manual_review:
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
            sum(coalesce(value_usd, 0)) as total_value_usd,
            sum(case when price_per_kg is not null then coalesce(quantity_kg, 0) else 0 end) as priced_quantity_kg,
            sum(case when price_per_kg is not null then coalesce(value_usd, 0) else 0 end) as priced_value_usd
        from clean_trade_records
        """
    ).fetchone()
    stats = dict(row)
    total_qty = stats.get("total_quantity_kg") or 0
    total_value = stats.get("total_value_usd") or 0
    priced_qty = stats.pop("priced_quantity_kg", 0) or 0
    priced_value = stats.pop("priced_value_usd", 0) or 0
    stats["avg_price_per_kg"] = round(priced_value / priced_qty, 2) if priced_qty else 0
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
    for row in rows:
        conn.execute(
            """
            insert into product_mappings(
                raw_product_description, suggested_standard_product, confidence_score,
                reason_for_suggestion, approved_standard_product, status, created_at
            ) values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["raw_product_description"],
                row["suggested_standard_product"],
                row["confidence_score"],
                row.get("reason_for_suggestion", ""),
                row["approved_standard_product"],
                row["status"],
                int(time.time()),
            ),
        )


def _replace_company_mappings(conn, rows):
    for row in rows:
        conn.execute(
            """
            insert into company_mappings(
                raw_company_name, suggested_standard_company_name, confidence_score,
                reason_for_suggestion, source_roles, approved_standard_company_name, status, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["raw_company_name"],
                row["suggested_standard_company_name"],
                row["confidence_score"],
                row.get("reason_for_suggestion", ""),
                row.get("source_roles", ""),
                row["approved_standard_company_name"],
                row["status"],
                int(time.time()),
            ),
        )


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
        clauses.append("(upper(standard_exporter_name) like '%SHODHANA%' or upper(standard_exporter_name) like '%JAI LARA%')")
    elif status == "Competitor Supply":
        clauses.append("(upper(standard_exporter_name) not like '%SHODHANA%' and upper(standard_exporter_name) not like '%JAI LARA%')")

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
    has_shodhana = any(is_shodhana_supplier(supplier) for supplier in suppliers)
    has_competitor = any(not is_shodhana_supplier(supplier) for supplier in suppliers)
    if has_competitor:
        return "Competitor Supply"
    if has_shodhana:
        return "Existing Shodhana Supply"
    return "Competitor Supply"


def is_shodhana_supplier(supplier):
    key = simple_key(supplier)
    return any(term in key for term in SHODHANA_SUPPLIER_TERMS)


def customer_identification_status(importer):
    key = simple_key(importer)
    return "Needs Buyer Identification" if key in GENERIC_COMPANY_KEYS else "Identified Customer"


def current_supplier_from_pairs(pairs, suppliers):
    parsed = []
    for pair in pairs:
        supplier, _, date = pair.partition("@@")
        parsed.append((date, supplier))
    parsed.sort(key=lambda item: _date_sort_key(item[0]), reverse=True)
    ordered = []
    for _, supplier in parsed:
        if supplier and supplier not in ordered:
            ordered.append(supplier)
    for supplier in suppliers:
        if supplier and supplier not in ordered:
            ordered.append(supplier)
    label = ", ".join(ordered[:3])
    if len(ordered) > 3:
        label += f" +{len(ordered) - 3}"
    return label


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
            "customer_identification_status": row["customer_identification_status"],
            "manual_review_rows": row["manual_review_rows"],
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


def get_settings():
    with connect() as conn:
        row = conn.execute("select * from settings where id = 1").fetchone()
        if row:
            return dict(row)
        return {
            "chemdoze_email": "nbd@shodhana.com",
            "chemdoze_password": "H56P9EcGNr",
            "auto_sync_enabled": 0,
            "auto_sync_interval_hours": 24,
            "last_sync_timestamp": None,
            "sync_query": "Duloxetine",
            "sync_from_date": "01/01/2020",
            "sync_to_date": "28/02/2026",
            "sync_status": "Idle"
        }


def update_settings(email, password, auto_sync_enabled, auto_sync_interval_hours, sync_query, sync_from_date, sync_to_date, sync_status=None):
    with connect() as conn:
        if sync_status is not None:
            conn.execute(
                """
                update settings
                set chemdoze_email = ?, chemdoze_password = ?, auto_sync_enabled = ?, auto_sync_interval_hours = ?,
                    sync_query = ?, sync_from_date = ?, sync_to_date = ?, sync_status = ?
                where id = 1
                """,
                (email, password, int(auto_sync_enabled), int(auto_sync_interval_hours), sync_query, sync_from_date, sync_to_date, sync_status)
            )
        else:
            conn.execute(
                """
                update settings
                set chemdoze_email = ?, chemdoze_password = ?, auto_sync_enabled = ?, auto_sync_interval_hours = ?,
                    sync_query = ?, sync_from_date = ?, sync_to_date = ?
                where id = 1
                """,
                (email, password, int(auto_sync_enabled), int(auto_sync_interval_hours), sync_query, sync_from_date, sync_to_date)
            )
        row = conn.execute("select * from settings where id = 1").fetchone()
        return dict(row)


def update_sync_timestamp_status(timestamp, status):
    with connect() as conn:
        conn.execute(
            """
            update settings
            set last_sync_timestamp = ?, sync_status = ?
            where id = 1
            """,
            (timestamp, status)
        )


def log_sent_email(opportunity_id, recipient_email, subject, body, status):
    with connect() as conn:
        conn.execute(
            """
            insert into sent_emails(opportunity_id, recipient_email, subject, body, status, sent_at)
            values (?, ?, ?, ?, ?, ?)
            """,
            (opportunity_id, recipient_email, subject, body, status, int(time.time()))
        )


def get_sent_emails(opportunity_id=None):
    with connect() as conn:
        if opportunity_id:
            rows = conn.execute(
                "select * from sent_emails where opportunity_id = ? order by sent_at desc",
                (opportunity_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "select * from sent_emails order by sent_at desc"
            ).fetchall()
        return [dict(r) for r in rows]


def approved_country_map(conn):
    rows = conn.execute(
        """
        select raw_country_name, approved_standard_country_name
        from country_mappings
        where status = 'Approved' and coalesce(approved_standard_country_name, '') != ''
        """
    ).fetchall()
    mapping = {}
    for row in rows:
        mapping[simple_key(row["raw_country_name"])] = row["approved_standard_country_name"]
    return mapping


def _replace_country_mappings(conn, rows):
    for row in rows:
        conn.execute(
            """
            insert into country_mappings(
                raw_country_name, suggested_standard_country_name, confidence_score,
                reason_for_suggestion, source_roles, approved_standard_country_name, status, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["raw_country_name"],
                row["suggested_standard_country_name"],
                row["confidence_score"],
                row.get("reason_for_suggestion", ""),
                row.get("source_roles", ""),
                row["approved_standard_country_name"],
                row["status"],
                int(time.time()),
            ),
        )


def _merge_country_mapping(mapping_rows, role, raw_name, standard_name, confidence, status, reason):
    key = simple_key(raw_name)
    if not key:
        return
    if key not in mapping_rows:
        mapping_rows[key] = {
            "raw_country_name": raw_name,
            "suggested_standard_country_name": standard_name,
            "confidence_score": confidence,
            "reason_for_suggestion": reason,
            "source_roles": role,
            "approved_standard_country_name": standard_name if status == "Approved" else "",
            "status": status,
        }
        return
    current = mapping_rows[key]
    roles = set(filter(None, [part.strip() for part in current.get("source_roles", "").split(",")]))
    roles.add(role)
    current["source_roles"] = ", ".join(sorted(roles))
    if confidence > current.get("confidence_score", 0):
        current["suggested_standard_country_name"] = standard_name
        current["confidence_score"] = confidence
        current["reason_for_suggestion"] = reason
        current["approved_standard_country_name"] = standard_name if status == "Approved" else current.get("approved_standard_country_name", "")
        current["status"] = status if current["status"] != "Approved" else current["status"]
