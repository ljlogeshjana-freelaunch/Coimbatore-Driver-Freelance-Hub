from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Numeric, Integer, Text, Index, Uuid
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc) if value is not None else None

def utcnow():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="customer")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

class Profile(Base):
    __tablename__ = "profiles"
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")

class Driver(Base):
    __tablename__ = "drivers"
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    commercial: Mapped[bool] = mapped_column(Boolean, default=False)

class PricingPackage(Base):
    __tablename__ = "pricing_packages"
    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(24), index=True)
    name: Mapped[str] = mapped_column(String(80))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    surcharge: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("50.00"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), index=True)
    pickup: Mapped[str] = mapped_column(String(300))
    destination: Mapped[str] = mapped_column(String(300))
    travel_at: Mapped[datetime] = mapped_column(UTCDateTime())
    trip_type: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(24))
    package_id: Mapped[int] = mapped_column(ForeignKey("pricing_packages.id"))
    requirements: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

class Assignment(Base):
    __tablename__ = "driver_assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    driver_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("drivers.user_id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="assigned")
    __table_args__ = (Index("uq_assignment_booking_driver", "booking_id", "driver_id", unique=True),)

class DutySession(Base):
    __tablename__ = "driver_duty_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), index=True)
    driver_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("drivers.user_id"), index=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("pricing_packages.id"))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    paused_seconds: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active")
    billable_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

Index("ix_duty_one_open_per_driver", DutySession.driver_id, unique=True, postgresql_where=DutySession.ended_at.is_(None))

class DutyEvent(Base):
    __tablename__ = "duty_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("driver_duty_sessions.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    action: Mapped[str] = mapped_column(String(20))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

class LoginActivity(Base):
    __tablename__ = "login_activity"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    account_type: Mapped[str] = mapped_column(String(20))
    logged_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

class FreelancingRequest(Base):
    __tablename__ = "freelancing_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    service: Mapped[str] = mapped_column(String(120))
    customer_name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(320), index=True)
    details: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
