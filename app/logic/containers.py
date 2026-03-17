"""Container purchase and receiving logic."""
import datetime
from sqlalchemy import select, delete, update, text
from app.models import Container, ContainerLine, FifoLot, Item, Sale, SaleLine, SaleAllocation, Stock
from app.logic.inventory import ensure_stock
from app.logic.shipping import estimate_shipping

ETA_DAYS = 42


def _default_eta(date_ordered: str) -> str:
    try:
        d = datetime.date.fromisoformat(date_ordered)
        return (d + datetime.timedelta(days=ETA_DAYS)).isoformat()
    except Exception:
        return ''


def calculate_landed_costs(lines_data: list, shipping_aud: float,
                            other1_aud: float, other2_aud: float,
                            used_rate: float, by_value: bool = False) -> list:
    total_overhead = (shipping_aud or 0) + (other1_aud or 0) + (other2_aud or 0)
    total_qty = sum(l['qty_ordered'] for l in lines_data if l.get('qty_ordered'))
    total_usd_value = (
        sum((l.get('unit_price_usd') or 0) * (l.get('qty_ordered') or 0) for l in lines_data)
        if by_value else 0
    )
    overhead_per_unit = total_overhead / total_qty if total_qty > 0 else 0

    result = []
    for l in lines_data:
        qty = l.get('qty_ordered') or 0
        unit_usd = l.get('unit_price_usd')
        usd_cost_aud = (unit_usd or 0) * qty * (used_rate or 0)
        if by_value and total_usd_value > 0 and unit_usd:
            line_usd_val = unit_usd * qty
            overhead_this_unit = (total_overhead * line_usd_val / total_usd_value) / qty if qty > 0 else 0
        else:
            overhead_this_unit = overhead_per_unit
        landed = (usd_cost_aud / qty + overhead_this_unit) if qty > 0 else overhead_this_unit
        result.append({**l, 'landed_cost_per_unit': landed})
    return result


def _compute_and_store_shipping_estimate(session, container: Container, lines_data: list) -> dict | None:
    """Compute shipping.py estimate for a container and persist breakdown fields."""
    skus = [ld.get('sku') for ld in lines_data if ld.get('sku')]
    if not skus:
        return None

    items_q = session.execute(select(Item).where(Item.sku.in_(skus))).scalars().all()
    items_map = {i.sku: i for i in items_q}

    ship_total_cbm = sum(
        ((items_map[ld['sku']].volume_m3 or 0) if ld['sku'] in items_map else 0)
        * (ld.get('qty_ordered') or 0)
        for ld in lines_data if ld.get('sku')
    )
    ship_total_aud_goods = sum(
        (ld.get('unit_price_usd') or 0) * (ld.get('qty_ordered') or 0)
        for ld in lines_data
    ) * (container.used_rate or 0)

    container.total_cbm = ship_total_cbm
    try:
        ship = estimate_shipping(
            cbm=ship_total_cbm,
            goods_value_aud=ship_total_aud_goods,
            usd_aud_rate=container.used_rate or 1.58,
        )
        summary = ship.summary()
    except Exception:
        summary = None

    if summary:
        container.ship_ocean_aud = summary.get('ocean_AUD', 0)
        container.ship_extras_aud = summary.get('extras_AUD', 0)
        container.ship_insurance_aud = summary.get('insurance_AUD', 0)
        container.ship_duty_aud = summary.get('duty_AUD', 0)
        container.ship_gst_aud = summary.get('gst_AUD', 0)
        container.ship_total_aud = summary.get('TOTAL_AUD', 0)

    return summary


def delete_draft(session, container_id: int):
    """Delete a draft container and its lines."""
    container = session.get(Container, container_id)
    if container is None:
        raise ValueError(f"Container {container_id} not found")
    if container.status != "draft":
        raise ValueError("Only draft containers can be deleted this way")
    session.execute(delete(ContainerLine).where(ContainerLine.container_id == container_id))
    session.delete(container)
    session.commit()


def create_container(session, header: dict, lines_data: list, status: str = "ordered") -> Container:
    date_ordered = header['date_ordered']
    eta = header.get('expected_arrival_date') or _default_eta(date_ordered)
    container = Container(
        date_ordered=date_ordered,
        expected_arrival_date=eta,
        used_rate=header['used_rate'],
        shipping_aud=header.get('shipping_aud', 0),
        other1_aud=header.get('other1_aud', 0),
        other1_label=header.get('other1_label', 'Other 1'),
        other2_aud=header.get('other2_aud', 0),
        other2_label=header.get('other2_label', 'Other 2'),
        container_size=header.get('container_size', '20ft'),
        container_fill=header.get('container_fill', 'full'),
        status=status,
    )
    session.add(container)
    session.flush()
    for ld in lines_data:
        if not ld.get('sku') or not ld.get('qty_ordered'):
            continue
        session.add(ContainerLine(
            container_id=container.id,
            sku=ld['sku'],
            qty_ordered=ld['qty_ordered'],
            unit_price_usd=ld.get('unit_price_usd'),
        ))
        ensure_stock(session, ld['sku'])

    # Persist shipping.py estimate immediately (ordered stage), so costs are visible
    # before receiving and can be reviewed while in transit.
    _compute_and_store_shipping_estimate(session, container, lines_data)
    session.commit()
    return container


def receive_container(session, container_id: int, by_value: bool = False):
    container = session.get(Container, container_id)
    if container is None:
        raise ValueError(f"Container {container_id} not found")
    if container.status in ('received', 'sold_out', 'closed'):
        raise ValueError('Container already received/closed')

    lines_data = [
        {'sku': l.sku, 'qty_ordered': l.qty_ordered,
         'unit_price_usd': l.unit_price_usd, 'line_id': l.id}
        for l in container.lines
    ]
    costed = calculate_landed_costs(
        lines_data, container.shipping_aud, container.other1_aud,
        container.other2_aud, container.used_rate, by_value=by_value,
    )

    ship_breakdown = _compute_and_store_shipping_estimate(session, container, costed)
    container.ship_breakdown = ship_breakdown

    ship_total_qty = sum(cd.get('qty_ordered') or 0 for cd in costed)
    ship_per_unit = None
    duty_per_unit = None
    manual_overhead = (container.shipping_aud or 0) + (container.other1_aud or 0) + (container.other2_aud or 0)
    if ship_breakdown and ship_total_qty > 0:
        # Effective landed overhead = shipping.py estimate + any manually entered overhead.
        # shipping.py estimate covers ocean/extras/insurance/duty/gst.
        effective_overhead = (container.ship_total_aud or 0) + manual_overhead
        ship_per_unit = effective_overhead / ship_total_qty
        duty_per_unit = (container.ship_duty_aud or 0) / ship_total_qty
        for cd in costed:
            qty = cd.get('qty_ordered') or 0
            usd_cost_aud = (cd.get('unit_price_usd') or 0) * qty * (container.used_rate or 0)
            cd['landed_cost_per_unit'] = (
                (usd_cost_aud / qty + ship_per_unit) if qty > 0 else ship_per_unit
            )
    elif ship_total_qty > 0:
        # Fallback: if estimate fails, still include manual overhead.
        ship_per_unit = manual_overhead / ship_total_qty
        duty_per_unit = 0.0
        for cd in costed:
            qty = cd.get('qty_ordered') or 0
            usd_cost_aud = (cd.get('unit_price_usd') or 0) * qty * (container.used_rate or 0)
            cd['landed_cost_per_unit'] = (
                (usd_cost_aud / qty + ship_per_unit) if qty > 0 else ship_per_unit
            )

    for cd in costed:
        sku = cd['sku']
        qty = cd['qty_ordered']
        landed = cd['landed_cost_per_unit']
        line_id = cd.get('line_id')

        stock = ensure_stock(session, sku)
        stock.qty_on_hand += qty

        cl = session.get(ContainerLine, line_id) if line_id else None
        if cl is None:
            cl = session.execute(
                select(ContainerLine).where(
                    ContainerLine.container_id == container_id,
                    ContainerLine.sku == sku
                )
            ).scalars().first()
        if cl:
            cl.qty_received = qty

        session.add(FifoLot(
            container_id=container_id,
            sku=sku,
            qty_remaining=qty,
            landed_cost_aud_per_unit=landed,
            used_rate=container.used_rate,
            ship_cost_per_unit_aud=ship_per_unit,
            duty_per_unit_aud=duty_per_unit,
        ))

    container.status = 'received'
    container.date_received = datetime.date.today().isoformat()
    session.commit()


def advance_container_status(session, container_id: int, new_status: str):
    """
    Valid transitions here (non-receive):
        ordered -> in_transit -> (use receive_container for 'received') -> closed
    """
    valid = {'in_transit', 'closed'}
    if new_status not in valid:
        raise ValueError(f"Use receive_container() for '{new_status}'; valid here: {valid}")
    container = session.get(Container, container_id)
    if container is None:
        raise ValueError(f"Container {container_id} not found")
    if container.status == 'sold_out' and new_status == 'in_transit':
        raise ValueError('Sold-out container cannot move back to transit')
    container.status = new_status
    session.commit()


def reset_container_and_warehouse_data(session):
    """
    Clear operational data only:
      - containers and lines
      - fifo lots
      - sales and sale lines/allocations
      - stock quantities (set to 0)
    Keeps catalog/cases (Item) untouched.
    """
    session.execute(delete(SaleAllocation))
    session.execute(delete(SaleLine))
    session.execute(delete(Sale))
    session.execute(delete(FifoLot))
    session.execute(delete(ContainerLine))
    session.execute(delete(Container))
    session.execute(update(Stock).values(qty_on_hand=0))

    # Reset AUTOINCREMENT counters for clean testing IDs
    try:
        session.execute(text(
            "DELETE FROM sqlite_sequence WHERE name IN "
            "('containers','container_lines','fifo_lots','sales','sale_lines','sale_allocations')"
        ))
    except Exception:
        pass

    session.commit()
