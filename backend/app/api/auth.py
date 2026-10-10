"""Login endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..auth.security import create_token, verify_password
from ..db.models import Customer, User
from ..db.session import get_db
from .deps import current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalars(select(User).where(User.email == body.email.strip().lower())).first()
    if not user or not verify_password(body.password, user.password_hash):
        audit("-", "login_failed", {"email": body.email[:120]})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    audit("-", "login", {}, user_id=user.id)
    return {"token": create_token(user.id), "user": {"email": user.email, "name": user.customer.name}}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"email": user.email, "name": user.customer.name, "customer_id": user.customer_id}


@router.get("/demo-accounts")
def demo_accounts(db: Session = Depends(get_db)):
    """Lists the fictional demo logins for the login page (no secrets - just who is who)."""
    rows = db.execute(select(User.email, Customer.name, Customer.segment)
                      .join(Customer, Customer.id == User.customer_id).order_by(User.id)).all()
    hints = {"priya": "Clean profile, excellent credit", "arjun": "Suspicious Dubai transactions",
             "rahul": "High existing EMIs", "ananya": "KYC pending, new to credit"}
    return [{"email": e, "name": n, "segment": s, "scenario": hints.get(e.split("@")[0], "")} for e, n, s in rows]
