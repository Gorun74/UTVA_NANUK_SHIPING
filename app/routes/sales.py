import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from sqlalchemy import select
from app.database import get_session
from app.models import Sale, SaleLine, Item, Stock
from app.logic.sales import create_sale
from app.logic.inventory import get_stock_qty

bp = Blueprint("sales", __name__)

CHANNELS = ["Direct", "eBay", "Amazon", "Wholesale", "Other"]


@bp.route("/sales")
@login_required
def list_sales():
    session = get_session()
    sales = session.execute(
        select(Sale).order_by(Sale.id.desc())
    ).scalars().all()

    sales_data = []
    for sale in sales:
        total_revenue = sum((l.revenue_aud or 0) for l in sale.lines)
        total_profit = sum((l.net_profit_aud or 0) for l in sale.lines)
        total_qty = sum((l.qty or 0) for l in sale.lines)
        sales_data.append({
            "id": sale.id,
            "date_sold": sale.date_sold,
            "channel": sale.channel,
            "current_rate": sale.current_rate,
            "total_revenue": total_revenue,
            "total_profit": total_profit,
            "total_qty": total_qty,
            "lines_count": len(sale.lines),
        })

    return render_template("sales/list.html", sales=sales_data)


@bp.route("/sales/new", methods=["GET", "POST"])
@login_required
def new_sale():
    session = get_session()

    if request.method == "POST":
        data = request.get_json() or {}
        header = {
            "date_sold": data.get("date_sold"),
            "channel": data.get("channel", "Direct"),
            "current_rate": float(data.get("current_rate", 1.58)),
        }
        lines_data = data.get("lines", [])

        if not lines_data:
            return jsonify({"error": "No items in sale"}), 400

        try:
            sale = create_sale(session, header, lines_data)
            return jsonify({"id": sale.id, "redirect": url_for("sales.detail", sale_id=sale.id)})
        except Exception as e:
            session.rollback()
            return jsonify({"error": str(e)}), 400

    # GET — load stock for sale form
    rows = session.execute(
        select(Item, Stock)
        .join(Stock, Stock.sku == Item.sku)
        .where(Stock.qty_on_hand > 0)
        .order_by(Item.sku)
    ).all()

    stock_items = [{
        "sku": item.sku,
        "description": item.description or item.sku,
        "qty_on_hand": stock.qty_on_hand,
        "price": item.price or 0,
        "us_map_price": item.us_map_price or 0,
    } for item, stock in rows]

    return render_template("sales/new.html",
                           stock_json=json.dumps(stock_items),
                           channels=CHANNELS)


@bp.route("/sales/<int:sale_id>")
@login_required
def detail(sale_id):
    session = get_session()
    sale = session.get(Sale, sale_id)
    if not sale:
        flash("Sale not found.", "error")
        return redirect(url_for("sales.list_sales"))

    lines_data = []
    for line in sale.lines:
        item = session.get(Item, line.sku)
        lines_data.append({
            "sku": line.sku,
            "description": item.description if item else line.sku,
            "qty": line.qty,
            "sell_price_aud": line.sell_price_aud,
            "cogs_aud": line.cogs_aud,
            "revenue_aud": line.revenue_aud,
            "gross_profit_aud": line.gross_profit_aud,
            "gross_margin_pct": line.gross_margin_pct,
            "fx_gain_loss": line.fx_gain_loss,
            "net_profit_aud": line.net_profit_aud,
        })

    total_revenue = sum(l["revenue_aud"] or 0 for l in lines_data)
    total_cogs = sum(l["cogs_aud"] or 0 for l in lines_data)
    total_profit = sum(l["net_profit_aud"] or 0 for l in lines_data)
    total_qty = sum(l["qty"] or 0 for l in lines_data)

    return render_template("sales/detail.html",
                           sale=sale,
                           lines=lines_data,
                           total_revenue=total_revenue,
                           total_cogs=total_cogs,
                           total_profit=total_profit,
                           total_qty=total_qty)
