# rms/analytics/views.py
"""
Advanced analytics dashboard + CSV export
"""

from io import BytesIO
from datetime import datetime
import pandas as pd
from flask import Blueprint, render_template, send_file
from flask_login import login_required
from sqlalchemy import func, text
from sqlalchemy.orm import aliased

from ..extensions import db
from ..models import Return, ReturnItem, User

analytics_bp = Blueprint(
    "analytics",
    __name__,
    template_folder="../../templates",
    url_prefix="/analytics",
)


# ──────────────────────────────────────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────────────────────────────────────
@analytics_bp.route("/", methods=["GET"])
@login_required
def dashboard():
    # A) High-level totals
    total_returns = db.session.query(func.count(Return.id)).scalar()
    total_credit  = db.session.query(
        func.coalesce(func.sum(ReturnItem.credit_amount), 0)
    ).scalar()
    total_items   = db.session.query(func.count(ReturnItem.id)).scalar()

    avg_credit = float(total_credit) / total_returns if total_returns else 0.0
    avg_items  = float(total_items)  / total_returns if total_returns else 0.0

    # B) Status breakdown (including WH Approved as its own bucket)
    status_counts = dict(
        db.session.query(Return.status, func.count(Return.id))
                  .group_by(Return.status)
    )
    status_credit = dict(
        db.session.query(
            Return.status,
            func.coalesce(func.sum(ReturnItem.credit_amount), 0)
        )
        .join(ReturnItem, Return.id == ReturnItem.return_id)
        .group_by(Return.status)
    )
    # ensure all four statuses present
    for s in ("Pending", "WH Approved", "Approved", "Rejected"):
        status_counts.setdefault(s, 0)
        status_credit.setdefault(s, 0)

    # C) Average approval times (in days)
    #  C1) Submission → WH approval
    wh_intervals = db.session.query(
        func.extract('epoch', Return.wh_approved_at - func.cast(Return.date_submitted, db.DateTime))
    ).filter(Return.wh_approved_at.isnot(None)).all()
    wh_days = [i[0]/86400 for i in wh_intervals if i[0] is not None]
    avg_wh_days = sum(wh_days)/len(wh_days) if wh_days else None

    #  C2) WH approval → Manager approval
    mgr_intervals = db.session.query(
        func.extract('epoch', Return.mgr_approved_at - Return.wh_approved_at)
    ).filter(
        Return.wh_approved_at.isnot(None),
        Return.mgr_approved_at.isnot(None)
    ).all()
    mgr_days = [i[0]/86400 for i in mgr_intervals if i[0] is not None]
    avg_mgr_days = sum(mgr_days)/len(mgr_days) if mgr_days else None

    #  C3) Submission → Manager approval (total cycle)
    total_intervals = db.session.query(
        func.extract('epoch', Return.mgr_approved_at - func.cast(Return.date_submitted, db.DateTime))
    ).filter(Return.mgr_approved_at.isnot(None)).all()
    total_days = [i[0]/86400 for i in total_intervals if i[0] is not None]
    avg_cycle_days = sum(total_days)/len(total_days) if total_days else None

    # D) Other breakdowns
    by_type = (
        db.session.query(Return.return_type, func.count(Return.id))
                  .group_by(Return.return_type)
                  .all()
    )
    by_rep = (
        db.session.query(Return.rep_name, func.count(Return.id))
                  .group_by(Return.rep_name)
                  .all()
    )
    by_customer = (
        db.session.query(Return.customer_name, func.count(Return.id))
                  .group_by(Return.customer_name)
                  .all()
    )
    avg_credit_by_type = (
        db.session.query(
            Return.return_type,
            func.coalesce(func.avg(ReturnItem.credit_amount), 0)
        )
        .join(ReturnItem, Return.id == ReturnItem.return_id)
        .group_by(Return.return_type)
        .all()
    )
    top_products = (
        db.session.query(
            ReturnItem.product_code,
            func.count(ReturnItem.id).label("count")
        )
        .group_by(ReturnItem.product_code)
        .order_by(func.count(ReturnItem.id).desc())
        .limit(10)
        .all()
    )
    over_time = db.session.execute(text("""
        SELECT to_char(date_created::date,'YYYY-MM-DD') AS day,
               COUNT(*) AS count
          FROM returns
         GROUP BY day
         ORDER BY day
    """)).all()

    return render_template(
        "analytics.html",
        # summary cards
        total_returns=total_returns,
        total_credit=total_credit,
        total_items=total_items,
        avg_credit=avg_credit,
        avg_items=avg_items,
        # status breakdown
        status_counts=status_counts,
        status_credit=status_credit,
        # approval timings
        avg_wh_days=avg_wh_days,
        avg_mgr_days=avg_mgr_days,
        avg_cycle_days=avg_cycle_days,
        # other breakdowns
        by_type=by_type,
        by_rep=by_rep,
        by_customer=by_customer,
        avg_credit_by_type=avg_credit_by_type,
        top_products=top_products,
        over_time=over_time,
    )


# ──────────────────────────────────────────────────────────────────────────────
# CSV export – full denormalised dump (already handles two-step columns)
@analytics_bp.route("/download_csv", methods=["GET"])
@login_required
def download_csv():
    Creator      = aliased(User)
    WHApprover   = aliased(User)
    MgrApprover  = aliased(User)

    q = (
        db.session.query(
            Return.id.label("return_id"),
            Return.date_created,
            Return.date_submitted,
            Return.date_shipped,
            Return.order_number,
            Return.customer_name,
            Return.return_type,
            Return.status,
            Return.advised_customer,
            Return.additional_notes,
            Creator.username.label("created_by"),
            WHApprover.username.label("warehouse_approved_by"),
            Return.wh_approved_at.label("warehouse_approved_at"),
            MgrApprover.username.label("manager_approved_by"),
            Return.mgr_approved_at.label("manager_approved_at"),
            ReturnItem.product_code,
            ReturnItem.product_desc,
            ReturnItem.price_per_lb,
            ReturnItem.weight_lb,
            ReturnItem.credit_amount,
            ReturnItem.product_returning,
            ReturnItem.reason_for_return,
            ReturnItem.follow_up_action,
            ReturnItem.supplier_credit,
        )
        .join(ReturnItem, Return.id == ReturnItem.return_id)
        .join(Creator,  Creator.id   == Return.created_by)
        .outerjoin(WHApprover,  WHApprover.id  == Return.wh_approved_by)
        .outerjoin(MgrApprover, MgrApprover.id == Return.mgr_approved_by)
    )

    df = pd.DataFrame([row._asdict() for row in q.all()])
    buf = BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    return send_file(
        buf,
        mimetype="text/csv",
        download_name="returns_full_export.csv"
    )
