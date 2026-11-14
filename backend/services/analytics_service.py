from __future__ import annotations

from datetime import date, datetime
from typing import Any

from ..database import database


class AnalyticsError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def executive_kpis() -> dict[str, Any]:
    today = date.today().isoformat()
    month_start = date.today().replace(day=1).isoformat()

    with database() as connection:
        product_count = connection.execute(
            "SELECT COUNT(*) FROM products WHERE is_active = 1"
        ).fetchone()[0]

        low_stock = connection.execute(
            """
            SELECT COUNT(*) FROM products p
            WHERE p.is_active = 1
              AND COALESCE((
                SELECT SUM(CASE WHEN s.status = 'in_stock' THEN 1 ELSE 0 END)
                FROM serial_numbers s WHERE s.product_id = p.id
              ), 0) <= p.critical_stock_level
            """
        ).fetchone()[0]

        open_service_tickets = connection.execute(
            "SELECT COUNT(*) FROM service_tickets WHERE status NOT IN ('completed', 'delivered', 'cancelled')"
        ).fetchone()[0]

        completed_repairs = connection.execute(
            "SELECT COUNT(*) FROM service_tickets WHERE status = 'completed'"
        ).fetchone()[0]

        today_sales = connection.execute(
            """
            SELECT COALESCE(SUM(total_cents), 0) AS total, COUNT(*) AS count
            FROM pos_sales WHERE substr(created_at, 1, 10) = ?
            """,
            (today,),
        ).fetchone()

        month_sales = connection.execute(
            """
            SELECT COALESCE(SUM(total_cents), 0) AS total, COUNT(*) AS count
            FROM pos_sales WHERE substr(created_at, 1, 10) >= ?
            """,
            (month_start,),
        ).fetchone()

        month_purchases = connection.execute(
            """
            SELECT COALESCE(SUM(total_cents), 0) AS total
            FROM purchase_orders
            WHERE status = 'received' AND substr(received_date, 1, 10) >= ?
            """,
            (month_start,),
        ).fetchone()[0]

        cash_income = connection.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN type = 'income' THEN amount_cents ELSE 0 END), 0) AS income,
                   COALESCE(SUM(CASE WHEN type = 'expense' THEN amount_cents ELSE 0 END), 0) AS expense
            FROM financial_transactions WHERE substr(created_at, 1, 10) >= ?
            """,
            (month_start,),
        ).fetchone()

        overdue_invoices = connection.execute(
            """
            SELECT COUNT(*) FROM quotes_invoices
            WHERE type = 'invoice' AND status = 'overdue'
            """
        ).fetchone()[0]

        overdue_amount = connection.execute(
            """
            SELECT COALESCE(SUM(total_cents), 0) FROM quotes_invoices
            WHERE type = 'invoice' AND status = 'overdue'
            """
        ).fetchone()[0]

    return {
        "product_count": int(product_count),
        "low_stock_count": int(low_stock),
        "open_service_tickets": int(open_service_tickets),
        "completed_repairs": int(completed_repairs),
        "today_sales_cents": int(today_sales["total"]),
        "today_sales_count": int(today_sales["count"]),
        "month_sales_cents": int(month_sales["total"]),
        "month_sales_count": int(month_sales["count"]),
        "month_purchase_cents": int(month_purchases),
        "month_cash_income_cents": int(cash_income["income"]),
        "month_cash_expense_cents": int(cash_income["expense"]),
        "month_net_cents": int(cash_income["income"]) - int(cash_income["expense"]),
        "overdue_invoice_count": int(overdue_invoices),
        "overdue_invoice_cents": int(overdue_amount),
    }


def profit_and_loss(
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if end < start:
        raise AnalyticsError(422, "End date must be on or after start date.")
    if (end - start).days > 366:
        raise AnalyticsError(422, "Range cannot exceed 367 days.")

    start_iso = start.isoformat()
    end_iso = end.isoformat()

    with database() as connection:
        sales = connection.execute(
            """
            SELECT COALESCE(SUM(total_cents), 0) AS sales_cents, COUNT(*) AS sale_count
            FROM pos_sales
            WHERE substr(created_at, 1, 10) BETWEEN ? AND ?
            """,
            (start_iso, end_iso),
        ).fetchone()

        purchases = connection.execute(
            """
            SELECT COALESCE(SUM(total_cents), 0) AS purchase_cents
            FROM purchase_orders
            WHERE status = 'received' AND substr(received_date, 1, 10) BETWEEN ? AND ?
            """,
            (start_iso, end_iso),
        ).fetchone()

        cash_income = connection.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN type = 'income' THEN amount_cents ELSE 0 END), 0) AS income
            FROM financial_transactions
            WHERE substr(created_at, 1, 10) BETWEEN ? AND ?
            """,
            (start_iso, end_iso),
        ).fetchone()[0]

        cash_expense = connection.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN type = 'expense' THEN amount_cents ELSE 0 END), 0) AS expense
            FROM financial_transactions
            WHERE substr(created_at, 1, 10) BETWEEN ? AND ?
            """,
            (start_iso, end_iso),
        ).fetchone()[0]

        daily_rows = connection.execute(
            """
            SELECT substr(created_at, 1, 10) AS day,
                   COALESCE(SUM(total_cents), 0) AS sales_cents
            FROM pos_sales
            WHERE substr(created_at, 1, 10) BETWEEN ? AND ?
            GROUP BY substr(created_at, 1, 10)
            ORDER BY day
            """,
            (start_iso, end_iso),
        ).fetchall()

    sales_cents = int(sales["sales_cents"])
    purchase_cents = int(purchases["purchase_cents"])
    gross_profit = sales_cents - purchase_cents
    net_profit = gross_profit + int(cash_income) - int(cash_expense)

    return {
        "start_date": start_iso,
        "end_date": end_iso,
        "sales_cents": sales_cents,
        "sale_count": int(sales["sale_count"]),
        "purchase_cents": purchase_cents,
        "gross_profit_cents": gross_profit,
        "cash_income_cents": int(cash_income),
        "cash_expense_cents": int(cash_expense),
        "net_profit_cents": net_profit,
        "daily_sales": [
            {"day": row["day"], "sales_cents": int(row["sales_cents"])}
            for row in daily_rows
        ],
    }


def top_defective_devices(limit: int = 10) -> list[dict[str, Any]]:
    if limit <= 0 or limit > 100:
        raise AnalyticsError(422, "Limit must be between 1 and 100.")

    with database() as connection:
        rows = connection.execute(
            """
            SELECT p.sku, p.name, p.brand, p.category,
                   COUNT(*) AS defective_count
            FROM serial_numbers s
            JOIN products p ON p.id = s.product_id
            WHERE s.status = 'defective'
            GROUP BY p.id
            ORDER BY defective_count DESC, p.name COLLATE NOCASE
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "sku": row["sku"],
            "name": row["name"],
            "brand": row["brand"],
            "category": row["category"],
            "defective_count": int(row["defective_count"]),
        }
        for row in rows
    ]


def overdue_payment_alerts() -> list[dict[str, Any]]:
    today = date.today().isoformat()
    with database() as connection:
        rows = connection.execute(
            """
            SELECT id, document_number, customer_code, total_cents,
                   currency, issue_date, due_date
            FROM quotes_invoices
            WHERE type = 'invoice'
              AND status IN ('sent', 'accepted')
              AND due_date IS NOT NULL
              AND due_date < ?
            ORDER BY due_date ASC
            """,
            (today,),
        ).fetchall()

        overdue_rows = connection.execute(
            """
            SELECT id, document_number, customer_code, total_cents,
                   currency, issue_date, due_date
            FROM quotes_invoices
            WHERE type = 'invoice' AND status = 'overdue'
            ORDER BY due_date ASC
            """,
        ).fetchall()

    alerts = []
    for row in rows:
        due = date.fromisoformat(row["due_date"])
        days_overdue = (date.today() - due).days
        alerts.append({
            "document_id": row["id"],
            "document_number": row["document_number"],
            "customer_code": row["customer_code"],
            "total_cents": int(row["total_cents"]),
            "currency": row["currency"],
            "issue_date": row["issue_date"],
            "due_date": row["due_date"],
            "days_overdue": days_overdue,
            "status": "upcoming_overdue",
        })
    for row in overdue_rows:
        due = date.fromisoformat(row["due_date"]) if row["due_date"] else None
        days_overdue = (date.today() - due).days if due else None
        alerts.append({
            "document_id": row["id"],
            "document_number": row["document_number"],
            "customer_code": row["customer_code"],
            "total_cents": int(row["total_cents"]),
            "currency": row["currency"],
            "issue_date": row["issue_date"],
            "due_date": row["due_date"],
            "days_overdue": days_overdue,
            "status": "overdue",
        })

    alerts.sort(key=lambda a: (a["days_overdue"] or 0), reverse=True)
    return alerts
