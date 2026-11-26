from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.models import AuditLog, Base, Driver, PricingPackage, User


@pytest.fixture
def api_client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", test_session)
    monkeypatch.setattr(main, "send_admin_notice", lambda *args: None)
    identity = {"user": None}
    main.app.dependency_overrides[main.current_user] = lambda: identity["user"]
    main.app.dependency_overrides[main.optional_user] = lambda: identity["user"]
    try:
        with TestClient(main.app) as client:
            yield client, test_session, identity
    finally:
        main.app.dependency_overrides.clear()
        engine.dispose()


def create_user(session_factory, *, role, email, driver_approved=None):
    user_id = str(uuid4())
    with session_factory() as db:
        user = User(id=user_id, email=email, role=role)
        db.add(user)
        if driver_approved is not None:
            db.add(Driver(user_id=user_id, approved=driver_approved))
        db.commit()
    return user


def booking_payload():
    return {
        "pickup": "Coimbatore",
        "destination": "Chennai",
        "travel_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "trip_type": "Outstation one-way",
        "category": "non_commercial",
        "package_id": 1,
        "requirements": "",
    }


def test_customer_driver_booking_and_duty_workflow(api_client):
    client, session_factory, identity = api_client
    customer = create_user(session_factory, role="customer", email="customer@example.com")
    admin = create_user(session_factory, role="admin", email="admin@example.com")
    driver = create_user(
        session_factory,
        role="driver",
        email="driver@example.com",
        driver_approved=True,
    )

    identity["user"] = customer
    created = client.post("/api/bookings", json=booking_payload())
    assert created.status_code == 201
    booking_id = created.json()["id"]

    identity["user"] = admin
    assigned = client.post(f"/api/admin/assign/{booking_id}/{driver.id}")
    assert assigned.status_code == 200

    identity["user"] = driver
    assignments = client.get("/api/bookings")
    assert assignments.status_code == 200
    assignment = assignments.json()[0]
    assert assignment["assignment_status"] == "assigned"
    assert assignment["assignment_id"]
    assert client.post(f"/api/duty/start", json={"booking_id": booking_id}).status_code == 400

    accepted = client.post(
        f"/api/driver/assignments/{assignment['assignment_id']}/accept"
    )
    assert accepted.json()["status"] == "accepted"
    started = client.post("/api/duty/start", json={"booking_id": booking_id})
    assert started.status_code == 200
    session_id = started.json()["id"]

    assert client.get("/api/duty/active").json()["status"] == "active"
    assert client.post(f"/api/duty/{session_id}/pause").status_code == 200
    assert client.get("/api/duty/active").json()["status"] == "paused"
    assert client.post(f"/api/duty/{session_id}/resume").status_code == 200
    ended = client.post(f"/api/duty/{session_id}/end")
    assert ended.status_code == 200
    assert ended.json()["total_amount"] == "50.00"
    assert client.get("/api/driver/earnings").json()[0]["booking_id"] == booking_id

    identity["user"] = customer
    assert client.get("/api/bookings").json()[0]["status"] == "completed"


def test_assignment_rejection_releases_booking_for_another_driver(api_client):
    client, session_factory, identity = api_client
    customer = create_user(session_factory, role="customer", email="customer@example.com")
    admin = create_user(session_factory, role="admin", email="admin@example.com")
    first_driver = create_user(
        session_factory,
        role="driver",
        email="first@example.com",
        driver_approved=True,
    )
    second_driver = create_user(
        session_factory,
        role="driver",
        email="second@example.com",
        driver_approved=True,
    )
    identity["user"] = customer
    booking_id = client.post("/api/bookings", json=booking_payload()).json()["id"]

    identity["user"] = admin
    assert client.post(f"/api/admin/assign/{booking_id}/{first_driver.id}").status_code == 200
    assert client.post(f"/api/admin/assign/{booking_id}/{second_driver.id}").status_code == 409

    identity["user"] = first_driver
    assignment_id = client.get("/api/bookings").json()[0]["assignment_id"]
    assert client.post(f"/api/driver/assignments/{assignment_id}/reject").status_code == 200

    identity["user"] = customer
    assert client.get("/api/bookings").json()[0]["status"] == "pending"
    identity["user"] = admin
    assert client.post(f"/api/admin/assign/{booking_id}/{second_driver.id}").status_code == 200


def test_public_freelance_request_uses_null_audit_actor(api_client):
    client, session_factory, _identity = api_client
    response = client.post(
        "/api/freelancing-requests",
        json={
            "service": "Portfolio websites",
            "customer_name": "Test Customer",
            "email": "customer@example.com",
            "details": "Please contact me about a portfolio website.",
        },
    )
    assert response.status_code == 201
    with session_factory() as db:
        audit = db.scalar(
            select(AuditLog).where(AuditLog.entity_type == "freelancing_request")
        )
        assert audit is not None
        assert audit.actor_id is None


def test_driver_onboarding_creates_pending_driver_application(api_client):
    client, session_factory, identity = api_client
    customer = create_user(session_factory, role="customer", email="applicant@example.com")
    identity["user"] = customer

    response = client.post(
        "/api/onboarding",
        json={"full_name": "Driver Applicant", "phone": "1234567890", "account_type": "driver"},
    )
    assert response.status_code == 200
    assert response.json() == {"role": "driver", "approval_required": True}
    with session_factory() as db:
        driver = db.get(Driver, customer.id)
        assert driver is not None
        assert driver.approved is False


def test_admin_can_list_disabled_pricing_but_public_list_hides_it(api_client):
    client, session_factory, identity = api_client
    admin = create_user(session_factory, role="admin", email="admin@example.com")
    with session_factory() as db:
        package = db.scalar(select(PricingPackage).where(PricingPackage.id == 1))
        package.enabled = False
        db.commit()
    identity["user"] = admin

    identity["user"] = None
    assert all(item["id"] != 1 for item in client.get("/api/pricing").json())
    identity["user"] = admin
    admin_packages = client.get("/api/pricing")
    assert admin_packages.status_code == 200
    assert next(item for item in admin_packages.json() if item["id"] == 1)["enabled"] is False
