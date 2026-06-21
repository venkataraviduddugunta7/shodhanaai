#!/usr/bin/env python3
import json
import mimetypes
import sys
import time
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from backend.ai_service import generate_ai_action
from backend.chemdoze_import import download_chemdoze_excel
from backend.config import WEB_DIR, ensure_dirs
from backend.db import init_db
from backend.engine import (
    bulk_update_mappings,
    cleaning_review,
    clean_records_for_export,
    dashboard,
    dashboard_summary_rows,
    generated_pitch,
    import_mapping_file,
    import_sample,
    import_trade_file,
    latest_upload,
    mappings,
    opportunity_detail,
    opportunities,
    opportunities_for_export,
    rerun_cleaning,
    review_records,
    rows_to_csv_bytes,
    rows_to_xlsx_bytes,
    save_uploaded_file,
    seed_files,
    update_mapping,
    get_settings,
    update_settings,
    log_sent_email,
    get_sent_emails,
    run_agentic_automap,
)

from backend.growth_advisor import generate_growth_insights
from backend.ppt_generator import generate_pitch_pptx



class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if (
            parsed.path in {"/", "/cleaning-review", "/dashboard", "/opportunities", "/pitch", "/products", "/companies", "/countries", "/advisor"}
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
        if parsed.path == "/api/settings":
            self.send_json(get_settings())
            return
        if parsed.path == "/api/sent-emails":
            query = parse_qs(parsed.query)
            opp_id = query.get("opportunity_id", [""])[0] or None
            self.send_json({"rows": get_sent_emails(opp_id)})
            return
        if parsed.path == "/api/growth-insights":
            self.send_json(generate_growth_insights(self.query_filters(parsed.query)))
            return
        if parsed.path == "/api/export/pitch-deck":
            query = parse_qs(parsed.query)
            opp_id = query.get("opportunity_id", [""])[0]
            try:
                opp_data = opportunity_detail(opp_id)
                pptx_buffer, success = generate_pitch_pptx(opp_data)
                cust_name = opp_data.get('opportunity', {}).get('importer', 'customer')
                clean_name = "".join(c if c.isalnum() else "_" for c in cust_name)
                filename = f"pitch_{clean_name}.pptx"
                self.send_binary(
                    pptx_buffer.getvalue(),
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    filename,
                )
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=500)
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
            if parsed.path == "/api/import-chemdoze":
                self.handle_chemdoze_import()
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
            if parsed.path == "/api/mapping-bulk-action":
                body = self.read_json()
                self.send_json(
                    bulk_update_mappings(
                        body.get("kind", ""),
                        float(body.get("min_confidence", 0.9)),
                    )
                )
                return
            if parsed.path == "/api/rerun-cleaning":
                self.send_json(rerun_cleaning())
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
            if parsed.path == "/api/settings":
                body = self.read_json()
                self.send_json(
                    update_settings(
                        email=body.get("chemdoze_email", ""),
                        password=body.get("chemdoze_password", ""),
                        auto_sync_enabled=body.get("auto_sync_enabled", 0),
                        auto_sync_interval_hours=body.get("auto_sync_interval_hours", 24),
                        sync_query=body.get("sync_query", "Duloxetine"),
                        sync_from_date=body.get("sync_from_date", "01/01/2020"),
                        sync_to_date=body.get("sync_to_date", "28/02/2026"),
                    )
                )
                return
            if parsed.path == "/api/send-email":
                body = self.read_json()
                log_sent_email(
                    opportunity_id=body.get("opportunity_id", ""),
                    recipient_email=body.get("recipient_email", ""),
                    subject=body.get("subject", ""),
                    body=body.get("body", ""),
                    status="Sent",
                )
                self.send_json({"success": True, "message": "Email sent and logged successfully."})
                return
            if parsed.path == "/api/import-downloads-file":
                source_path = Path("/Users/venkataraviaithinkers/Downloads/duloxetine_01_01_2020_to_01_01_2020-2.xlsx")
                if not source_path.exists():
                    raise FileNotFoundError("The file /Users/venkataraviaithinkers/Downloads/duloxetine_01_01_2020_to_01_01_2020-2.xlsx was not found in your Downloads folder.")
                result = import_trade_file(source_path, source_path.name, replace=True)
                self.send_json({"source_type": "downloads_file", "stored_path": str(source_path), **result})
                return
            if parsed.path == "/api/mappings/auto-map":
                result = run_agentic_automap()
                self.send_json({"success": True, **result})
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

    def handle_chemdoze_import(self):
        body = self.read_json()
        stored = download_chemdoze_excel(
            email=body.get("email", ""),
            password=body.get("password", ""),
            query=body.get("query", ""),
            from_date=body.get("from_date", ""),
            to_date=body.get("to_date", ""),
        )
        result = import_trade_file(stored, stored.name, replace=True)
        self.send_json({"source_type": "chemdoze", "stored_path": str(stored), **result})

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


def sync_worker():
    # Wait a few seconds for database initialization
    time.sleep(5)
    while True:
        try:
            settings = get_settings()
            if settings and settings.get("auto_sync_enabled"):
                interval_hours = settings.get("auto_sync_interval_hours") or 24
                last_sync = settings.get("last_sync_timestamp")
                current_time = int(time.time())
                
                # Check if it is time to sync (convert hours to seconds)
                should_sync = False
                if last_sync is None:
                    should_sync = True
                else:
                    time_elapsed = current_time - last_sync
                    if time_elapsed >= (interval_hours * 3600):
                        should_sync = True
                
                if should_sync:
                    from backend.engine import update_sync_timestamp_status
                    update_sync_timestamp_status(last_sync, "Syncing...")
                    print(f"[Sync Worker] Starting automated download from Chemdoze for {settings.get('sync_query')}...")
                    try:
                        stored = download_chemdoze_excel(
                            email=settings.get("chemdoze_email", ""),
                            password=settings.get("chemdoze_password", ""),
                            query=settings.get("sync_query", ""),
                            from_date=settings.get("sync_from_date", ""),
                            to_date=settings.get("sync_to_date", ""),
                        )
                        result = import_trade_file(stored, stored.name, replace=True)
                        update_sync_timestamp_status(int(time.time()), f"Success: Cleaned {result.get('clean_rows', 0)} rows")
                        print("[Sync Worker] Automated sync complete!")
                    except Exception as e:
                        print(f"[Sync Worker] Automated sync failed: {e}")
                        update_sync_timestamp_status(last_sync, f"Failed: {str(e)[:100]}")
        except Exception as e:
            print(f"[Sync Worker] Error in worker loop: {e}")
        # Sleep for 60 seconds before checking again
        time.sleep(60)


def main():
    ensure_dirs()
    init_db()
    seed_files()
    
    # Start auto-sync worker thread
    import threading
    t = threading.Thread(target=sync_worker, daemon=True)
    t.start()
    
    import os
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", 8010))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Shodhana AI Duloxetine POC running at http://{host}:{port}")
    print("Upload the provided Excel or click Import Sample File in the app.")
    server.serve_forever()


if __name__ == "__main__":
    main()
