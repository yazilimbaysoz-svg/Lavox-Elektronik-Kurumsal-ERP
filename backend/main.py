from __future__ import annotations

import json
import sqlite3
import shutil
import tempfile
from contextlib import asynccontextmanager, closing
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from starlette.background import BackgroundTask
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .database import DATABASE_PATH, PROJECT_ROOT, database, initialize_database
from .kvkk_security import (
    AuthenticationError,
    SecurityError,
    authenticate_user,
    audit_action,
    hash_password,
    kvkk_mask,
    require_role,
)
from .services import analytics_service, inventory_service, sales_finance_service, service_desk_service
from .services.inventory_service import InventoryError
from .services.sales_finance_service import SalesFinanceError
from .services.service_desk_service import ServiceDeskError


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict[str, Any]


class CurrentUser(BaseModel):
    id: int
    username: str
    email: str
    role: str


@asynccontextmanager
async def lifespan(_application: FastAPI) -> AsyncGenerator[None, None]:
    del _application
    initialize_database()
    yield


app = FastAPI(
    title="LAVOX Elektronik ERP",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "frontend"), name="static")


def _current_user_dependency(request: Request) -> dict[str, Any]:
    header = request.headers.get("x-current-user")
    if not header:
        raise AuthenticationError("Authentication required.")
    try:
        return json.loads(header)
    except json.JSONDecodeError as error:
        raise AuthenticationError("Invalid user context.") from error


def _require_role(*roles: str):
    def dependency(request: Request) -> dict[str, Any]:
        user = _current_user_dependency(request)
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{user.get('role')}' not authorized. Required: {', '.join(roles)}.",
            )
        return user

    return dependency


@app.exception_handler(SecurityError)
async def handle_security_error(_request: Request, error: SecurityError) -> JSONResponse:
    del _request
    return JSONResponse(status_code=error.status_code, content={"detail": error.detail})


@app.exception_handler(InventoryError)
async def handle_inventory_error(_request: Request, error: InventoryError) -> JSONResponse:
    del _request
    return JSONResponse(status_code=error.status_code, content={"detail": error.detail})


@app.exception_handler(SalesFinanceError)
async def handle_sales_error(_request: Request, error: SalesFinanceError) -> JSONResponse:
    del _request
    return JSONResponse(status_code=error.status_code, content={"detail": error.detail})


@app.exception_handler(ServiceDeskError)
async def handle_service_error(_request: Request, error: ServiceDeskError) -> JSONResponse:
    del _request
    return JSONResponse(status_code=error.status_code, content={"detail": error.detail})


@app.exception_handler(sqlite3.Error)
async def handle_database_error(_request: Request, _error: sqlite3.Error) -> JSONResponse:
    del _request, _error
    return JSONResponse(
        status_code=503,
        content={"detail": "The local database is temporarily unavailable."},
    )


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "frontend" / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "LAVOX Elektronik ERP"}


@app.get("/api/locales/tr.json")
def locales() -> JSONResponse:
    base_path = PROJECT_ROOT / "frontend" / "locales" / "tr.json"
    additions_path = PROJECT_ROOT / "locales" / "tr.json"
    translations = json.loads(base_path.read_text(encoding="utf-8"))
    additions = json.loads(additions_path.read_text(encoding="utf-8"))

    def merge(target: dict[str, Any], source: dict[str, Any]) -> None:
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                merge(target[key], value)
            else:
                target[key] = value

    merge(translations, additions)
    return JSONResponse(content=translations)


@app.get("/api/backup/database")
def backup_database(
    user: dict[str, Any] = Depends(_require_role("Admin")),
) -> FileResponse:
    del user
    if not DATABASE_PATH.is_file():
        raise HTTPException(status_code=503, detail="The database is not available.")

    backup_directory: Path | None = None
    try:
        backup_directory = Path(tempfile.mkdtemp(prefix="lavox-backup-"))
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup_path = backup_directory / f"lavox_enterprise_{timestamp}.db"
        with closing(sqlite3.connect(str(DATABASE_PATH), timeout=30)) as source:
            with closing(sqlite3.connect(str(backup_path), timeout=30)) as destination:
                source.backup(destination, pages=128, sleep=0.05)
    except (OSError, sqlite3.Error) as error:
        if backup_directory is not None and backup_directory.exists():
            shutil.rmtree(backup_directory)
        raise HTTPException(
            status_code=503,
            detail="The database backup could not be created.",
        ) from error

    return FileResponse(
        backup_path,
        media_type="application/vnd.sqlite3",
        filename=backup_path.name,
        background=BackgroundTask(shutil.rmtree, backup_directory),
    )


@app.post("/api/auth/login", response_model=TokenResponse)
def login(request: Request, payload: TokenRequest) -> dict[str, Any]:
    ip_address = request.client.host if request.client else None
    user = authenticate_user(payload.username, payload.password, ip_address)
    import json

    return {
        "access_token": "local-" + str(user["id"]),
        "token_type": "bearer",
        "user": user,
    }


@app.get("/api/auth/me", response_model=CurrentUser)
def me(user: dict[str, Any] = Depends(_current_user_dependency)) -> dict[str, Any]:
    return user


# --- Users ---
@app.get("/api/users")
def list_users(user: dict[str, Any] = Depends(_require_role("Admin"))) -> list[dict[str, Any]]:
    with database() as connection:
        rows = connection.execute(
            """
            SELECT id, username, email, role, is_active, created_at
            FROM users ORDER BY username COLLATE NOCASE
            """
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/users")
def create_user(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(_require_role("Admin")),
) -> dict[str, Any]:
    username = (payload.get("username") or "").strip()
    email = (payload.get("email") or "").strip()
    password = payload.get("password") or ""
    role = (payload.get("role") or "Cashier").strip()
    if role not in ("Admin", "Cashier", "Technician"):
        raise HTTPException(status_code=422, detail="Invalid role.")
    if not username or not email or not password:
        raise HTTPException(status_code=422, detail="All fields are required.")
    password_hash, _salt = hash_password(password)
    try:
        with database() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (username, email, password_hash, role, _iso_now()),
            )
            row = connection.execute(
                "SELECT id, username, email, role, is_active, created_at FROM users WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="Username or email already exists.") from error
    return dict(row)


def _iso_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# --- Warehouses ---
@app.get("/api/warehouses")
def list_warehouses_endpoint(
    user: dict[str, Any] = Depends(_current_user_dependency),
) -> list[dict[str, Any]]:
    return inventory_service.list_warehouses()


@app.post("/api/warehouses")
def create_warehouse_endpoint(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(_require_role("Admin")),
) -> dict[str, Any]:
    return inventory_service.create_warehouse(payload, user)


# --- Products ---
@app.get("/api/products")
def list_products_endpoint(
    warehouse_id: int | None = None,
    user: dict[str, Any] = Depends(_current_user_dependency),
) -> list[dict[str, Any]]:
    return inventory_service.list_products(warehouse_id=warehouse_id)


@app.post("/api/products")
def create_product_endpoint(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(_require_role("Admin", "Cashier")),
) -> dict[str, Any]:
    return inventory_service.create_product(payload, user)


# --- Serial Numbers ---
@app.get("/api/serials")
def list_serials_endpoint(
    product_id: int | None = None,
    warehouse_id: int | None = None,
    status: str | None = None,
    user: dict[str, Any] = Depends(_current_user_dependency),
) -> list[dict[str, Any]]:
    return inventory_service.list_serial_numbers(
        product_id=product_id, warehouse_id=warehouse_id, status=status
    )


@app.post("/api/serials/receive")
def receive_serials_endpoint(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(_require_role("Admin", "Cashier")),
) -> list[dict[str, Any]]:
    product_id = payload.get("product_id")
    warehouse_id = payload.get("warehouse_id")
    serials = payload.get("serials", [])
    if not product_id or not warehouse_id or not serials:
        raise HTTPException(status_code=422, detail="product_id, warehouse_id, and serials are required.")
    return inventory_service.receive_serial_numbers(product_id, warehouse_id, serials, user)


@app.get("/api/serials/{serial_number}/warranty")
def warranty_status_endpoint(serial_number: str) -> dict[str, Any]:
    return inventory_service.get_warranty_status(serial_number)


@app.get("/api/alerts/critical-stock")
def critical_stock_endpoint() -> list[dict[str, Any]]:
    return inventory_service.critical_stock_alerts()


@app.post("/api/serials/transfer")
def transfer_serial_endpoint(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(_require_role("Admin", "Cashier")),
) -> dict[str, Any]:
    return inventory_service.transfer_serial(
        payload.get("serial_number", ""),
        payload.get("from_warehouse_id"),
        payload.get("to_warehouse_id"),
        user,
    )


# --- Service Desk ---
@app.get("/api/service-tickets")
def list_service_tickets_endpoint(
    status: str | None = None,
    technician_id: int | None = None,
    user: dict[str, Any] = Depends(_current_user_dependency),
) -> list[dict[str, Any]]:
    return service_desk_service.list_service_tickets(status=status, technician_id=technician_id)


@app.post("/api/service-tickets")
def create_service_ticket_endpoint(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(_current_user_dependency),
) -> dict[str, Any]:
    return service_desk_service.create_service_ticket(payload, user)


@app.post("/api/service-tickets/{ticket_id}/assign")
def assign_technician_endpoint(
    ticket_id: int,
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(_require_role("Admin")),
) -> dict[str, Any]:
    technician_id = payload.get("technician_id")
    if technician_id is None:
        raise HTTPException(status_code=422, detail="technician_id is required.")
    return service_desk_service.assign_technician(ticket_id, technician_id, user)


@app.post("/api/service-tickets/{ticket_id}/status")
def update_ticket_status_endpoint(
    ticket_id: int,
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(_current_user_dependency),
) -> dict[str, Any]:
    status = payload.get("status")
    if not status:
        raise HTTPException(status_code=422, detail="status is required.")
    return service_desk_service.update_ticket_status(
        ticket_id, status, user, payload.get("completion_date")
    )


@app.post("/api/service-tickets/{ticket_id}/parts")
def deduct_part_endpoint(
    ticket_id: int,
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(_require_role("Admin", "Technician")),
) -> dict[str, Any]:
    return service_desk_service.deduct_service_part(
        ticket_id,
        payload.get("product_id"),
        payload.get("serial_number"),
        payload.get("quantity_used", 1),
        payload.get("unit_price_cents", 0),
        user,
    )


@app.post("/api/service-tickets/{ticket_id}/warranty")
def repair_warranty_endpoint(
    ticket_id: int,
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(_current_user_dependency),
) -> dict[str, Any]:
    return service_desk_service.calculate_repair_warranty(
        ticket_id, payload.get("warranty_months", 12), user
    )


@app.get("/api/service-tickets/{ticket_id}/receipt")
def service_receipt_endpoint(ticket_id: int) -> dict[str, Any]:
    return service_desk_service.get_service_receipt(ticket_id)


# --- Customers/Suppliers ---
@app.get("/api/parties")
def list_parties_endpoint(
    party_type: str | None = None,
    user: dict[str, Any] = Depends(_current_user_dependency),
) -> list[dict[str, Any]]:
    return sales_finance_service.list_customers_suppliers(party_type=party_type)


@app.post("/api/parties")
def create_party_endpoint(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(_require_role("Admin", "Cashier")),
) -> dict[str, Any]:
    return sales_finance_service.create_customer_supplier(payload, user)


# --- POS Sales ---
@app.get("/api/pos-sales")
def list_pos_sales_endpoint(
    customer_code: str | None = None,
    cashier_id: int | None = None,
    limit: int = 50,
    user: dict[str, Any] = Depends(_current_user_dependency),
) -> list[dict[str, Any]]:
    return sales_finance_service.list_pos_sales(
        customer_code=customer_code, cashier_id=cashier_id, limit=limit
    )


@app.post("/api/pos-sales")
def create_pos_sale_endpoint(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(_require_role("Admin", "Cashier")),
) -> dict[str, Any]:
    return sales_finance_service.create_pos_sale(payload, user)


# --- Purchase Orders ---
@app.post("/api/purchase-orders")
def create_purchase_order_endpoint(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(_require_role("Admin", "Cashier")),
) -> dict[str, Any]:
    return sales_finance_service.create_purchase_order(payload, user)


@app.get("/api/purchase-orders")
def list_purchase_orders_endpoint(
    limit: int = Query(default=100, ge=1, le=500),
    user: dict[str, Any] = Depends(_current_user_dependency),
) -> list[dict[str, Any]]:
    with database() as connection:
        rows = connection.execute(
            """
            SELECT id, po_number, supplier_code, warehouse_id, status,
                   subtotal_cents, tax_cents, total_cents, expected_date,
                   received_date, created_at
            FROM purchase_orders
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/purchase-orders/{po_id}/receive")
def receive_purchase_order_endpoint(
    po_id: int,
    user: dict[str, Any] = Depends(_require_role("Admin", "Cashier")),
) -> dict[str, Any]:
    return sales_finance_service.receive_purchase_order(po_id, user)


# --- Cash/Bank & Financial ---
@app.get("/api/accounts")
def list_accounts_endpoint(
    user: dict[str, Any] = Depends(_current_user_dependency),
) -> list[dict[str, Any]]:
    return sales_finance_service.list_cash_bank_accounts()


@app.post("/api/accounts")
def create_account_endpoint(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(_require_role("Admin")),
) -> dict[str, Any]:
    return sales_finance_service.create_cash_bank_account(payload, user)


@app.post("/api/transactions")
def create_transaction_endpoint(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(_require_role("Admin", "Cashier")),
) -> dict[str, Any]:
    return sales_finance_service.record_financial_transaction(payload, user)


@app.get("/api/transactions")
def list_transactions_endpoint(
    limit: int = Query(default=100, ge=1, le=500),
    user: dict[str, Any] = Depends(_current_user_dependency),
) -> list[dict[str, Any]]:
    with database() as connection:
        rows = connection.execute(
            """
            SELECT t.id, t.account_id, a.name AS account_name, t.type,
                   t.amount_cents, t.currency, t.created_at
            FROM financial_transactions t
            JOIN cash_bank_accounts a ON a.id = t.account_id
            ORDER BY t.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


# --- Quotes/Invoices ---
@app.post("/api/documents")
def create_document_endpoint(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(_require_role("Admin", "Cashier")),
) -> dict[str, Any]:
    return sales_finance_service.create_quote_invoice(payload, user)


@app.get("/api/documents")
def list_documents_endpoint(
    limit: int = Query(default=100, ge=1, le=500),
    user: dict[str, Any] = Depends(_current_user_dependency),
) -> list[dict[str, Any]]:
    with database() as connection:
        rows = connection.execute(
            """
            SELECT id, document_number, type, customer_code, status,
                   subtotal_cents, tax_cents, discount_cents, total_cents,
                   currency, issue_date, due_date, created_at
            FROM quotes_invoices
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/documents/{document_id}/convert")
def convert_document_endpoint(
    document_id: int,
    user: dict[str, Any] = Depends(_require_role("Admin", "Cashier")),
) -> dict[str, Any]:
    return sales_finance_service.convert_quote_to_invoice(document_id, user)


# --- Analytics ---
@app.get("/api/analytics/kpis")
def analytics_kpis_endpoint(
    user: dict[str, Any] = Depends(_current_user_dependency),
) -> dict[str, Any]:
    return analytics_service.executive_kpis()


@app.get("/api/analytics/profit-loss")
def analytics_profit_loss_endpoint(
    start_date: str,
    end_date: str,
    user: dict[str, Any] = Depends(_current_user_dependency),
) -> dict[str, Any]:
    return analytics_service.profit_and_loss(start_date, end_date)


@app.get("/api/analytics/defective-devices")
def analytics_defective_endpoint(
    limit: int = 10,
    user: dict[str, Any] = Depends(_current_user_dependency),
) -> list[dict[str, Any]]:
    return analytics_service.top_defective_devices(limit=limit)


@app.get("/api/analytics/overdue-payments")
def analytics_overdue_endpoint(
    user: dict[str, Any] = Depends(_current_user_dependency),
) -> list[dict[str, Any]]:
    return analytics_service.overdue_payment_alerts()


# --- Audit Logs ---
@app.get("/api/audit-logs")
def list_audit_logs_endpoint(
    limit: int = 100,
    user: dict[str, Any] = Depends(_require_role("Admin")),
) -> list[dict[str, Any]]:
    with database() as connection:
        rows = connection.execute(
            """
            SELECT id, user_id, action, table_name, record_id, old_values,
                   new_values, timestamp, ip_address
            FROM audit_logs ORDER BY timestamp DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
