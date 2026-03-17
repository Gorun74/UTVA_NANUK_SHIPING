from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import select, func
from app.database import get_session
from app.models import Container, Stock, Item
from app.logic.inventory import get_stock_value, get_critical_stock, get_low_stock

bp = Blueprint("dashboard", __name__)


@bp.route("/dashboard")
@login_required
def index():
    session = get_session()

    stock_value = get_stock_value(session)
    critical = get_critical_stock(session)
    low = get_low_stock(session)

    # Container status counts
    statuses = ["ordered", "in_transit", "received", "sold_out", "closed"]
    container_counts = {}
    for s in statuses:
        count = session.execute(
            select(func.count(Container.id)).where(Container.status == s)
        ).scalar() or 0
        container_counts[s] = count

    # Recent containers (last 5)
    recent_containers = session.execute(
        select(Container).order_by(Container.id.desc()).limit(5)
    ).scalars().all()

    # Total items & stock
    total_items = session.execute(select(func.count(Item.sku))).scalar() or 0
    total_qty = session.execute(
        select(func.sum(Stock.qty_on_hand))
    ).scalar() or 0

    return render_template(
        "dashboard/index.html",
        stock_value=stock_value,
        critical=critical,
        low_stock=low,
        container_counts=container_counts,
        recent_containers=recent_containers,
        total_items=total_items,
        total_qty=total_qty,
    )
