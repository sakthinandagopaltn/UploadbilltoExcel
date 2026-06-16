# Family Expense Tracker

A Python script that tracks family expenses from photos of bills (restaurant, shop, medicine, etc.). It reads the spent amount from the image using OCR and saves each expense to an Excel file.

## Features

- Accepts a bill image as input
- Extracts the total amount with OCR
- Auto-detects expense category when possible
- Appends each expense to `family_expenses.xlsx`

## Requirements

- Python 3.10+
- Node.js 18+ (for the React UI)
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)

Install Tesseract:

```bash
# macOS
brew install tesseract

# Ubuntu / Debian
sudo apt install tesseract-ocr
```

Install Python dependencies:

```bash
pip install -r requirements.txt
```

## React Web UI (recommended)

One command starts both the API and React app:

```bash
chmod +x run_react_ui.sh
./run_react_ui.sh
```

Then open **http://127.0.0.1:5173** in your browser.

Or run them separately in two terminals:

```bash
# Terminal 1 — API
source .venv/bin/activate
pip install -r requirements.txt
uvicorn api:app --host 127.0.0.1 --port 8000
```

```bash
# Terminal 2 — React UI
cd frontend
npm install
npm run dev
```

Upload a bill image, click **Scan bill & save to Excel**, and view the saved details in the results panel.

## Command line

```bash
python expense_tracker.py path/to/bill.jpg
```

Optional flags:

```bash
python expense_tracker.py bill.jpg --category restaurant
python expense_tracker.py bill.jpg --description "Weekly groceries"
python expense_tracker.py bill.jpg --amount 42.50
python expense_tracker.py bill.jpg --show-text
python expense_tracker.py bill.jpg --excel custom_expenses.xlsx
```

## Excel Output

Each saved row includes:

| Column | Description |
|--------|-------------|
| `date` | When the expense was recorded |
| `amount` | Detected or manually entered amount |
| `category` | `restaurant`, `shop`, `medicine`, or `other` |
| `description` | Short note from the bill or manual input |
| `source_image` | Full path to the bill image |

## Tips For Better OCR

- Use a clear, well-lit photo
- Keep the total amount line visible
- If OCR fails, pass `--amount` manually

## Project Files

- `frontend/` - React.js web UI (Vite)
- `api.py` - FastAPI backend for the React UI
- `expense_tracker.py` - Main script and OCR logic
- `app.py` - Legacy Streamlit UI (optional)
- `requirements.txt` - Python dependencies
- `family_expenses.xlsx` - Created automatically after the first expense
- `projectprompt` - Original prompt used to create this tool
