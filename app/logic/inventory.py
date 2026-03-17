"""Stock operations and FIFO logic."""
from sqlalchemy import select
from app.models import FifoLot, Container, Stock, Item


def get_stock_qty(session, sku: str) -> int:
    s = session.get(Stock, sku)
    return s.qty_on_hand if s else 0


def ensure_stock(session, sku: str):
    s = session.get(Stock, sku)
    if s is None:
        s = Stock(sku=sku, qty_on_hand=0)
        session.add(s)
    return s


def deduct_fifo(session, sku: str, qty_needed: int, sale_rate: float, return_allocations: bool = False):
    """
    Deduct qty_needed from FIFO lots (oldest container first).
    Returns (cogs_aud, cogs_usd_equiv, fx_gain_loss[, allocations]).
    """
    stmt = (
        select(FifoLot)
        .join(Container, FifoLot.container_id == Container.id)
        .where(FifoLot.sku == sku)
        .where(FifoLot.qty_remaining > 0)
        .order_by(Container.date_ordered.asc(), FifoLot.id.asc())
    )
    lots = session.execute(stmt).scalars().all()

    total_cogs_aud = 0.0
    total_cogs_usd = 0.0
    total_fx = 0.0
    has_usd = False
    remaining = qty_needed
    allocations = []

    for lot in lots:
        if remaining <= 0:
            break
        take = min(lot.qty_remaining, remaining)
        cogs_aud = take * lot.landed_cost_aud_per_unit
        total_cogs_aud += cogs_aud

        if lot.used_rate and lot.used_rate > 0:
            has_usd = True
            usd_equiv = take * (lot.landed_cost_aud_per_unit / lot.used_rate)
            total_cogs_usd += usd_equiv
            total_fx += (sale_rate - lot.used_rate) * usd_equiv

        if return_allocations:
            allocations.append({
                'container_id': lot.container_id,
                'sku': sku,
                'qty': take,
                'cogs_aud': cogs_aud,
                'ship_cost_per_unit_aud': lot.ship_cost_per_unit_aud,
                'duty_per_unit_aud': lot.duty_per_unit_aud,
            })

        lot.qty_remaining -= take
        remaining -= take

    if remaining > 0:
        raise ValueError(f"Insufficient stock for {sku}: need {qty_needed}, short by {remaining}")

    base = (
        total_cogs_aud,
        total_cogs_usd if has_usd else None,
        total_fx if has_usd else None,
    )
    if return_allocations:
        return (*base, allocations)
    return base


def get_stock_value(session) -> float:
    stmt = select(Stock).where(Stock.qty_on_hand > 0)
    stocks = session.execute(stmt).scalars().all()
    total = 0.0
    for s in stocks:
        lots_stmt = (
            select(FifoLot)
            .where(FifoLot.sku == s.sku)
            .where(FifoLot.qty_remaining > 0)
        )
        lots = session.execute(lots_stmt).scalars().all()
        for lot in lots:
            total += lot.qty_remaining * lot.landed_cost_aud_per_unit
    return total


def get_unrealized_fx(session, today_rate: float) -> float:
    stmt = select(FifoLot).where(FifoLot.qty_remaining > 0)
    lots = session.execute(stmt).scalars().all()
    exposure = 0.0
    for lot in lots:
        if lot.used_rate and lot.used_rate > 0:
            usd_equiv = lot.qty_remaining * lot.landed_cost_aud_per_unit / lot.used_rate
            exposure += (today_rate - lot.used_rate) * usd_equiv
    return exposure


def get_low_stock(session):
    stmt = (
        select(Stock, Item)
        .join(Item, Stock.sku == Item.sku)
        .where(Stock.qty_on_hand <= Item.reorder_point)
        .order_by(Stock.qty_on_hand.asc())
    )
    rows = session.execute(stmt).all()
    result = []
    for stock, item in rows:
        result.append({
            'sku': item.sku,
            'description': item.description or '',
            'qty_on_hand': stock.qty_on_hand,
            'reorder_point': item.reorder_point,
        })
    return result


def get_critical_stock(session):
    """
    Returns items where qty_on_hand < 10% of total units ever received.
    """
    from app.models import ContainerLine
    stocks_stmt = (
        select(Stock, Item)
        .join(Item, Stock.sku == Item.sku)
        .order_by(Item.sku)
    )
    rows = session.execute(stocks_stmt).all()
    result = []
    for stock, item in rows:
        cl_stmt = (
            select(ContainerLine)
            .join(Container, ContainerLine.container_id == Container.id)
            .where(
                ContainerLine.sku == item.sku,
                Container.status.in_(['received', 'closed', 'sold_out']),
            )
        )
        cl_rows = session.execute(cl_stmt).scalars().all()
        total_received = sum((cl.qty_received or cl.qty_ordered or 0) for cl in cl_rows)
        if total_received > 0 and stock.qty_on_hand < 0.1 * total_received:
            result.append({
                'sku': item.sku,
                'description': item.description or '',
                'qty_on_hand': stock.qty_on_hand,
                'total_received': total_received,
                'pct_remaining': round(stock.qty_on_hand / total_received * 100, 1),
                'reorder_flag': stock.qty_on_hand <= item.reorder_point,
            })
    result.sort(key=lambda x: x['pct_remaining'])
    return result
