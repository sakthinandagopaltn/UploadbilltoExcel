#!/usr/bin/env python3
"""REST API for the family expense tracker."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from expense_tracker import (
    DEFAULT_EXCEL_FILE,
    DuplicateBillError,
    duplicate_error_message,
    find_duplicate_expense,
    load_existing_expenses,
    process_bill_image,
)

app = FastAPI(title="Family Expense Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}


@app.on_event("startup")
def prepare_storage() -> None:
    """Ensure the Excel file has the latest columns (including image_hash)."""
    df = load_existing_expenses(DEFAULT_EXCEL_FILE)
    df.to_excel(DEFAULT_EXCEL_FILE, index=False)


def expenses_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []

    records = df.sort_values("date", ascending=False).to_dict(orient="records")
    for record in records:
        if "source_image" in record and pd.notna(record["source_image"]):
            record["source_image"] = Path(str(record["source_image"])).name
        if "amount" in record and pd.notna(record["amount"]):
            record["amount"] = round(float(record["amount"]), 2)
    return records


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/expenses")
def list_expenses() -> dict[str, Any]:
    df = load_existing_expenses(DEFAULT_EXCEL_FILE)
    return {
        "excel_filename": DEFAULT_EXCEL_FILE.name,
        "expenses": expenses_to_records(df),
    }


@app.post("/api/process-bill")
async def process_bill(
    image: UploadFile = File(...),
) -> dict[str, Any]:
    suffix = Path(image.filename or "bill.jpg").suffix.lower() or ".jpg"
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Use: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    contents = await image.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    content_hash = hashlib.sha256(contents).hexdigest()
    duplicate = find_duplicate_expense(DEFAULT_EXCEL_FILE, content_hash)
    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail=duplicate_error_message(duplicate),
        )

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(contents)
            temp_path = Path(temp_file.name)

        result = process_bill_image(
            image_path=temp_path,
            excel_path=DEFAULT_EXCEL_FILE,
            source_label=image.filename,
            image_hash=content_hash,
        )
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DuplicateBillError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to process bill: {exc}") from exc
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)
