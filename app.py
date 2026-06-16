#!/usr/bin/env python3
"""Web UI for the family expense tracker."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image

from expense_tracker import (
    DEFAULT_EXCEL_FILE,
    load_existing_expenses,
    process_bill_image,
)

CATEGORY_LABELS = {
    "restaurant": "Restaurant",
    "shop": "Shop",
    "medicine": "Medicine",
    "other": "Other",
}

CATEGORY_ICONS = {
    "restaurant": "🍽️",
    "shop": "🛒",
    "medicine": "💊",
    "other": "📄",
}


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'DM Sans', sans-serif;
        }

        .main .block-container {
            padding-top: 2rem;
            max-width: 1100px;
        }

        .hero {
            background: linear-gradient(135deg, #0f766e 0%, #14b8a6 50%, #2dd4bf 100%);
            border-radius: 20px;
            padding: 2rem 2.25rem;
            color: white;
            margin-bottom: 1.5rem;
            box-shadow: 0 12px 40px rgba(15, 118, 110, 0.25);
        }

        .hero h1 {
            margin: 0 0 0.35rem 0;
            font-size: 2rem;
            font-weight: 700;
            color: white !important;
        }

        .hero p {
            margin: 0;
            opacity: 0.92;
            font-size: 1.05rem;
        }

        .success-card {
            background: linear-gradient(180deg, #ecfdf5 0%, #f0fdf4 100%);
            border: 1px solid #86efac;
            border-radius: 16px;
            padding: 1.5rem 1.75rem;
            margin-top: 1rem;
            box-shadow: 0 4px 20px rgba(34, 197, 94, 0.12);
        }

        .success-title {
            color: #166534;
            font-size: 1.15rem;
            font-weight: 700;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .detail-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 1rem;
        }

        @media (max-width: 700px) {
            .detail-grid { grid-template-columns: 1fr; }
        }

        .detail-item {
            background: white;
            border-radius: 12px;
            padding: 1rem 1.1rem;
            border: 1px solid #d1fae5;
        }

        .detail-label {
            color: #6b7280;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            font-weight: 600;
            margin-bottom: 0.25rem;
        }

        .detail-value {
            color: #111827;
            font-size: 1.15rem;
            font-weight: 600;
        }

        .detail-value.amount {
            color: #047857;
            font-size: 1.5rem;
        }

        .excel-banner {
            margin-top: 1rem;
            background: white;
            border-radius: 12px;
            padding: 1rem 1.1rem;
            border: 1px dashed #34d399;
            color: #065f46;
            font-weight: 500;
        }

        .preview-box {
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid #e5e7eb;
            box-shadow: 0 4px 16px rgba(0,0,0,0.06);
        }

        div[data-testid="stFileUploader"] {
            border-radius: 14px;
        }

        div[data-testid="stFileUploader"] section {
            border: 2px dashed #99f6e4;
            border-radius: 14px;
            background: #f0fdfa;
        }

        div[data-testid="stFileUploader"] section:hover {
            border-color: #14b8a6;
            background: #ecfeff;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_success_card(result: dict) -> None:
    icon = CATEGORY_ICONS.get(result["category"], "📄")
    category_label = CATEGORY_LABELS.get(result["category"], result["category"])

    st.markdown(
        f"""
        <div class="success-card">
            <div class="success-title">✅ Expense saved to Excel</div>
            <div class="detail-grid">
                <div class="detail-item">
                    <div class="detail-label">Amount</div>
                    <div class="detail-value amount">${result['amount']:.2f}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Date recorded</div>
                    <div class="detail-value">{result['date']}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Category</div>
                    <div class="detail-value">{icon} {category_label}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Description</div>
                    <div class="detail-value">{result['description']}</div>
                </div>
            </div>
            <div class="excel-banner">
                📊 Uploaded to <strong>{result['excel_filename']}</strong>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def save_uploaded_image(uploaded_file) -> Path:
    suffix = Path(uploaded_file.name).suffix or ".jpg"
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_file.write(uploaded_file.getvalue())
    temp_file.close()
    return Path(temp_file.name)


def main() -> None:
    st.set_page_config(
        page_title="Family Expense Tracker",
        page_icon="🧾",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    inject_styles()

    st.markdown(
        """
        <div class="hero">
            <h1>🧾 Family Expense Tracker</h1>
            <p>Upload a bill photo — we read the amount and save it to your Excel file.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_upload, col_result = st.columns([1, 1], gap="large")

    with col_upload:
        st.subheader("Upload your bill")
        uploaded = st.file_uploader(
            "Drag and drop or browse",
            type=["jpg", "jpeg", "png", "webp", "bmp", "tiff"],
            help="Restaurant, shop, pharmacy, or any receipt with a total amount.",
        )

        if uploaded:
            image = Image.open(uploaded)
            st.markdown('<div class="preview-box">', unsafe_allow_html=True)
            st.image(image, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

        process_clicked = st.button(
            "Scan bill & save to Excel",
            type="primary",
            use_container_width=True,
            disabled=uploaded is None,
        )

    with col_result:
        st.subheader("Bill details")

        if process_clicked and uploaded:
            with st.spinner("Reading your bill…"):
                temp_path = save_uploaded_image(uploaded)
                try:
                    result = process_bill_image(
                        image_path=temp_path,
                        excel_path=DEFAULT_EXCEL_FILE,
                        source_label=uploaded.name,
                    )
                    st.session_state["last_result"] = result
                except Exception as exc:
                    st.error(str(exc))
                finally:
                    temp_path.unlink(missing_ok=True)

        if "last_result" in st.session_state:
            render_success_card(st.session_state["last_result"])
        else:
            st.info(
                "Upload a bill and click **Scan bill & save to Excel** "
                "to see the detected amount, date, and confirmation here."
            )

    st.divider()
    st.subheader("Recent expenses")

    df = load_existing_expenses(DEFAULT_EXCEL_FILE)
    if df.empty:
        st.caption("No expenses recorded yet. Your first bill will appear here.")
    else:
        display_df = df.copy()
        if "source_image" in display_df.columns:
            display_df["source_image"] = display_df["source_image"].apply(
                lambda p: Path(str(p)).name if pd.notna(p) else ""
            )
        st.dataframe(
            display_df.sort_values("date", ascending=False),
            use_container_width=True,
            hide_index=True,
        )


if __name__ == "__main__":
    main()
