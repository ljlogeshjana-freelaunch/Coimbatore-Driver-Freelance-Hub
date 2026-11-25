from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Numeric, Integer, Text, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase): pass

def utcnow(): return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)  # Supabase auth UUID
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="customer")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Profile(Base):
    __tablename__ = "profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")

class Driver(Base):
    __tablename__ = "drivers"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    commercial: Mapped[bool] = mapped_column(Boolean, default=False)

class PricingPackage(Base):
    __tablename__ = "pricing_packages"
    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(24), index=True)
    name: Mapped[str] = mapped_column(String(80))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Numeric(10,2))
    surcharge: Mapped[Decimal] = mapped_column(Numeric(10,2), default=Decimal("50.00"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    pickup: Mapped[str] = mapped_column(String(300))
    destination: Mapped[str] = mapped_column(String(300))
    travel_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trip_type: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(24))
    package_id: Mapped[int] = mapped_column(ForeignKey("pricing_packages.id"))
    requirements: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Assignment(Base):
    __tablename__ = "driver_assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.user_id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="assigned")

class DutySession(Base):
    __tablename__ = "driver_duty_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), index=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.user_id"), index=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("pricing_packages.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_seconds: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active")
    billable_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(10,2), nullable=True)

class DutyEvent(Base):
    __tablename__ = "duty_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("driver_duty_sessions.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(20))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(100), index=True)
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class LoginActivity(Base):
    __tablename__ = "login_activity"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    account_type: Mapped[str] = mapped_column(String(20))
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

Index("ix_duty_one_open_per_driver", DutySession.driver_id, unique=True, postgresql_where=DutySession.ended_at.is_(None))
