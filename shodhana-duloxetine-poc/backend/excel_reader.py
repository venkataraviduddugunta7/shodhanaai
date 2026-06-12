import csv
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


def read_table(path):
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        return read_xlsx(path)
    return read_csv(path)


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    path = Path(path)
    if not rows:
        path.write_text("", encoding="utf-8")
        return 0
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def read_xlsx(path):
    matrix = []
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        shared_strings = _shared_strings(archive, names)
        sheet_name = _first_sheet_name(archive, names)
        if not sheet_name:
            return []
        root = ET.fromstring(archive.read(sheet_name))
        for row_node in root.findall(".//{*}row"):
            values = []
            for cell in row_node.findall("{*}c"):
                index = _column_index(cell.attrib.get("r", ""))
                while len(values) <= index:
                    values.append("")
                values[index] = _cell_value(cell, shared_strings)
            if any(str(value).strip() for value in values):
                matrix.append(values)
    if not matrix:
        return []
    headers = [str(value).strip() or f"column_{index + 1}" for index, value in enumerate(matrix[0])]
    rows = []
    for values in matrix[1:]:
        row = {}
        for index, header in enumerate(headers):
            row[header] = values[index] if index < len(values) else ""
        if any(str(value).strip() for value in row.values()):
            rows.append(row)
    return rows


def _shared_strings(archive, names):
    if "xl/sharedStrings.xml" not in names:
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(item.itertext()) for item in root.findall(".//{*}si")]


def _first_sheet_name(archive, names):
    preferred = "xl/worksheets/sheet1.xml"
    if preferred in names:
        return preferred
    candidates = sorted(name for name in names if name.startswith("xl/worksheets/sheet"))
    return candidates[0] if candidates else ""


def _column_index(cell_ref):
    letters = re.sub(r"[^A-Z]", "", str(cell_ref or "").upper())
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return max(index - 1, 0)


def _cell_value(cell, shared_strings):
    cell_type = cell.attrib.get("t")
    value_node = cell.find("{*}v")
    if cell_type == "s" and value_node is not None:
        raw = value_node.text or "0"
        return shared_strings[int(raw)] if raw.isdigit() and int(raw) < len(shared_strings) else ""
    if cell_type == "inlineStr":
        return "".join(cell.itertext()).strip()
    return value_node.text if value_node is not None else ""

