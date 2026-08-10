"""
db.py
Database layer for the CBI NEFT/RTGS form-filling app.

Schema is intentionally kept identical (same tables, same field names/meanings)
to the original cbi_neft__rev0.accdb, with two fixes:
  - Real PRIMARY KEY / FOREIGN KEY constraints (the .accdb had none)
  - neft_id is AUTOINCREMENT instead of being manually assigned

No extra fields (customer ID, account type, e-mail, PAN, LEI) were added to
the database, per instructions. Those are printed as blank lines on the form.
"""

import sqlite3
import os
import csv
import shutil

DB_FILENAME = "neft_data.db"


def get_db_path():
    """
    Store the database next to the running app (works both as a .py script
    and as a frozen PyInstaller .exe).
    """
    import sys
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, DB_FILENAME)


def get_connection():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS dim_company (
    company_id          TEXT PRIMARY KEY,
    company_name        TEXT,
    company_bank_name   TEXT,
    company_bank_ac_no  TEXT,
    company_ifsc        TEXT,
    company_bank_branch TEXT,
    company_phone       TEXT,
    company_address     TEXT
);

CREATE TABLE IF NOT EXISTS dim_supplier (
    supplier_id         TEXT PRIMARY KEY,
    supplier_name       TEXT,
    supplier_bank       TEXT,
    supplier_bank_ac_no TEXT,
    supplier_ifsc       TEXT,
    supplier_branch     TEXT
);

CREATE TABLE IF NOT EXISTS fact_neft (
    neft_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    neft_date          TEXT NOT NULL,
    depositing_branch  TEXT,
    neft_amount        REAL NOT NULL,
    company_id         TEXT NOT NULL,
    supplier_id        TEXT NOT NULL,
    cheque_no          TEXT,
    printed            INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (company_id)  REFERENCES dim_company(company_id),
    FOREIGN KEY (supplier_id) REFERENCES dim_supplier(supplier_id)
);
"""


def init_db():
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Company CRUD
# ---------------------------------------------------------------------------

def list_companies():
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM dim_company ORDER BY company_name"
        ).fetchall()
    finally:
        conn.close()


def get_company(company_id):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM dim_company WHERE company_id = ?", (company_id,)
        ).fetchone()
    finally:
        conn.close()


def upsert_company(data):
    """data: dict with keys matching dim_company columns."""
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO dim_company
                (company_id, company_name, company_bank_name, company_bank_ac_no,
                 company_ifsc, company_bank_branch, company_phone, company_address)
            VALUES (:company_id, :company_name, :company_bank_name, :company_bank_ac_no,
                    :company_ifsc, :company_bank_branch, :company_phone, :company_address)
            ON CONFLICT(company_id) DO UPDATE SET
                company_name=excluded.company_name,
                company_bank_name=excluded.company_bank_name,
                company_bank_ac_no=excluded.company_bank_ac_no,
                company_ifsc=excluded.company_ifsc,
                company_bank_branch=excluded.company_bank_branch,
                company_phone=excluded.company_phone,
                company_address=excluded.company_address
            """,
            data,
        )
        conn.commit()
    finally:
        conn.close()


def delete_company(company_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM dim_company WHERE company_id = ?", (company_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Supplier CRUD
# ---------------------------------------------------------------------------

def list_suppliers():
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM dim_supplier ORDER BY supplier_name"
        ).fetchall()
    finally:
        conn.close()


def get_supplier(supplier_id):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM dim_supplier WHERE supplier_id = ?", (supplier_id,)
        ).fetchone()
    finally:
        conn.close()


def upsert_supplier(data):
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO dim_supplier
                (supplier_id, supplier_name, supplier_bank, supplier_bank_ac_no,
                 supplier_ifsc, supplier_branch)
            VALUES (:supplier_id, :supplier_name, :supplier_bank, :supplier_bank_ac_no,
                    :supplier_ifsc, :supplier_branch)
            ON CONFLICT(supplier_id) DO UPDATE SET
                supplier_name=excluded.supplier_name,
                supplier_bank=excluded.supplier_bank,
                supplier_bank_ac_no=excluded.supplier_bank_ac_no,
                supplier_ifsc=excluded.supplier_ifsc,
                supplier_branch=excluded.supplier_branch
            """,
            data,
        )
        conn.commit()
    finally:
        conn.close()


def delete_supplier(supplier_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM dim_supplier WHERE supplier_id = ?", (supplier_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# NEFT fact CRUD
# ---------------------------------------------------------------------------

def insert_neft(neft_date, depositing_branch, neft_amount, company_id, supplier_id, cheque_no):
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO fact_neft
                (neft_date, depositing_branch, neft_amount, company_id, supplier_id, cheque_no)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (neft_date, depositing_branch, neft_amount, company_id, supplier_id, cheque_no),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def mark_printed(neft_id):
    conn = get_connection()
    try:
        conn.execute("UPDATE fact_neft SET printed = 1 WHERE neft_id = ?", (neft_id,))
        conn.commit()
    finally:
        conn.close()


def get_neft_full(neft_id):
    """Return a NEFT row joined with company + supplier details, for printing."""
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT f.*,
                   c.company_name, c.company_bank_name, c.company_bank_ac_no,
                   c.company_ifsc, c.company_bank_branch, c.company_phone, c.company_address,
                   s.supplier_name, s.supplier_bank, s.supplier_bank_ac_no,
                   s.supplier_ifsc, s.supplier_branch
            FROM fact_neft f
            JOIN dim_company c ON c.company_id = f.company_id
            JOIN dim_supplier s ON s.supplier_id = f.supplier_id
            WHERE f.neft_id = ?
            """,
            (neft_id,),
        ).fetchone()
        return row
    finally:
        conn.close()


def list_history(search_text=None):
    conn = get_connection()
    try:
        if search_text:
            like = f"%{search_text}%"
            return conn.execute(
                """
                SELECT f.neft_id, f.neft_date, f.depositing_branch, f.neft_amount,
                       f.cheque_no, f.printed, c.company_name, s.supplier_name
                FROM fact_neft f
                JOIN dim_company c ON c.company_id = f.company_id
                JOIN dim_supplier s ON s.supplier_id = f.supplier_id
                WHERE c.company_name LIKE ? OR s.supplier_name LIKE ?
                   OR f.cheque_no LIKE ? OR f.depositing_branch LIKE ?
                ORDER BY f.neft_id DESC
                """,
                (like, like, like, like),
            ).fetchall()
        return conn.execute(
            """
            SELECT f.neft_id, f.neft_date, f.depositing_branch, f.neft_amount,
                   f.cheque_no, f.printed, c.company_name, s.supplier_name
            FROM fact_neft f
            JOIN dim_company c ON c.company_id = f.company_id
            JOIN dim_supplier s ON s.supplier_id = f.supplier_id
            ORDER BY f.neft_id DESC
            """
        ).fetchall()
    finally:
        conn.close()


def delete_neft(neft_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM fact_neft WHERE neft_id = ?", (neft_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Backup / Restore — full database file (recommended, exact fidelity)
# ---------------------------------------------------------------------------

def backup_database(dest_path):
    """Copy the whole SQLite file (all 3 tables, exactly as-is) to dest_path."""
    src = get_db_path()
    shutil.copy2(src, dest_path)
    return dest_path


def restore_database(src_path):
    """
    Replace the current database file with a previously backed-up one.
    The caller is responsible for warning the user this overwrites everything
    and for refreshing all open UI tabs afterwards.
    """
    dest = get_db_path()
    shutil.copy2(src_path, dest)
    return dest


# ---------------------------------------------------------------------------
# CSV Export — one table at a time, for opening in Excel / sharing / backup
# ---------------------------------------------------------------------------

COMPANY_COLUMNS = [
    "company_id", "company_name", "company_bank_name", "company_bank_ac_no",
    "company_ifsc", "company_bank_branch", "company_phone", "company_address",
]
SUPPLIER_COLUMNS = [
    "supplier_id", "supplier_name", "supplier_bank", "supplier_bank_ac_no",
    "supplier_ifsc", "supplier_branch",
]
NEFT_COLUMNS = [
    "neft_id", "neft_date", "depositing_branch", "neft_amount",
    "company_id", "supplier_id", "cheque_no", "printed", "created_at",
]


def _export_csv(path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row[col] if row[col] is not None else "" for col in columns])
    return len(rows)


def export_companies_csv(path):
    return _export_csv(path, COMPANY_COLUMNS, list_companies())


def export_suppliers_csv(path):
    return _export_csv(path, SUPPLIER_COLUMNS, list_suppliers())


def export_neft_csv(path):
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM fact_neft ORDER BY neft_id").fetchall()
    finally:
        conn.close()
    return _export_csv(path, NEFT_COLUMNS, rows)


# ---------------------------------------------------------------------------
# CSV Import — restores/merges master data and history from a CSV backup.
# Existing rows with matching IDs are updated (upsert); new IDs are added.
# Returns (success_count, list_of_error_strings) so the UI can report both.
# ---------------------------------------------------------------------------

def import_companies_csv(path):
    errors = []
    count = 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):  # row 1 = header
            try:
                data = {col: (row.get(col) or "").strip() for col in COMPANY_COLUMNS}
                if not data["company_id"]:
                    errors.append(f"Row {i}: missing company_id, skipped.")
                    continue
                upsert_company(data)
                count += 1
            except Exception as e:
                errors.append(f"Row {i}: {e}")
    return count, errors


def import_suppliers_csv(path):
    errors = []
    count = 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            try:
                data = {col: (row.get(col) or "").strip() for col in SUPPLIER_COLUMNS}
                if not data["supplier_id"]:
                    errors.append(f"Row {i}: missing supplier_id, skipped.")
                    continue
                upsert_supplier(data)
                count += 1
            except Exception as e:
                errors.append(f"Row {i}: {e}")
    return count, errors


def import_neft_csv(path):
    """
    Restores NEFT history rows, preserving their original neft_id so
    reprints/history stay consistent with a previous backup. Rows whose
    company_id / supplier_id no longer exist in the master tables are
    skipped (reported back) rather than silently dropped or crashing.
    """
    errors = []
    count = 0
    conn = get_connection()
    try:
        existing_companies = {r["company_id"] for r in list_companies()}
        existing_suppliers = {r["supplier_id"] for r in list_suppliers()}
        with open(path, newline="", encoding="utf-8-sig") as f:
            for i, row in enumerate(csv.DictReader(f), start=2):
                try:
                    company_id = (row.get("company_id") or "").strip()
                    supplier_id = (row.get("supplier_id") or "").strip()
                    if company_id not in existing_companies:
                        errors.append(f"Row {i}: company_id '{company_id}' not found, skipped. "
                                       f"Import companies first.")
                        continue
                    if supplier_id not in existing_suppliers:
                        errors.append(f"Row {i}: supplier_id '{supplier_id}' not found, skipped. "
                                       f"Import suppliers first.")
                        continue
                    neft_id = row.get("neft_id")
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO fact_neft
                            (neft_id, neft_date, depositing_branch, neft_amount,
                             company_id, supplier_id, cheque_no, printed, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            int(neft_id) if neft_id else None,
                            row.get("neft_date") or "",
                            row.get("depositing_branch") or "",
                            float(row.get("neft_amount") or 0),
                            company_id,
                            supplier_id,
                            row.get("cheque_no") or None,
                            int(row.get("printed") or 0),
                            row.get("created_at") or "",
                        ),
                    )
                    count += 1
                except Exception as e:
                    errors.append(f"Row {i}: {e}")
        conn.commit()
    finally:
        conn.close()
    return count, errors
