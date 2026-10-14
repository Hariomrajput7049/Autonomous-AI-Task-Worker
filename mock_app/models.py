"""
SQLAlchemy ORM models and Pydantic schemas for the mock ERP system.
Strict validation is enforced so invalid formats (e.g. non-ISO dates, negative amounts)
raise 422 Unprocessable Entity with structured machine-readable error details.
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional, List
import re

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# ---------------------------------------------------------
# SQLAlchemy ORM Models
# ---------------------------------------------------------

class VendorModel(Base):
    """Represents an approved company vendor in the ERP system."""
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    category = Column(String(50), default="General")
    created_at = Column(DateTime, default=datetime.utcnow)


class InvoiceStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class InvoiceModel(Base):
    """Represents an Accounts Payable invoice."""
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    vendor = Column(String(100), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)
    due_date = Column(Date, nullable=False)
    status = Column(String(20), default=InvoiceStatus.PENDING.value, nullable=False)
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Prevent accidental duplicates of the exact same vendor, amount, and due_date
    __table_args__ = (
        UniqueConstraint('vendor', 'amount', 'due_date', name='uq_invoice_vendor_amount_date'),
    )


# ---------------------------------------------------------
# Pydantic Schemas for Validation and Serialization
# ---------------------------------------------------------

class LoginRequest(BaseModel):
    username: str = Field(..., description="API Username")
    password: str = Field(..., description="API Password")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in_seconds: int = 3600


class VendorResponse(BaseModel):
    id: int
    name: str
    category: str

    class Config:
        from_attributes = True


class InvoiceCreate(BaseModel):
    """
    Strict payload for creating an invoice.
    Date must follow strict ISO format (YYYY-MM-DD).
    Amount must be a positive float.
    """
    vendor: str = Field(..., min_length=1, description="Exact vendor company name")
    amount: float = Field(..., gt=0.0, description="Positive numeric invoice total amount")
    due_date: str = Field(
        ...,
        description="Invoice payment due date in strict YYYY-MM-DD format"
    )
    currency: str = Field("USD", max_length=5, description="Currency code (e.g., USD, EUR)")
    notes: Optional[str] = Field(None, max_length=255)

    @field_validator("due_date")
    @classmethod
    def validate_strict_iso_date(cls, v: str) -> str:
        # Enforce exact YYYY-MM-DD pattern regex
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("due_date must strictly be formatted as YYYY-MM-DD (e.g. 2026-11-15)")
        try:
            # Also ensure it's a valid calendar date
            date.fromisoformat(v)
        except ValueError:
            raise ValueError(f"Invalid calendar date: {v}")
        return v


class InvoiceUpdate(BaseModel):
    """Schema for updating an invoice (e.g. correcting due date or notes)."""
    amount: Optional[float] = Field(None, gt=0.0)
    due_date: Optional[str] = None
    status: Optional[InvoiceStatus] = None
    notes: Optional[str] = None

    @field_validator("due_date")
    @classmethod
    def validate_strict_iso_date_opt(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("due_date must strictly be formatted as YYYY-MM-DD (e.g. 2026-11-15)")
        date.fromisoformat(v)
        return v


class InvoiceResponse(BaseModel):
    id: int
    vendor: str
    amount: float
    currency: str
    due_date: str
    status: str
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_model(cls, model: InvoiceModel):
        return cls(
            id=model.id,
            vendor=model.vendor,
            amount=model.amount,
            currency=model.currency,
            due_date=model.due_date.isoformat(),
            status=model.status,
            notes=model.notes,
            created_at=model.created_at
        )
