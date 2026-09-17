"""Internal workbook baseline format; no database schema or timestamp authority."""

import hashlib
import json


BASELINE_SHEET = "_个人字段基线"
BASELINE_FORMAT = "scientific-reading-user-fields-v1"
BASELINE_COLUMNS = ("paper_id", "personal_thoughts", "understanding_level", "user_notes")


def text_value(value):
    return "" if value is None else str(value)


def _digest(records):
    payload = json.dumps(sorted(records.items()), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_baseline(workbook, records):
    sheet = workbook.create_sheet(BASELINE_SHEET)
    sheet.append(BASELINE_COLUMNS)
    for paper_id, values in records.items():
        if any(len(value) > 32767 for value in (paper_id, *values)):
            raise ValueError("xlsx_user_field_too_long")
        sheet.append((paper_id, *values))
        # Literal '=' and error-looking notes must remain strings, not formulas.
        for cell in sheet[sheet.max_row]:
            cell.data_type = "s"
    sheet.sheet_state = "veryHidden"
    workbook["_身份"]["C1"] = BASELINE_FORMAT
    workbook["_身份"]["D1"] = _digest(records)


def read_baseline(workbook, paper_ids):
    identity = workbook["_身份"]
    marker, checksum = identity["C1"].value, identity["D1"].value
    if BASELINE_SHEET not in workbook.sheetnames and marker is None and checksum is None:
        return None  # Legacy: equality with SQLite is the only safe import.
    if marker != BASELINE_FORMAT or BASELINE_SHEET not in workbook.sheetnames:
        raise ValueError("baseline_format_or_sheet_missing")
    sheet = workbook[BASELINE_SHEET]
    if tuple(cell.value for cell in sheet[1]) != BASELINE_COLUMNS:
        raise ValueError("baseline_columns_invalid")
    records = {}
    for row in sheet.iter_rows(min_row=2):
        paper_id = row[0].value
        if not isinstance(paper_id, str) or not paper_id or paper_id in records:
            raise ValueError("baseline_identity_invalid_or_duplicate")
        if any(cell.data_type == "f" or (cell.value is not None and not isinstance(cell.value, str)) for cell in row):
            raise ValueError("baseline_value_invalid")
        records[paper_id] = tuple(text_value(cell.value) for cell in row[1:])
    if set(records) != set(paper_ids):
        raise ValueError("baseline_identity_set_mismatch")
    if checksum != _digest(records):
        raise ValueError("baseline_checksum_mismatch")
    return records
