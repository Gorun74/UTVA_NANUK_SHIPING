"""Report generation and export."""
import csv
from sqlalchemy import select, func
from app.models import Stock, Item, Sale, Container, FifoLot, SaleAllocation


def stock_snapshot(session) -> list:
    stmt = (
        select(Stock, Item)
        .join(Item, Stock.sku == Item.sku)
        .order_by(Item.sku)
    )
    rows = session.execute(stmt).all()
    result = []
    for stock, item in rows:
        lots_stmt = select(FifoLot).where(FifoLot.sku == item.sku, FifoLot.qty_remaining > 0)
        lots = session.execute(lots_stmt).scalars().all()
        total_qty = sum(l.qty_remaining for l in lots)
        total_val = sum(l.qty_remaining * l.landed_cost_aud_per_unit for l in lots)
        avg_cost = total_val / total_qty if total_qty > 0 else None

        result.append({
            'SKU': item.sku,
            'Description': item.description or '',
            'UPC': item.upc or '',
            'Qty On Hand': stock.qty_on_hand,
            'Reorder Point': item.reorder_point,
            'Avg Landed Cost AUD': round(avg_cost, 4) if avg_cost else '',
            'Stock Value AUD': round(total_val, 2) if total_val else 0,
            'MAP Price USD': item.us_map_price or '',
            'Price USD': item.price or '',
        })
    return result


def sales_report(session, from_date: str = None, to_date: str = None) -> list:
    stmt = select(Sale).order_by(Sale.date_sold)
    if from_date:
        stmt = stmt.where(Sale.date_sold >= from_date)
    if to_date:
        stmt = stmt.where(Sale.date_sold <= to_date)

    sales = session.execute(stmt).scalars().all()
    result = []
    for sale in sales:
        for line in sale.lines:
            item = line.item
            revenue = (line.revenue_aud if line.revenue_aud is not None else (line.sell_price_aud or 0) * (line.qty or 0))
            cogs = line.cogs_aud or 0
            gross_profit = revenue - cogs
            result.append({
                'Sale ID': sale.id,
                'Date': sale.date_sold,
                'Channel': sale.channel or '',
                'SKU': line.sku,
                'Description': item.description if item else '',
                'Qty': line.qty,
                'Sell Price AUD': line.sell_price_aud,
                'Revenue AUD': round(revenue, 2),
                'COGS AUD': round(cogs, 4) if line.cogs_aud is not None else '',
                'Gross Profit AUD': round(gross_profit, 2) if line.cogs_aud is not None else '',
                'Ship Cost AUD': round(line.ship_cost_sale_aud, 2) if line.ship_cost_sale_aud is not None else '',
                'Net Profit AUD': round(line.net_profit_aud, 2) if line.net_profit_aud is not None else '',
                'Net Margin %': round(line.net_margin_pct, 2) if line.net_margin_pct is not None else '',
                'COGS USD Equiv': round(line.cogs_usd_equiv, 4) if line.cogs_usd_equiv is not None else '',
                'FX Gain/Loss AUD': round(line.fx_gain_loss, 2) if line.fx_gain_loss is not None else '',
                'Sale Rate': sale.current_rate,
            })
    return result


def container_summary(session) -> list:
    stmt = select(Container).order_by(Container.date_ordered)
    containers = session.execute(stmt).scalars().all()
    result = []
    for c in containers:
        total_qty = sum(l.qty_ordered for l in c.lines)
        total_usd = sum((l.unit_price_usd or 0) * l.qty_ordered for l in c.lines)
        total_overhead = (c.shipping_aud or 0) + (c.other1_aud or 0) + (c.other2_aud or 0)
        total_aud = total_usd * (c.used_rate or 0) + total_overhead

        units_remaining = session.execute(
            select(func.sum(FifoLot.qty_remaining)).where(FifoLot.container_id == c.id)
        ).scalar_one_or_none() or 0
        units_sold = max(0, total_qty - units_remaining)

        profit = session.execute(
            select(func.sum(SaleAllocation.net_profit_aud)).where(SaleAllocation.container_id == c.id)
        ).scalar_one_or_none() or 0

        result.append({
            'Container ID': c.id,
            'Date Ordered': c.date_ordered,
            'Status': c.status,
            'USD->AUD Rate': c.used_rate,
            'Total Qty': total_qty,
            'Units Sold': units_sold,
            'Total USD': round(total_usd, 2),
            'Shipping AUD': c.shipping_aud,
            f'{c.other1_label} AUD': c.other1_aud,
            f'{c.other2_label} AUD': c.other2_aud,
            'Total Overhead AUD': round(total_overhead, 2),
            'Total AUD': round(total_aud, 2),
            'Ship Estimate AUD': round(c.ship_total_aud or 0, 2),
            'Container Profit AUD': round(profit, 2),
        })
    return result


def export_to_csv(data: list, filepath: str):
    if not data:
        return
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)


def profitability_report(session) -> dict:
    row = session.execute(
        select(
            func.sum(SaleAllocation.revenue_aud).label('revenue'),
            func.sum(SaleAllocation.cogs_aud).label('cogs'),
            func.sum(SaleAllocation.net_profit_aud).label('net_profit'),
            func.sum(SaleAllocation.qty).label('units_sold'),
        )
    ).first()

    revenue = (row.revenue or 0) if row else 0
    cogs = (row.cogs or 0) if row else 0
    net_profit = (row.net_profit or 0) if row else 0
    units_sold = int(row.units_sold or 0) if row else 0
    gross_profit = revenue - cogs

    return {
        'total_revenue_aud': round(revenue, 2),
        'total_cogs_aud': round(cogs, 2),
        'gross_profit_aud': round(gross_profit, 2),
        'gross_margin_%': round(gross_profit / revenue * 100, 2) if revenue else None,
        'net_profit_aud': round(net_profit, 2),
        'net_margin_%': round(net_profit / revenue * 100, 2) if revenue else None,
        'units_sold': units_sold,
    }


def export_to_excel(data: list, filepath: str, sheet_name: str = 'Report'):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    if not data:
        wb.save(filepath)
        return
    headers = list(data[0].keys())
    ws.append(headers)
    for row in data:
        ws.append([row.get(h, '') for h in headers])
    wb.save(filepath)
