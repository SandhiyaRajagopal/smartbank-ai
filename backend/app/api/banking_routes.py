"""Dashboard data endpoints. They call the same services/banking.py functions the agents use."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..db.models import Alert, User
from ..db.session import get_db
from ..realtime.hub import hub
from ..realtime.simulator import simulate_transaction
from ..services import banking
from .deps import current_user

router = APIRouter(prefix="/api", tags=["banking"])


@router.get("/overview")
def overview(user: User = Depends(current_user), db: Session = Depends(get_db)):
    cid = user.customer_id
    return {
        "profile": banking.customer_profile(db, cid),
        "accounts": banking.list_accounts(db, cid),
        "cards": banking.list_cards(db, cid),
        "credit": banking.credit_report(db, cid),
        "loans": banking.list_loans(db, cid),
        "spending": banking.spending_summary(db, cid, days=30),
        "unread_alerts": len(banking.list_alerts(db, cid, unread_only=True, limit=100)),
    }


@router.get("/transactions")
def transactions(limit: int = Query(25, le=100), days: int | None = None, category: str | None = None,
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    return banking.list_transactions(db, user.customer_id, limit=limit, days=days, category=category)


@router.get("/alerts")
def alerts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return banking.list_alerts(db, user.customer_id, limit=30)


@router.post("/alerts/read-all")
def mark_alerts_read(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.query(Alert).filter(Alert.customer_id == user.customer_id, Alert.read.is_(False)).update({"read": True})
    db.commit()
    return {"ok": True}


# ---------- demo controls (used in the demo video to trigger scenarios on demand) ----------

class SimulateRequest(BaseModel):
    suspicious: bool = False


@router.post("/demo/simulate")
async def demo_simulate(body: SimulateRequest, user: User = Depends(current_user)):
    """Inject one live transaction right now (normal or suspicious) and push it over WebSocket."""
    result = await run_in_threadpool(simulate_transaction, user.customer_id, body.suspicious)
    for event in result["events"]:
        await hub.publish(user.customer_id, event)
    return result["events"][0]["data"]


@router.post("/demo/reset-cards")
def demo_reset_cards(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Re-activate this customer's cards so the fraud demo can be repeated."""
    for card in banking.list_cards(db, user.customer_id):
        banking.unblock_card(db, user.customer_id, card["id"])
    db.commit()
    return banking.list_cards(db, user.customer_id)
