from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ..database import database
from ..kvkk_security import timestamp_now


class SalesFinanceError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)

VALID_CURRENCIES = ("TRY", "USD", "EUR")
VALID_PAYMENT_METHODS = ("cash", "card", "bank_transfer", "credit")


def _now() -> str:
    return timestamp_now()


def _cents(value: Any) -> int:
    return int(Decimal(str(value)) * 100)


def list_cash_bank_accounts() -> list[dict[str, Any]]:
    with database() as connection:
        rows = connection.execute(
            """
            SELECT id, name, type, currency, balance_cents, is_active, created_at
            FROM cash_bank_accounts WHERE is_active = 1
            ORDER BY type, name COLLATE NOCASE
            """
        ).fetchall()
    return [dict(row) for row in rows]


def create_cash_bank_account(
    payload: dict[str, Any],
    current_user: dict[str, Any],
) -> dict[str, Any]:
    name = (payload.get("name") or "").strip()
    account_type = (payload.get("type") or "").strip().lower()
    currency = (payload.get("currency") or "TRY").strip().upper()
    opening_balance = payload.get("opening_balance", 0)

    if not name:
        raise SalesFinanceError(422, "Account name is required.")
    if account_type not in ("cash", "bank"):
        raise SalesFinanceError(422, "Account type must be 'cash' or 'bank'.")
    if currency not in VALID_CURRENCIES:
        raise SalesFinanceError(422, f"Currency must be one of: {', '.join(VALID_CURRENCIES)}.")
    try:
        balance_cents = _cents(opening_balance)
    except Exception:
        raise SalesFinanceError(422, "Opening balance must be a valid amount.")

    try:
        with database() as connection:
            cursor = connection.execute(
                """
                INSERT INTO cash_bank_accounts (name, type, currency, balance_cents, is_active, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (name, account_type, currency, balance_cents, _now()),
            )
            row = connection.execute(
                """
                SELECT id, name, type, currency, balance_cents, is_active, created_at
                FROM cash_bank_accounts WHERE id = ?
                """,
                (cursor.lastrowid,),
            ).fetchone()
    except sqlite3.IntegrityError as error:
        raise SalesFinanceError(409, "Account could not be created.") from error
    if row is None:
        raise RuntimeError("Account could not be read back.")
    return dict(row)


import sqlite3  # noqa: E402


def record_financial_transaction(
    payload: dict[str, Any],
    current_user: dict[str, Any],
) -> dict[str, Any]:
    account_id = payload.get("account_id")
    tx_type = (payload.get("type") or "").strip().lower()
    amount = payload.get("amount")
    currency = (payload.get("currency") or "TRY").strip().upper()
    reference_type = payload.get("reference_type")
    reference_id = payload.get("reference_id")
    description = (payload.get("description") or "").strip() or None

    if not account_id:
        raise SalesFinanceError(422, "Account is required.")
    if tx_type not in ("income", "expense", "transfer", "sale_payment", "purchase_payment"):
        raise SalesFinanceError(422, "Invalid transaction type.")
    try:
        amount_cents = _cents(amount)
    except Exception:
        raise SalesFinanceError(422, "Amount must be a valid amount.")
    if amount_cents <= 0:
        raise SalesFinanceError(422, "Amount must be greater than zero.")
    if currency not in VALID_CURRENCIES:
        raise SalesFinanceError(422, f"Currency must be one of: {', '.join(VALID_CURRENCIES)}.")

    with database() as connection:
        account = connection.execute(
            "SELECT id, currency, balance_cents FROM cash_bank_accounts WHERE id = ? AND is_active = 1",
            (account_id,),
        ).fetchone()
        if account is None:
            raise SalesFinanceError(404, "Active account not found.")

        new_balance = int(account["balance_cents"])
        if tx_type == "income":
            new_balance += amount_cents
        elif tx_type == "expense":
            new_balance -= amount_cents

        cursor = connection.execute(
            """
            INSERT INTO financial_transactions
                (account_id, type, reference_type, reference_id, amount_cents,
                 currency, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (account_id, tx_type, reference_type, reference_id, amount_cents,
             currency, description, _now()),
        )
        connection.execute(
            "UPDATE cash_bank_accounts SET balance_cents = ? WHERE id = ?",
            (new_balance, account_id),
        )
        row = connection.execute(
            """
            SELECT id, account_id, type, reference_type, reference_id, amount_cents,
                   currency, description, created_at
            FROM financial_transactions WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return dict(row)


def list_customers_suppliers(
    party_type: str | None = None,
) -> list[dict[str, Any]]:
    if party_type is not None and party_type not in ("customer", "supplier", "both"):
        raise SalesFinanceError(422, "Party type must be customer, supplier, or both.")

    with database() as connection:
        if party_type:
            rows = connection.execute(
                """
                SELECT id, type, code, name, tax_number, phone, email, address, city,
                       credit_limit_cents, balance_cents, is_active, created_at
                FROM customers_suppliers WHERE type = ? AND is_active = 1
                ORDER BY name COLLATE NOCASE
                """,
                (party_type,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT id, type, code, name, tax_number, phone, email, address, city,
                       credit_limit_cents, balance_cents, is_active, created_at
                FROM customers_suppliers WHERE is_active = 1
                ORDER BY type, name COLLATE NOCASE
                """,
            ).fetchall()
    return [dict(row) for row in rows]


def create_customer_supplier(
    payload: dict[str, Any],
    current_user: dict[str, Any],
) -> dict[str, Any]:
    party_type = (payload.get("type") or "").strip().lower()
    code = (payload.get("code") or "").strip().upper()
    name = (payload.get("name") or "").strip()
    tax_number = (payload.get("tax_number") or "").strip() or None
    phone = (payload.get("phone") or "").strip() or None
    email = (payload.get("email") or "").strip() or None
    address = (payload.get("address") or "").strip() or None
    city = (payload.get("city") or "").strip() or None
    credit_limit = payload.get("credit_limit", 0)

    if party_type not in ("customer", "supplier", "both"):
        raise SalesFinanceError(422, "Type must be customer, supplier, or both.")
    if not code:
        raise SalesFinanceError(422, "Party code is required.")
    if not name:
        raise SalesFinanceError(422, "Party name is required.")
    try:
        credit_limit_cents = _cents(credit_limit)
    except Exception:
        raise SalesFinanceError(422, "Credit limit must be a valid amount.")

    try:
        with database() as connection:
            cursor = connection.execute(
                """
                INSERT INTO customers_suppliers
                    (type, code, name, tax_number, phone, email, address, city,
                     credit_limit_cents, balance_cents, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?)
                """,
                (party_type, code, name, tax_number, phone, email, address, city,
                 credit_limit_cents, _now()),
            )
            row = connection.execute(
                """
                SELECT id, type, code, name, tax_number, phone, email, address, city,
                       credit_limit_cents, balance_cents, is_active, created_at
                FROM customers_suppliers WHERE id = ?
                """,
                (cursor.lastrowid,),
            ).fetchone()
    except sqlite3.IntegrityError as error:
        raise SalesFinanceError(409, "A party with this code already exists.") from error
    if row is None:
        raise RuntimeError("Party could not be read back.")
    return dict(row)


def create_pos_sale(
    payload: dict[str, Any],
    current_user: dict[str, Any],
) -> dict[str, Any]:
    customer_code = (payload.get("customer_code") or "").strip().upper() or None
    cashier_id = current_user.get("id")
    warehouse_id = payload.get("warehouse_id")
    payment_method = (payload.get("payment_method") or "cash").strip().lower()
    currency = (payload.get("currency") or "TRY").strip().upper()
    exchange_rate = payload.get("exchange_rate", 1.0)
    items = payload.get("items", [])

    if not warehouse_id:
        raise SalesFinanceError(422, "Warehouse is required.")
    if payment_method not in VALID_PAYMENT_METHODS:
        raise SalesFinanceError(422, f"Payment method must be one of: {', '.join(VALID_PAYMENT_METHODS)}.")
    if currency not in VALID_CURRENCIES:
        raise SalesFinanceError(422, f"Currency must be one of: {', '.join(VALID_CURRENCIES)}.")
    try:
        exchange_rate = float(exchange_rate)
    except Exception:
        raise SalesFinanceError(422, "Exchange rate must be a valid number.")
    if exchange_rate <= 0:
        raise SalesFinanceError(422, "Exchange rate must be greater than zero.")
    if not items:
        raise SalesFinanceError(422, "At least one sale item is required.")

    if customer_code:
        with database() as connection:
            party = connection.execute(
                "SELECT code, credit_limit_cents, balance_cents FROM customers_suppliers WHERE code = ?",
                (customer_code,),
            ).fetchone()
            if party is None:
                raise SalesFinanceError(404, "Customer not found.")

    subtotal_cents = 0
    tax_cents = 0
    discount_cents = 0

    with database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if customer_code:
            party = connection.execute(
                "SELECT code, credit_limit_cents, balance_cents FROM customers_suppliers WHERE code = ?",
                (customer_code,),
            ).fetchone()
            if party is None:
                raise SalesFinanceError(404, "Customer not found.")
            projected_balance = int(party["balance_cents"])
            if payment_method == "credit":
                projected_balance += 0  # total added below

        sale_number = "POS-" + datetime.now().strftime("%Y%m%d%H%M%S")
        cursor = connection.execute(
            """
            INSERT INTO pos_sales
                (sale_number, customer_code, cashier_id, warehouse_id, subtotal_cents,
                 tax_cents, discount_cents, total_cents, payment_method, currency,
                 exchange_rate, created_at)
            VALUES (?, ?, ?, ?, 0, 0, 0, 0, ?, ?, ?, ?)
            """,
            (sale_number, customer_code, cashier_id, warehouse_id,
             payment_method, currency, exchange_rate, _now()),
        )
        sale_id = cursor.lastrowid

        for item in items:
            product_id = item.get("product_id")
            quantity = item.get("quantity", 1)
            serial_number = (item.get("serial_number") or "").strip().upper() or None
            unit_price = item.get("unit_price")
            line_discount = item.get("discount", 0)

            if not product_id:
                raise SalesFinanceError(422, "Product is required for each item.")
            try:
                quantity = int(quantity)
            except Exception:
                raise SalesFinanceError(422, "Quantity must be an integer.")
            if quantity <= 0:
                raise SalesFinanceError(422, "Quantity must be greater than zero.")
            try:
                unit_price_cents = _cents(unit_price)
            except Exception:
                raise SalesFinanceError(422, "Unit price must be a valid amount.")

            product = connection.execute(
                "SELECT id, sku, is_tracked_serial FROM products WHERE id = ? AND is_active = 1",
                (product_id,),
            ).fetchone()
            if product is None:
                raise SalesFinanceError(404, f"Product {product_id} not found.")

            if product["is_tracked_serial"] and not serial_number:
                raise SalesFinanceError(422, f"Serial number required for tracked product {product['sku']}.")

            if product["is_tracked_serial"]:
                stock_row = connection.execute(
                    """
                    SELECT COUNT(*) AS in_stock FROM serial_numbers
                    WHERE product_id = ? AND status = 'in_stock' AND warehouse_id = ?
                    """,
                    (product_id, warehouse_id),
                ).fetchone()
                if int(stock_row["in_stock"]) < quantity:
                    raise SalesFinanceError(409, f"Insufficient stock for product {product['sku']}.")

            line_total_cents = unit_price_cents * quantity - int(Decimal(str(line_discount)) * 100)
            if line_total_cents < 0:
                line_total_cents = 0

            connection.execute(
                """
                INSERT INTO pos_sale_items
                    (pos_sale_id, product_id, serial_number, quantity,
                     unit_price_cents, line_total_cents)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (sale_id, product_id, serial_number, quantity,
                 unit_price_cents, line_total_cents),
            )

            if product["is_tracked_serial"]:
                serials = connection.execute(
                    """
                    SELECT id FROM serial_numbers
                    WHERE product_id = ? AND status = 'in_stock' AND warehouse_id = ?
                    LIMIT ?
                    """,
                    (product_id, warehouse_id, quantity),
                ).fetchall()
                for serial_row in serials:
                    connection.execute(
                        "UPDATE serial_numbers SET status = 'sold' WHERE id = ?",
                        (serial_row["id"],),
                    )

            subtotal_cents += line_total_cents

        tax_rate = Decimal("0.18")
        tax_cents = int(subtotal_cents * tax_rate)
        total_cents = subtotal_cents + tax_cents - discount_cents

        if customer_code and payment_method == "credit":
            party = connection.execute(
                "SELECT credit_limit_cents, balance_cents FROM customers_suppliers WHERE code = ?",
                (customer_code,),
            ).fetchone()
            projected = int(party["balance_cents"]) + total_cents
            if projected > int(party["credit_limit_cents"]) and int(party["credit_limit_cents"]) >= 0:
                raise SalesFinanceError(409, "Customer credit limit would be exceeded.")

        connection.execute(
            """
            UPDATE pos_sales
            SET subtotal_cents = ?, tax_cents = ?, discount_cents = ?, total_cents = ?
            WHERE id = ?
            """,
            (subtotal_cents, tax_cents, discount_cents, total_cents, sale_id),
        )

        if payment_method != "credit":
            account = connection.execute(
                """
                SELECT id FROM cash_bank_accounts
                WHERE type = 'cash' AND currency = ? AND is_active = 1 LIMIT 1
                """,
                (currency,),
            ).fetchone()
            if account:
                connection.execute(
                    """
                    INSERT INTO financial_transactions
                        (account_id, type, reference_type, reference_id, amount_cents,
                         currency, description, created_at)
                    VALUES (?, 'sale_payment', 'pos_sale', ?, ?, ?, ?, ?)
                    """,
                    (account["id"], sale_id, total_cents, currency,
                     f"POS sale {sale_number}", _now()),
                )
                connection.execute(
                    "UPDATE cash_bank_accounts SET balance_cents = balance_cents + ? WHERE id = ?",
                    (total_cents, account["id"]),
                )

        if customer_code:
            connection.execute(
                """
                UPDATE customers_suppliers
                SET balance_cents = balance_cents + ?
                WHERE code = ?
                """,
                (total_cents if payment_method == "credit" else 0, customer_code),
            )

        row = connection.execute(
            """
            SELECT id, sale_number, customer_code, cashier_id, warehouse_id,
                   subtotal_cents, tax_cents, discount_cents, total_cents,
                   payment_method, currency, exchange_rate, created_at
            FROM pos_sales WHERE id = ?
            """,
            (sale_id,),
        ).fetchone()
    return dict(row)


def list_pos_sales(
    customer_code: str | None = None,
    cashier_id: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    if customer_code:
        conditions.append("customer_code = ?")
        params.append(customer_code)
    if cashier_id is not None:
        conditions.append("cashier_id = ?")
        params.append(cashier_id)
    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    with database() as connection:
        rows = connection.execute(
            f"""
            SELECT id, sale_number, customer_code, cashier_id, warehouse_id,
                   subtotal_cents, tax_cents, discount_cents, total_cents,
                   payment_method, currency, exchange_rate, created_at
            FROM pos_sales {where_clause}
            ORDER BY created_at DESC LIMIT ?
            """,
            params + [limit],
        ).fetchall()
    return [dict(row) for row in rows]


def create_purchase_order(
    payload: dict[str, Any],
    current_user: dict[str, Any],
) -> dict[str, Any]:
    supplier_code = (payload.get("supplier_code") or "").strip().upper()
    warehouse_id = payload.get("warehouse_id")
    expected_date = payload.get("expected_date")
    items = payload.get("items", [])

    if not supplier_code:
        raise SalesFinanceError(422, "Supplier code is required.")
    if not warehouse_id:
        raise SalesFinanceError(422, "Warehouse is required.")
    if not items:
        raise SalesFinanceError(422, "At least one purchase item is required.")

    subtotal_cents = 0
    for item in items:
        try:
            unit_price_cents = _cents(item.get("unit_price"))
        except Exception:
            raise SalesFinanceError(422, "Unit price must be a valid amount.")
        try:
            quantity = int(item.get("quantity", 1))
        except Exception:
            raise SalesFinanceError(422, "Quantity must be an integer.")
        if quantity <= 0:
            raise SalesFinanceError(422, "Quantity must be greater than zero.")
        subtotal_cents += unit_price_cents * quantity

    tax_rate = Decimal("0.18")
    tax_cents = int(subtotal_cents * tax_rate)
    total_cents = subtotal_cents + tax_cents

    po_number = "PO-" + datetime.now().strftime("%Y%m%d%H%M%S")

    try:
        with database() as connection:
            supplier = connection.execute(
                "SELECT code FROM customers_suppliers WHERE code = ? AND type IN ('supplier', 'both')",
                (supplier_code,),
            ).fetchone()
            if supplier is None:
                raise SalesFinanceError(404, "Supplier not found.")
            warehouse = connection.execute(
                "SELECT id FROM warehouses WHERE id = ? AND is_active = 1", (warehouse_id,)
            ).fetchone()
            if warehouse is None:
                raise SalesFinanceError(404, "Active warehouse not found.")

            cursor = connection.execute(
                """
                INSERT INTO purchase_orders
                    (po_number, supplier_code, warehouse_id, status, subtotal_cents,
                     tax_cents, total_cents, expected_date, received_date, created_at)
                VALUES (?, ?, ?, 'draft', ?, ?, ?, ?, NULL, ?)
                """,
                (po_number, supplier_code, warehouse_id, subtotal_cents,
                 tax_cents, total_cents, expected_date, _now()),
            )
            po_id = cursor.lastrowid

            row = connection.execute(
                """
                SELECT id, po_number, supplier_code, warehouse_id, status,
                       subtotal_cents, tax_cents, total_cents, expected_date,
                       received_date, created_at
                FROM purchase_orders WHERE id = ?
                """,
                (po_id,),
            ).fetchone()
    except sqlite3.IntegrityError as error:
        raise SalesFinanceError(409, "Purchase order could not be created.") from error
    return dict(row)


def receive_purchase_order(
    po_id: int,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    with database() as connection:
        po = connection.execute(
            "SELECT id, po_number, status, warehouse_id FROM purchase_orders WHERE id = ?",
            (po_id,),
        ).fetchone()
        if po is None:
            raise SalesFinanceError(404, "Purchase order not found.")
        if po["status"] == "received":
            raise SalesFinanceError(409, "Purchase order already received.")
        if po["status"] == "cancelled":
            raise SalesFinanceError(409, "Cannot receive a cancelled purchase order.")

        received_date = _now()
        connection.execute(
            """
            UPDATE purchase_orders
            SET status = 'received', received_date = ?
            WHERE id = ?
            """,
            (received_date, po_id),
        )
        updated = connection.execute(
            """
            SELECT id, po_number, supplier_code, warehouse_id, status,
                   subtotal_cents, tax_cents, total_cents, expected_date,
                   received_date, created_at
            FROM purchase_orders WHERE id = ?
            """,
            (po_id,),
        ).fetchone()
    return dict(updated)


def create_quote_invoice(
    payload: dict[str, Any],
    current_user: dict[str, Any],
) -> dict[str, Any]:
    document_type = (payload.get("type") or "invoice").strip().lower()
    customer_code = (payload.get("customer_code") or "").strip().upper()
    status = (payload.get("status") or "draft").strip().lower()
    currency = (payload.get("currency") or "TRY").strip().upper()
    issue_date = payload.get("issue_date")
    due_date = payload.get("due_date")
    items = payload.get("items", [])

    if document_type not in ("quote", "invoice"):
        raise SalesFinanceError(422, "Type must be 'quote' or 'invoice'.")
    if not customer_code:
        raise SalesFinanceError(422, "Customer code is required.")
    if status not in ("draft", "sent", "accepted", "paid", "overdue", "cancelled"):
        raise SalesFinanceError(422, "Invalid status.")
    if currency not in VALID_CURRENCIES:
        raise SalesFinanceError(422, f"Currency must be one of: {', '.join(VALID_CURRENCIES)}.")
    if not items:
        raise SalesFinanceError(422, "At least one item is required.")
    if not issue_date:
        raise SalesFinanceError(422, "Issue date is required.")

    subtotal_cents = 0
    for item in items:
        try:
            unit_price_cents = _cents(item.get("unit_price"))
        except Exception:
            raise SalesFinanceError(422, "Unit price must be a valid amount.")
        try:
            quantity = int(item.get("quantity", 1))
        except Exception:
            raise SalesFinanceError(422, "Quantity must be an integer.")
        if quantity <= 0:
            raise SalesFinanceError(422, "Quantity must be greater than zero.")
        discount = int(Decimal(str(item.get("discount", 0))) * 100)
        subtotal_cents += unit_price_cents * quantity - discount

    tax_rate = Decimal("0.18")
    tax_cents = int(subtotal_cents * tax_rate)
    discount_cents = sum(int(Decimal(str(i.get("discount", 0))) * 100) for i in items)
    total_cents = subtotal_cents + tax_cents - discount_cents

    prefix = "QTE-" if document_type == "quote" else "INV-"
    document_number = prefix + datetime.now().strftime("%Y%m%d%H%M%S")

    try:
        with database() as connection:
            customer = connection.execute(
                "SELECT code FROM customers_suppliers WHERE code = ? AND type IN ('customer', 'both')",
                (customer_code,),
            ).fetchone()
            if customer is None:
                raise SalesFinanceError(404, "Customer not found.")

            cursor = connection.execute(
                """
                INSERT INTO quotes_invoices
                    (document_number, type, customer_code, status, subtotal_cents,
                     tax_cents, discount_cents, total_cents, currency,
                     issue_date, due_date, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (document_number, document_type, customer_code, status, subtotal_cents,
                 tax_cents, discount_cents, total_cents, currency,
                 issue_date, due_date, _now()),
            )
            row = connection.execute(
                """
                SELECT id, document_number, type, customer_code, status,
                       subtotal_cents, tax_cents, discount_cents, total_cents,
                       currency, issue_date, due_date, created_at
                FROM quotes_invoices WHERE id = ?
                """,
                (cursor.lastrowid,),
            ).fetchone()
    except sqlite3.IntegrityError as error:
        raise SalesFinanceError(409, "Document could not be created.") from error
    return dict(row)


def convert_quote_to_invoice(
    document_id: int,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    with database() as connection:
        doc = connection.execute(
            "SELECT id, document_number, type, status FROM quotes_invoices WHERE id = ?",
            (document_id,),
        ).fetchone()
        if doc is None:
            raise SalesFinanceError(404, "Document not found.")
        if doc["type"] != "quote":
            raise SalesFinanceError(409, "Only quotes can be converted to invoices.")
        if doc["status"] in ("paid", "cancelled"):
            raise SalesFinanceError(409, "Quote cannot be converted in its current status.")

        connection.execute(
            """
            UPDATE quotes_invoices
            SET type = 'invoice', status = 'sent'
            WHERE id = ?
            """,
            (document_id,),
        )
        updated = connection.execute(
            """
            SELECT id, document_number, type, customer_code, status,
                   subtotal_cents, tax_cents, discount_cents, total_cents,
                   currency, issue_date, due_date, created_at
            FROM quotes_invoices WHERE id = ?
            """,
            (document_id,),
        ).fetchone()
    return dict(updated)
