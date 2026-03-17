import json
import re
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required
from sqlalchemy import select
from app.database import get_session
from app.models import Container, ContainerLine, Item, Stock
from app.logic.containers import (
    create_container, receive_container, advance_container_status,
    reset_container_and_warehouse_data, delete_draft,
)
from app.logic.shipping import estimate_shipping

bp = Blueprint("containers", __name__)

CONTAINER_CAPACITY_M3 = {"20ft": 33.2, "40ft": 67.7}

# ── Color code → display name ──────────────────────────────────────────────
_COLOR_MAP = {
    "BK": "Black",   "OR": "Orange",  "OL": "Olive",   "DT": "Desert Tan",
    "YL": "Yellow",  "RD": "Red",     "GP": "Graphite", "BL": "Blue",
    "SV": "Silver",  "LI": "Lime",    "TN": "Tan",     "CL": "Clear",
    "PR": "Purple",
}
_CHASSIS_NAME = {"W": "Wheels", "T": "Team Carry", "M": "Molded", "H": "HDW"}
_FOAM_WORDS   = ("w/foam", "w foam", "with foam")


def _model_group(sku: str) -> tuple:
    """Return (group_key, display_name, color_name) from a case SKU."""
    # NANUK-R: 910SR000BK-0A0  (no dash after SR)
    m = re.match(r'^(T?\d{3,4})SR\d{3}([A-Z]{2})', sku, re.IGNORECASE)
    if m:
        num = m.group(1).upper()
        color = _COLOR_MAP.get(m.group(2).upper(), m.group(2).upper())
        return num, f"NANUK {num}", color

    # Standard/special chassis: 910S-000BK-0A0, 975W-000BK-0A0, 991M-010BK
    m = re.match(r'^(T?\d{3,4})([STWHM])-\d{3}([A-Z]{2})', sku, re.IGNORECASE)
    if m:
        num     = m.group(1).upper()
        chassis = m.group(2).upper()
        color   = _COLOR_MAP.get(m.group(3).upper(), m.group(3).upper())
        if chassis == 'S':
            return num, f"NANUK {num}", color
        cname = _CHASSIS_NAME.get(chassis, chassis)
        return f"{num}{chassis}", f"NANUK {num} ({cname})", color

    return sku[:8], sku[:8], "Black"


@bp.route("/containers")
@login_required
def list_containers():
    session = get_session()
    all_containers = session.execute(
        select(Container).order_by(Container.id.desc())
    ).scalars().all()
    drafts = [c for c in all_containers if c.status == 'draft']
    containers = [c for c in all_containers if c.status != 'draft']
    return render_template("containers/list.html", containers=containers, drafts=drafts)


@bp.route("/containers/new", methods=["GET", "POST"])
@login_required
def new_container():
    session = get_session()

    if request.method == "POST":
        data = request.get_json() or request.form
        save_as_draft = bool(data.get("save_as_draft"))
        draft_id = data.get("draft_id")  # present when editing an existing draft

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

        status = "draft" if save_as_draft else "ordered"
        try:
            # If editing an existing draft, delete it first then recreate
            if draft_id:
                old = session.get(Container, int(draft_id))
                if old and old.status == "draft":
                    from sqlalchemy import delete as sa_delete
                    from app.models import ContainerLine as CL
                    session.execute(sa_delete(CL).where(CL.container_id == old.id))
                    session.delete(old)
                    session.flush()

            container = create_container(session, header, lines_data, status=status)
            if request.is_json:
                return jsonify({"id": container.id, "redirect": url_for("containers.detail", container_id=container.id)})
            verb = "Draft saved" if save_as_draft else "Container created"
            flash(f"{verb} — #{container.id}.", "success")
            return redirect(url_for("containers.detail", container_id=container.id))
        except Exception as e:
            session.rollback()
            if request.is_json:
                return jsonify({"error": str(e)}), 400
            flash(f"Error: {e}", "error")
            return redirect(url_for("containers.new_container"))

    # GET — load case items that have volume (needed for container packer)
    items = session.execute(
        select(Item, Stock)
        .outerjoin(Stock, Stock.sku == Item.sku)
        .where(Item.category == 'case')
        .where(Item.volume_m3 > 0)
        .order_by(Item.sku)
    ).all()

    from app.routes.catalog import _size_category
    # Group by model — one entry per model, variants dict per color
    model_groups: dict = {}
    for item, stock in items:
        desc_lower = (item.description or "").lower()
        # Skip foam variants — user wants empty cases only
        if any(fw in desc_lower for fw in _FOAM_WORDS):
            continue
        group_key, display_name, color_name = _model_group(item.sku)
        if group_key not in model_groups:
            model_groups[group_key] = {
                "model":        group_key,
                "display_name": display_name,
                "volume_m3":    item.volume_m3 or 0,
                "ext_l":        item.ext_length_mm,
                "ext_w":        item.ext_width_mm,
                "ext_h":        item.ext_height_mm,
                "dim_ext":      item.dim_exterior or "",
                "size_cat":     _size_category(item),
                "variants":     {},
            }
        model_groups[group_key]["variants"][color_name] = {
            "sku":   item.sku,
            "price": item.price or 0,
        }

    cases_data = sorted(model_groups.values(), key=lambda x: x["model"])

    import datetime
    return render_template(
        "containers/new.html",
        cases_json=json.dumps(cases_data),
        capacity=CONTAINER_CAPACITY_M3,
        today=datetime.date.today().isoformat(),
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


@bp.route("/containers/<int:container_id>/edit")
@login_required
def edit_draft(container_id):
    """Reopen the packer with an existing draft pre-populated."""
    session = get_session()
    container = session.get(Container, container_id)
    if not container or container.status != "draft":
        flash("Draft not found.", "error")
        return redirect(url_for("containers.list_containers"))

    lines = session.execute(
        select(ContainerLine, Item)
        .join(Item, ContainerLine.sku == Item.sku)
        .where(ContainerLine.container_id == container_id)
    ).all()

    # Build prefill dict matching JS orderedItems format
    prefill = {}
    for cl, item in lines:
        group_key, display_name, color_name = _model_group(cl.sku)
        prefill[cl.sku] = {
            "sku": cl.sku,
            "model": group_key,
            "display_name": display_name,
            "color": color_name,
            "qty": cl.qty_ordered or 1,
            "sell_price": cl.unit_price_usd or 0,
            "volume_m3": item.volume_m3 or 0 if item else 0,
            "ext_l": item.ext_length_mm if item else None,
            "ext_w": item.ext_width_mm if item else None,
            "ext_h": item.ext_height_mm if item else None,
        }

    # Reuse GET part of new_container
    items = session.execute(
        select(Item, Stock)
        .outerjoin(Stock, Stock.sku == Item.sku)
        .where(Item.category == 'case')
        .where(Item.volume_m3 > 0)
        .order_by(Item.sku)
    ).all()

    from app.routes.catalog import _size_category
    model_groups: dict = {}
    for item, stock in items:
        desc_lower = (item.description or "").lower()
        if any(fw in desc_lower for fw in _FOAM_WORDS):
            continue
        group_key, display_name, color_name = _model_group(item.sku)
        if group_key not in model_groups:
            model_groups[group_key] = {
                "model": group_key, "display_name": display_name,
                "volume_m3": item.volume_m3 or 0,
                "ext_l": item.ext_length_mm, "ext_w": item.ext_width_mm,
                "ext_h": item.ext_height_mm, "dim_ext": item.dim_exterior or "",
                "size_cat": _size_category(item), "variants": {},
            }
        model_groups[group_key]["variants"][color_name] = {
            "sku": item.sku, "price": item.price or 0,
        }

    import datetime
    return render_template(
        "containers/new.html",
        cases_json=json.dumps(sorted(model_groups.values(), key=lambda x: x["model"])),
        capacity=CONTAINER_CAPACITY_M3,
        today=datetime.date.today().isoformat(),
        draft_id=container.id,
        prefill_json=json.dumps(prefill),
        draft_header={
            "date_ordered": container.date_ordered or "",
            "expected_arrival_date": container.expected_arrival_date or "",
            "used_rate": container.used_rate or 1.58,
            "shipping_aud": container.shipping_aud or 0,
            "other1_aud": container.other1_aud or 0,
            "other2_aud": container.other2_aud or 0,
            "container_size": container.container_size or "20ft",
            "container_fill": container.container_fill or "full",
        },
    )


@bp.route("/containers/<int:container_id>/confirm", methods=["POST"])
@login_required
def confirm_draft(container_id):
    """Convert a draft to an ordered container."""
    session = get_session()
    container = session.get(Container, container_id)
    if not container or container.status != "draft":
        flash("Draft not found.", "error")
        return redirect(url_for("containers.list_containers"))
    try:
        container.status = "ordered"
        session.commit()
        flash(f"Container #{container_id} confirmed as order!", "success")
    except Exception as e:
        session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("containers.detail", container_id=container_id))


@bp.route("/containers/<int:container_id>/delete", methods=["POST"])
@login_required
def delete_container(container_id):
    """Delete a draft container."""
    session = get_session()
    try:
        delete_draft(session, container_id)
        flash("Draft deleted.", "success")
    except Exception as e:
        session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("containers.list_containers"))


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
