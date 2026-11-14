from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


configured_data_root = os.environ.get("LAVOX_DATA_ROOT")

if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(getattr(sys, "_MEIPASS")).resolve()
    DATA_ROOT = (
        Path(configured_data_root).expanduser().resolve()
        if configured_data_root
        else Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Lavox Elektronik ERP"
    )
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    DATA_ROOT = (
        Path(configured_data_root).expanduser().resolve()
        if configured_data_root
        else PROJECT_ROOT
    )

DATABASE_PATH = DATA_ROOT / "data" / "lavox_enterprise.db"
LEGACY_DATABASE_PATH = DATA_ROOT / "data" / "lavox_erp.sqlite3"


@contextmanager
def database() -> Generator[sqlite3.Connection, None, None]:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    if not DATABASE_PATH.exists() and LEGACY_DATABASE_PATH.exists():
        shutil.move(str(LEGACY_DATABASE_PATH), str(DATABASE_PATH))

    with database() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('Admin', 'Cashier', 'Technician')),
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                action TEXT NOT NULL CHECK (action IN ('CREATE', 'UPDATE', 'DELETE', 'LOGIN', 'LOGOUT')),
                table_name TEXT NOT NULL,
                record_id INTEGER,
                old_values TEXT,
                new_values TEXT,
                timestamp TEXT NOT NULL,
                ip_address TEXT
            );

            CREATE TABLE IF NOT EXISTS warehouses (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                code TEXT NOT NULL UNIQUE,
                address TEXT,
                city TEXT,
                phone TEXT,
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY,
                sku TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                brand TEXT NOT NULL,
                description TEXT,
                unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
                critical_stock_level INTEGER NOT NULL DEFAULT 5 CHECK (critical_stock_level >= 0),
                is_tracked_serial INTEGER NOT NULL DEFAULT 0 CHECK (is_tracked_serial IN (0, 1)),
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS serial_numbers (
                id INTEGER PRIMARY KEY,
                product_id INTEGER NOT NULL REFERENCES products(id),
                serial_number TEXT NOT NULL,
                imei TEXT,
                warehouse_id INTEGER REFERENCES warehouses(id),
                status TEXT NOT NULL CHECK (status IN ('in_stock', 'sold', 'reserved', 'in_repair', 'returned', 'defective')),
                purchase_date TEXT,
                warranty_end_date TEXT,
                sale_date TEXT,
                customer_name TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(serial_number)
            );

            CREATE TABLE IF NOT EXISTS service_tickets (
                id INTEGER PRIMARY KEY,
                ticket_number TEXT NOT NULL UNIQUE,
                customer_name TEXT NOT NULL,
                customer_phone TEXT,
                device_brand TEXT NOT NULL,
                device_model TEXT NOT NULL,
                serial_number TEXT,
                imei TEXT,
                problem_description TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('intake', 'diagnosis', 'waiting_parts', 'repairing', 'quality_control', 'completed', 'delivered', 'cancelled')),
                priority TEXT NOT NULL CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
                technician_id INTEGER REFERENCES users(id),
                intake_date TEXT NOT NULL,
                completion_date TEXT,
                status_updated_at TEXT NOT NULL DEFAULT '',
                estimated_cost_cents INTEGER DEFAULT 0 CHECK (estimated_cost_cents >= 0),
                final_cost_cents INTEGER DEFAULT 0 CHECK (final_cost_cents >= 0),
                warranty_claim INTEGER NOT NULL DEFAULT 0 CHECK (warranty_claim IN (0, 1)),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS service_parts (
                id INTEGER PRIMARY KEY,
                service_ticket_id INTEGER NOT NULL REFERENCES service_tickets(id),
                product_id INTEGER NOT NULL REFERENCES products(id),
                serial_number TEXT,
                quantity_used INTEGER NOT NULL CHECK (quantity_used > 0),
                unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
                deducted_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS customers_suppliers (
                id INTEGER PRIMARY KEY,
                type TEXT NOT NULL CHECK (type IN ('customer', 'supplier', 'both')),
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                tax_number TEXT,
                phone TEXT,
                email TEXT,
                address TEXT,
                city TEXT,
                credit_limit_cents INTEGER NOT NULL DEFAULT 0 CHECK (credit_limit_cents >= 0),
                balance_cents INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pos_sales (
                id INTEGER PRIMARY KEY,
                sale_number TEXT NOT NULL UNIQUE,
                customer_code TEXT REFERENCES customers_suppliers(code),
                cashier_id INTEGER NOT NULL REFERENCES users(id),
                warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
                subtotal_cents INTEGER NOT NULL CHECK (subtotal_cents >= 0),
                tax_cents INTEGER NOT NULL CHECK (tax_cents >= 0),
                discount_cents INTEGER NOT NULL CHECK (discount_cents >= 0),
                total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
                payment_method TEXT NOT NULL CHECK (payment_method IN ('cash', 'card', 'bank_transfer', 'credit')),
                currency TEXT NOT NULL CHECK (currency IN ('TRY', 'USD', 'EUR')),
                exchange_rate REAL NOT NULL DEFAULT 1.0 CHECK (exchange_rate > 0),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pos_sale_items (
                id INTEGER PRIMARY KEY,
                pos_sale_id INTEGER NOT NULL REFERENCES pos_sales(id),
                product_id INTEGER NOT NULL REFERENCES products(id),
                serial_number TEXT,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
                line_total_cents INTEGER NOT NULL CHECK (line_total_cents >= 0)
            );

            CREATE TABLE IF NOT EXISTS purchase_orders (
                id INTEGER PRIMARY KEY,
                po_number TEXT NOT NULL UNIQUE,
                supplier_code TEXT NOT NULL REFERENCES customers_suppliers(code),
                warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
                status TEXT NOT NULL CHECK (status IN ('draft', 'sent', 'received', 'cancelled')),
                subtotal_cents INTEGER NOT NULL CHECK (subtotal_cents >= 0),
                tax_cents INTEGER NOT NULL CHECK (tax_cents >= 0),
                total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
                expected_date TEXT,
                received_date TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cash_bank_accounts (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('cash', 'bank')),
                currency TEXT NOT NULL CHECK (currency IN ('TRY', 'USD', 'EUR')),
                balance_cents INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS financial_transactions (
                id INTEGER PRIMARY KEY,
                account_id INTEGER NOT NULL REFERENCES cash_bank_accounts(id),
                type TEXT NOT NULL CHECK (type IN ('income', 'expense', 'transfer', 'sale_payment', 'purchase_payment')),
                reference_type TEXT,
                reference_id INTEGER,
                amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
                currency TEXT NOT NULL CHECK (currency IN ('TRY', 'USD', 'EUR')),
                description TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS quotes_invoices (
                id INTEGER PRIMARY KEY,
                document_number TEXT NOT NULL UNIQUE,
                type TEXT NOT NULL CHECK (type IN ('quote', 'invoice')),
                customer_code TEXT NOT NULL REFERENCES customers_suppliers(code),
                status TEXT NOT NULL CHECK (status IN ('draft', 'sent', 'accepted', 'paid', 'overdue', 'cancelled')),
                subtotal_cents INTEGER NOT NULL CHECK (subtotal_cents >= 0),
                tax_cents INTEGER NOT NULL CHECK (tax_cents >= 0),
                discount_cents INTEGER NOT NULL CHECK (discount_cents >= 0),
                total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
                currency TEXT NOT NULL CHECK (currency IN ('TRY', 'USD', 'EUR')),
                issue_date TEXT NOT NULL,
                due_date TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_audit_user_time
                ON audit_logs(user_id, timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_audit_table_record
                ON audit_logs(table_name, record_id);
            CREATE INDEX IF NOT EXISTS idx_serial_product
                ON serial_numbers(product_id, status);
            CREATE INDEX IF NOT EXISTS idx_serial_imei
                ON serial_numbers(imei);
            CREATE INDEX IF NOT EXISTS idx_service_ticket_status
                ON service_tickets(status, technician_id);
            CREATE INDEX IF NOT EXISTS idx_service_ticket_customer
                ON service_tickets(customer_name);
            CREATE INDEX IF NOT EXISTS idx_pos_sale_customer
                ON pos_sales(customer_code, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_pos_sale_cashier
                ON pos_sales(cashier_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_purchase_order_supplier
                ON purchase_orders(supplier_code, status);
            CREATE INDEX IF NOT EXISTS idx_financial_account_time
                ON financial_transactions(account_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_quote_customer_status
                ON quotes_invoices(customer_code, status);
            """
        )
        service_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(service_tickets)")
        }
        if "status_updated_at" not in service_columns:
            connection.execute(
                "ALTER TABLE service_tickets ADD COLUMN status_updated_at TEXT NOT NULL DEFAULT ''"
            )
        connection.execute(
            """
            UPDATE service_tickets
            SET status_updated_at = COALESCE(NULLIF(intake_date, ''), created_at)
            WHERE status_updated_at = ''
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_service_ticket_status_time
            ON service_tickets(status, status_updated_at)
            """
        )
