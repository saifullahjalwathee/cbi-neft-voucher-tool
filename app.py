"""
app.py
Central Bank of India NEFT/RTGS voucher tool.

A small desktop app (Tkinter) that:
  - maintains Company and Supplier master data (dim_company / dim_supplier)
  - records NEFT entries (fact_neft)
  - generates a filled, print-ready PDF that overlays the actual CBI
    RTGS/NEFT application form
  - keeps a history of past entries with reprint

Run directly with: python app.py
Or launch the packaged NEFTApp.exe (see BUILD.md).
"""

import os
import sys
import sqlite3
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import date, datetime

from tkcalendar import DateEntry

import db
from number_to_words import amount_to_words
from pdf_fill import build_neft_pdf

APP_TITLE = "Central Bank of India — NEFT/RTGS Voucher Tool"
DEFAULT_DEPOSITING_BRANCH = "Ammapattinam"


def output_dir():
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(base_dir, "printed_vouchers")
    os.makedirs(out, exist_ok=True)
    return out


def open_file(path):
    """Open a file with the OS default handler (used for the History 'view' action)."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: F821  (only exists on Windows)
        elif sys.platform == "darwin":
            subprocess.call(["open", path])
        else:
            subprocess.call(["xdg-open", path])
    except Exception as e:
        messagebox.showwarning(
            "Could not auto-open",
            f"The PDF was created at:\n{path}\n\nBut it could not be opened automatically ({e}).",
        )


def print_file(path):
    """
    Send the file straight to the default PDF handler's Print dialog.
    On Windows this uses the 'print' shell verb (same as right-click > Print
    in Explorer) — the handler (Edge/Adobe/Foxit/etc.) then shows its own
    print dialog. Falls back to a plain open if that verb isn't available,
    so the user is never left with nothing happening.
    """
    try:
        if sys.platform.startswith("win"):
            os.startfile(path, "print")  # noqa: F821  (Windows-only API)
            return
        elif sys.platform == "darwin":
            subprocess.call(["lp", path])
            return
        else:
            subprocess.call(["xdg-open", path])
            return
    except Exception:
        # Any failure (no app registered for "print", missing lp, etc.)
        # falls back to just opening the file so the user can print manually.
        open_file(path)


# ---------------------------------------------------------------------------
# Reusable master-data tab (works for both Company and Supplier)
# ---------------------------------------------------------------------------

class MasterDataTab(ttk.Frame):
    """
    Generic CRUD grid for a master table.
    fields: list of (column_key, label, width)
    """

    def __init__(self, parent, title, fields, list_fn, upsert_fn, delete_fn, id_field, on_change=None):
        super().__init__(parent)
        self.fields = fields
        self.list_fn = list_fn
        self.upsert_fn = upsert_fn
        self.delete_fn = delete_fn
        self.id_field = id_field
        self.on_change = on_change

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(self, text=title, font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=(10, 5)
        )

        # --- Tree (list) ---
        tree_frame = ttk.Frame(self)
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=10)
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        cols = [f[0] for f in fields]
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=8)
        for key, label, width in fields:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scroll.set)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # --- Form (entry fields) ---
        form_frame = ttk.LabelFrame(self, text="Add / Edit")
        form_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        for i in range(4):
            form_frame.columnconfigure(i, weight=1)

        self.entries = {}
        for idx, (key, label, _) in enumerate(fields):
            r, c = divmod(idx, 2)
            ttk.Label(form_frame, text=label + ":").grid(row=r, column=c * 2, sticky="e", padx=5, pady=4)
            ent = ttk.Entry(form_frame, width=30)
            ent.grid(row=r, column=c * 2 + 1, sticky="ew", padx=5, pady=4)
            self.entries[key] = ent

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=3, column=0, sticky="w", padx=10, pady=(0, 10))
        ttk.Button(btn_frame, text="Save", command=self._save).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Clear", command=self._clear).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Delete Selected", command=self._delete).pack(side="left", padx=4)

        self.refresh()

    def refresh(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for row in self.list_fn():
            values = [row[key] if row[key] is not None else "" for key, _, _ in self.fields]
            self.tree.insert("", "end", iid=row[self.id_field], values=values)
        if self.on_change:
            self.on_change()

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        values = self.tree.item(sel[0], "values")
        for (key, _, _), val in zip(self.fields, values):
            self.entries[key].delete(0, "end")
            self.entries[key].insert(0, val)

    def _save(self):
        data = {key: self.entries[key].get().strip() for key, _, _ in self.fields}
        if not data.get(self.id_field):
            messagebox.showerror("Missing ID", f"'{self.id_field}' is required.")
            return
        self.upsert_fn(data)
        self.refresh()
        self._clear()

    def _clear(self):
        for ent in self.entries.values():
            ent.delete(0, "end")

    def _delete(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select a row", "Select a row to delete first.")
            return
        if messagebox.askyesno("Confirm delete", "Delete selected record?"):
            try:
                self.delete_fn(sel[0])
            except sqlite3.IntegrityError:
                messagebox.showerror(
                    "Cannot delete",
                    "This record is used by one or more NEFT entries in History, "
                    "so it can't be deleted. Delete those history entries first if you "
                    "really need to remove it.",
                )
                return
            self.refresh()
            self._clear()

    def get_ids(self):
        return [row[self.id_field] for row in self.list_fn()]


# ---------------------------------------------------------------------------
# New NEFT entry tab
# ---------------------------------------------------------------------------

class NeftEntryTab(ttk.Frame):
    def __init__(self, parent, refresh_history_cb):
        super().__init__(parent)
        self.refresh_history_cb = refresh_history_cb
        self.columnconfigure(1, weight=1)

        pad = dict(padx=8, pady=6)

        ttk.Label(self, text="New NEFT / RTGS Entry", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", **pad
        )

        ttk.Label(self, text="Date:").grid(row=1, column=0, sticky="e", **pad)
        self.date_picker = DateEntry(
            self, width=18, date_pattern="dd-mm-yyyy",
            background="darkblue", foreground="white", borderwidth=2,
        )
        self.date_picker.set_date(date.today())
        self.date_picker.grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(self, text="Depositing Branch:").grid(row=2, column=0, sticky="e", **pad)
        self.branch_var = tk.StringVar(value=DEFAULT_DEPOSITING_BRANCH)
        ttk.Entry(self, textvariable=self.branch_var, width=30).grid(row=2, column=1, sticky="w", **pad)

        ttk.Label(self, text="Company (Applicant):").grid(row=3, column=0, sticky="e", **pad)
        self.company_cb = ttk.Combobox(self, state="readonly", width=40)
        self.company_cb.grid(row=3, column=1, sticky="w", **pad)
        self.company_cb.bind("<<ComboboxSelected>>", self._on_company_selected)

        company_details = ttk.LabelFrame(self, text="Company Bank Details")
        company_details.grid(row=4, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 6))
        for i in range(4):
            company_details.columnconfigure(i, weight=1)
        self.company_detail_vars = {
            "account_no": tk.StringVar(), "ifsc": tk.StringVar(),
            "bank_name": tk.StringVar(), "branch": tk.StringVar(),
        }
        ttk.Label(company_details, text="Account No.:").grid(row=0, column=0, sticky="e", padx=5, pady=3)
        ttk.Entry(company_details, textvariable=self.company_detail_vars["account_no"],
                  state="readonly", width=20).grid(row=0, column=1, sticky="ew", padx=5, pady=3)
        ttk.Label(company_details, text="IFSC:").grid(row=0, column=2, sticky="e", padx=5, pady=3)
        ttk.Entry(company_details, textvariable=self.company_detail_vars["ifsc"],
                  state="readonly", width=16).grid(row=0, column=3, sticky="ew", padx=5, pady=3)
        ttk.Label(company_details, text="Bank Name:").grid(row=1, column=0, sticky="e", padx=5, pady=3)
        ttk.Entry(company_details, textvariable=self.company_detail_vars["bank_name"],
                  state="readonly", width=20).grid(row=1, column=1, sticky="ew", padx=5, pady=3)
        ttk.Label(company_details, text="Branch:").grid(row=1, column=2, sticky="e", padx=5, pady=3)
        ttk.Entry(company_details, textvariable=self.company_detail_vars["branch"],
                  state="readonly", width=16).grid(row=1, column=3, sticky="ew", padx=5, pady=3)

        ttk.Label(self, text="Supplier (Beneficiary):").grid(row=5, column=0, sticky="e", **pad)
        self.supplier_cb = ttk.Combobox(self, state="readonly", width=40)
        self.supplier_cb.grid(row=5, column=1, sticky="w", **pad)
        self.supplier_cb.bind("<<ComboboxSelected>>", self._on_supplier_selected)

        supplier_details = ttk.LabelFrame(self, text="Supplier Bank Details")
        supplier_details.grid(row=6, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 6))
        for i in range(4):
            supplier_details.columnconfigure(i, weight=1)
        self.supplier_detail_vars = {
            "account_no": tk.StringVar(), "ifsc": tk.StringVar(),
            "bank_name": tk.StringVar(), "branch": tk.StringVar(),
        }
        ttk.Label(supplier_details, text="Account No.:").grid(row=0, column=0, sticky="e", padx=5, pady=3)
        ttk.Entry(supplier_details, textvariable=self.supplier_detail_vars["account_no"],
                  state="readonly", width=20).grid(row=0, column=1, sticky="ew", padx=5, pady=3)
        ttk.Label(supplier_details, text="IFSC:").grid(row=0, column=2, sticky="e", padx=5, pady=3)
        ttk.Entry(supplier_details, textvariable=self.supplier_detail_vars["ifsc"],
                  state="readonly", width=16).grid(row=0, column=3, sticky="ew", padx=5, pady=3)
        ttk.Label(supplier_details, text="Bank Name:").grid(row=1, column=0, sticky="e", padx=5, pady=3)
        ttk.Entry(supplier_details, textvariable=self.supplier_detail_vars["bank_name"],
                  state="readonly", width=20).grid(row=1, column=1, sticky="ew", padx=5, pady=3)
        ttk.Label(supplier_details, text="Branch:").grid(row=1, column=2, sticky="e", padx=5, pady=3)
        ttk.Entry(supplier_details, textvariable=self.supplier_detail_vars["branch"],
                  state="readonly", width=16).grid(row=1, column=3, sticky="ew", padx=5, pady=3)

        ttk.Label(self, text="Amount (Rs.):").grid(row=7, column=0, sticky="e", **pad)
        self.amount_var = tk.StringVar()
        amount_entry = ttk.Entry(self, textvariable=self.amount_var, width=20)
        amount_entry.grid(row=7, column=1, sticky="w", **pad)
        amount_entry.bind("<KeyRelease>", self._update_words_preview)

        ttk.Label(self, text="Cheque No. (blank = Cash):").grid(row=8, column=0, sticky="e", **pad)
        self.cheque_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.cheque_var, width=20).grid(row=8, column=1, sticky="w", **pad)

        self.words_preview = ttk.Label(self, text="", foreground="#555", wraplength=420, justify="left")
        self.words_preview.grid(row=9, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 6))

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=10, column=0, columnspan=2, sticky="w", padx=8, pady=10)
        ttk.Button(btn_frame, text="Save && Print", command=self._save_and_print).pack(side="left")

        self._company_map = {}
        self._supplier_map = {}
        self.refresh_dropdowns()

    def refresh_dropdowns(self):
        companies = db.list_companies()
        suppliers = db.list_suppliers()
        self._company_map = {f"{c['company_name']} ({c['company_id']})": c["company_id"] for c in companies}
        self._supplier_map = {f"{s['supplier_name']} ({s['supplier_id']})": s["supplier_id"] for s in suppliers}
        self.company_cb["values"] = list(self._company_map.keys())
        self.supplier_cb["values"] = list(self._supplier_map.keys())

    def _on_company_selected(self, _event=None):
        company_id = self._company_map.get(self.company_cb.get())
        row = db.get_company(company_id) if company_id else None
        self.company_detail_vars["account_no"].set(row["company_bank_ac_no"] if row else "")
        self.company_detail_vars["ifsc"].set(row["company_ifsc"] if row else "")
        self.company_detail_vars["bank_name"].set(row["company_bank_name"] if row else "")
        self.company_detail_vars["branch"].set(row["company_bank_branch"] if row else "")

    def _on_supplier_selected(self, _event=None):
        supplier_id = self._supplier_map.get(self.supplier_cb.get())
        row = db.get_supplier(supplier_id) if supplier_id else None
        self.supplier_detail_vars["account_no"].set(row["supplier_bank_ac_no"] if row else "")
        self.supplier_detail_vars["ifsc"].set(row["supplier_ifsc"] if row else "")
        self.supplier_detail_vars["bank_name"].set(row["supplier_bank"] if row else "")
        self.supplier_detail_vars["branch"].set(row["supplier_branch"] if row else "")

    def _update_words_preview(self, _event=None):
        val = self.amount_var.get().strip().replace(",", "")
        if not val:
            self.words_preview.config(text="")
            return
        try:
            self.words_preview.config(text=amount_to_words(val))
        except ValueError:
            self.words_preview.config(text="(enter a valid number)")

    def _save_and_print(self):
        neft_date = self.date_picker.get_date().isoformat()  # stored as YYYY-MM-DD
        branch = self.branch_var.get().strip()
        amount_raw = self.amount_var.get().strip().replace(",", "")
        cheque_no = self.cheque_var.get().strip()

        if not self.company_cb.get() or not self.supplier_cb.get():
            messagebox.showerror("Missing data", "Select both a company and a supplier.")
            return
        if not amount_raw:
            messagebox.showerror("Missing data", "Enter the amount.")
            return
        try:
            amount = float(amount_raw)
        except ValueError:
            messagebox.showerror("Invalid amount", "Amount must be a number.")
            return

        company_id = self._company_map[self.company_cb.get()]
        supplier_id = self._supplier_map[self.supplier_cb.get()]

        neft_id = db.insert_neft(neft_date, branch, amount, company_id, supplier_id, cheque_no or None)

        row = db.get_neft_full(neft_id)
        out_path = os.path.join(output_dir(), f"NEFT_{neft_id}_{row['company_name']}.pdf".replace(" ", "_"))
        build_neft_pdf(row, out_path)
        db.mark_printed(neft_id)

        self.refresh_history_cb()
        messagebox.showinfo("Saved", f"NEFT entry #{neft_id} saved.\nPDF created:\n{out_path}\n\nSending to Print...")
        print_file(out_path)

        # reset form
        self.company_cb.set("")
        self.supplier_cb.set("")
        self._on_company_selected()
        self._on_supplier_selected()
        self.branch_var.set(DEFAULT_DEPOSITING_BRANCH)
        self.amount_var.set("")
        self.cheque_var.set("")
        self.words_preview.config(text="")


# ---------------------------------------------------------------------------
# History / reprint tab
# ---------------------------------------------------------------------------

class HistoryTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        ttk.Label(top, text="History", font=("Segoe UI", 12, "bold")).pack(side="left")
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(top, textvariable=self.search_var, width=30)
        search_entry.pack(side="left", padx=10)
        search_entry.bind("<KeyRelease>", lambda e: self.refresh())
        ttk.Button(top, text="Reprint Selected", command=self._reprint).pack(side="left", padx=6)
        ttk.Button(top, text="Delete Selected", command=self._delete).pack(side="left", padx=6)

        cols = ("neft_id", "neft_date", "company_name", "supplier_name", "neft_amount",
                 "depositing_branch", "cheque_no", "printed")
        labels = ("ID", "Date", "Company", "Supplier", "Amount", "Branch", "Cheque No.", "Printed")
        widths = (40, 90, 160, 160, 90, 110, 90, 60)

        self.tree = ttk.Treeview(self, columns=cols, show="headings")
        for col, label, width in zip(cols, labels, widths):
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, anchor="w")
        self.tree.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        self.totals_label = ttk.Label(self, text="", font=("Segoe UI", 10, "bold"))
        self.totals_label.grid(row=2, column=0, sticky="w", padx=10, pady=(0, 10))

        self.refresh()

    def refresh(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        rows = db.list_history(self.search_var.get().strip() or None)
        total_amount = 0.0
        for row in rows:
            total_amount += row["neft_amount"]
            self.tree.insert(
                "", "end", iid=row["neft_id"],
                values=(row["neft_id"], row["neft_date"], row["company_name"], row["supplier_name"],
                        f"{row['neft_amount']:,.2f}", row["depositing_branch"] or "",
                        row["cheque_no"] or "", "Yes" if row["printed"] else "No"),
            )
        count = len(rows)
        self.totals_label.config(
            text=f"Showing {count} entr{'y' if count == 1 else 'ies'}   |   Total Amount: Rs. {total_amount:,.2f}"
        )

    def _reprint(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select a row", "Select a NEFT entry to reprint.")
            return
        neft_id = int(sel[0])
        row = db.get_neft_full(neft_id)
        out_path = os.path.join(output_dir(), f"NEFT_{neft_id}_{row['company_name']}_reprint.pdf".replace(" ", "_"))
        build_neft_pdf(row, out_path)
        print_file(out_path)

    def _delete(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select a row", "Select a NEFT entry to delete.")
            return
        if messagebox.askyesno("Confirm delete", "Delete this NEFT history entry?"):
            db.delete_neft(int(sel[0]))
            self.refresh()


# ---------------------------------------------------------------------------
# Backup / Restore tab
# ---------------------------------------------------------------------------

class BackupRestoreTab(ttk.Frame):
    def __init__(self, parent, refresh_all_cb):
        super().__init__(parent)
        self.refresh_all_cb = refresh_all_cb
        self.columnconfigure(0, weight=1)

        ttk.Label(self, text="Backup / Restore", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=(10, 5)
        )

        # --- Full database backup/restore (recommended) ---
        db_frame = ttk.LabelFrame(self, text="Full Backup (recommended — restores everything exactly)")
        db_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        ttk.Label(
            db_frame,
            text="Saves/restores Company Master, Supplier Master, and NEFT History together,\n"
                 "including history IDs and printed status. Use this for routine backups.",
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(6, 10))
        ttk.Button(db_frame, text="Backup Now...", command=self._backup_database).grid(
            row=1, column=0, sticky="w", padx=8, pady=(0, 10)
        )
        ttk.Button(db_frame, text="Restore from Backup...", command=self._restore_database).grid(
            row=1, column=1, sticky="w", padx=8, pady=(0, 10)
        )

        # --- Per-table CSV export/import (for Excel / sharing) ---
        csv_frame = ttk.LabelFrame(self, text="CSV Export / Import (for Excel, sharing, or per-table backup)")
        csv_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        ttk.Label(
            csv_frame,
            text="When restoring from CSV into an empty database, import in this order:\n"
                 "Companies -> Suppliers -> NEFT History (history rows need their company/supplier to exist first).",
            justify="left",
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(6, 10))

        self._csv_row(csv_frame, 1, "Company Master", db.export_companies_csv, db.import_companies_csv, "companies")
        self._csv_row(csv_frame, 2, "Supplier Master", db.export_suppliers_csv, db.import_suppliers_csv, "suppliers")
        self._csv_row(csv_frame, 3, "NEFT History", db.export_neft_csv, db.import_neft_csv, "neft_history")

    def _csv_row(self, parent, row, label, export_fn, import_fn, default_name):
        ttk.Label(parent, text=label + ":").grid(row=row, column=0, sticky="e", padx=8, pady=4)
        ttk.Button(
            parent, text="Export CSV...",
            command=lambda: self._export_csv(export_fn, default_name, label),
        ).grid(row=row, column=1, sticky="w", padx=4, pady=4)
        ttk.Button(
            parent, text="Import CSV...",
            command=lambda: self._import_csv(import_fn, label),
        ).grid(row=row, column=2, sticky="w", padx=4, pady=4)

    # --- Full database ---

    def _backup_database(self):
        default_name = f"neft_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        path = filedialog.asksaveasfilename(
            title="Save backup as", initialfile=default_name,
            defaultextension=".db", filetypes=[("SQLite Database", "*.db")],
        )
        if not path:
            return
        db.backup_database(path)
        messagebox.showinfo("Backup complete", f"Full backup saved to:\n{path}")

    def _restore_database(self):
        path = filedialog.askopenfilename(
            title="Select backup file to restore", filetypes=[("SQLite Database", "*.db"), ("All files", "*.*")],
        )
        if not path:
            return
        if not messagebox.askyesno(
            "Confirm restore",
            "This will REPLACE all current data (Company Master, Supplier Master, "
            "and NEFT History) with the contents of the selected backup file.\n\n"
            "This cannot be undone. Continue?",
        ):
            return
        db.restore_database(path)
        self.refresh_all_cb()
        messagebox.showinfo("Restore complete", "Database restored successfully.")

    # --- CSV ---

    def _export_csv(self, export_fn, default_name, label):
        path = filedialog.asksaveasfilename(
            title=f"Export {label} as", initialfile=f"{default_name}.csv",
            defaultextension=".csv", filetypes=[("CSV file", "*.csv")],
        )
        if not path:
            return
        count = export_fn(path)
        messagebox.showinfo("Export complete", f"Exported {count} {label} row(s) to:\n{path}")

    def _import_csv(self, import_fn, label):
        path = filedialog.askopenfilename(
            title=f"Select {label} CSV to import", filetypes=[("CSV file", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        if not messagebox.askyesno(
            "Confirm import",
            f"This will add/update {label} records from the selected CSV "
            f"(existing IDs will be overwritten with the CSV's values). Continue?",
        ):
            return
        count, errors = import_fn(path)
        self.refresh_all_cb()
        msg = f"Imported {count} {label} row(s)."
        if errors:
            shown = "\n".join(errors[:15])
            more = f"\n...and {len(errors) - 15} more." if len(errors) > 15 else ""
            msg += f"\n\n{len(errors)} row(s) had problems and were skipped:\n{shown}{more}"
            messagebox.showwarning("Import finished with warnings", msg)
        else:
            messagebox.showinfo("Import complete", msg)


# ---------------------------------------------------------------------------
# Main app window
# ---------------------------------------------------------------------------

class NeftApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("880x640")
        self.minsize(760, 560)

        db.init_db()

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        self.history_tab = HistoryTab(notebook)

        self.entry_tab = NeftEntryTab(notebook, refresh_history_cb=self.history_tab.refresh)

        company_fields = [
            ("company_id", "Company ID", 90),
            ("company_name", "Company Name", 160),
            ("company_bank_name", "Bank Name", 160),
            ("company_bank_ac_no", "Account No.", 120),
            ("company_ifsc", "IFSC", 100),
            ("company_bank_branch", "Branch", 110),
            ("company_phone", "Phone", 100),
            ("company_address", "Address", 200),
        ]
        self.company_tab = MasterDataTab(
            notebook, "Company Master (Applicant)", company_fields,
            db.list_companies, db.upsert_company, db.delete_company, "company_id",
            on_change=self.entry_tab.refresh_dropdowns,
        )

        supplier_fields = [
            ("supplier_id", "Supplier ID", 90),
            ("supplier_name", "Supplier Name", 160),
            ("supplier_bank", "Bank Name", 160),
            ("supplier_bank_ac_no", "Account No.", 140),
            ("supplier_ifsc", "IFSC", 100),
            ("supplier_branch", "Branch", 120),
        ]
        self.supplier_tab = MasterDataTab(
            notebook, "Supplier Master (Beneficiary)", supplier_fields,
            db.list_suppliers, db.upsert_supplier, db.delete_supplier, "supplier_id",
            on_change=self.entry_tab.refresh_dropdowns,
        )

        notebook.add(self.entry_tab, text="New NEFT Entry")
        notebook.add(self.company_tab, text="Company Master")
        notebook.add(self.supplier_tab, text="Supplier Master")
        notebook.add(self.history_tab, text="History / Reprint")

        self.backup_tab = BackupRestoreTab(notebook, refresh_all_cb=self.refresh_all)
        notebook.add(self.backup_tab, text="Backup / Restore")

    def refresh_all(self):
        """Called after a restore/import so every open tab reflects the new data."""
        self.company_tab.refresh()
        self.supplier_tab.refresh()
        self.entry_tab.refresh_dropdowns()
        self.history_tab.refresh()


def main():
    app = NeftApp()
    app.mainloop()


if __name__ == "__main__":
    main()
