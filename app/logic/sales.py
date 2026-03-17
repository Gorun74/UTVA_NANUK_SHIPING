"""Sales logic with FIFO deduction and per-container allocation."""
from sqlalchemy import select
from app.models import Sale, SaleLine, SaleAllocation, Container, FifoLot
from app.logic.inventory import deduct_fifo, ensure_stock


def _mark_sold_out_containers(session, container_ids: set[int]):
    for cid in container_ids:
        container = session.get(Container, cid)
        if not container:
            continue
        if container.status not in ('received', 'sold_out'):
            continue

        remaining = session.execute(
            select(FifoLot).where(
                FifoLot.container_id == cid,
                FifoLot.qty_remaining > 0,
            )
        ).scalars().first()

        if remaining is None:
            container.status = 'sold_out'


def create_sale(session, header: dict, lines_data: list) -> Sale:
    """
    Create a sale with FIFO deduction.
    Shipping/duty from shipping.py are already in landed COGS, so net profit equals gross profit.
    """
    current_rate = header['current_rate']

    sale = Sale(
        date_sold=header['date_sold'],
        channel=header.get('channel', ''),
        current_rate=current_rate,
    )
    session.add(sale)
    session.flush()

    touched_container_ids = set()

    for ld in lines_data:
        sku = ld['sku']
        qty = ld['qty']
        sell_price = ld['sell_price_aud']

        cogs_aud, cogs_usd, fx_gain, allocs = deduct_fifo(
            session,
            sku,
            qty,
            current_rate,
            return_allocations=True,
        )

        stock = ensure_stock(session, sku)
        stock.qty_on_hand = max(0, stock.qty_on_hand - qty)

        revenue = round((sell_price or 0) * qty, 2)
        gross_profit = round(revenue - (cogs_aud or 0), 2) if cogs_aud is not None else None
        gross_margin = round(gross_profit / revenue * 100, 2) if (gross_profit is not None and revenue) else None

        ship_cost_sale = round(sum((a.get('ship_cost_per_unit_aud') or 0) * a['qty'] for a in allocs), 2)
        duty_sale = round(sum((a.get('duty_per_unit_aud') or 0) * a['qty'] for a in allocs), 2)
        avg_ship_per_unit = round(ship_cost_sale / qty, 4) if qty else None
        avg_duty_per_unit = round(duty_sale / qty, 4) if qty else None

        net_profit = gross_profit
        net_margin = gross_margin
        total_return = round(net_profit + (fx_gain or 0), 2) if net_profit is not None else None

        line = SaleLine(
            sale_id=sale.id,
            sku=sku,
            qty=qty,
            sell_price_aud=sell_price,
            cogs_aud=cogs_aud,
            cogs_usd_equiv=cogs_usd,
            fx_gain_loss=fx_gain,
            revenue_aud=revenue,
            gross_profit_aud=gross_profit,
            gross_margin_pct=gross_margin,
            ship_cost_per_unit_aud=avg_ship_per_unit,
            ship_cost_sale_aud=ship_cost_sale,
            duty_per_unit_aud=avg_duty_per_unit,
            net_profit_aud=net_profit,
            net_margin_pct=net_margin,
            total_return_aud=total_return,
        )
        session.add(line)
        session.flush()

        for a in allocs:
            alloc_qty = a['qty']
            alloc_revenue = round((sell_price or 0) * alloc_qty, 2)
            alloc_cogs = round(a['cogs_aud'], 2)
            alloc_net = round(alloc_revenue - alloc_cogs, 2)

            session.add(SaleAllocation(
                sale_id=sale.id,
                sale_line_id=line.id,
                container_id=a['container_id'],
                sku=sku,
                qty=alloc_qty,
                revenue_aud=alloc_revenue,
                cogs_aud=alloc_cogs,
                net_profit_aud=alloc_net,
            ))
            touched_container_ids.add(a['container_id'])

    _mark_sold_out_containers(session, touched_container_ids)
    session.commit()
    return sale


def profit_summary(sale_line, ship_breakdown: dict = None, container_total_qty: int = None) -> dict:
    qty = sale_line.qty or 0
    sell_price = sale_line.sell_price_aud or 0
    cogs = sale_line.cogs_aud or 0
    fx = sale_line.fx_gain_loss

    revenue_aud = sell_price * qty
    gross_profit_aud = revenue_aud - cogs
    gross_margin = (gross_profit_aud / revenue_aud * 100) if revenue_aud else None

    ship_cost_aud = None
    duty_aud = None
    gst_aud = None
    if ship_breakdown and container_total_qty:
        ratio = qty / container_total_qty
        ship_cost_aud = round(ship_breakdown.get('TOTAL_AUD', 0) * ratio, 2)
        duty_aud = round(ship_breakdown.get('duty_AUD', 0) * ratio, 2)
        gst_aud = round(ship_breakdown.get('gst_AUD', 0) * ratio, 2)

    net_profit_aud = gross_profit_aud
    net_margin = (net_profit_aud / revenue_aud * 100) if revenue_aud else None

    total_return_aud = None
    if net_profit_aud is not None and fx is not None:
        total_return_aud = round(net_profit_aud + fx, 2)

    return {
        'revenue_aud': round(revenue_aud, 2),
        'cogs_aud': round(cogs, 4) if sale_line.cogs_aud is not None else None,
        'gross_profit_aud': round(gross_profit_aud, 2),
        'gross_margin_%': round(gross_margin, 2) if gross_margin is not None else None,
        'ship_cost_aud': ship_cost_aud,
        'duty_aud': duty_aud,
        'gst_aud': gst_aud,
        'net_profit_aud': round(net_profit_aud, 2),
        'net_margin_%': round(net_margin, 2) if net_margin is not None else None,
        'fx_gain_loss_aud': round(fx, 2) if fx is not None else None,
        'total_return_aud': total_return_aud,
    }
