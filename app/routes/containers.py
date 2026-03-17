import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required
from sqlalchemy import select
from app.database import get_session
from app.models import Container, ContainerLine, Item, Stock
from app.logic.containers import (
    create_container, receive_container, advance_container_status,
    reset_container_and_warehouse_data
)
from app.logic.shipping import estimate_shipping

bp = Blueprint("containers", __name__)

CONTAINER_CAPACITY_M3 = {"20ft": 33.2, "40ft": 67.7}


@bp.route("/containers")
@login_required
def list_containers():
    session = get_session()
    containers = session.execute(
        select(Container).order_by(Container.id.desc())
    ).scalars().all()
    return render_template("containers/list.html", containers=containers)


@bp.route("/containers/new", methods=["GET", "POST"])
@login_required
def new_container():
    session = get_session()

    if request.method == "POST":
        data = request.get_json() or request.form
        header = {
            "date_ordered": data.get("date_ordered"),
            "expected_arrival_date": data.get("expected_arrival_date") or None,
            "used_rate": float(data.get("used_rate", 1.58)),
            "shipping_aud": float(data.get("shipping_aud") or 0),
            "other1_aud": float(data.get("other1_aud") or 0),
            "other1_label": data.get("other1_label") or "Other 1",
            "other2_aud": float(data.get("other2_aud") or 0),
            "other2_label": data.get("other2_label") or "Other 2",
            "container_size": data.get("container_size", "20ft"),
            "container_fill": data.get("container_fill", "full"),
        }

        lines_raw = data.get("lines") or "[]"
        if isinstance(lines_raw, str):
            lines_data = json.loads(lines_raw)
        else:
            lines_data = lines_raw

        if not lines_data:
            if request.is_json:
                return jsonify({"error": "No items added"}), 400
            flash("Add at least one item.", "error")
            return redirect(url_for("containers.new_container"))

        try:
            container = create_container(session, header, lines_data)
            if request.is_json:
                return jsonify({"id": container.id, "redirect": url_for("containers.detail", container_id=container.id)})
            flash(f"Container #{container.id} created.", "success")
            return redirect(url_for("containers.detail", container_id=container.id))
        except Exception as e:
            session.rollback()
            if request.is_json:
                return jsonify({"error": str(e)}), 400
            flash(f"Error: {e}", "error")
            return redirect(url_for("containers.new_container"))

    # GET — load items for animated packer
    items = session.execute(
        select(Item, Stock).outerjoin(Stock, Stock.sku == Item.sku).order_by(Item.sku)
    ).all()

    from app.routes.catalog import _size_category, CASE_COLORS
    cases_data = []
    for item, stock in items:
        cases_data.append({
            "sku": item.sku,
            "description": item.description or item.sku,
            "price": item.price or 0,
            "volume_m3": item.volume_m3 or 0,
            "ext_l": item.ext_length_mm,
            "ext_w": item.ext_width_mm,
            "ext_h": item.ext_height_mm,
            "dim_ext": item.dim_exterior or "",
            "size_cat": _size_category(item),
        })

    return render_template(
        "containers/new.html",
        cases_json=json.dumps(cases_data),
        colors=CASE_COLORS,
        capacity=CONTAINER_CAPACITY_M3,
    )


@bp.route("/containers/<int:container_id>")
@login_required
def detail(container_id):
    session = get_session()
    container = session.get(Container, container_id)
    if not container:
        flash("Container not found.", "error")
        return redirect(url_for("containers.list_containers"))

    lines = session.execute(
        select(ContainerLine, Item)
        .join(Item, ContainerLine.sku == Item.sku)
        .where(ContainerLine.container_id == container_id)
    ).all()

    lines_data = []
    for cl, item in lines:
        lines_data.append({
            "sku": cl.sku,
            "description": item.description if item else cl.sku,
            "qty_ordered": cl.qty_ordered,
            "qty_received": cl.qty_received,
            "unit_price_usd": cl.unit_price_usd,
            "line_total_usd": (cl.unit_price_usd or 0) * (cl.qty_ordered or 0),
        })

    total_qty = sum(l["qty_ordered"] or 0 for l in lines_data)
    total_usd = sum(l["line_total_usd"] for l in lines_data)
    total_aud = total_usd * (container.used_rate or 1)

    return render_template(
        "containers/detail.html",
        container=container,
        lines=lines_data,
        total_qty=total_qty,
        total_usd=total_usd,
        total_aud=total_aud,
    )


@bp.route("/containers/<int:container_id>/status", methods=["POST"])
@login_required
def update_status(container_id):
    session = get_session()
    new_status = request.form.get("status")
    try:
        if new_status == "received":
            receive_container(session, container_id)
            flash("Container received and stock updated.", "success")
        else:
            advance_container_status(session, container_id, new_status)
            flash(f"Status updated to {new_status}.", "success")
    except Exception as e:
        session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("containers.detail", container_id=container_id))


@bp.route("/containers/<int:container_id>/export")
@login_required
def export_order(container_id):
    session = get_session()
    from app.utils.exporter import export_container_order
    buf = export_container_order(container_id, session)
    return send_file(
        buf,
        as_attachment=True,
        download_name=f"container_{container_id}_order.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@bp.route("/containers/reset", methods=["POST"])
@login_required
def reset():
    session = get_session()
    try:
        reset_container_and_warehouse_data(session)
        flash("Warehouse and container data reset.", "success")
    except Exception as e:
        session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("containers.list_containers"))


@bp.route("/api/shipping-estimate", methods=["POST"])
@login_required
def shipping_estimate():
    data = request.get_json()
    try:
        result = estimate_shipping(
            cbm=float(data.get("cbm", 0)),
            goods_value_aud=float(data.get("goods_value_aud", 0)),
            usd_aud_rate=float(data.get("usd_aud_rate", 1.58)),
        )
        return jsonify(result.summary())
    except Exception as e:
        return jsonify({"error": str(e)}), 400
