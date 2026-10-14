"""
FastAPI application for the Mock Internal ERP & Accounts Payable System.
Provides:
- Authentication via /auth/login -> Bearer token
- Invoices CRUD (/invoices)
- Vendors directory (/vendors)
- OpenAPI discovery at /openapi.json
- Built-in failure injection hooks
"""

import os
from datetime import datetime, timedelta, date
from typing import List, Optional

import jwt
from fastapi import FastAPI, Depends, HTTPException, status, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError

from mock_app.models import (
    Base, VendorModel, InvoiceModel,
    LoginRequest, TokenResponse,
    VendorResponse, InvoiceCreate, InvoiceUpdate, InvoiceResponse
)
from mock_app.failures import check_injected_failures, reset_failure_state

# Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mock_erp.db")
API_USERNAME = os.getenv("API_USERNAME", "admin")
API_PASSWORD = os.getenv("API_PASSWORD", "secret_token_pass")
SECRET_KEY = os.getenv("API_SECRET_KEY", "super_mock_erp_secret_key_12345")
ALGORITHM = "HS256"

# Database Engine & Session
# Uses SQLite by default (zero setup, no Docker required)
# To use PostgreSQL, set DATABASE_URL in .env to a postgres connection string
if "postgresql" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
else:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Security Scheme
security = HTTPBearer()

app = FastAPI(
    title="Mock Corporate ERP & Accounts Payable API",
    description="Mock internal company API for autonomous AI task worker prototype. Demonstrates strict schema validation, auth, and failure handling.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    """Dependency that yields a database session and ensures cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_access_token(username: str, expires_delta: timedelta = timedelta(hours=2)) -> str:
    """Generates a signed JWT access token."""
    expire = datetime.utcnow() + expires_delta
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verifies incoming Bearer token."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "InvalidToken", "message": "Could not validate credentials."}
            )
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "TokenExpired", "message": "Bearer token has expired. Please re-authenticate."}
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "InvalidToken", "message": "Invalid token signature."}
        )


def init_db():
    """Initialize database tables and seed baseline vendors."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        initial_vendors = [
            ("Acme Cloud Solutions", "Cloud Hosting"),
            ("Nexus Logistics Inc", "Supply Chain"),
            ("Apex Office Supplies", "Office Equipment"),
            ("Quantum Data Labs", "Data Science"),
            ("Skyline Telecom", "Telecommunications"),
        ]
        for name, category in initial_vendors:
            existing = db.query(VendorModel).filter(VendorModel.name == name).first()
            if not existing:
                db.add(VendorModel(name=name, category=category))
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Warning during DB startup seed: {e}")
    finally:
        db.close()

# Ensure database tables exist right away
init_db()

@app.on_event("startup")
def startup_event():
    init_db()


# ---------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------

@app.post("/auth/login", response_model=TokenResponse, tags=["Authentication"])
async def login(request: Request, body: LoginRequest):
    """
    Authenticate with username and password to obtain a Bearer token.
    """
    await check_injected_failures(request)
    if body.username == API_USERNAME and body.password == API_PASSWORD:
        token = create_access_token(body.username)
        return TokenResponse(access_token=token)
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": "AuthenticationFailed", "message": "Invalid username or password"}
    )


@app.get("/vendors", response_model=List[VendorResponse], tags=["Vendors"])
async def list_vendors(
    request: Request,
    current_user: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """List all registered vendors in the system."""
    injected_resp = await check_injected_failures(request)
    if injected_resp:
        return injected_resp

    vendors = db.query(VendorModel).order_by(VendorModel.name).all()
    return vendors


@app.post("/invoices", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED, tags=["Invoices"])
async def create_invoice(
    request: Request,
    payload: InvoiceCreate,
    current_user: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """
    Create a new invoice in the accounts payable ledger.
    Strictly validates due_date (YYYY-MM-DD) and amount (> 0).
    Returns 409 Conflict if duplicate invoice (same vendor, amount, due_date) already exists.
    """
    injected_resp = await check_injected_failures(request)
    if injected_resp:
        return injected_resp

    # Check for existing duplicate
    existing = db.query(InvoiceModel).filter(
        InvoiceModel.vendor == payload.vendor,
        InvoiceModel.amount == payload.amount,
        InvoiceModel.due_date == date.fromisoformat(payload.due_date)
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "DuplicateInvoiceError",
                "message": f"An invoice for '{payload.vendor}' with amount {payload.amount} due on {payload.due_date} already exists (ID: {existing.id}).",
                "existing_invoice_id": existing.id
            }
        )

    try:
        new_inv = InvoiceModel(
            vendor=payload.vendor,
            amount=payload.amount,
            currency=payload.currency,
            due_date=date.fromisoformat(payload.due_date),
            notes=payload.notes,
            status="PENDING"
        )
        db.add(new_inv)
        db.commit()
        db.refresh(new_inv)
        return InvoiceResponse.from_orm_model(new_inv)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "DuplicateInvoiceError", "message": "Duplicate invoice constraint violated."}
        )


@app.get("/invoices", response_model=List[InvoiceResponse], tags=["Invoices"])
async def list_invoices(
    request: Request,
    vendor: Optional[str] = Query(None, description="Filter by exact or partial vendor name"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (PENDING, APPROVED, PAID)"),
    current_user: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """List and filter existing invoices."""
    injected_resp = await check_injected_failures(request)
    if injected_resp:
        return injected_resp

    query = db.query(InvoiceModel)
    if vendor:
        query = query.filter(InvoiceModel.vendor.ilike(f"%{vendor}%"))
    if status_filter:
        query = query.filter(InvoiceModel.status == status_filter.upper())

    results = query.order_by(InvoiceModel.id.desc()).all()
    return [InvoiceResponse.from_orm_model(item) for item in results]


@app.get("/invoices/{invoice_id}", response_model=InvoiceResponse, tags=["Invoices"])
async def get_invoice_by_id(
    request: Request,
    invoice_id: int,
    current_user: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """
    Retrieve single invoice by ID. Used for the independent verification check.
    """
    injected_resp = await check_injected_failures(request)
    if injected_resp:
        return injected_resp

    invoice = db.query(InvoiceModel).filter(InvoiceModel.id == invoice_id).first()
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NotFound", "message": f"Invoice with ID {invoice_id} not found."}
        )
    return InvoiceResponse.from_orm_model(invoice)


@app.patch("/invoices/{invoice_id}", response_model=InvoiceResponse, tags=["Invoices"])
async def update_invoice(
    request: Request,
    invoice_id: int,
    payload: InvoiceUpdate,
    current_user: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Update fields on an existing invoice (e.g. correcting due date or notes)."""
    injected_resp = await check_injected_failures(request)
    if injected_resp:
        return injected_resp

    invoice = db.query(InvoiceModel).filter(InvoiceModel.id == invoice_id).first()
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NotFound", "message": f"Invoice with ID {invoice_id} not found."}
        )

    if payload.amount is not None:
        invoice.amount = payload.amount
    if payload.due_date is not None:
        invoice.due_date = date.fromisoformat(payload.due_date)
    if payload.status is not None:
        invoice.status = payload.status.value
    if payload.notes is not None:
        invoice.notes = payload.notes

    db.commit()
    db.refresh(invoice)
    return InvoiceResponse.from_orm_model(invoice)


@app.delete("/invoices/{invoice_id}", tags=["Invoices"])
async def delete_invoice(
    request: Request,
    invoice_id: int,
    current_user: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Delete an invoice (Destructive action - requires human approval)."""
    injected_resp = await check_injected_failures(request)
    if injected_resp:
        return injected_resp

    invoice = db.query(InvoiceModel).filter(InvoiceModel.id == invoice_id).first()
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NotFound", "message": f"Invoice with ID {invoice_id} not found."}
        )
    db.delete(invoice)
    db.commit()
    return {"status": "success", "message": f"Invoice {invoice_id} deleted successfully."}


@app.post("/system/reset", tags=["Testing"])
async def reset_system_database(
    db: Session = Depends(get_db)
):
    """Helper endpoint to wipe invoices and reset failure state before evaluation runs."""
    reset_failure_state()
    db.query(InvoiceModel).delete()
    db.commit()
    return {"status": "success", "message": "Invoices wiped and failure simulation reset."}
