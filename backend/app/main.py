from datetime import datetime, timezone
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session
import jwt
from .config import settings
from .models import Base, User, Profile, Driver, PricingPackage, Booking, Assignment, DutySession, DutyEvent, AuditLog, LoginActivity, utcnow
from .billing import billable_minutes, calculate_bill

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
app = FastAPI(title="Coimbatore Driver & Freelance Hub API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.cors_origins.split(",")], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
bearer = HTTPBearer()

@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        defaults = [("non_commercial", "2 hours", 120, "300.00", "50.00"), ("non_commercial", "4 hours", 240, "500.00", "50.00"), ("non_commercial", "8 hours", 480, "1000.00", "50.00"), ("non_commercial", "12 hours", 720, "1200.00", "50.00")]
        if not db.scalar(select(PricingPackage.id).limit(1)):
            for category,name,duration,price,surcharge in defaults:
                db.add(PricingPackage(category=category,name=name,duration_minutes=duration,price=price,surcharge=surcharge))
            db.commit()

def get_db():
    db=SessionLocal()
    try: yield db
    finally: db.close()

def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)):
    if not settings.supabase_jwt_secret: raise HTTPException(503, "Authentication is not configured")
    try:
        options={"require": ["sub", "exp"]}
        claims=jwt.decode(credentials.credentials, settings.supabase_jwt_secret, algorithms=["HS256"], options=options, issuer=settings.supabase_issuer or None)
        uid=claims["sub"]; email=str(claims.get("email", "")).lower()
    except Exception: raise HTTPException(401, "Invalid or expired access token")
    user=db.get(User, uid)
    # Bootstrap admin only from the verified identity's email, never from client-provided role.
    if not user:
        role="admin" if email == settings.admin_email.lower() else "customer"
        user=User(id=uid,email=email,role=role); db.add(user); db.commit(); db.refresh(user)
    elif email == settings.admin_email.lower() and user.role != "admin":
        user.role="admin"; db.commit()
    return user

def roles(*allowed):
    def check(user: User = Depends(current_user)):
        if user.role not in allowed: raise HTTPException(403, "Insufficient permissions")
        if user.role == "driver":
            raise HTTPException(403, "Driver role is not approved")
        return user
    return check

def driver_user(user: User = Depends(current_user), db: Session = Depends(get_db)):
    driver=db.get(Driver,user.id)
    if user.role != "driver" or not driver or not driver.approved: raise HTTPException(403,"Approved driver account required")
    return user

class Onboard(BaseModel):
    full_name: str = Field(min_length=2,max_length=160)
    phone: str = Field(default="",max_length=32)
    account_type: str = Field(pattern="^(customer|driver)$")
class BookingIn(BaseModel):
    pickup: str = Field(min_length=2,max_length=300)
    destination: str = Field(min_length=2,max_length=300)
    travel_at: datetime
    trip_type: str = Field(min_length=2,max_length=40)
    category: str = Field(pattern="^(commercial|non_commercial)$")
    package_id: int
    requirements: str = Field(default="",max_length=3000)
class DutyAction(BaseModel): booking_id: int
class PriceIn(BaseModel):
    category: str
    name: str
    duration_minutes: int = Field(gt=0)
    price: float = Field(ge=0)
    surcharge: float = Field(ge=0)
    enabled: bool = True

@app.get("/health")
def health(): return {"status":"ok"}

@app.post("/api/onboarding")
def onboarding(data: Onboard, user: User=Depends(current_user), db: Session=Depends(get_db)):
    if user.role == "admin": data.account_type="customer" # do not mutate company admin's role/profile to driver
    user.role = "admin" if user.email.lower()==settings.admin_email.lower() else data.account_type
    db.add(Profile(user_id=user.id,full_name=data.full_name,phone=data.phone))
    if data.account_type == "driver" and user.role != "admin": db.add(Driver(user_id=user.id,approved=False))
    db.add(AuditLog(actor_id=user.id,action="registration",entity_type="user",entity_id=user.id))
    db.commit()
    return {"role":user.role,"approval_required":user.role=="driver"}

@app.post("/api/login-event")
def login_event(user: User=Depends(current_user), db: Session=Depends(get_db)):
    # Called after an explicit successful sign-in, not on token refresh.
    db.add(LoginActivity(user_id=user.id,email=user.email,account_type=user.role)); db.commit()
    return {"recorded":True}

@app.get("/api/pricing")
def pricing(db: Session=Depends(get_db)):
    return [dict(id=p.id,category=p.category,name=p.name,duration_minutes=p.duration_minutes,price=str(p.price),surcharge=str(p.surcharge)) for p in db.scalars(select(PricingPackage).where(PricingPackage.enabled.is_(True))).all()]

@app.post("/api/bookings")
def create_booking(data: BookingIn,user: User=Depends(current_user),db: Session=Depends(get_db)):
    package=db.get(PricingPackage,data.package_id)
    if not package or not package.enabled or package.category != data.category: raise HTTPException(400,"Select an available package in the chosen category")
    booking=Booking(customer_id=user.id,pickup=data.pickup,destination=data.destination,travel_at=data.travel_at,trip_type=data.trip_type,category=data.category,package_id=package.id,requirements=data.requirements)
    db.add(booking); db.flush(); db.add(AuditLog(actor_id=user.id,action="booking_created",entity_type="booking",entity_id=str(booking.id))); db.commit(); db.refresh(booking)
    return {"id":booking.id,"status":booking.status,"whatsapp_url":f"https://wa.me/918438996308?text=Booking%20{booking.id}%20-%20{booking.pickup}%20to%20{booking.destination}%20on%20{booking.travel_at.date()}"}

@app.get("/api/bookings")
def bookings(user: User=Depends(current_user),db: Session=Depends(get_db)):
    query=select(Booking)
    if user.role == "customer": query=query.where(Booking.customer_id==user.id)
    elif user.role == "driver":
        driver=db.get(Driver,user.id)
        if not driver or not driver.approved: raise HTTPException(403,"Driver approval pending")
        query=query.join(Assignment,Assignment.booking_id==Booking.id).where(Assignment.driver_id==user.id)
    elif user.role != "admin": raise HTTPException(403,"Forbidden")
    return [dict(id=b.id,pickup=b.pickup,destination=b.destination,travel_at=b.travel_at.isoformat(),trip_type=b.trip_type,category=b.category,status=b.status,package_id=b.package_id) for b in db.scalars(query.order_by(Booking.created_at.desc())).all()]

@app.post("/api/admin/assign/{booking_id}/{driver_id}")
def assign(booking_id:int,driver_id:str,admin:User=Depends(roles("admin")),db:Session=Depends(get_db)):
    booking=db.get(Booking,booking_id); driver=db.get(Driver,driver_id)
    if not booking or not driver or not driver.approved: raise HTTPException(404,"Booking or approved driver not found")
    assignment=Assignment(booking_id=booking_id,driver_id=driver_id); booking.status="assigned"
    db.add(assignment); db.add(AuditLog(actor_id=admin.id,action="booking_assigned",entity_type="booking",entity_id=str(booking_id))); db.commit()
    return {"assigned":True}

@app.post("/api/admin/drivers/{driver_id}/approve")
def approve_driver(driver_id:str,approved:bool,admin:User=Depends(roles("admin")),db:Session=Depends(get_db)):
    driver=db.get(Driver,driver_id)
    if not driver: raise HTTPException(404,"Driver not found")
    driver.approved=approved; db.add(AuditLog(actor_id=admin.id,action="driver_approval_changed",entity_type="driver",entity_id=driver_id)); db.commit(); return {"approved":approved}

@app.put("/api/admin/pricing/{package_id}")
def update_price(package_id:int,data:PriceIn,admin:User=Depends(roles("admin")),db:Session=Depends(get_db)):
    package=db.get(PricingPackage,package_id)
    if not package: package=PricingPackage(id=package_id,**data.model_dump())
    else:
        for k,v in data.model_dump().items(): setattr(package,k,v)
    db.add(package); db.add(AuditLog(actor_id=admin.id,action="pricing_updated",entity_type="pricing_package",entity_id=str(package_id))); db.commit(); return {"id":package.id,"updated":True}

@app.post("/api/duty/start")
def start_duty(data:DutyAction,user:User=Depends(driver_user),db:Session=Depends(get_db)):
    booking=db.get(Booking,data.booking_id)
    assignment=db.scalar(select(Assignment).where(Assignment.booking_id==data.booking_id,Assignment.driver_id==user.id,Assignment.status!="rejected"))
    if not booking or not assignment or booking.status not in ("assigned","confirmed"): raise HTTPException(400,"Booking is not assigned and ready")
    if db.scalar(select(DutySession.id).where(DutySession.driver_id==user.id,DutySession.ended_at.is_(None))): raise HTTPException(409,"An active duty already exists")
    s=DutySession(booking_id=booking.id,driver_id=user.id,package_id=booking.package_id); db.add(s); db.flush(); db.add(DutyEvent(session_id=s.id,actor_id=user.id,action="start")); booking.status="in_progress"; db.commit(); db.refresh(s)
    return {"id":s.id,"status":s.status,"started_at":s.started_at.isoformat()}

@app.get("/api/duty/active")
def active_duty(user:User=Depends(driver_user),db:Session=Depends(get_db)):
    s=db.scalar(select(DutySession).where(DutySession.driver_id==user.id,DutySession.ended_at.is_(None)))
    if not s:return None
    now=utcnow(); paused=s.paused_seconds+(int((now-s.paused_at).total_seconds()) if s.paused_at else 0)
    return {"id":s.id,"booking_id":s.booking_id,"status":s.status,"started_at":s.started_at.isoformat(),"paused_seconds":paused,"server_now":now.isoformat()}

@app.post("/api/duty/{session_id}/{action}")
def duty_action(session_id:int,action:str,user:User=Depends(driver_user),db:Session=Depends(get_db)):
    if action not in ("pause","resume","end"): raise HTTPException(404,"Unknown duty action")
    s=db.get(DutySession,session_id)
    if not s or s.driver_id!=user.id or s.ended_at: raise HTTPException(404,"Active session not found")
    now=utcnow()
    if action=="pause":
        if s.paused_at: raise HTTPException(409,"Already paused")
        s.paused_at=now; s.status="paused"
    elif action=="resume":
        if not s.paused_at: raise HTTPException(409,"Session is not paused")
        s.paused_seconds+=max(0,int((now-s.paused_at).total_seconds())); s.paused_at=None; s.status="active"
    else:
        if s.paused_at:
            s.paused_seconds+=max(0,int((now-s.paused_at).total_seconds())); s.paused_at=None
        s.ended_at=now; s.status="ended"
        mins=billable_minutes(s.started_at,now,s.paused_seconds)
        package=db.get(PricingPackage,s.package_id)
        result=calculate_bill(package.price,package.duration_minutes,mins,package.surcharge)
        s.billable_minutes=mins; s.total_amount=result["total"]
        booking=db.get(Booking,s.booking_id); booking.status="completed"
    db.add(DutyEvent(session_id=s.id,actor_id=user.id,action=action,occurred_at=now)); db.add(AuditLog(actor_id=user.id,action=f"duty_{action}",entity_type="duty_session",entity_id=str(s.id))); db.commit()
    return {"id":s.id,"status":s.status,"billable_minutes":s.billable_minutes,"total_amount":str(s.total_amount) if s.total_amount is not None else None,"server_time":now.isoformat()}

@app.get("/api/admin/overview")
def admin_overview(admin:User=Depends(roles("admin")),db:Session=Depends(get_db)):
    from sqlalchemy import func
    return {"customers":db.scalar(select(func.count()).select_from(User).where(User.role=="customer")) or 0,"drivers":db.scalar(select(func.count()).select_from(Driver)) or 0,"bookings":db.scalar(select(func.count()).select_from(Booking)) or 0,"logins_today":db.scalar(select(func.count()).select_from(LoginActivity).where(LoginActivity.logged_at>=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0))) or 0}
