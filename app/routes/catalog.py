import os
from flask import Blueprint, render_template, request, jsonify, send_file, current_app, flash, redirect, url_for
from flask_login import login_required
from sqlalchemy import select, or_, func
from app.database import get_session
from app.models import Item, Stock

bp = Blueprint("catalog", __name__)

CASE_COLORS = ["Black", "Orange", "Olive", "Desert Tan"]


def _size_category(item: Item) -> str:
    dims = [item.ext_length_mm, item.ext_width_mm, item.ext_height_mm]
    dims = [d for d in dims if d]
    if not dims:
        return "medium"
    max_dim = max(dims)
    if max_dim <= 400:
        return "small"
    elif max_dim <= 650:
        return "medium"
    return "large"


@bp.route("/catalog")
@login_required
def list_items():
    session = get_session()
    q = request.args.get("q", "").strip()

    stmt = select(Item, Stock).outerjoin(Stock, Stock.sku == Item.sku)
    if q:
        stmt = stmt.where(
            or_(
                Item.sku.ilike(f"%{q}%"),
                Item.description.ilike(f"%{q}%"),
            )
        )
    stmt = stmt.order_by(Item.sku)
    rows = session.execute(stmt).all()

    items = []
    for item, stock in rows:
        items.append({
            "sku": item.sku,
            "description": item.description or "",
            "price": item.price,
            "us_map_price": item.us_map_price,
            "volume_m3": item.volume_m3,
            "ext_dim": item.dim_exterior or "",
            "ext_l": item.ext_length_mm,
            "ext_w": item.ext_width_mm,
            "ext_h": item.ext_height_mm,
            "qty": stock.qty_on_hand if stock else 0,
            "size_cat": _size_category(item),
        })

    return render_template("catalog/list.html", items=items, q=q)


@bp.route("/api/cases")
@login_required
def api_cases():
    """JSON endpoint for the animated container packer."""
    session = get_session()
    rows = session.execute(
        select(Item, Stock).outerjoin(Stock, Stock.sku == Item.sku).order_by(Item.sku)
    ).all()

    cases = []
    for item, stock in rows:
        cases.append({
            "sku": item.sku,
            "description": item.description or item.sku,
            "price": item.price,
            "volume_m3": item.volume_m3,
            "ext_l": item.ext_length_mm,
            "ext_w": item.ext_width_mm,
            "ext_h": item.ext_height_mm,
            "dim_ext": item.dim_exterior or "",
            "qty_on_hand": stock.qty_on_hand if stock else 0,
            "size_cat": _size_category(item),
            "colors": CASE_COLORS,
        })
    return jsonify(cases)


@bp.route("/catalog/import", methods=["GET", "POST"])
@login_required
def import_catalog():
    """Import cases catalog from the 3 known files."""
    session = get_session()

    # Default paths — same machine as desktop app
    default_cases  = r"D:\!Posao\#2026\UTVAWA NANUK\IVENTAR\nanuk_cases_only.csv"
    default_catalog= r"D:\!Posao\#2026\UTVAWA NANUK\IVENTAR\Case_catalog.xlsx"
    default_price  = r"D:\!Posao\#2026\UTVAWA NANUK\IVENTAR\Price Agreement - UTVA WA.xlsx"

    if request.method == "POST":
        cases_path   = request.form.get("cases_path",   default_cases).strip()
        catalog_path = request.form.get("catalog_path", default_catalog).strip()
        price_path   = request.form.get("price_path",   default_price).strip()

        missing = [p for p in [cases_path, catalog_path, price_path] if not os.path.exists(p)]
        if missing:
            flash(f"File(s) not found: {', '.join(missing)}", "error")
            return render_template("catalog/import.html",
                                   default_cases=cases_path,
                                   default_catalog=catalog_path,
                                   default_price=price_path)

        try:
            from app.utils.importer import import_cases_catalog
            imported, skipped = import_cases_catalog(cases_path, catalog_path, price_path, session)
            flash(f"Import complete: {imported} items imported, {skipped} skipped.", "success")
            return redirect(url_for("catalog.list_items"))
        except Exception as e:
            session.rollback()
            flash(f"Import error: {e}", "error")

    item_count = session.execute(select(func.count(Item.sku))).scalar() or 0
    return render_template("catalog/import.html",
                           default_cases=default_cases,
                           default_catalog=default_catalog,
                           default_price=default_price,
                           item_count=item_count)


@bp.route("/api/case-image/<sku>")
@login_required
def case_image(sku):
    image_root = current_app.config.get("IMAGE_ROOT", "")
    if not image_root:
        return "", 404
    from app.utils.image_utils import get_thumbnail
    img = get_thumbnail(sku, image_root)
    if img and os.path.exists(img):
        return send_file(img)
    return "", 404
