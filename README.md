# TDS App

Automate your entire TDS payable workflow – from raw Tally Daybook exports to a fully reconciled workbook – with **one command**.

![pipeline](docs/pipeline.svg)

---

## ✨ Key features

| Phase                       | What it does                                                                                 |
| --------------------------- | -------------------------------------------------------------------------------------------- |
| **Step 1 – Section Mapper** | Uses GPT‑4o‑mini to classify every ledger into the correct TDS section & caches the mapping. |
| **Step 2 – Expense Prep**   | Enriches Daybook entries with PAN, applicability flags, rates & vendor totals.               |
| **Step 3 – TDS Payable**    | Builds a Tally‑style TDS payable ledger and month/vendor‑wise reconciliation.                |
| **Step 4 – Parse 26Q**      | Extracts challan data from Form 26Q *.docx* and produces a clean Excel.                      |
| **Step 5 – Final Reco**     | Combines all sources into a two‑sheet reconciliation workbook & vendor summary.              |

---

## 🚀 Quick start

### Option 1: Enhanced Batch File (Recommended for Windows Users)

1. **Download the built application** from the `dist/` folder
2. **Run the enhanced launcher**:
   ```cmd
   Run_TDS_Menu.bat
   ```
3. **Use the interactive menu** to:
   - Check file status before running
   - Execute individual steps or full pipeline
   - Access help and troubleshooting tools
   - Clean output files when needed

### Option 2: Command Line Interface

```bash
# 1)  Install Python ≥ 3.11 and Git (if not already)
# 2)  Clone the repo & install deps
$ git clone https://github.com/your‑org/tds_app.git
$ cd tds_app
$ pip install poetry
$ poetry install --with dev

# 3)  Add your OpenAI key (GPT‑4o‑mini is recommended)
$ set OPENAI_API_KEY=sk‑...

# 4)  Drop input files in the project root
#     ├─ Daybook.xlsx
#     ├─ Ledger.xlsx
#     └─ 26Q.docx

# 5)  Run the full pipeline – no prompts!
$ poetry run tds-app run-all --turnover-gt-10cr
```

The generated workbooks appear in the same folder:

* **ledger_tds_sections.csv** – the cached ledger ↔ section mapping
* **processed_expense_data_with_tds.xlsx** – enriched expense data
* **tdspayable_tally.xlsx** – Tally‑style payable summary
* **parsed_26Q.xlsx** – cleaned challan data
* **tds_reconciliation_report.xlsx** – final month‑wise + vendor‑wise reconciliation

---

## 🎯 Enhanced Batch File Features

The `Run_TDS_Menu.bat` provides a user-friendly interface with:

### 📋 **Core Operations**
- **Full Pipeline**: Complete workflow with ODBC fetch
- **Individual Steps**: Run any step independently
- **Smart Turnover Handling**: Automatic 194Q applicability detection

### 🛠️ **Utility Features**
- **🔍 File Status Checker**: Verify all required files are present
- **🧹 File Cleanup**: Safely remove output files for fresh starts
- **📖 Help System**: Comprehensive documentation and troubleshooting
- **⚙️ Settings Menu**: Configuration and system tools

### 🎨 **User Experience**
- **Visual Interface**: Emojis and clear formatting
- **Operation Tracking**: Timestamps and progress indicators
- **Error Prevention**: File existence checks and validation
- **Session History**: Track last run operation

---

## 🔧 Command reference

| Command                                                           | Description      |
| ----------------------------------------------------------------- | ---------------- |
| `tds-app section-map <DAYBOOK>`                                   | Run only Step 1. |
| `tds-app prepare-expense <DAYBOOK> <LEDGER> [--turnover-gt-10cr]` | Step 2.          |
| `tds-app tds-payable`                                             | Step 3.          |
| `tds-app parse-26q <26Q.docx>`                                    | Step 4.          |
| `tds-app final-reco`                                              | Step 5.          |
| `tds-app run-all [options]`                                       | Full pipeline.   |

### Common flags

* `--turnover-gt-10cr` – set if previous‑year turnover exceeded ₹10 crore (affects 194Q applicability).
* `--verbose` – show DEBUG‑level logs (set via `TDS_VERBOSE=1` env var).

---

## 🐛 Recent Bug Fixes & Improvements

### **Error Handling & Robustness**
- ✅ **File Existence Checks**: Prevents crashes from missing input files
- ✅ **ODBC Connection Handling**: Better error messages for Tally connectivity issues
- ✅ **Excel Writer Protection**: Handles file permission errors gracefully
- ✅ **OpenAI API Validation**: Improved environment variable checking

### **Data Processing Fixes**
- ✅ **Variable Name Corrections**: Fixed DataFrame reference bugs
- ✅ **Empty DataFrame Handling**: Improved concatenation logic
- ✅ **Optional File Support**: Made hardcoded vendors file optional
- ✅ **Settings Type Safety**: Corrected configuration assignments

### **Dependency Management**
- ✅ **Complete Requirements**: Updated `requirements.txt` with all necessary packages
- ✅ **Poetry Compatibility**: Ensured proper dependency resolution
- ✅ **Version Pinning**: Consistent package versions across environments

---

## 📁 Required Input Files

### **Essential Files**
- `Daybook.xlsx` - Tally daybook export
- `Ledger.xlsx` - Tally ledger export  
- `26Q.docx` - Form 26Q document
- `ledger_tds_sections.csv` - TDS section mapping (auto-generated)
- `tds_rates.csv` - TDS rates configuration

### **Optional Files**
- `Hardcoded Vendors.csv` - Vendor-specific mappings (optional)

### **Generated Output Files**
- `processed_expense_data_with_tds.xlsx` - Enriched expense data
- `tdspayable_tally.xlsx` - TDS payable ledger
- `parsed_26Q.xlsx` - Cleaned challan data
- `tds_reconciliation_report.xlsx` - Final reconciliation report
- `Discrepancies.xlsx` - Discrepancy analysis

---

## 🗂️ Project layout

```text
tds_app/
 ├─ cli.py             ← Typer CLI entry‑point
 ├─ config/
 │    └─ settings.py   ← Pydantic‑Settings configuration
 ├─ logging_config.py  ← Rich logging setup
 ├─ schemas/           ← (coming soon) Pandera schemas
 └─ steps/             ← Five pipeline modules
    ├─ step0_fetch_odbc.py
    ├─ step1_tds_section_mapper.py
    ├─ step2_prepare_expense_data.py
    ├─ step3_tdspayable_reco.py
    ├─ step4_parse_26q.py
    └─ step5_tds_reconciliation.py

dist/
 ├─ tds-app.exe        ← Built executable
 ├─ Run_TDS_Menu.bat   ← Enhanced launcher
 └─ freeze.exe         ← Development launcher
```

---

## 🔧 Troubleshooting

### **Common Issues**

| Issue | Solution |
|-------|----------|
| **Missing files** | Use "Check file status" in batch menu or verify file presence |
| **ODBC errors** | Ensure Tally is running and ODBC DSN is configured |
| **Excel errors** | Close any open Excel files before running operations |
| **API errors** | Verify `OPENAI_API_KEY` environment variable is set |
| **Permission errors** | Run as administrator or close locked files |

### **Getting Help**
1. **Use the built-in help** in the batch file (Option 9)
2. **Check file status** before running operations (Option 7)
3. **Review system information** in settings (Option 0)
4. **Clean output files** if starting fresh (Option 8)

---

## 🧪 Developer workflow

```bash
# Format & sort imports
$ poetry run black tds_app tests
$ poetry run isort  tds_app tests

# Run tests & schema checks
$ poetry run pytest -q

# Build executable
$ poetry run pyinstaller tds-app.spec

# Test batch file
$ dist/Run_TDS_Menu.bat
```

CI runs automatically on every push (see **.github/workflows/ci.yml**).

---

## 📄 License

MIT © 2025 Your Company
