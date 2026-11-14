from __future__ import annotations

from datetime import date, datetime
from typing import Any

from ..database import database
from ..kvkk_security import timestamp_now


class ServiceDeskError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)

VALID_STATUSES = (
    "intake", "diagnosis", "waiting_parts", "repairing",
    "quality_control", "completed", "delivered", "cancelled",
)
VALID_PRIORITIES = ("low", "normal", "high", "urgent")


def _now() -> str:
    return timestamp_now()


def list_service_tickets(
    status: str | None = None,
    technician_id: int | None = None,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    if status is not None:
        conditions.append("status = ?")
        params.append(status)
    if technician_id is not None:
        conditions.append("technician_id = ?")
        params.append(technician_id)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    with database() as connection:
        rows = connection.execute(
            f"""
            SELECT id, ticket_number, customer_name, customer_phone, device_brand,
                   device_model, serial_number, imei, problem_description, status,
                   priority, technician_id, intake_date, completion_date,
                   status_updated_at, estimated_cost_cents, final_cost_cents,
                   warranty_claim, created_at
            FROM service_tickets {where_clause}
            ORDER BY created_at DESC
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def create_service_ticket(
    payload: dict[str, Any],
    current_user: dict[str, Any],
) -> dict[str, Any]:
    customer_name = (payload.get("customer_name") or "").strip()
    customer_phone = (payload.get("customer_phone") or "").strip() or None
    device_brand = (payload.get("device_brand") or "").strip()
    device_model = (payload.get("device_model") or "").strip()
    serial_number = (payload.get("serial_number") or "").strip().upper() or None
    imei = (payload.get("imei") or "").strip().upper() or None
    problem_description = (payload.get("problem_description") or "").strip()
    priority = (payload.get("priority") or "normal").strip().lower()
    warranty_claim = 1 if payload.get("warranty_claim") else 0

    if not customer_name:
        raise ServiceDeskError(422, "Customer name is required.")
    if not device_brand:
        raise ServiceDeskError(422, "Device brand is required.")
    if not device_model:
        raise ServiceDeskError(422, "Device model is required.")
    if not problem_description:
        raise ServiceDeskError(422, "Problem description is required.")
    if priority not in VALID_PRIORITIES:
        raise ServiceDeskError(422, f"Priority must be one of: {', '.join(VALID_PRIORITIES)}.")

    import re as _re
    ticket_number = "SRV-" + _re.sub(r"\W+", "", datetime.now().strftime("%Y%m%d%H%M%S"))

    try:
        with database() as connection:
            cursor = connection.execute(
                """
                INSERT INTO service_tickets
                    (ticket_number, customer_name, customer_phone, device_brand,
                     device_model, serial_number, imei, problem_description, status,
                     priority, technician_id, intake_date, completion_date,
                     status_updated_at, estimated_cost_cents, final_cost_cents,
                     warranty_claim, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'intake', ?, NULL, ?, NULL,
                        ?, 0, 0, ?, ?)
                """,
                (
                    ticket_number, customer_name, customer_phone, device_brand,
                    device_model, serial_number, imei, problem_description,
                    priority, _now(), _now(), warranty_claim, _now(),
                ),
            )
            row = connection.execute(
                """
                SELECT id, ticket_number, customer_name, customer_phone, device_brand,
                       device_model, serial_number, imei, problem_description, status,
                       priority, technician_id, intake_date, completion_date,
                       status_updated_at, estimated_cost_cents, final_cost_cents,
                       warranty_claim, created_at
                FROM service_tickets WHERE id = ?
                """,
                (cursor.lastrowid,),
            ).fetchone()
    except sqlite3.IntegrityError as error:
        raise ServiceDeskError(409, "Service ticket could not be created.") from error
    if row is None:
        raise RuntimeError("Service ticket could not be read back.")
    return dict(row)


import sqlite3  # noqa: E402


def assign_technician(
    ticket_id: int,
    technician_id: int,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    with database() as connection:
        ticket = connection.execute(
            "SELECT id, status, technician_id FROM service_tickets WHERE id = ?",
            (ticket_id,),
        ).fetchone()
        if ticket is None:
            raise ServiceDeskError(404, "Service ticket not found.")
        technician = connection.execute(
            "SELECT id, role FROM users WHERE id = ? AND is_active = 1", (technician_id,)
        ).fetchone()
        if technician is None or technician["role"] != "Technician":
            raise ServiceDeskError(404, "Active technician not found.")
        if ticket["status"] == "cancelled":
            raise ServiceDeskError(409, "Cannot assign technician to a cancelled ticket.")
        connection.execute(
            "UPDATE service_tickets SET technician_id = ? WHERE id = ?",
            (technician_id, ticket_id),
        )
        updated = connection.execute(
            """
            SELECT id, ticket_number, customer_name, device_brand, device_model,
                   status, technician_id, intake_date, completion_date
            FROM service_tickets WHERE id = ?
            """,
            (ticket_id,),
        ).fetchone()
    return dict(updated)


def update_ticket_status(
    ticket_id: int,
    status: str,
    current_user: dict[str, Any],
    completion_date: str | None = None,
) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ServiceDeskError(422, f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}.")

    with database() as connection:
        ticket = connection.execute(
            "SELECT id, status FROM service_tickets WHERE id = ?", (ticket_id,)
        ).fetchone()
        if ticket is None:
            raise ServiceDeskError(404, "Service ticket not found.")

        values: dict[str, Any] = {"status": status, "status_updated_at": _now()}
        if status == "completed" and completion_date:
            values["completion_date"] = completion_date
        elif status == "completed":
            values["completion_date"] = _now()

        set_clause = ", ".join(f"{k} = ?" for k in values)
        params = list(values.values()) + [ticket_id]
        connection.execute(
            f"UPDATE service_tickets SET {set_clause} WHERE id = ?",
            params,
        )
        updated = connection.execute(
            """
            SELECT id, ticket_number, customer_name, device_brand, device_model,
                   status, technician_id, intake_date, completion_date,
                   status_updated_at, estimated_cost_cents, final_cost_cents
            FROM service_tickets WHERE id = ?
            """,
            (ticket_id,),
        ).fetchone()
    return dict(updated)


def deduct_service_part(
    ticket_id: int,
    product_id: int,
    serial_number: str | None,
    quantity_used: int,
    unit_price_cents: int,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    if quantity_used <= 0:
        raise ServiceDeskError(422, "Quantity used must be greater than zero.")
    if unit_price_cents < 0:
        raise ServiceDeskError(422, "Unit price cannot be negative.")

    serial_number = (serial_number or "").strip().upper() or None

    with database() as connection:
        ticket = connection.execute(
            "SELECT id, status FROM service_tickets WHERE id = ?", (ticket_id,)
        ).fetchone()
        if ticket is None:
            raise ServiceDeskError(404, "Service ticket not found.")
        if ticket["status"] in ("completed", "delivered", "cancelled"):
            raise ServiceDeskError(409, "Cannot deduct parts from a closed or cancelled ticket.")

        product = connection.execute(
            "SELECT id, is_tracked_serial FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        if product is None:
            raise ServiceDeskError(404, "Product not found.")
        if product["is_tracked_serial"] and not serial_number:
            raise ServiceDeskError(422, "Serial number is required for tracked serial products.")

        if serial_number:
            serial_row = connection.execute(
                """
                SELECT id, status, warehouse_id FROM serial_numbers
                WHERE serial_number = ? AND product_id = ?
                """,
                (serial_number, product_id),
            ).fetchone()
            if serial_row is None:
                raise ServiceDeskError(404, "Serial number not found for this product.")
            if serial_row["status"] not in ("in_stock", "reserved"):
                raise ServiceDeskError(409, "Serial number is not available for deduction.")
            connection.execute(
                "UPDATE serial_numbers SET status = 'reserved' WHERE id = ?",
                (serial_row["id"],),
            )

        cursor = connection.execute(
            """
            INSERT INTO service_parts
                (service_ticket_id, product_id, serial_number, quantity_used,
                 unit_price_cents, deducted_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ticket_id, product_id, serial_number, quantity_used,
             unit_price_cents, _now()),
        )
        connection.execute(
            """
            UPDATE service_tickets
            SET final_cost_cents = COALESCE(final_cost_cents, 0) + (? * ?)
            WHERE id = ?
            """,
            (quantity_used, unit_price_cents, ticket_id),
        )
        part = connection.execute(
            """
            SELECT id, service_ticket_id, product_id, serial_number, quantity_used,
                   unit_price_cents, deducted_at
            FROM service_parts WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return dict(part)


def calculate_repair_warranty(
    ticket_id: int,
    warranty_months: int,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    if warranty_months <= 0:
        raise ServiceDeskError(422, "Warranty months must be greater than zero.")

    with database() as connection:
        ticket = connection.execute(
            """
            SELECT id, ticket_number, completion_date, warranty_claim
            FROM service_tickets WHERE id = ?
            """,
            (ticket_id,),
        ).fetchone()
        if ticket is None:
            raise ServiceDeskError(404, "Service ticket not found.")
        if ticket["completion_date"] is None:
            raise ServiceDeskError(409, "Ticket must be completed before calculating repair warranty.")

        completed = date.fromisoformat(ticket["completion_date"])
        warranty_end = date.fromordinal(completed.toordinal() + int(warranty_months) * 30)

    return {
        "ticket_id": ticket_id,
        "ticket_number": ticket["ticket_number"],
        "completion_date": ticket["completion_date"],
        "warranty_months": warranty_months,
        "repair_warranty_end_date": warranty_end.isoformat(),
    }


def get_service_receipt(ticket_id: int) -> dict[str, Any]:
    with database() as connection:
        ticket = connection.execute(
            """
            SELECT id, ticket_number, customer_name, customer_phone, device_brand,
                   device_model, serial_number, imei, problem_description, status,
                   priority, technician_id, intake_date, completion_date,
                   estimated_cost_cents, final_cost_cents, warranty_claim, created_at
            FROM service_tickets WHERE id = ?
            """,
            (ticket_id,),
        ).fetchone()
        if ticket is None:
            raise ServiceDeskError(404, "Service ticket not found.")

        parts = connection.execute(
            """
            SELECT id, product_id, serial_number, quantity_used, unit_price_cents, deducted_at
            FROM service_parts WHERE service_ticket_id = ?
            ORDER BY deducted_at
            """,
            (ticket_id,),
        ).fetchall()

        technician = None
        if ticket["technician_id"]:
            tech = connection.execute(
                "SELECT id, username FROM users WHERE id = ?", (ticket["technician_id"],)
            ).fetchone()
            if tech:
                technician = dict(tech)

    parts_total = sum(int(p["quantity_used"]) * int(p["unit_price_cents"]) for p in parts)
    return {
        "ticket": dict(ticket),
        "parts": [dict(p) for p in parts],
        "parts_total_cents": parts_total,
        "technician": technician,
        "receipt_generated_at": _now(),
    }
