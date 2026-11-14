from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ..database import database
from ..kvkk_security import timestamp_now


class InventoryError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


SERIAL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{3,63}$")
IMEI_PATTERN = re.compile(r"^[0-9]{14,18}$")


def _now() -> str:
    return timestamp_now()


def list_warehouses() -> list[dict[str, Any]]:
    with database() as connection:
        rows = connection.execute(
            """
            SELECT id, name, code, address, city, phone, is_active, created_at
            FROM warehouses ORDER BY name COLLATE NOCASE
            """
        ).fetchall()
    return [dict(row) for row in rows]


def create_warehouse(payload: dict[str, Any], current_user: dict[str, Any]) -> dict[str, Any]:
    name = (payload.get("name") or "").strip()
    code = (payload.get("code") or "").strip().upper()
    address = (payload.get("address") or "").strip() or None
    city = (payload.get("city") or "").strip() or None
    phone = (payload.get("phone") or "").strip() or None

    if not name:
        raise InventoryError(422, "Warehouse name is required.")
    if not re.fullmatch(r"[A-Z0-9]{2,20}", code):
        raise InventoryError(422, "Warehouse code must be 2-20 uppercase alphanumeric characters.")

    try:
        with database() as connection:
            cursor = connection.execute(
                """
                INSERT INTO warehouses (name, code, address, city, phone, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (name, code, address, city, phone, _now()),
            )
            row = connection.execute(
                """
                SELECT id, name, code, address, city, phone, is_active, created_at
                FROM warehouses WHERE id = ?
                """,
                (cursor.lastrowid,),
            ).fetchone()
    except sqlite3.IntegrityError as error:
        raise InventoryError(409, "A warehouse with this code already exists.") from error
    if row is None:
        raise RuntimeError("Created warehouse could not be read back.")
    return dict(row)


import sqlite3  # noqa: E402


def list_products(warehouse_id: int | None = None, include_inactive: bool = False) -> list[dict[str, Any]]:
    if warehouse_id is not None:
        condition = "WHERE p.is_tracked_serial IS NOT NULL"
        params: list[Any] = []
        if not include_inactive:
            condition += " AND p.is_active = 1"
        params.append(warehouse_id)
        query = f"""
            SELECT p.id, p.sku, p.name, p.category, p.brand, p.description,
                   p.unit_price_cents, p.critical_stock_level, p.is_tracked_serial,
                   p.is_active, p.created_at,
                   COALESCE(s.current_stock, 0) AS current_stock,
                   w.id AS warehouse_id, w.name AS warehouse_name
            FROM products p
            LEFT JOIN (
                SELECT product_id, warehouse_id, SUM(CASE WHEN status = 'in_stock' THEN 1 ELSE 0 END) AS current_stock
                FROM serial_numbers GROUP BY product_id, warehouse_id
            ) s ON s.product_id = p.id AND s.warehouse_id = ?
            LEFT JOIN warehouses w ON w.id = ?
            {condition}
            ORDER BY p.category COLLATE NOCASE, p.name COLLATE NOCASE
        """
        params = [warehouse_id, warehouse_id]
    else:
        if not include_inactive:
            query = """
                SELECT p.id, p.sku, p.name, p.category, p.brand, p.description,
                       p.unit_price_cents, p.critical_stock_level, p.is_tracked_serial,
                       p.is_active, p.created_at, 0 AS current_stock,
                       NULL AS warehouse_id, NULL AS warehouse_name
                FROM products p
                WHERE p.is_active = 1
                ORDER BY p.category COLLATE NOCASE, p.name COLLATE NOCASE
            """
            params = []
        else:
            query = """
                SELECT p.id, p.sku, p.name, p.category, p.brand, p.description,
                       p.unit_price_cents, p.critical_stock_level, p.is_tracked_serial,
                       p.is_active, p.created_at, 0 AS current_stock,
                       NULL AS warehouse_id, NULL AS warehouse_name
                FROM products p
                ORDER BY p.category COLLATE NOCASE, p.name COLLATE NOCASE
            """
            params = []

    with database() as connection:
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def create_product(payload: dict[str, Any], current_user: dict[str, Any]) -> dict[str, Any]:
    sku = (payload.get("sku") or "").strip().upper()
    name = (payload.get("name") or "").strip()
    category = (payload.get("category") or "").strip()
    brand = (payload.get("brand") or "").strip()
    description = (payload.get("description") or "").strip() or None
    unit_price = payload.get("unit_price")
    critical_level = payload.get("critical_stock_level", 5)
    is_tracked_serial = 1 if payload.get("is_tracked_serial") else 0

    if not sku or not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{1,63}", sku):
        raise InventoryError(422, "SKU must use letters, numbers, hyphens, or underscores.")
    if not name:
        raise InventoryError(422, "Product name is required.")
    if not category:
        raise InventoryError(422, "Product category is required.")
    if not brand:
        raise InventoryError(422, "Product brand is required.")
    try:
        price_cents = int(Decimal(str(unit_price)) * 100)
    except Exception:
        raise InventoryError(422, "Unit price must be a valid decimal amount.")
    if price_cents < 0:
        raise InventoryError(422, "Unit price cannot be negative.")
    try:
        critical_level = int(critical_level)
    except Exception:
        raise InventoryError(422, "Critical stock level must be an integer.")
    if critical_level < 0:
        raise InventoryError(422, "Critical stock level cannot be negative.")

    try:
        with database() as connection:
            cursor = connection.execute(
                """
                INSERT INTO products
                    (sku, name, category, brand, description, unit_price_cents,
                     critical_stock_level, is_tracked_serial, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (sku, name, category, brand, description, price_cents,
                 critical_level, is_tracked_serial, _now()),
            )
            row = connection.execute(
                """
                SELECT id, sku, name, category, brand, description, unit_price_cents,
                       critical_stock_level, is_tracked_serial, is_active, created_at
                FROM products WHERE id = ?
                """,
                (cursor.lastrowid,),
            ).fetchone()
    except sqlite3.IntegrityError as error:
        raise InventoryError(409, "A product with this SKU already exists.") from error
    if row is None:
        raise RuntimeError("Created product could not be read back.")
    return dict(row)


def receive_serial_numbers(
    product_id: int,
    warehouse_id: int,
    serials: list[dict[str, Any]],
    current_user: dict[str, Any],
) -> list[dict[str, Any]]:
    if not serials:
        raise InventoryError(422, "At least one serial number is required.")

    created: list[dict[str, Any]] = []
    with database() as connection:
        product = connection.execute(
            "SELECT is_tracked_serial FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        if product is None:
            raise InventoryError(404, "Product not found.")
        warehouse = connection.execute(
            "SELECT id FROM warehouses WHERE id = ? AND is_active = 1", (warehouse_id,)
        ).fetchone()
        if warehouse is None:
            raise InventoryError(404, "Active warehouse not found.")

        for entry in serials:
            serial_number = (entry.get("serial_number") or "").strip().upper()
            imei = (entry.get("imei") or "").strip().upper() or None
            purchase_date = entry.get("purchase_date")
            warranty_months = entry.get("warranty_months", 12)

            if not serial_number or not SERIAL_PATTERN.match(serial_number):
                raise InventoryError(422, f"Invalid serial number: {serial_number}")
            if imei is not None and not IMEI_PATTERN.match(imei):
                raise InventoryError(422, f"Invalid IMEI: {imei}")

            warranty_end: str | None = None
            if purchase_date:
                try:
                    purchased = date.fromisoformat(purchase_date)
                    warranty_end = date.fromordinal(
                        purchased.toordinal() + int(warranty_months) * 30
                    ).isoformat()
                except Exception:
                    raise InventoryError(422, "Invalid purchase date or warranty months.")

            try:
                cursor = connection.execute(
                    """
                    INSERT INTO serial_numbers
                        (product_id, serial_number, imei, warehouse_id, status,
                         purchase_date, warranty_end_date, sale_date, customer_name, created_at)
                    VALUES (?, ?, ?, ?, 'in_stock', ?, ?, NULL, NULL, ?)
                    """,
                    (product_id, serial_number, imei, warehouse_id,
                     purchase_date, warranty_end, _now()),
                )
                row = connection.execute(
                    """
                    SELECT id, product_id, serial_number, imei, warehouse_id, status,
                           purchase_date, warranty_end_date, sale_date, customer_name, created_at
                    FROM serial_numbers WHERE id = ?
                    """,
                    (cursor.lastrowid,),
                ).fetchone()
                created.append(dict(row))
            except sqlite3.IntegrityError as error:
                raise InventoryError(409, f"Serial number already exists: {serial_number}") from error

    return created


def list_serial_numbers(
    product_id: int | None = None,
    warehouse_id: int | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    if product_id is not None:
        conditions.append("product_id = ?")
        params.append(product_id)
    if warehouse_id is not None:
        conditions.append("warehouse_id = ?")
        params.append(warehouse_id)
    if status is not None:
        conditions.append("status = ?")
        params.append(status)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    with database() as connection:
        rows = connection.execute(
            f"""
            SELECT id, product_id, serial_number, imei, warehouse_id, status,
                   purchase_date, warranty_end_date, sale_date, customer_name, created_at
            FROM serial_numbers {where_clause}
            ORDER BY created_at DESC
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def get_warranty_status(serial_number: str) -> dict[str, Any]:
    with database() as connection:
        row = connection.execute(
            """
            SELECT s.serial_number, s.warranty_end_date, s.status, s.purchase_date,
                   p.name AS product_name, p.sku AS product_sku
            FROM serial_numbers s
            JOIN products p ON p.id = s.product_id
            WHERE s.serial_number = ?
            """,
            (serial_number.upper(),),
        ).fetchone()
    if row is None:
        raise InventoryError(404, "Serial number not found.")

    warranty_end = row["warranty_end_date"]
    in_warranty = False
    days_remaining = None
    if warranty_end:
        end_date = date.fromisoformat(warranty_end)
        today = date.today()
        days_remaining = (end_date - today).days
        in_warranty = days_remaining >= 0

    return {
        "serial_number": row["serial_number"],
        "product_name": row["product_name"],
        "product_sku": row["product_sku"],
        "status": row["status"],
        "purchase_date": row["purchase_date"],
        "warranty_end_date": warranty_end,
        "in_warranty": in_warranty,
        "days_remaining": days_remaining,
    }


def critical_stock_alerts() -> list[dict[str, Any]]:
    with database() as connection:
        rows = connection.execute(
            """
            SELECT p.id, p.sku, p.name, p.category, p.brand,
                   p.critical_stock_level,
                   COALESCE(s.in_stock_count, 0) AS current_stock,
                   w.name AS warehouse_name, w.id AS warehouse_id
            FROM products p
            LEFT JOIN (
                SELECT product_id, warehouse_id,
                       SUM(CASE WHEN status = 'in_stock' THEN 1 ELSE 0 END) AS in_stock_count
                FROM serial_numbers GROUP BY product_id, warehouse_id
            ) s ON s.product_id = p.id
            LEFT JOIN warehouses w ON w.id = COALESCE(s.warehouse_id, (
                SELECT id FROM warehouses WHERE is_active = 1 LIMIT 1
            ))
            WHERE p.is_active = 1
              AND COALESCE(s.in_stock_count, 0) <= p.critical_stock_level
            ORDER BY (COALESCE(s.in_stock_count, 0) * 1.0 / NULLIF(p.critical_stock_level, 0)) ASC, p.name
            """
        ).fetchall()
    return [dict(row) for row in rows]


def transfer_serial(
    serial_number: str,
    from_warehouse_id: int,
    to_warehouse_id: int,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    serial_number = serial_number.strip().upper()
    with database() as connection:
        row = connection.execute(
            """
            SELECT id, warehouse_id, status FROM serial_numbers WHERE serial_number = ?
            """,
            (serial_number,),
        ).fetchone()
        if row is None:
            raise InventoryError(404, "Serial number not found.")
        if int(row["warehouse_id"]) != from_warehouse_id:
            raise InventoryError(409, "Serial number is not located in the source warehouse.")
        if row["status"] != "in_stock":
            raise InventoryError(409, "Only in-stock serial numbers can be transferred.")

        to_warehouse = connection.execute(
            "SELECT id FROM warehouses WHERE id = ? AND is_active = 1", (to_warehouse_id,)
        ).fetchone()
        if to_warehouse is None:
            raise InventoryError(404, "Target active warehouse not found.")

        connection.execute(
            "UPDATE serial_numbers SET warehouse_id = ? WHERE id = ?",
            (to_warehouse_id, row["id"]),
        )

    return {
        "serial_number": serial_number,
        "from_warehouse_id": from_warehouse_id,
        "to_warehouse_id": to_warehouse_id,
    }
