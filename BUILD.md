# Building NEFTApp.exe (do this once, on Windows)

This has to run on a real Windows machine — a Linux-built exe won't run on
Windows. The whole thing is one build command.

## 1. One-time setup on the Windows PC

1. Install Python 3.11 or 3.12 from https://python.org/downloads
   - During install, tick **"Add python.exe to PATH"**.
2. Copy the whole `neft_app` folder onto that PC (keep it as one folder —
   `app.py`, `db.py`, `pdf_fill.py`, `number_to_words.py`, `requirements.txt`,
   `NEFTApp.spec`, and the `assets/` folder with `neft_template.pdf` inside it).
3. Open **Command Prompt**, `cd` into the `neft_app` folder, then run:

   ```
   pip install -r requirements.txt
   ```

## 2. Build the exe

Still inside the `neft_app` folder:

```
pyinstaller NEFTApp.spec
```

This creates `dist\NEFTApp.exe` — a single file, nothing else needed next to
it. That's the one you actually deploy/copy around.

## 3. Make it double-click launchable

- Right-click `dist\NEFTApp.exe` → **Send to → Desktop (create shortcut)**.
- Rename the shortcut to whatever you like, e.g. "CBI NEFT Form".
- Double-click it — the app window opens directly, no console window, no
  Access/Office install required on this or any other PC you copy the exe to.

The database file (`neft_data.db`) and any generated PDFs
(`printed_vouchers\`) are created next to wherever `NEFTApp.exe` is sitting,
the first time you run it. If you move the exe, take that folder structure
with it (or start fresh — the app recreates the empty database
automatically).

## 4. First-run notes

- Windows SmartScreen may show an "Unknown publisher" warning the first time,
  since the exe isn't code-signed. Click **More info → Run anyway**. This is
  normal for any unsigned exe and only appears once per machine.
- Rebuilding after a code change: just re-run `pyinstaller NEFTApp.spec`
  from the same folder — it overwrites `dist\NEFTApp.exe`.

## 5. If something looks wrong on the printed form

Tell me what's off (a field shifted, wrong page margin for your printer,
text too small/large) and I'll adjust the coordinates in `pdf_fill.py` —
you only need to re-run step 2 to get the corrected exe, no reinstall needed.
