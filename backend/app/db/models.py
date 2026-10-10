"""Database tables (SQLAlchemy ORM) - this is our simulated "core banking system".

Layer 6 of the reference architecture (Enterprise Data): Core Banking, CRM,
Transactions and Loan Systems are all represented by these tables.
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    """Login identity. One user maps to one bank customer."""
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    customer: Mapped["Customer"] = relationship()


class Customer(Base):
    """CRM / Customer 360 record."""
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20))
    city: Mapped[str] = mapped_column(String(60))
    home_country: Mapped[str] = mapped_column(String(2), default="IN")
    segment: Mapped[str] = mapped_column(String(30))  # e.g. Salaried, Business, Student
    employment: Mapped[str] = mapped_column(String(80))
    monthly_income: Mapped[float] = mapped_column(Float)
    kyc_status: Mapped[str] = mapped_column(String(20), default="VERIFIED")  # VERIFIED / PENDING
    travel_notice: Mapped[bool] = mapped_column(Boolean, default=False)  # told the bank they are travelling
    customer_since: Mapped[datetime] = mapped_column(DateTime)

    accounts: Mapped[list["Account"]] = relationship(back_populates="customer")
    cards: Mapped[list["Card"]] = relationship(back_populates="customer")
    loans: Mapped[list["Loan"]] = relationship(back_populates="customer")
    credit_report: Mapped["CreditReport"] = relationship(back_populates="customer", uselist=False)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    account_number: Mapped[str] = mapped_column(String(20), unique=True)
    type: Mapped[str] = mapped_column(String(20))  # SAVINGS / CURRENT
    balance: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    customer: Mapped[Customer] = relationship(back_populates="accounts")


class Card(Base):
    __tablename__ = "cards"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    masked_number: Mapped[str] = mapped_column(String(25))
    type: Mapped[str] = mapped_column(String(10))  # DEBIT / CREDIT
    network: Mapped[str] = mapped_column(String(15))
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE")  # ACTIVE / BLOCKED
    credit_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    customer: Mapped[Customer] = relationship(back_populates="cards")


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    card_id: Mapped[int | None] = mapped_column(ForeignKey("cards.id"), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    amount: Mapped[float] = mapped_column(Float)
    direction: Mapped[str] = mapped_column(String(6))  # DEBIT / CREDIT
    merchant: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(30))
    channel: Mapped[str] = mapped_column(String(15))  # UPI / CARD / NETBANKING / ATM / NEFT
    city: Mapped[str] = mapped_column(String(60))
    country: Mapped[str] = mapped_column(String(2), default="IN")
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_level: Mapped[str] = mapped_column(String(6), default="LOW")
    risk_reasons: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(10), default="COMPLETED")  # COMPLETED / FLAGGED / DECLINED


class Loan(Base):
    __tablename__ = "loans"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    type: Mapped[str] = mapped_column(String(15))  # PERSONAL / CAR / HOME / EDUCATION
    principal: Mapped[float] = mapped_column(Float)
    outstanding: Mapped[float] = mapped_column(Float)
    interest_rate: Mapped[float] = mapped_column(Float)
    tenure_months: Mapped[int] = mapped_column(Integer)
    emi: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(12))  # ACTIVE / CLOSED / APPLIED
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    customer: Mapped[Customer] = relationship(back_populates="loans")


class CreditReport(Base):
    """Simulated credit bureau data (like a CIBIL report)."""
    __tablename__ = "credit_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), unique=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = no credit history
    enquiries_6m: Mapped[int] = mapped_column(Integer, default=0)
    missed_payments_12m: Mapped[int] = mapped_column(Integer, default=0)
    credit_utilisation: Mapped[float] = mapped_column(Float, default=0.0)  # 0-1
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    customer: Mapped[Customer] = relationship(back_populates="credit_report")


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(20))  # FRAUD / CARD / LOAN / INFO
    severity: Mapped[str] = mapped_column(String(8))  # INFO / WARNING / CRITICAL
    title: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AuditLog(Base):
    """Every chat request, routing decision, guardrail hit and sensitive action is recorded here."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trace_id: Mapped[str] = mapped_column(String(40), index=True)
    event: Mapped[str] = mapped_column(String(40))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
