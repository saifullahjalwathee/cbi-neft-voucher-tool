# CBI NEFT/RTGS Voucher Tool

A lightweight Windows desktop app that fills and prints Central Bank of
India's RTGS/NEFT application form — no more hand-writing the same
beneficiary bank details every time. Built to replace a Microsoft Access
front-end I created for my personal use with a standalone tool that needs nothing installed on the target
PC except the `.exe` itself.

![License](https://img.shields.io/badge/license-MIT-blue.svg)

## Features

- **New NEFT Entry** — pick a saved Company (applicant) and Supplier
  (beneficiary) from dropdowns; their account number, IFSC, bank name, and
  branch auto-fill (read-only) so nothing gets mistyped.
- Generates a print-ready PDF that's an exact overlay onto the real CBI
  RTGS/NEFT form — correct field positions, amount-in-words (Indian
  lakh/crore numbering), and a checkmark in the Cash/Cheque box.
- **Company Master** / **Supplier Master** — one-time entry of bank details,
  reused on every voucher afterwards.
- **History / Reprint** — every entry is searchable, with running totals,
  and can be reprinted without re-entering anything.
- **Backup / Restore** — one-click full database backup/restore, plus
  per-table CSV export/import for use in Excel.
- Date picker, "Save & Print" sends straight to your default PDF app's
  print dialog.

## Fields intentionally left blank on the printed form

The official form has a few fields this tool doesn't collect, so they print
blank for manual fill-in: Customer ID No., Type of Account (HSS/CD/CC/OD),
E-mail ID, Sender PAN No., Sender/Receiver LEI No., and the "For Office Use
only" / signature / acknowledgement section.

## Getting started

### Option A — just run the exe (no Python needed)

Grab `NEFTApp.exe` from [Releases](https://github.com/saifullahjalwathee/cbi-neft-voucher-tool/releases/tag/v1.0.0), copy it
anywhere on a Windows PC, and double-click. Windows SmartScreen will show an
"Unknown publisher" warning the first time since the exe isn't code-signed —
click **More info → Run anyway**.

### Option B — run from source / build it yourself

```bash
git clone https://github.com/saifullahjalwathee/cbi-neft-voucher-tool.git
cd <repo-name>
pip install -r requirements.txt
python app.py
```

To build your own standalone `.exe` on Windows, see [BUILD.md](BUILD.md).

## Data model

Three tables in a local SQLite file (`neft_data.db`, created automatically
next to the app, and gitignored — never committed):

- `dim_company` — applicant/company master data
- `dim_supplier` — beneficiary/supplier master data
- `fact_neft` — one row per NEFT/RTGS voucher, linked to the two tables above
  with real foreign keys

## Project structure

| File | Purpose |
|---|---|
| `app.py` | Tkinter GUI — entry point |
| `db.py` | SQLite schema, CRUD, backup/restore, CSV import/export |
| `pdf_fill.py` | Overlays entry data onto the official CBI form PDF |
| `number_to_words.py` | Amount-in-words (Indian numbering system) |
| `assets/neft_template.pdf` | Blank official CBI RTGS/NEFT form, used as the print background |
| `NEFTApp.spec` | PyInstaller build config |
| `BUILD.md` | Step-by-step build instructions |

## Contributing

Issues and pull requests are welcome — this started as a personal tool for
one bank branch's workflow, so contributions that generalize it (configurable
bank templates, other form layouts, etc.) are especially useful.

## License

MIT — see [LICENSE](LICENSE). Do whatever you like with it.

## Credits

This project was vibe-coded in collaboration with **Claude Sonnet 5**
(medium effort) via [Claude.ai](https://claude.ai) — from analyzing the
original Access database I created for my personal use, through building the SQLite/Tkinter rewrite, to
mapping exact print coordinates off the real bank form PDF. Every feature
was iteratively tested end-to-end (including headless GUI smoke tests)
before being handed off for a real build.

## Disclaimer

This is an unofficial, community-built tool. It is not affiliated with or
endorsed by Central Bank of India. The blank form template is the bank's own
official published format, reproduced here only as a print background for
this tool. Always verify beneficiary details before submitting any funds
transfer.
