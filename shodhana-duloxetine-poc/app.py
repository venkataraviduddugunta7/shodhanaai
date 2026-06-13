#!/usr/bin/env python3
import json
import mimetypes
import os
import sys
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from backend.ai_service import generate_ai_action
from backend.config import WEB_DIR, ensure_dirs
from backend.db import init_db
from backend.engine import (
    cleaning_review,
    clean_records_for_export,
    dashboard,
    dashboard_summary_rows,
    generated_pitch,
    import_mapping_file,
    import_sample,
    import_trade_file,
    latest_upload,
    mapping_groups,
    mappings,
    opportunity_detail,
    opportunities,
    opportunities_for_export,
    rerun_cleaning,
    review_records,
    rows_to_csv_bytes,
    rows_to_xlsx_bytes,
    save_uploaded_file,
    seed_database_mappings,
    seed_files,
    sync_master_mappings_to_seed,
    update_mapping_group,
    update_mapping,
)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if (
            parsed.path in {"/", "/cleaning-review", "/dashboard", "/opportunities", "/countries", "/pitch"}
            or parsed.path.startswith("/opportunities/")
            or parsed.path.startswith("/pitch/")
        ):
            self.serve_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path.startswith("/web/"):
            requested = WEB_DIR / parsed.path.replace("/web/", "", 1)
            if requested.exists() and requested.is_file():
                self.serve_file(requested)
                return
        if parsed.path == "/api/dashboard":
            self.send_json(dashboard(self.query_filters(parsed.query)))
            return
        if parsed.path == "/api/cleaning-review":
            self.send_json(cleaning_review())
            return
        if parsed.path == "/api/review-records":
            query = parse_qs(parsed.query)
            filter_name = query.get("filter", ["pending"])[0]
            self.send_json({"rows": review_records(filter_name)})
            return
        if parsed.path == "/api/latest-upload":
            self.send_json(latest_upload())
            return
        if parsed.path == "/api/opportunities":
            query = parse_qs(parsed.query)
            filters = {key: values[0] for key, values in query.items() if values and key != "limit"}
            limit = int(query.get("limit", ["100"])[0])
            self.send_json({"rows": opportunities(filters=filters, limit=limit)})
            return
        if parsed.path == "/api/opportunity-detail":
            query = parse_qs(parsed.query)
            try:
                self.send_json(opportunity_detail(query.get("id", [""])[0]))
            except ValueError as exc:
                self.send_json({"error": str(exc)}, status=404)
            return
        if parsed.path == "/api/pitch":
            query = parse_qs(parsed.query)
            try:
                self.send_json(generated_pitch(query.get("id", [""])[0], regenerate=False))
            except ValueError as exc:
                self.send_json({"error": str(exc)}, status=404)
            return
        if parsed.path == "/api/export/cleaned.xlsx":
            rows = clean_records_for_export(self.query_filters(parsed.query))
            self.send_binary(
                rows_to_xlsx_bytes("Cleaned Data", rows),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "shodhana_cleaned_data.xlsx",
            )
            return
        if parsed.path == "/api/export/opportunities.xlsx":
            rows = opportunities_for_export(self.query_filters(parsed.query))
            self.send_binary(
                rows_to_xlsx_bytes("Opportunities", rows),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "shodhana_opportunities.xlsx",
            )
            return
        if parsed.path == "/api/export/dashboard-summary.csv":
            rows = dashboard_summary_rows(self.query_filters(parsed.query))
            self.send_binary(rows_to_csv_bytes(rows), "text/csv; charset=utf-8", "shodhana_dashboard_summary.csv")
            return
        if parsed.path == "/api/mappings/products":
            self.send_json({"rows": mappings("products")})
            return
        if parsed.path == "/api/mappings/companies":
            self.send_json({"rows": mappings("companies")})
            return
        if parsed.path == "/api/mappings/countries":
            self.send_json({"rows": mappings("countries")})
            return
        if parsed.path == "/api/mapping-groups":
            self.send_json(mapping_groups())
            return
        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/import-sample":
                self.send_json(import_sample())
                return
            if parsed.path == "/api/upload":
                self.handle_upload()
                return
            if parsed.path == "/api/mapping-action":
                body = self.read_json()
                self.send_json(
                    update_mapping(
                        body.get("kind", ""),
                        int(body.get("id", 0)),
                        body.get("action", ""),
                        body.get("value", ""),
                    )
                )
                return
            if parsed.path == "/api/mapping-group-action":
                body = self.read_json()
                self.send_json(
                    update_mapping_group(
                        body.get("kind", ""),
                        body.get("ids", []),
                        body.get("action", ""),
                        body.get("value", ""),
                        body.get("excluded_ids", []),
                    )
                )
                return
            if parsed.path == "/api/rerun-cleaning":
                self.send_json(rerun_cleaning())
                return
            if parsed.path == "/api/sync-master-mappings":
                self.send_json(sync_master_mappings_to_seed())
                return
            if parsed.path == "/api/ai-action":
                body = self.read_json()
                self.send_json({"content": generate_ai_action(body.get("action", "pitch"), body.get("opportunity", {}))})
                return
            if parsed.path == "/api/pitch/regenerate":
                body = self.read_json()
                try:
                    self.send_json(generated_pitch(body.get("id", ""), regenerate=True))
                except ValueError as exc:
                    self.send_json({"error": str(exc)}, status=404)
                return
            self.send_error(404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def handle_upload(self):
        fields, files = self.read_multipart()
        file_item = files.get("file")
        if file_item is None or not file_item.get("filename"):
            raise ValueError("Choose a CSV or Excel file first.")
        source_type = fields.get("source_type", "trade_data")
        stored = save_uploaded_file(file_item["filename"], file_item["data"])

        if source_type == "product_mapping":
            result = import_mapping_file("product_mapping", stored)
        elif source_type == "company_mapping":
            result = import_mapping_file("company_mapping", stored)
        elif source_type == "country_mapping":
            result = import_mapping_file("country_mapping", stored)
        else:
            result = import_trade_file(stored, file_item["filename"], replace=True)
        self.send_json({"source_type": source_type, "stored_path": str(stored), **result})

    def read_multipart(self):
        content_type = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        message_bytes = (
            f"Content-Type: {content_type}\r\n"
            "MIME-Version: 1.0\r\n\r\n"
        ).encode("utf-8") + body
        message = BytesParser(policy=policy.default).parsebytes(message_bytes)
        fields = {}
        files = {}
        for part in message.iter_parts():
            if part.get_content_disposition() != "form-data":
                continue
            name = part.get_param("name", header="content-disposition")
            filename = part.get_filename()
            payload = part.get_payload(decode=True) or b""
            if filename:
                files[name] = {"filename": filename, "data": payload}
            else:
                fields[name] = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        return fields, files

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def query_filters(self, query):
        parsed = parse_qs(query)
        return {key: values[0] for key, values in parsed.items() if values and key != "limit"}

    def serve_file(self, path, content_type=None):
        path = Path(path)
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        body = path.read_bytes()
        guessed = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", guessed)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload, status=200):
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_binary(self, body, content_type, filename):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args))


def main():
    ensure_dirs()
    init_db()
    seed_files()
    seed_database_mappings()
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8010"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Shodhana AI Duloxetine POC running at http://{host}:{port}")
    print("Upload the provided Excel or click Import Sample File in the app.")
    server.serve_forever()


if __name__ == "__main__":
    main()
