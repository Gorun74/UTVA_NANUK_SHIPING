from flask import Blueprint, render_template, request, send_file
from flask_login import login_required
from app.database import get_session
from app.logic.reports import (
    stock_snapshot, sales_report, container_summary, profitability_report,
    export_to_excel
)
import tempfile, os

bp = Blueprint("reports", __name__)


@bp.route("/reports")
@login_required
def index():
    session = get_session()
    from_date = request.args.get("from_date", "")
    to_date = request.args.get("to_date", "")

    stock = stock_snapshot(session)
    sales = sales_report(session, from_date or None, to_date or None)
    containers = container_summary(session)
    profitability = profitability_report(session)

    return render_template("reports/index.html",
                           stock=stock,
                           sales=sales,
                           containers=containers,
                           profitability=profitability,
                           from_date=from_date,
                           to_date=to_date)


@bp.route("/reports/export/<report_type>")
@login_required
def export(report_type):
    session = get_session()
    from_date = request.args.get("from_date", "")
    to_date = request.args.get("to_date", "")

    if report_type == "stock":
        data = stock_snapshot(session)
        name = "stock_snapshot"
    elif report_type == "sales":
        data = sales_report(session, from_date or None, to_date or None)
        name = "sales_report"
    elif report_type == "containers":
        data = container_summary(session)
        name = "container_summary"
    else:
        return "Unknown report type", 400

    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    export_to_excel(data, tmp.name, name)
    return send_file(
        tmp.name,
        as_attachment=True,
        download_name=f"{name}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
