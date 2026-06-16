#!/usr/bin/env python3
"""Track family expenses from bill images and save them to Excel."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter

DEFAULT_EXCEL_FILE = Path(__file__).resolve().parent / "family_expenses.xlsx"
EXCEL_COLUMNS = ["date", "amount", "category", "description", "source_image", "image_hash"]


class DuplicateBillError(ValueError):
    """Raised when the same bill image was already saved."""

CATEGORY_KEYWORDS = {
    "restaurant": (
        "restaurant",
        "cafe",
        "coffee",
        "dining",
        "food",
        "pizza",
        "burger",
        "bistro",
        "kitchen",
        "grill",
        "takeaway",
        "take out",
    ),
    "medicine": (
        "pharmacy",
        "medical",
        "medicine",
        "hospital",
        "clinic",
        "drug",
        "health",
        "chemist",
        "prescription",
    ),
    "shop": (
        "store",
        "mart",
        "market",
        "shop",
        "retail",
        "supermarket",
        "grocery",
        "mall",
        "outlet",
        "department",
    ),
}

TOTAL_KEYWORDS = (
    "grand total",
    "total due",
    "amount due",
    "balance due",
    "net amount",
    "you paid",
    "total paid",
    "total",
    "payable",
    "subtotal",
    "sub total",
)

# Lines that mention "total" but are usually not the bill total.
LOW_PRIORITY_TOTAL_HINTS = (
    "debit",
    "credit",
    "card",
    "auth",
    "approval",
    "change",
    "rec#",
    "vcd#",
    "aid:",
    "transaction",
)

SKIP_AMOUNT_LINE_PATTERN = re.compile(
    r"rec#|vcd#|aid:|auth|approval|trans\s*id|ref\s*#|invoice\s*#|"
    r"qty|quantity|sku|upc|item\s*#",
    re.IGNORECASE,
)

AMOUNT_PATTERN = re.compile(
    r"(?<!\d)"
    r"(?:₹|Rs\.?|INR|\$|USD|€|EUR)?\s*"
    r"(\d{1,3}(?:,\d{3})*\.\d{2}|\d+\.\d{2})"
    r"(?!\d)",
    re.IGNORECASE,
)

WHOLE_AMOUNT_PATTERN = re.compile(
    r"(?<!\d)"
    r"(?:₹|Rs\.?|INR|\$|USD|€|EUR)?\s*"
    r"(\d{1,4})"
    r"(?!\d|\.)",
    re.IGNORECASE,
)

TESSERACT_CANDIDATES = (
    "/opt/homebrew/bin/tesseract",
    "/usr/local/bin/tesseract",
)


def configure_tesseract() -> None:
    """Use Tesseract from PATH, or common Homebrew install locations."""
    if shutil.which("tesseract"):
        return

    for candidate in TESSERACT_CANDIDATES:
        if Path(candidate).is_file():
            pytesseract.pytesseract.tesseract_cmd = candidate
            return


def preprocess_image(image_path: Path) -> Image.Image:
    """Improve OCR accuracy with basic image cleanup."""
    image = Image.open(image_path).convert("L")
    image = ImageEnhance.Contrast(image).enhance(2.0)
    image = image.filter(ImageFilter.SHARPEN)
    return image


def extract_text(image_path: Path) -> str:
    configure_tesseract()
    image = preprocess_image(image_path)
    return pytesseract.image_to_string(image)


def parse_amount(value: str) -> float | None:
    cleaned = value.replace(",", "").strip()
    try:
        amount = float(cleaned)
    except ValueError:
        return None
    if amount <= 0 or amount > 1_000_000:
        return None
    return round(amount, 2)


def find_amounts_in_line(line: str) -> list[float]:
    amounts: list[float] = []
    for match in AMOUNT_PATTERN.finditer(line):
        parsed = parse_amount(match.group(1))
        if parsed is not None:
            amounts.append(parsed)

    # Whole-dollar amounts only when the line looks like a total/payment line.
    lower_line = line.lower()
    if any(keyword in lower_line for keyword in TOTAL_KEYWORDS) or "$" in line:
        for match in WHOLE_AMOUNT_PATTERN.finditer(line):
            parsed = parse_amount(match.group(1))
            if parsed is not None:
                amounts.append(parsed)

    return amounts


def _score_total_line(lower_line: str) -> int:
    if SKIP_AMOUNT_LINE_PATTERN.search(lower_line):
        return -1
    if any(hint in lower_line for hint in LOW_PRIORITY_TOTAL_HINTS):
        return 10
    if "grand total" in lower_line:
        return 100
    if any(k in lower_line for k in ("total due", "amount due", "balance due", "you paid")):
        return 90
    if "subtotal" in lower_line or "sub total" in lower_line:
        return 30
    if re.search(r"\btotal\b", lower_line):
        return 80
    return -1


def _pick_amount_from_line(line: str) -> float | None:
    amounts = find_amounts_in_line(line)
    if not amounts:
        return None

    # On total lines the payable amount is usually the last currency value.
    decimal_amounts = [amount for amount in amounts if amount != int(amount)]
    if decimal_amounts:
        return decimal_amounts[-1]
    return amounts[-1]


def extract_amount(text: str) -> float | None:
    """Pick the most likely total amount from OCR text."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    scored_lines: list[tuple[int, int, float]] = []

    for index, line in enumerate(lines):
        lower_line = line.lower()
        score = _score_total_line(lower_line)
        if score < 0:
            continue
        amount = _pick_amount_from_line(line)
        if amount is not None:
            scored_lines.append((score, index, amount))

    if scored_lines:
        scored_lines.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return scored_lines[0][2]

    fallback_amounts: list[float] = []
    for line in lines:
        if SKIP_AMOUNT_LINE_PATTERN.search(line.lower()):
            continue
        for match in AMOUNT_PATTERN.finditer(line):
            parsed = parse_amount(match.group(1))
            if parsed is not None:
                fallback_amounts.append(parsed)

    if fallback_amounts:
        return max(fallback_amounts)

    return None


def _clean_description_text(line: str) -> str:
    cleaned = re.sub(r"[©®™&@#*=+|\\/_\[\]{}<>~`]", " ", line)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:.,;")
    return cleaned


def _is_garbage_description(line: str) -> bool:
    cleaned = _clean_description_text(line)
    if len(cleaned) < 3:
        return True

    letters = [char for char in cleaned if char.isalpha()]
    if len(letters) < 2:
        return True

    upper_letters = [char for char in letters if char.isupper()]
    if len(letters) >= 4 and len(upper_letters) / len(letters) > 0.6:
        x_ratio = cleaned.upper().count("X") / max(len(cleaned), 1)
        if x_ratio > 0.2:
            return True

    if AMOUNT_PATTERN.search(line) and not re.search(r"[A-Za-z]{3,}", cleaned):
        return True

    if any(keyword in cleaned.lower() for keyword in TOTAL_KEYWORDS):
        return True

    if re.search(r"\d{2}/\d{2}/\d{2,4}", cleaned):
        return True

    if re.fullmatch(r"[\d\s\W]+", cleaned):
        return True

    return False


def guess_description(text: str) -> str:
    candidates: list[str] = []

    for line in text.splitlines():
        cleaned = _clean_description_text(line.strip())
        if _is_garbage_description(line):
            continue
        candidates.append(cleaned)

    if candidates:
        # Merchant/store name is usually near the top of the receipt.
        return candidates[0][:120]

    for line in text.splitlines():
        cleaned = _clean_description_text(line.strip())
        if len(cleaned) >= 3:
            return cleaned[:120]

    return "Bill expense"


def detect_category(text: str) -> str:
    lower_text = text.lower()
    scores = {
        category: sum(1 for keyword in keywords if keyword in lower_text)
        for category, keywords in CATEGORY_KEYWORDS.items()
    }
    best_category, best_score = max(scores.items(), key=lambda item: item[1])
    return best_category if best_score > 0 else "other"


def compute_image_hash(image_path: Path) -> str:
    digest = hashlib.sha256()
    with image_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_duplicate_expense(excel_path: Path, image_hash: str) -> dict | None:
    df = load_existing_expenses(excel_path)
    if df.empty:
        return None

    hash_series = df["image_hash"].fillna("").astype(str).str.strip()
    matches = df[hash_series == image_hash]
    if matches.empty:
        return None
    return matches.iloc[-1].to_dict()


def find_duplicate_by_source_and_amount(
    excel_path: Path,
    source_label: str,
    amount: float,
) -> dict | None:
    """Fallback for older rows saved before image hashes were stored."""
    if not source_label:
        return None

    basename = Path(source_label).name
    df = load_existing_expenses(excel_path)
    if df.empty:
        return None

    for _, row in df.iloc[::-1].iterrows():
        source_value = str(row.get("source_image", ""))
        if Path(source_value).name != basename:
            continue
        try:
            row_amount = float(row.get("amount", 0))
        except (TypeError, ValueError):
            continue
        if abs(row_amount - amount) < 0.01:
            return row.to_dict()
    return None


def duplicate_error_message(duplicate: dict) -> str:
    duplicate_date = duplicate.get("date", "a previous date")
    duplicate_amount = float(duplicate.get("amount", 0))
    duplicate_description = duplicate.get("description", "Bill expense")
    return (
        "This bill has already been uploaded. "
        f"It was saved on {duplicate_date} as ${duplicate_amount:.2f} "
        f"({duplicate_description})."
    )


def load_existing_expenses(excel_path: Path) -> pd.DataFrame:
    if excel_path.exists():
        df = pd.read_excel(excel_path)
    else:
        df = pd.DataFrame(columns=EXCEL_COLUMNS)

    for column in EXCEL_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA

    return df[EXCEL_COLUMNS]


def save_expense(
    excel_path: Path,
    amount: float,
    category: str,
    description: str,
    source_image: Path | str,
    image_hash: str,
) -> str:
    df = load_existing_expenses(excel_path)
    recorded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(source_image, Path) and source_image.exists():
        source_value = str(source_image.resolve())
    else:
        source_value = str(source_image)
    new_row = pd.DataFrame(
        [
            {
                "date": recorded_at,
                "amount": amount,
                "category": category,
                "description": description,
                "source_image": source_value,
                "image_hash": image_hash,
            }
        ]
    )
    updated = pd.concat([df, new_row], ignore_index=True)
    updated = updated[EXCEL_COLUMNS]
    updated.to_excel(excel_path, index=False)
    return recorded_at


def update_last_expense_source(excel_path: Path, source_label: str) -> None:
    """Replace the temp upload path with the original filename on the last row."""
    if not source_label:
        return

    df = load_existing_expenses(excel_path)
    if df.empty:
        return

    df.iloc[-1, df.columns.get_loc("source_image")] = source_label
    df.to_excel(excel_path, index=False)


def process_bill_image(
    image_path: Path,
    excel_path: Path,
    category: str | None = None,
    description: str | None = None,
    amount_override: float | None = None,
    source_label: str | None = None,
    image_hash: str | None = None,
) -> dict:
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    content_hash = image_hash or compute_image_hash(image_path)
    duplicate = find_duplicate_expense(excel_path, content_hash)
    if duplicate is not None:
        raise DuplicateBillError(duplicate_error_message(duplicate))

    text = extract_text(image_path)
    if not text.strip():
        raise ValueError("Could not read any text from the bill image.")

    detected_category = category or detect_category(text)
    detected_description = description or guess_description(text)
    amount = amount_override if amount_override is not None else extract_amount(text)

    if amount is None:
        raise ValueError(
            "Could not detect an expense amount from the bill. "
            "Try a clearer photo or pass --amount manually."
        )

    if source_label:
        duplicate = find_duplicate_by_source_and_amount(excel_path, source_label, amount)
        if duplicate is not None:
            raise DuplicateBillError(duplicate_error_message(duplicate))

    source_for_record = source_label or image_path
    recorded_at = save_expense(
        excel_path=excel_path,
        amount=amount,
        category=detected_category,
        description=detected_description,
        source_image=source_for_record,
        image_hash=content_hash,
    )

    return {
        "amount": amount,
        "category": detected_category,
        "description": detected_description,
        "date": recorded_at,
        "excel_path": str(excel_path.resolve()),
        "excel_filename": excel_path.name,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Track family expenses from bill photos and save them to Excel."
    )
    parser.add_argument(
        "image",
        type=Path,
        help="Path to a bill image (restaurant, shop, medicine, etc.)",
    )
    parser.add_argument(
        "--excel",
        type=Path,
        default=DEFAULT_EXCEL_FILE,
        help=f"Excel file to update (default: {DEFAULT_EXCEL_FILE.name})",
    )
    parser.add_argument(
        "--category",
        choices=["restaurant", "shop", "medicine", "other"],
        help="Expense category (auto-detected from bill text when omitted)",
    )
    parser.add_argument(
        "--description",
        help="Short note for the expense (auto-detected when omitted)",
    )
    parser.add_argument(
        "--amount",
        type=float,
        help="Manual amount override if OCR cannot read the bill clearly",
    )
    parser.add_argument(
        "--show-text",
        action="store_true",
        help="Print OCR text extracted from the bill",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.show_text:
            print(extract_text(args.image))

        result = process_bill_image(
            image_path=args.image,
            excel_path=args.excel,
            category=args.category,
            description=args.description,
            amount_override=args.amount,
        )
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except DuplicateBillError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except pytesseract.TesseractNotFoundError:
        print(
            "Error: Tesseract OCR is not installed.\n"
            "Install it first:\n"
            "  macOS: brew install tesseract\n"
            "  Ubuntu/Debian: sudo apt install tesseract-ocr\n"
            "  Windows: https://github.com/UB-Mannheim/tesseract/wiki",
            file=sys.stderr,
        )
        return 1

    print("Expense saved successfully.")
    print(f"  Amount: ${result['amount']:.2f}")
    print(f"  Category: {result['category']}")
    print(f"  Description: {result['description']}")
    print(f"  Excel file: {result['excel_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
