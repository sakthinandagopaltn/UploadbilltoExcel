#!/usr/bin/env python3
"""Track family expenses from bill images and save them to Excel."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter

DEFAULT_EXCEL_FILE = Path(__file__).resolve().parent / "family_expenses.xlsx"
EXCEL_COLUMNS = ["date", "amount", "category", "description", "source_image"]

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
    "total",
    "amount due",
    "grand total",
    "balance due",
    "net amount",
    "payable",
    "subtotal",
)

AMOUNT_PATTERN = re.compile(
    r"(?:₹|Rs\.?|INR|\$|USD|€|EUR)?\s*"
    r"(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)",
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
    return amounts


def extract_amount(text: str) -> float | None:
    """Pick the most likely total amount from OCR text."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    priority_amounts: list[float] = []

    for line in lines:
        lower_line = line.lower()
        if any(keyword in lower_line for keyword in TOTAL_KEYWORDS):
            priority_amounts.extend(find_amounts_in_line(line))

    if priority_amounts:
        return max(priority_amounts)

    all_amounts = [amount for line in lines for amount in find_amounts_in_line(line)]
    if not all_amounts:
        return None

    # Bills often show the final total as one of the larger values.
    return max(all_amounts)


def detect_category(text: str) -> str:
    lower_text = text.lower()
    scores = {
        category: sum(1 for keyword in keywords if keyword in lower_text)
        for category, keywords in CATEGORY_KEYWORDS.items()
    }
    best_category, best_score = max(scores.items(), key=lambda item: item[1])
    return best_category if best_score > 0 else "other"


def guess_description(text: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip()
        if len(cleaned) >= 3 and not AMOUNT_PATTERN.fullmatch(cleaned.replace(" ", "")):
            if not any(keyword in cleaned.lower() for keyword in TOTAL_KEYWORDS):
                return cleaned[:120]
    return "Bill expense"


def load_existing_expenses(excel_path: Path) -> pd.DataFrame:
    if excel_path.exists():
        return pd.read_excel(excel_path)
    return pd.DataFrame(columns=EXCEL_COLUMNS)


def save_expense(
    excel_path: Path,
    amount: float,
    category: str,
    description: str,
    source_image: Path,
) -> None:
    df = load_existing_expenses(excel_path)
    new_row = pd.DataFrame(
        [
            {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "amount": amount,
                "category": category,
                "description": description,
                "source_image": str(source_image.resolve()),
            }
        ]
    )
    updated = pd.concat([df, new_row], ignore_index=True)
    updated.to_excel(excel_path, index=False)


def process_bill_image(
    image_path: Path,
    excel_path: Path,
    category: str | None = None,
    description: str | None = None,
    amount_override: float | None = None,
) -> dict:
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

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

    save_expense(
        excel_path=excel_path,
        amount=amount,
        category=detected_category,
        description=detected_description,
        source_image=image_path,
    )

    return {
        "amount": amount,
        "category": detected_category,
        "description": detected_description,
        "excel_path": str(excel_path.resolve()),
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
