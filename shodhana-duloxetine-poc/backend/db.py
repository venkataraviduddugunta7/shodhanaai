import json
import os
import sqlite3
import threading
import time

from .config import DB_PATH, ensure_dirs

SQLITE_TIMEOUT_SECONDS = int(os.environ.get("SHODHANA_SQLITE_TIMEOUT_SECONDS", "30"))
_WAL_LOCK = threading.Lock()
_WAL_ENABLED = False


def connect():
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, timeout=SQLITE_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    conn.execute(f"pragma busy_timeout = {SQLITE_TIMEOUT_SECONDS * 1000}")
    conn.execute("pragma foreign_keys = on")
    conn.execute("pragma synchronous = normal")
    _enable_wal(conn)
    return conn


def _enable_wal(conn):
    global _WAL_ENABLED
    if _WAL_ENABLED:
        return
    with _WAL_LOCK:
        if _WAL_ENABLED:
            return
        conn.execute("pragma journal_mode = wal")
        _WAL_ENABLED = True


def init_db():
    with connect() as conn:
        conn.executescript(
            """
            create table if not exists uploaded_files (
                id integer primary key autoincrement,
                original_name text not null,
                stored_path text not null,
                source_type text not null,
                row_count integer not null,
                clean_count integer not null,
                duplicate_count integer not null,
                quality_json text not null,
                column_map_json text not null,
                imported_at integer not null
            );

            create table if not exists raw_trade_records (
                id integer primary key autoincrement,
                upload_id integer not null,
                row_number integer not null,
                raw_json text not null
            );

            create table if not exists clean_trade_records (
                id integer primary key autoincrement,
                upload_id integer not null,
                raw_record_id integer,
                shipment_date text,
                year integer,
                month_key text,
                hs_code text,
                raw_product_description text,
                standard_product text,
                product_confidence real,
                product_status text,
                raw_importer_name text,
                standard_importer_name text,
                importer_confidence real,
                importer_status text,
                importer_country text,
                importer_port text,
                raw_exporter_name text,
                standard_exporter_name text,
                exporter_confidence real,
                exporter_status text,
                exporter_country text,
                exporter_port text,
                market_category text,
                quantity real,
                units text,
                quantity_kg real,
                quantity_status text,
                value_usd real,
                price_per_kg real,
                invoice_currency text,
                duplicate_key text,
                data_status text,
                created_at integer not null
            );

            create table if not exists product_mappings (
                id integer primary key autoincrement,
                raw_product_description text not null,
                suggested_standard_product text not null,
                confidence_score real not null,
                reason_for_suggestion text,
                approved_standard_product text,
                status text not null,
                is_master integer not null default 0,
                created_at integer not null
            );

            create table if not exists company_mappings (
                id integer primary key autoincrement,
                raw_company_name text not null,
                suggested_standard_company_name text not null,
                confidence_score real not null,
                reason_for_suggestion text,
                source_roles text,
                approved_standard_company_name text,
                status text not null,
                is_master integer not null default 0,
                created_at integer not null
            );

            create table if not exists country_mappings (
                id integer primary key autoincrement,
                raw_country_name text not null,
                suggested_standard_country_name text not null,
                confidence_score real not null,
                reason_for_suggestion text,
                source_roles text,
                approved_standard_country_name text,
                status text not null,
                is_master integer not null default 0,
                created_at integer not null
            );

            create table if not exists generated_pitches (
                id integer primary key autoincrement,
                opportunity_key text not null,
                action_type text not null,
                content text not null,
                opportunity_id text,
                customer_summary text,
                buying_pattern text,
                price_strategy text,
                email_draft_formal text,
                email_draft_short text,
                email_draft_relationship text,
                ppt_outline_json text,
                follow_up_plan text,
                created_at integer not null
            );
            """
        )
        ensure_column(conn, "product_mappings", "reason_for_suggestion", "text")
        ensure_column(conn, "company_mappings", "reason_for_suggestion", "text")
        ensure_column(conn, "company_mappings", "source_roles", "text")
        ensure_column(conn, "country_mappings", "reason_for_suggestion", "text")
        ensure_column(conn, "country_mappings", "source_roles", "text")
        ensure_column(conn, "product_mappings", "is_master", "integer not null default 0")
        ensure_column(conn, "company_mappings", "is_master", "integer not null default 0")
        ensure_column(conn, "country_mappings", "is_master", "integer not null default 0")
        ensure_column(conn, "generated_pitches", "opportunity_id", "text")
        ensure_column(conn, "generated_pitches", "customer_summary", "text")
        ensure_column(conn, "generated_pitches", "buying_pattern", "text")
        ensure_column(conn, "generated_pitches", "price_strategy", "text")
        ensure_column(conn, "generated_pitches", "email_draft_formal", "text")
        ensure_column(conn, "generated_pitches", "email_draft_short", "text")
        ensure_column(conn, "generated_pitches", "email_draft_relationship", "text")
        ensure_column(conn, "generated_pitches", "ppt_outline_json", "text")
        ensure_column(conn, "generated_pitches", "follow_up_plan", "text")


def ensure_column(conn, table, column, definition):
    existing = {row["name"] for row in conn.execute(f"pragma table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"alter table {table} add column {column} {definition}")


def reset_trade_data(conn):
    conn.execute("delete from generated_pitches")
    conn.execute("delete from clean_trade_records")
    conn.execute("delete from raw_trade_records")
    conn.execute("delete from uploaded_files")


def insert_upload(conn, original_name, stored_path, source_type, row_count, clean_count, duplicates, quality, column_map):
    cursor = conn.execute(
        """
        insert into uploaded_files(
            original_name, stored_path, source_type, row_count, clean_count,
            duplicate_count, quality_json, column_map_json, imported_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            original_name,
            stored_path,
            source_type,
            row_count,
            clean_count,
            duplicates,
            json.dumps(quality),
            json.dumps(column_map),
            int(time.time()),
        ),
    )
    return cursor.lastrowid


def rows_to_dicts(rows):
    return [dict(row) for row in rows]
