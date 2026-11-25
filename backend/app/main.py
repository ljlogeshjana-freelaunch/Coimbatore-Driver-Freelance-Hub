from datetime import datetime, timezone
from decimal import Decimal
from email_validator import validate_email, EmailNotValidError
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, EmailStr, field_validator
from sqlalchemy import create_engine, select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from typing import Optional
import logging
import jwt
from jwt import PyJWKClient
from .config import settings
from .models import Base, User, Profile, Driver, PricingPackage, Booking, Assignment, DutySession, DutyEvent, AuditLog, LoginActivity, FreelancingRequest, Notification, utcnow
from .billing import billable_minutes, calculate_bill
from .email_service import notify_admin, EmailDeliveryError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hub.api")
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine_options = {"connect_args": connect_args}
if settings.database_url == "sqlite:///:memory:": engine_options["poolclass"] = StaticPool
engine = create_engine(settings.database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
app = FastAPI(title="Coimbatore Driver & Freelance Hub API", version="1.1.0", description="Customer bookings, driver duty and company operations API")
origins = [x.strip() for x in settings.cors_origins.split(",") if x.strip()]
if settings.environment == "production" and (not origins or "*" in origins):
    raise RuntimeError("CORS_ORIGINS must contain explicit production origins; wildcard CORS is not allowed")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])
bearer = HTTPBearer(auto_error=False)
jwks_client = PyJWKClient(settings.supabase_jwks_url) if settings.supabase_jwks_url else None

@app.on_event("startup")
def startup():
    # Local SQLite is convenient for development. Production PostgreSQL is migrated
    # explicitly using Supabase migrations; startup must not mutate production schema.
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.scalar(select(PricingPackage.id).limit(1)):
            for category, name, duration, price in [
                ("non_commercial", "2 hours", 120, "300.00"),
                ("non_commercial", "4 hours", 240, "500.00"),
                ("non_commercial", "8 hours", 480, "1000.00"),
                ("non_commercial", "12 hours", 720, "1200.00"),
            ]:
                db.add(PricingPackage(category=category, name=name, duration_minutes=duration, price=Decimal(price), surcharge=Decimal("50.00")))
            db.commit()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def decode_token(token: str) -> dict:
    try:
        if settings.supabase_jwt_secret:
            claims = jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], options={"require": ["sub", "exp"]}, issuer=settings.supabase_issuer or None, audience="authenticated")
        elif jwks_client:
            key = jwks_client.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["ES256", "RS256"], options={"require": ["sub", "exp"]}, issuer=settings.supabase_issuer or None, audience="authenticated")
        else:
            raise HTTPException(503, "Authentication is not configured: set SUPABASE_JWT_SECRET or SUPABASE_JWKS_URL")
        return claims
    except HTTPException:
        raise
    except Exception as exc:
        logger.info("Access token rejected (%s)", type(exc).__name__)
        raise HTTPException(401, "Invalid or expired access token") from exc

def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)):
    if credentials is None:
        raise HTTPException(401, "Sign in is required", headers={"WWW-Authenticate": "Bearer"})
    claims = decode_token(credentials.credentials)
    uid = claims["sub"]
    email = str(claims.get("email", "")).strip().lower()
    if not email:
        raise HTTPException(401, "Verified account email is missing")
    user = db.get(User, uid)
    if not user:
        user = User(id=uid, email=email, role="admin" if email == settings.admin_email.lower() else "customer")
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            user = db.get(User, uid)
        if not user:
            raise HTTPException(409, "Unable to create account profile")
    elif user.email.lower() != email:
        user.email = email
        db.commit()
    # Admin privileges derive only from the verified token email and configured address.
    if email == settings.admin_email.lower() and user.role != "admin":
        user.role = "admin"
        db.commit()
    return user

def optional_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer), db: Session = Depends(get_db)):
    if credentials is None:
        return None
    return current_user(credentials, db)

def roles(*allowed):
    def check(user: User = Depends(current_user)):
        if user.role not in allowed:
            raise HTTPException(403, "Insufficient permissions")
        return user
    return check

def driver_user(user: User = Depends(current_user), db: Session = Depends(get_db)):
    driver = db.get(Driver, user.id)
    if user.role != "driver" or not driver or not driver.approved:
        raise HTTPException(403, "Approved driver account required")
    return user

def send_admin_notice(subject: str, text: str):
    try:
        notify_admin(subject, text)
    except EmailDeliveryError:
        logger.warning("Admin notification delivery failed for event: %s", subject)

class Onboard(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    phone: str = Field(default="", max_length=32)
    account_type: str = Field(pattern="^(customer|driver)$")
class BookingIn(BaseModel):
    pickup: str = Field(min_length=2, max_length=300)
    destination: str = Field(min_length=2, max_length=300)
    travel_at: datetime
    trip_type: str = Field(min_length=2, max_length=40)
    category: str = Field(pattern="^(commercial|non_commercial)$")
    package_id: int
    requirements: str = Field(default="", max_length=3000)
class DutyAction(BaseModel):
    booking_id: int
class PriceIn(BaseModel):
    category: str = Field(pattern="^(commercial|non_commercial)$")
    name: str = Field(min_length=2, max_length=80)
    duration_minutes: int = Field(gt=0, le=10080)
    price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    surcharge: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    enabled: bool = True
class FreelanceIn(BaseModel):
    service: str = Field(min_length=2, max_length=120)
    customer_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    details: str = Field(min_length=5, max_length=5000)
    @field_validator("email")
    @classmethod
    def normalized_email(cls, value):
        return str(value).lower()
class StatusIn(BaseModel):
    status: str = Field(pattern="^(pending|in_progress|completed|cancelled)$")

@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        logger.exception("Health check database connection failed")
        raise HTTPException(503, "Database unavailable") from exc

@app.post("/api/onboarding")
def onboarding(data: Onboard, user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = db.get(Profile, user.id)
    if profile:
        # Account type is immutable after initial onboarding. This prevents a user
        # from changing roles by replaying the client onboarding request.
        if user.role not in ("admin", data.account_type):
            raise HTTPException(409, "Account type cannot be changed after registration")
        profile.full_name = data.full_name
        profile.phone = data.phone
    else:
        if user.role != "admin":
            user.role = data.account_type
        profile = Profile(user_id=user.id, full_name=data.full_name, phone=data.phone)
        db.add(profile)
        if data.account_type == "driver" and user.role != "admin" and not db.get(Driver, user.id):
            db.add(Driver(user_id=user.id, approved=False))
        db.add(AuditLog(actor_id=user.id, action="registration", entity_type="user", entity_id=user.id))
    db.commit()
    return {"role": user.role, "approval_required": user.role == "driver" and not bool(db.get(Driver, user.id) and db.get(Driver, user.id).approved)}

@app.post("/api/login-event")
def login_event(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.add(LoginActivity(user_id=user.id, email=user.email, account_type=user.role))
    db.commit()
    send_admin_notice("Successful account login", f"Account type: {user.role}\nEmail: {user.email}\nTime (UTC): {utcnow().isoformat()}")
    return {"recorded": True}

@app.get("/api/pricing")
def pricing(db: Session = Depends(get_db)):
    rows = db.scalars(select(PricingPackage).where(PricingPackage.enabled.is_(True)).order_by(PricingPackage.category, PricingPackage.duration_minutes)).all()
    return [dict(id=p.id, category=p.category, name=p.name, duration_minutes=p.duration_minutes, price=str(p.price), surcharge=str(p.surcharge)) for p in rows]

@app.post("/api/bookings", status_code=201)
def create_booking(data: BookingIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role not in ("customer", "admin"):
        raise HTTPException(403, "Customer account required to book")
    package = db.get(PricingPackage, data.package_id)
    if not package or not package.enabled or package.category != data.category:
        raise HTTPException(400, "Select an available package in the chosen category")
    travel_at = data.travel_at
    if travel_at.tzinfo is None:
        raise HTTPException(422, "Travel date and time must include a timezone")
    booking = Booking(customer_id=user.id, pickup=data.pickup.strip(), destination=data.destination.strip(), travel_at=travel_at.astimezone(timezone.utc), trip_type=data.trip_type, category=data.category, package_id=package.id, requirements=data.requirements.strip())
    db.add(booking)
    db.flush()
    db.add(AuditLog(actor_id=user.id, action="booking_created", entity_type="booking", entity_id=str(booking.id)))
    db.add(Notification(user_id=user.id, title="Booking request received", body=f"Request #{booking.id} is pending manual availability confirmation."))
    db.commit()
    message = f"Driver booking request #{booking.id}\nPickup: {booking.pickup}\nDestination: {booking.destination}\nTravel date: {booking.travel_at.isoformat()}"
    send_admin_notice(f"New driver booking request #{booking.id}", message)
    from urllib.parse import quote
    return {"id": booking.id, "status": booking.status, "whatsapp_url": f"https://wa.me/918438996308?text={quote(message)}"}

@app.get("/api/bookings")
def bookings(user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Booking)
    if user.role == "customer":
        query = query.where(Booking.customer_id == user.id)
    elif user.role == "driver":
        driver = db.get(Driver, user.id)
        if not driver or not driver.approved:
            raise HTTPException(403, "Driver approval pending")
        query = query.join(Assignment, Assignment.booking_id == Booking.id).where(Assignment.driver_id == user.id, Assignment.status != "rejected")
    elif user.role != "admin":
        raise HTTPException(403, "Forbidden")
    rows = db.scalars(query.order_by(Booking.created_at.desc()).limit(200)).all()
    return [dict(id=b.id, pickup=b.pickup, destination=b.destination, travel_at=b.travel_at.isoformat(), trip_type=b.trip_type, category=b.category, status=b.status, package_id=b.package_id) for b in rows]

@app.post("/api/freelancing-requests", status_code=201)
def create_freelance_request(data: FreelanceIn, request: Request, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    # Lightweight per-process abuse guard. Use an edge/WAF limit for multi-instance production deployments.
    now = datetime.now(timezone.utc).timestamp()
    bucket = app.state.__dict__.setdefault("freelance_rate", {})
    key = request.client.host if request.client else "unknown"
    previous, count = bucket.get(key, (now, 0))
    if now - previous > 3600:
        previous, count = now, 0
    if count >= 10:
        raise HTTPException(429, "Too many requests. Please contact us by email or WhatsApp.")
    bucket[key] = (previous, count + 1)
    item = FreelancingRequest(customer_id=user.id if user else None, service=data.service, customer_name=data.customer_name.strip(), email=str(data.email), details=data.details.strip())
    db.add(item)
    db.flush()
    db.add(AuditLog(actor_id=user.id if user else "public", action="freelance_request_created", entity_type="freelancing_request", entity_id=str(item.id)))
    db.commit()
    message = f"Freelance enquiry #{item.id}\nService: {item.service}\nName: {item.customer_name}\nEmail: {item.email}\nDetails: {item.details}"
    send_admin_notice(f"New freelance enquiry #{item.id}", message)
    from urllib.parse import quote
    return {"id": item.id, "status": item.status, "whatsapp_url": f"https://wa.me/918122599306?text={quote(message)}"}

@app.get("/api/freelancing-requests/mine")
def my_freelance_requests(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(FreelancingRequest).where(FreelancingRequest.customer_id == user.id).order_by(FreelancingRequest.created_at.desc())).all()
    return [dict(id=x.id, service=x.service, details=x.details, status=x.status, created_at=x.created_at.isoformat()) for x in rows]

@app.get("/api/admin/freelancing-requests")
def admin_freelance_requests(admin: User = Depends(roles("admin")), db: Session = Depends(get_db)):
    rows = db.scalars(select(FreelancingRequest).order_by(FreelancingRequest.created_at.desc()).limit(200)).all()
    return [dict(id=x.id, service=x.service, customer_name=x.customer_name, email=x.email, details=x.details, status=x.status, created_at=x.created_at.isoformat()) for x in rows]

@app.patch("/api/admin/freelancing-requests/{request_id}")
def update_freelance_status(request_id: int, data: StatusIn, admin: User = Depends(roles("admin")), db: Session = Depends(get_db)):
    item = db.get(FreelancingRequest, request_id)
    if not item:
        raise HTTPException(404, "Freelance request not found")
    item.status = data.status
    db.add(AuditLog(actor_id=admin.id, action="freelance_status_changed", entity_type="freelancing_request", entity_id=str(item.id)))
    db.commit()
    return {"id": item.id, "status": item.status}

@app.get("/api/admin/drivers")
def admin_drivers(admin: User = Depends(roles("admin")), db: Session = Depends(get_db)):
    rows = db.execute(select(Driver, User, Profile).join(User, User.id == Driver.user_id).outerjoin(Profile, Profile.user_id == Driver.user_id).order_by(User.created_at.desc())).all()
    return [dict(user_id=d.user_id, email=u.email, full_name=p.full_name if p else "", phone=p.phone if p else "", approved=d.approved, commercial=d.commercial) for d,u,p in rows]

@app.get("/api/admin/login-history")
def login_history(admin: User = Depends(roles("admin")), db: Session = Depends(get_db)):
    rows = db.scalars(select(LoginActivity).order_by(LoginActivity.logged_at.desc()).limit(200)).all()
    return [dict(email=x.email, account_type=x.account_type, logged_at=x.logged_at.isoformat()) for x in rows]

@app.post("/api/admin/assign/{booking_id}/{driver_id}")
def assign(booking_id: int, driver_id: str, admin: User = Depends(roles("admin")), db: Session = Depends(get_db)):
    booking, driver = db.get(Booking, booking_id), db.get(Driver, driver_id)
    if not booking or not driver or not driver.approved:
        raise HTTPException(404, "Booking or approved driver not found")
    assignment = db.scalar(select(Assignment).where(Assignment.booking_id == booking_id, Assignment.driver_id == driver_id))
    if assignment:
        if assignment.status != "rejected":
            raise HTTPException(409, "Driver is already assigned")
        assignment.status = "assigned"
    else:
        assignment = Assignment(booking_id=booking_id, driver_id=driver_id, status="assigned")
        db.add(assignment)
    booking.status = "assigned"
    db.add(AuditLog(actor_id=admin.id, action="booking_assigned", entity_type="booking", entity_id=str(booking_id)))
    db.commit()
    return {"assigned": True}

@app.post("/api/admin/drivers/{driver_id}/approve")
def approve_driver(driver_id: str, approved: bool, admin: User = Depends(roles("admin")), db: Session = Depends(get_db)):
    driver = db.get(Driver, driver_id)
    if not driver:
        raise HTTPException(404, "Driver not found")
    driver.approved = approved
    db.add(AuditLog(actor_id=admin.id, action="driver_approval_changed", entity_type="driver", entity_id=driver_id))
    db.commit()
    return {"approved": approved}

@app.put("/api/admin/pricing/{package_id}")
def update_price(package_id: int, data: PriceIn, admin: User = Depends(roles("admin")), db: Session = Depends(get_db)):
    package = db.get(PricingPackage, package_id)
    if not package:
        package = PricingPackage(id=package_id, **data.model_dump())
    else:
        for key, value in data.model_dump().items():
            setattr(package, key, value)
    db.add(package)
    db.add(AuditLog(actor_id=admin.id, action="pricing_updated", entity_type="pricing_package", entity_id=str(package_id)))
    db.commit()
    return {"id": package.id, "updated": True}

@app.post("/api/driver/assignments/{assignment_id}/{action}")
def driver_assignment_action(assignment_id: int, action: str, user: User = Depends(driver_user), db: Session = Depends(get_db)):
    if action not in ("accept", "reject"):
        raise HTTPException(404, "Unknown assignment action")
    assignment = db.get(Assignment, assignment_id)
    if not assignment or assignment.driver_id != user.id or assignment.status != "assigned":
        raise HTTPException(404, "Pending assignment not found")
    assignment.status = "accepted" if action == "accept" else "rejected"
    booking = db.get(Booking, assignment.booking_id)
    if action == "reject" and booking:
        booking.status = "pending"
    db.add(AuditLog(actor_id=user.id, action=f"assignment_{action}", entity_type="assignment", entity_id=str(assignment.id)))
    db.commit()
    return {"status": assignment.status}

@app.get("/api/driver/earnings")
def driver_earnings(user: User = Depends(driver_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(DutySession).where(DutySession.driver_id == user.id, DutySession.ended_at.is_not(None)).order_by(DutySession.ended_at.desc()).limit(200)).all()
    return [dict(id=s.id, booking_id=s.booking_id, started_at=s.started_at.isoformat(), ended_at=s.ended_at.isoformat(), billable_minutes=s.billable_minutes, total_amount=str(s.total_amount or Decimal("0.00"))) for s in rows]

@app.post("/api/duty/start")
def start_duty(data: DutyAction, user: User = Depends(driver_user), db: Session = Depends(get_db)):
    booking = db.get(Booking, data.booking_id)
    assignment = db.scalar(select(Assignment).where(Assignment.booking_id == data.booking_id, Assignment.driver_id == user.id, Assignment.status.in_(["assigned", "accepted"])))
    if not booking or not assignment or booking.status not in ("assigned", "confirmed"):
        raise HTTPException(400, "Booking is not assigned and ready")
    if db.scalar(select(DutySession.id).where(DutySession.driver_id == user.id, DutySession.ended_at.is_(None))):
        raise HTTPException(409, "An active duty already exists")
    session = DutySession(booking_id=booking.id, driver_id=user.id, package_id=booking.package_id)
    db.add(session)
    db.flush()
    db.add(DutyEvent(session_id=session.id, actor_id=user.id, action="start"))
    booking.status = "in_progress"
    db.commit()
    db.refresh(session)
    return {"id": session.id, "status": session.status, "started_at": session.started_at.isoformat()}

@app.get("/api/duty/active")
def active_duty(user: User = Depends(driver_user), db: Session = Depends(get_db)):
    session = db.scalar(select(DutySession).where(DutySession.driver_id == user.id, DutySession.ended_at.is_(None)))
    if not session:
        return None
    now = utcnow()
    paused = session.paused_seconds + (int((now - session.paused_at).total_seconds()) if session.paused_at else 0)
    return {"id": session.id, "booking_id": session.booking_id, "status": session.status, "started_at": session.started_at.isoformat(), "paused_seconds": paused, "server_now": now.isoformat()}

@app.post("/api/duty/{session_id}/{action}")
def duty_action(session_id: int, action: str, user: User = Depends(driver_user), db: Session = Depends(get_db)):
    if action not in ("pause", "resume", "end"):
        raise HTTPException(404, "Unknown duty action")
    session = db.get(DutySession, session_id)
    if not session or session.driver_id != user.id or session.ended_at:
        raise HTTPException(404, "Active session not found")
    now = utcnow()
    if action == "pause":
        if session.paused_at:
            raise HTTPException(409, "Already paused")
        session.paused_at = now
        session.status = "paused"
    elif action == "resume":
        if not session.paused_at:
            raise HTTPException(409, "Session is not paused")
        session.paused_seconds += max(0, int((now - session.paused_at).total_seconds()))
        session.paused_at = None
        session.status = "active"
    else:
        if session.paused_at:
            session.paused_seconds += max(0, int((now - session.paused_at).total_seconds()))
            session.paused_at = None
        session.ended_at = now
        session.status = "ended"
        minutes = billable_minutes(session.started_at, now, session.paused_seconds)
        package = db.get(PricingPackage, session.package_id)
        result = calculate_bill(package.price, package.duration_minutes, minutes, package.surcharge)
        session.billable_minutes = minutes
        session.total_amount = result["total"]
        booking = db.get(Booking, session.booking_id)
        booking.status = "completed"
        db.add(Notification(user_id=booking.customer_id, title="Driver duty completed", body=f"Booking #{booking.id} completed. Billable time: {minutes} minutes; total: ₹{result['total']} ."))
    db.add(DutyEvent(session_id=session.id, actor_id=user.id, action=action, occurred_at=now))
    db.add(AuditLog(actor_id=user.id, action=f"duty_{action}", entity_type="duty_session", entity_id=str(session.id)))
    db.commit()
    return {"id": session.id, "status": session.status, "billable_minutes": session.billable_minutes, "total_amount": str(session.total_amount) if session.total_amount is not None else None, "server_time": now.isoformat()}

@app.get("/api/notifications")
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(100)).all()
    return [dict(id=n.id, title=n.title, body=n.body, read_at=n.read_at.isoformat() if n.read_at else None, created_at=n.created_at.isoformat()) for n in rows]

@app.get("/api/admin/overview")
def admin_overview(admin: User = Depends(roles("admin")), db: Session = Depends(get_db)):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return {"customers": db.scalar(select(func.count()).select_from(User).where(User.role == "customer")) or 0, "drivers": db.scalar(select(func.count()).select_from(Driver)) or 0, "bookings": db.scalar(select(func.count()).select_from(Booking)) or 0, "logins_today": db.scalar(select(func.count()).select_from(LoginActivity).where(LoginActivity.logged_at >= today)) or 0}
