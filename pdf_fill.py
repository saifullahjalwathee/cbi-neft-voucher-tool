"""
pdf_fill.py
Overlays NEFT voucher data onto the real Central Bank of India RTGS/NEFT
application PDF (assets/neft_template.pdf), using exact coordinates measured
from that PDF (the template has no fillable AcroForm fields, it's a flat
layout, so text is drawn at fixed positions on top of it).

Fields NOT in the database (Customer ID, Type of Account, E-mail, PAN, LEI)
are intentionally left blank on the printed form, as instructed.
"""

import io
import os
import sys

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from pypdf import PdfReader, PdfWriter

from number_to_words import amount_to_words

PAGE_W, PAGE_H = letter  # 612 x 792


def _asset_path(name):
    if getattr(sys, "frozen", False):
        base_dir = sys._MEIPASS  # PyInstaller temp extraction dir
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "assets", name)


def _y(pdf_top_coord):
    """
    Convert a pdfplumber-style 'top of page, y grows downward' coordinate
    into a reportlab 'bottom of page, y grows upward' coordinate.
    """
    return PAGE_H - pdf_top_coord


def _fmt_date(date_str):
    """date_str expected as YYYY-MM-DD (from the date picker) -> DD-MM-YYYY."""
    try:
        y, m, d = date_str.split("-")
        return f"{d}-{m}-{y}"
    except Exception:
        return date_str


def _fmt_amount(amount):
    try:
        return f"{float(amount):,.0f}" if float(amount) == int(float(amount)) else f"{float(amount):,.2f}"
    except Exception:
        return str(amount)


def build_neft_pdf(neft_row, output_path):
    """
    neft_row: sqlite3.Row (or dict) from db.get_neft_full() with fields:
        neft_date, depositing_branch, neft_amount, cheque_no,
        company_name, company_bank_name, company_bank_ac_no, company_ifsc,
        company_bank_branch, company_phone, company_address,
        supplier_name, supplier_bank, supplier_bank_ac_no, supplier_ifsc,
        supplier_branch
    output_path: where to write the final filled PDF.
    """
    row = dict(neft_row)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFont("Helvetica-Bold", 9)

    def text(x, top, s, size=9, font="Helvetica-Bold", max_width=None):
        if not s:
            return
        s = str(s)
        c.setFont(font, size)
        if max_width:
            s = _wrap_and_draw(c, x, top, s, size, font, max_width)
        else:
            c.drawString(x, _y(top) + 1.5, s)

    def _wrap_and_draw(c, x, top, s, size, font, max_width):
        words = s.split()
        lines = []
        cur = ""
        for w in words:
            trial = (cur + " " + w).strip()
            if c.stringWidth(trial, font, size) <= max_width:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        for i, line in enumerate(lines[:2]):  # max 2 lines available in template
            c.drawString(x, _y(top) + 1.5 - (i * 11), line)

    # ---- Date (top right) ----
    text(485, 87.7, _fmt_date(row.get("neft_date", "")))

    # ---- Branch line: "___________Branch" ----
    text(60, 115.8, row.get("depositing_branch", ""))

    # ---- Amount figures ----
    text(162, 152.3, _fmt_amount(row.get("neft_amount", 0)))

    # ---- Amount in words ----
    words = amount_to_words(row.get("neft_amount", 0), prefix="", suffix="")
    text(316, 152.3, words.strip(), size=8.5, max_width=228)

    # ---- Cash / Cheque checkbox ----
    # Checkbox glyph boxes measured on the template:
    #   Cash box:   x 61.4 - 77.8 , top 164.6 - 180.4
    #   Cheque box: x 138.0 - 154.5, top 166.1 - 180.4
    CASH_BOX = (62.0, 165.5, 15.0)
    CHEQUE_BOX = (138.5, 165.5, 15.0)
    cheque_no = row.get("cheque_no")
    if cheque_no:
        _draw_check(c, *CHEQUE_BOX)
    else:
        _draw_check(c, *CASH_BOX)

    # ---- DETAILS OF APPLICANT (company) ----
    text(90, 213.3, row.get("company_name", ""), size=9)
    text(115, 224.8, row.get("company_bank_ac_no", ""), size=9)
    # TYPE OF ACCOUNT, CUSTOMER ID NO -> intentionally left blank
    text(98, 259.1, row.get("company_address", ""), size=8, max_width=220)
    text(123, 282.2, row.get("company_phone", ""), size=9)
    # E-mail ID, SENDER PAN NO, SENDER LEI NO -> intentionally left blank

    # ---- DETAILS OF BENEFICIARY (supplier) ----
    text(368, 213.3, row.get("supplier_ifsc", ""), size=9)
    text(349, 224.8, row.get("supplier_bank", ""), size=8.5, max_width=155)
    text(360, 236.4, row.get("supplier_branch", ""), size=9)
    text(400, 247.6, row.get("supplier_bank_ac_no", ""), size=8.5, max_width=150)
    text(432, 259.1, row.get("supplier_bank_ac_no", ""), size=8, max_width=115)
    # TYPE OF A/C (beneficiary) -> intentionally left blank
    text(353, 282.2, row.get("supplier_name", ""), size=9)
    # TEL.NO./MOBILE NO. (beneficiary) -> not in schema, left blank

    c.showPage()
    c.save()
    buf.seek(0)

    # ---- Merge overlay onto the real template ----
    overlay_reader = PdfReader(buf)
    template_reader = PdfReader(_asset_path("neft_template.pdf"))
    writer = PdfWriter()

    base_page = template_reader.pages[0]
    base_page.merge_page(overlay_reader.pages[0])
    writer.add_page(base_page)

    with open(output_path, "wb") as f:
        writer.write(f)

    return output_path


def _draw_check(c, x, top, size):
    """Draw an X mark inside a checkbox at the given top-left corner."""
    c.setLineWidth(1.3)
    y_top = _y(top)
    y_bot = _y(top) - size
    c.line(x + 1.5, y_top - 1.5, x + size - 1.5, y_bot + 1.5)
    c.line(x + 1.5, y_bot + 1.5, x + size - 1.5, y_top - 1.5)


