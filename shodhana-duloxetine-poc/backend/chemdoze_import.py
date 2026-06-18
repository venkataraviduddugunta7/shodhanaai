import json
import os
import re
import time
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

from .config import (
    CHEMDOZE_CHAPTERS,
    CHEMDOZE_DEFAULT_FROM_DATE,
    CHEMDOZE_DEFAULT_QUERY,
    CHEMDOZE_DEFAULT_TO_DATE,
    CHEMDOZE_DOWNLOAD_EXCEL_URL,
    CHEMDOZE_DOWNLOAD_FILE_URL,
    CHEMDOZE_DOWNLOAD_PROGRESS_URL,
    CHEMDOZE_LOGIN_URL,
    CHEMDOZE_SEARCH_URL,
    UPLOAD_DIR,
)


class ChemdozeClient:
    def __init__(self):
        self.cookies = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.csrf_token = ""

    def get_text(self, url):
        response = self.opener.open(self.request(url), timeout=60)
        body = response.read()
        return body.decode("utf-8", errors="replace"), response.geturl()

    def post_form(self, url, fields):
        body = urllib.parse.urlencode(fields, doseq=True).encode("utf-8")
        response = self.opener.open(
            self.request(
                url,
                data=body,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                    **({"X-CSRF-TOKEN": self.csrf_token} if self.csrf_token else {}),
                },
            ),
            timeout=120,
        )
        return response.read(), response.geturl(), response.headers

    def request(self, url, data=None, headers=None):
        default_headers = {
            "User-Agent": "Mozilla/5.0 ShodhanaGrowthEngine/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": CHEMDOZE_LOGIN_URL,
        }
        default_headers.update(headers or {})
        return urllib.request.Request(url, data=data, headers=default_headers)

    def login(self, email, password):
        login_html, _ = self.get_text(CHEMDOZE_LOGIN_URL)
        token = extract_csrf(login_html)
        self.csrf_token = token
        body = urllib.parse.urlencode({
            "_token": token,
            "email": email,
            "password": password,
        }).encode("utf-8")
        response = self.opener.open(
            self.request(
                CHEMDOZE_LOGIN_URL,
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": CHEMDOZE_LOGIN_URL},
            ),
            timeout=60,
        )
        html = response.read().decode("utf-8", errors="replace")
        if "credentials do not match" in html.lower() or response.geturl().endswith("/login"):
            raise ValueError("Chemdoze rejected the email/password.")

    def open_search(self, query, from_date, to_date):
        url = search_url(query, from_date, to_date)
        html, final_url = self.get_text(url)
        self.csrf_token = extract_csrf(html) or self.csrf_token
        if "downloadExcelBtn" not in html and "download-excel" not in html:
            raise ValueError("Chemdoze search loaded, but the Excel download control was not available.")
        return final_url

    def start_download(self, query, from_date, to_date):
        fields = [
            ("hs_type", ""),
            ("showCasNo", ""),
            ("isCurated", "0"),
            ("main_search", query),
            ("downloadfilter[mainSearch]", query),
            ("downloadfilter[fromDate]", from_date),
            ("downloadfilter[toDate]", to_date),
            ("downloadedPage", "0"),
        ]
        for chapter in CHEMDOZE_CHAPTERS:
            fields.append(("downloadfilter[chapters][]", chapter))
        self.post_form(CHEMDOZE_DOWNLOAD_EXCEL_URL, fields)

    def wait_for_download(self):
        for _ in range(120):
            response = self.opener.open(
                self.request(
                    CHEMDOZE_DOWNLOAD_PROGRESS_URL,
                    headers={
                        "Accept": "application/json",
                        "X-Requested-With": "XMLHttpRequest",
                        **({"X-CSRF-TOKEN": self.csrf_token} if self.csrf_token else {}),
                    },
                ),
                timeout=30,
            )
            payload = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
            if int(payload.get("progress") or 0) >= 100:
                return
            time.sleep(1)
        raise TimeoutError("Chemdoze export did not finish within 120 seconds.")

    def download_file(self, filename):
        url = CHEMDOZE_DOWNLOAD_FILE_URL + "?" + urllib.parse.urlencode({"showCasNo": "", "isCurated": ""})
        response = self.opener.open(
            self.request(
                url,
                headers={
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                    **({"X-CSRF-TOKEN": self.csrf_token} if self.csrf_token else {}),
                },
            ),
            timeout=60,
        )
        payload = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
        file_url = payload.get("fileUrl")
        if not file_url:
            raise ValueError("Chemdoze did not return a downloadable Excel URL.")
        file_url = urllib.parse.urljoin(CHEMDOZE_SEARCH_URL, file_url)
        excel_response = self.opener.open(self.request(file_url), timeout=120)
        data = excel_response.read()
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        stored = UPLOAD_DIR / filename
        stored.write_bytes(data)
        return stored


def download_chemdoze_excel(email="", password="", query="", from_date="", to_date=""):
    email = (email or os.getenv("CHEMDOZE_EMAIL") or "").strip()
    password = password or os.getenv("CHEMDOZE_PASSWORD") or ""
    query = (query or os.getenv("CHEMDOZE_PRODUCT_QUERY") or CHEMDOZE_DEFAULT_QUERY).strip()
    from_date = (from_date or os.getenv("CHEMDOZE_FROM_DATE") or CHEMDOZE_DEFAULT_FROM_DATE).strip()
    to_date = (to_date or os.getenv("CHEMDOZE_TO_DATE") or CHEMDOZE_DEFAULT_TO_DATE).strip()
    if not email or not password:
        raise ValueError("Enter Chemdoze email/password or set CHEMDOZE_EMAIL and CHEMDOZE_PASSWORD.")
    client = ChemdozeClient()
    client.login(email, password)
    client.open_search(query, from_date, to_date)
    client.start_download(query, from_date, to_date)
    client.wait_for_download()
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{query}_{from_date}_to_{to_date}.xlsx").replace("/", "_")
    return client.download_file(safe_name)


def search_url(query, from_date, to_date):
    params = [
        ("isCurated", "0"),
        ("isReloaded", "false"),
        ("main_search", query),
        ("from_date", from_date),
        ("to_date", to_date),
    ]
    for chapter in CHEMDOZE_CHAPTERS:
        params.append(("chapter_no[]", chapter))
    return CHEMDOZE_SEARCH_URL + "?" + urllib.parse.urlencode(params, doseq=True)


def extract_csrf(html):
    for pattern in [
        r"<meta[^>]+name=[\"']csrf-token[\"'][^>]+content=[\"']([^\"']+)[\"']",
        r"name=[\"']_token[\"'][^>]+value=[\"']([^\"']+)[\"']",
    ]:
        match = re.search(pattern, html or "", flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return ""
