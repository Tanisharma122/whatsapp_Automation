"""
sheets_client.py — Reusable Google Sheets client.

This module handles authentication and raw read/write operations
against the Google Sheets API using the gspread library.

Authentication uses a Google Cloud Service Account. The path to the
JSON credentials file is loaded from the GOOGLE_SERVICE_ACCOUNT_JSON_PATH
environment variable — never hardcoded.

WHY gspread instead of raw google-api-python-client?
  gspread wraps the low-level API with a clean Pythonic interface:
    - worksheet.get_all_records()  → list of dicts, headers are keys
    - worksheet.append_row([...])  → appends a new row safely
  The raw client still underpins gspread, so we get all its reliability.

Error handling:
    - gspread.exceptions.SpreadsheetNotFound   → wrong ID or no access
    - gspread.exceptions.WorksheetNotFound     → wrong sheet/tab name
    - google.auth.exceptions.TransportError    → network failure
    - gspread.exceptions.APIError (429)        → quota exceeded
    - FileNotFoundError                        → credentials file missing
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

import gspread
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound
from google.oauth2.service_account import Credentials

from app.config import settings

logger = logging.getLogger(__name__)

# The scopes required to read and write Google Sheets
_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


class SheetsClientError(Exception):
    """Raised when a Google Sheets operation fails."""

    def __init__(self, message: str, original: Optional[Exception] = None) -> None:
        super().__init__(message)
        self.original = original


def _get_credentials_path() -> Path:
    """
    Resolve and validate the service account JSON file path.
    The path is relative to the project root (parent of src/).
    """
    raw_path = settings.google_service_account_json_path
    if not raw_path:
        raise SheetsClientError(
            "GOOGLE_SERVICE_ACCOUNT_JSON_PATH is not configured. "
            "Set this env var to the path of your service account JSON file."
        )

    # Resolve relative to project root (two levels above src/app/)
    project_root = Path(__file__).resolve().parents[3]
    creds_path = Path(raw_path)
    if not creds_path.is_absolute():
        creds_path = project_root / creds_path

    if not creds_path.exists():
        raise SheetsClientError(
            f"Google credentials file not found at: {creds_path}. "
            f"Make sure the file exists and GOOGLE_SERVICE_ACCOUNT_JSON_PATH is correct."
        )

    return creds_path


def _build_gspread_client() -> gspread.Client:
    """
    Authenticate with Google and return a gspread client.
    Raises SheetsClientError on any configuration or auth failure.
    """
    try:
        creds_path = _get_credentials_path()
        creds = Credentials.from_service_account_file(str(creds_path), scopes=_SCOPES)
        client = gspread.authorize(creds)
        logger.info("Google Sheets client authenticated successfully.")
        return client
    except SheetsClientError:
        raise
    except Exception as exc:
        raise SheetsClientError(
            f"Failed to authenticate with Google Sheets API: {exc}", original=exc
        ) from exc


class SheetsClient:
    """
    A thin wrapper around gspread for reading from and writing to Google Sheets.

    Usage:
        client = SheetsClient()
        rows = client.read_all_records(spreadsheet_id="abc123", worksheet_name="Inventory")
        client.append_row(spreadsheet_id="abc123", worksheet_name="Orders", row=[...])
    """

    def __init__(self) -> None:
        self._client: Optional[gspread.Client] = None

    def _ensure_connected(self) -> gspread.Client:
        """Lazily build and cache the gspread client."""
        if self._client is None:
            self._client = _build_gspread_client()
        return self._client

    def read_all_records(
        self, spreadsheet_id: str, worksheet_name: str
    ) -> list[dict[str, Any]]:
        """
        Read all rows from a worksheet as a list of dicts.

        The first row of the sheet is used as the dictionary keys.
        Completely empty rows are automatically skipped by gspread.

        Args:
            spreadsheet_id:  The long ID from the Google Sheets URL.
            worksheet_name:  The name of the tab (e.g. "Inventory").

        Returns:
            A list of dicts, one dict per data row.

        Raises:
            SheetsClientError on any API, auth, or connectivity failure.
        """
        try:
            gc = self._ensure_connected()
            sh = gc.open_by_key(spreadsheet_id)
            ws = sh.worksheet(worksheet_name)
            records = ws.get_all_records()
            logger.info(
                "Read %d records from sheet '%s' (id=...%s)",
                len(records), worksheet_name, spreadsheet_id[-6:]
            )
            return records
        except SpreadsheetNotFound:
            raise SheetsClientError(
                f"Spreadsheet not found (id=...{spreadsheet_id[-6:]}). "
                "Check the ID and that the service account has been granted access."
            )
        except WorksheetNotFound:
            raise SheetsClientError(
                f"Worksheet '{worksheet_name}' not found in spreadsheet id=...{spreadsheet_id[-6:]}. "
                "Check the tab name."
            )
        except APIError as exc:
            if exc.response.status_code == 429:
                raise SheetsClientError(
                    "Google Sheets API quota exceeded. Wait and retry.", original=exc
                )
            raise SheetsClientError(
                f"Google Sheets API error: {exc}", original=exc
            ) from exc
        except Exception as exc:
            raise SheetsClientError(
                f"Unexpected error reading from Google Sheets: {exc}", original=exc
            ) from exc

    def read_raw_column(
        self, spreadsheet_id: str, worksheet_name: str, col: int = 1
    ) -> list[str]:
        """
        Read a single column as a flat list of strings.

        Used for the faqs sheet which stores all fields in one column.

        Args:
            spreadsheet_id:  Sheet ID.
            worksheet_name:  Tab name.
            col:             1-based column index (default: 1 = column A).

        Returns:
            List of string values from that column.
        """
        try:
            gc = self._ensure_connected()
            sh = gc.open_by_key(spreadsheet_id)
            ws = sh.worksheet(worksheet_name)
            col_values = ws.col_values(col)
            logger.info(
                "Read %d rows from column %d of sheet '%s'",
                len(col_values), col, worksheet_name
            )
            return col_values
        except (SpreadsheetNotFound, WorksheetNotFound, APIError, Exception) as exc:
            raise SheetsClientError(
                f"Error reading column from sheet '{worksheet_name}': {exc}", original=exc
            ) from exc

    def append_row(
        self, spreadsheet_id: str, worksheet_name: str, row: list[Any]
    ) -> None:
        """
        Append a single new row to the end of a worksheet.

        gspread.append_row() always adds AFTER the last row with data,
        so it won't overwrite existing records.

        Args:
            spreadsheet_id:  Sheet ID.
            worksheet_name:  Tab name.
            row:             A list of values in column order.

        Raises:
            SheetsClientError on any failure.
        """
        try:
            gc = self._ensure_connected()
            sh = gc.open_by_key(spreadsheet_id)
            ws = sh.worksheet(worksheet_name)
            ws.append_row(row, value_input_option="USER_ENTERED")
            logger.info(
                "Appended row to sheet '%s' (id=...%s)",
                worksheet_name, spreadsheet_id[-6:]
            )
        except SpreadsheetNotFound:
            raise SheetsClientError(
                f"Spreadsheet not found (id=...{spreadsheet_id[-6:]}). "
                "Check the ID and service account permissions."
            )
        except WorksheetNotFound:
            raise SheetsClientError(
                f"Worksheet '{worksheet_name}' not found. Check the tab name."
            )
        except APIError as exc:
            if exc.response.status_code == 429:
                raise SheetsClientError(
                    "Google Sheets API quota exceeded. Wait and retry.", original=exc
                )
            raise SheetsClientError(
                f"Google Sheets API error when appending row: {exc}", original=exc
            ) from exc
        except Exception as exc:
            raise SheetsClientError(
                f"Unexpected error appending row to Google Sheets: {exc}", original=exc
            ) from exc

    def find_row_by_value(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
        column_header: str,
        value: str,
    ) -> Optional[dict[str, Any]]:
        """
        Find the first row where a specific column matches a value.

        Used for duplicate order detection — checks if an order_id already exists.

        Returns:
            The matching row as a dict, or None if not found.
        """
        records = self.read_all_records(spreadsheet_id, worksheet_name)
        for record in records:
            if str(record.get(column_header, "")).strip() == str(value).strip():
                return record
        return None
