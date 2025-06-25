# rms/returns/views.py
# ─────────────────────────────────────────────────────────────────────────────
# Handles return submission, two-step approval, PDF export, and email notifications.

import os
from io import BytesIO
from datetime import datetime
from functools import wraps
from zoneinfo import ZoneInfo
from fpdf import FPDF

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, abort, current_app, send_file
)
from flask_login import login_required, current_user

from ..extensions import db
from ..models     import Return, ReturnItem, User
from ..mailer     import send_return_notice

PST = ZoneInfo("America/Los_Angeles")


def fmt_pst(d):
    """Format any date/datetime as YY/MM/DD in Pacific time."""
    if not d:
        return "-"
    if isinstance(d, datetime):
        d = d.astimezone(PST)
    return d.strftime("%y/%m/%d")


returns_bp = Blueprint(
    "returns", __name__,
    template_folder="../templates",
    url_prefix="/returns",
)


def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# 1) List all returns, with Status/Date filters
@returns_bp.route("/", methods=["GET"])
@login_required
def list_returns():
    status   = request.args.get("status", "")
    from_dt  = request.args.get("from", "")
    to_dt    = request.args.get("to", "")

    q = Return.query

    # status filter
    if status == "Pending":
        q = q.filter_by(status="Pending")
    elif status == "Accepted":
        q = q.filter(Return.status.in_(["WH Approved", "Approved"]))
    elif status == "Rejected":
        q = q.filter_by(status="Rejected")

    # date-range filters (YYYY-MM-DD)
    if from_dt:
        try:
            d0 = datetime.strptime(from_dt, "%Y-%m-%d").date()
            q = q.filter(Return.date_submitted >= d0)
        except ValueError:
            flash("⚠️ From date must be YYYY-MM-DD", "warning")
    if to_dt:
        try:
            d1 = datetime.strptime(to_dt, "%Y-%m-%d").date()
            q = q.filter(Return.date_submitted <= d1)
        except ValueError:
            flash("⚠️ To date must be YYYY-MM-DD", "warning")

    # sales users only see their own
    if current_user.role == "sales":
        q = q.filter_by(created_by=current_user.id)

    all_returns = q.order_by(Return.date_submitted.desc()).all()
    return render_template(
        "list_returns.html",
        returns=all_returns,
        fmt_pst=fmt_pst,
        status=status,
        from_dt=from_dt,
        to_dt=to_dt,
    )

# ─────────────────────────────────────────────────────────────────────────────
# 2) Submit a new return
@returns_bp.route("/new", methods=["GET", "POST"])
@login_required
@roles_required("sales")
def new_return():
    if request.method == "POST":
        form = request.form

        # parse submission date
        try:
            sub_dt = datetime.strptime(form.get("date_submitted", ""), "%Y-%m-%d").date()
        except ValueError:
            sub_dt = datetime.now(PST).date()
            flash("⚠️ Submission date must be YYYY-MM-DD", "warning")

        # parse shipped date
        ship_dt = None
        if form.get("date_shipped"):
            try:
                ship_dt = datetime.strptime(form.get("date_shipped"), "%Y-%m-%d").date()
            except ValueError:
                flash("⚠️ Ship date must be YYYY-MM-DD", "warning")

        # build and persist
        r = Return(
            rep_name         = form.get("rep_name"),
            date_submitted   = sub_dt,
            order_number     = form.get("order_number"),
            customer_name    = form.get("customer_name"),
            date_shipped     = ship_dt,
            return_type      = form.get("return_type"),
            advised_customer = form.get("advised_customer"),
            additional_notes = form.get("additional_notes"),
            status           = "Pending",
            created_by       = current_user.id,
        )
        db.session.add(r)
        db.session.flush()

        # add items
        for idx, code in enumerate(form.getlist("product_code")):
            price  = float(form.getlist("price_per_lb")[idx] or 0)
            weight = float(form.getlist("weight_lb")[idx]    or 0)
            credit = round(price * weight, 2)
            db.session.add(ReturnItem(
                return_id         = r.id,
                product_code      = code,
                product_desc      = form.getlist("product_desc")[idx],
                price_per_lb      = price,
                weight_lb         = weight,
                credit_amount     = credit,
                product_returning = form.getlist("product_returning")[idx],
                reason_for_return = form.getlist("reason_for_return")[idx],
                follow_up_action  = form.getlist("follow_up_action")[idx],
                supplier_credit   = ("supplier_credit" in form)
            ))

        db.session.commit()

        # 1) Notify only the submitter (sales rep)
        rep_email = (current_user.email or "").strip()
        if "@" not in rep_email:
            current_app.logger.error(f"Invalid rep email for user id={current_user.id}: '{current_user.email}'")
            flash("⚠️ Could not send confirmation email: invalid email address", "warning")
        else:
            send_return_notice(
                to_addr=rep_email,
                r=r,
                event="new"
            )

        # 2) Notify all active warehouse users
        for wh in User.query.filter_by(role="warehouse", is_active=True):
            email = (wh.email or "").strip()
            if "@" not in email:
                current_app.logger.warning(f"Skipping warehouse user id={wh.id} with invalid email: '{wh.email}'")
                continue
            send_return_notice(
                to_addr=email,
                r=r,
                event="new_return"
            )

        flash(f"Return #{r.id} submitted for approval", "success")
        return redirect(url_for("returns.list_returns"))

    # GET → render form
    return render_template(
        "new_return.html",
        rep_name=current_user.name or current_user.username,
        today=datetime.now(PST).date().isoformat()
    )

# ─────────────────────────────────────────────────────────────────────────────
# 3) Return detail
@returns_bp.route("/<int:id>", methods=["GET"])
@login_required
def return_detail(id):
    r = Return.query.get_or_404(id)
    if current_user.role == "sales" and r.created_by != current_user.id:
        abort(403)
    return render_template("return_detail.html", r=r, fmt_pst=fmt_pst)

# ─────────────────────────────────────────────────────────────────────────────
# 4) Combined approvals view
@returns_bp.route("/approvals", methods=["GET"])
@login_required
@roles_required("warehouse", "manager", "admin")
def approvals():
    pend = Return.query.filter(
        Return.status.in_(["Pending", "WH Approved"])
    ).order_by(Return.date_submitted).all()
    return render_template("approvals.html", returns=pend, fmt_pst=fmt_pst)

# ─────────────────────────────────────────────────────────────────────────────
# 5a) Warehouse approval
@returns_bp.route("/<int:id>/approve_wh", methods=["POST"])
@login_required
@roles_required("warehouse")
def approve_wh(id):
    r = Return.query.get_or_404(id)
    if r.status != "Pending":
        abort(400, "Already processed")
    r.status           = "WH Approved"
    r.wh_approved_at   = datetime.now(PST)
    r.wh_approved_by   = current_user.id
    db.session.commit()

    # notify managers
    for mgr in User.query.filter_by(role="manager"):
        email = (mgr.email or "").strip()
        if "@" not in email:
            current_app.logger.warning(
                f"Skipping manager user id={mgr.id} with invalid email: '{mgr.email}'"
            )
            continue
        send_return_notice(
            to_addr=email,
            r=r,
            event="warehouse"
        )

    flash("Warehouse approval recorded", "success")
    return redirect(url_for("returns.approvals"))

# ─────────────────────────────────────────────────────────────────────────────
# 5b) Manager approval & Credit-PO generation
@returns_bp.route("/<int:id>/approve_mgr", methods=["POST"])
@login_required
@roles_required("manager")
def approve_mgr(id):
    r = Return.query.get_or_404(id)
    if r.status != "WH Approved":
        abort(400, "Must be WH-approved first")

    r.status           = "Approved"
    r.mgr_approved_at  = datetime.now(PST)
    r.mgr_approved_by  = current_user.id
    db.session.commit()

    pdf_bytes    = build_credit_po_pdf(r)
    submitter    = User.query.get(r.created_by)
    email        = (submitter.email or "").strip()
    total_credit = sum(float(it.credit_amount) for it in r.items)

    if "@" not in email:
        current_app.logger.error(
            f"Invalid submitter email for id={r.created_by}: '{submitter.email}'"
        )
        flash("⚠️ Could not send credit PO email: invalid email address", "warning")
    else:
        send_return_notice(
            to_addr             = email,
            r                   = r,
            event               = "manager",
            total_credit        = total_credit,
            view_url            = "",
            attachment_bytes    = pdf_bytes,
            attachment_filename = f"credit_po_{r.id}.pdf"
        )

    flash("Manager approval complete & emailed credit PO", "success")
    return send_file(
        BytesIO(pdf_bytes),
        download_name=f"credit_po_{r.id}.pdf",
        mimetype="application/pdf"
    )

# ─────────────────────────────────────────────────────────────────────────────
# PDF generation helper

def build_credit_po_pdf(r):
    pdf = FPDF("P", "mm", "A4")
    pdf.add_page()

    logo_path = os.path.join(current_app.static_folder, "images", "logo.png")
    if os.path.exists(logo_path):
        pdf.image(logo_path, x=10, y=8, w=30)
    pdf.set_xy(45, 10)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 6, "Two Rivers Meats", ln=1)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 5, "180 Donaghy Ave, North Vancouver, BC V7P 2L5", ln=1)
    pdf.ln(8)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 6, f"CREDIT-PO - Return #{r.id}", ln=1)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 6, f"Order #: {r.order_number}", ln=1)
    pdf.cell(0, 6, f"Rep: {r.rep_name}", ln=1)
    pdf.cell(0, 6, f"Date: {datetime.now(PST).strftime('%Y-%m-%d')}", ln=1)
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(30, 6, "Code", 1)
    pdf.cell(80, 6, "Description", 1)
    pdf.cell(25, 6, "Price/lb", 1, align="R")
    pdf.cell(25, 6, "Weight", 1, align="R")
    pdf.cell(30, 6, "Credit", 1, ln=1, align="R")

    pdf.set_font("Helvetica", size=10)
    total = 0
    for it in r.items:
        pdf.cell(30, 6, it.product_code or "", 1)
        pdf.cell(80, 6, (it.product_desc or "")[:40], 1)
        pdf.cell(25, 6, f"{it.price_per_lb:.2f}", 1, align="R")
        pdf.cell(25, 6, f"{it.weight_lb:.3f}", 1, align="R")
        pdf.cell(30, 6, f"${it.credit_amount:.2f}", 1, ln=1, align="R")
        total += float(it.credit_amount or 0)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(135, 8, "TOTAL CREDIT", 1)
    pdf.cell(30, 8, f"${total:,.2f}", 1, ln=1, align="R")

    raw = pdf.output(dest="S")
    return raw.encode("latin-1") if isinstance(raw, str) else bytes(raw)

# ─────────────────────────────────────────────────────────────────────────────
# 6) Reject
@returns_bp.route("/<int:id>/reject", methods=["POST"])
@login_required
@roles_required("warehouse", "manager", "admin")
def reject(id):
    r = Return.query.get_or_404(id)
    r.status         = "Rejected"
    r.approved_by_id = current_user.id
    r.approved_at    = datetime.now(PST)
    db.session.commit()

    user = User.query.get(r.created_by)
    email = (user.email or "").strip()
    if "@" not in email:
        current_app.logger.error(
            f"Invalid email for rejected user id={user.id}: '{user.email}'"
        )
        flash("⚠️ Could not send rejection email: invalid email address", "warning")
    else:
        send_return_notice(
            to_addr=email,
            r=r,
            event="rejected"
        )

    flash(f"Return #{r.id} rejected", "warning")
    return redirect(url_for("returns.approvals"))

# ─────────────────────────────────────────────────────────────────────────────
# 7) PDF export
@returns_bp.route("/<int:id>/pdf", methods=["GET"])
@login_required
def return_pdf(id):
    r = Return.query.get_or_404(id)
    if current_user.role == "sales" and r.created_by != current_user.id:
        abort(403)

    pdf = FPDF("P", "mm", "A4")
    pdf.set_creator("ReturnApp")
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, f"Return #{r.id}", ln=1, align="C")

    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 6, f"Submitted: {fmt_pst(r.date_submitted)}", ln=1)
    pdf.cell(
        0, 6,
        f"Rep: {r.rep_name or '-'}    Order #: {r.order_number or '-'}",
        ln=1
    )
    pdf.cell(0, 6, f"Customer: {r.customer_name or '-'}", ln=1)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(30, 6, "Code", 1)
    pdf.cell(70, 6, "Description", 1)
    pdf.cell(25, 6, "Price/lb", 1, align="R")
    pdf.cell(25, 6, "Weight", 1, align="R")
    pdf.cell(30, 6, "Credit", 1, ln=1, align="R")

    pdf.set_font("Helvetica", size=10)
    total = 0
    for it in r.items:
        pdf.cell(30, 6, str(it.product_code or ""), 1)
        pdf.cell(70, 6, str(it.product_desc or "")[:40], 1)
        pdf.cell(25, 6, f"{it.price_per_lb:.2f}", 1, align="R")
        pdf.cell(25, 6, f"{it.weight_lb:.3f}", 1, align="R")
        pdf.cell(30, 6, f"{it.credit_amount:.2f}", 1, ln=1, align="R")
        total += float(it.credit_amount or 0)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(150, 8, "TOTAL CREDIT", 1)
    pdf.cell(30, 8, f"${total:,.2f}", 1, ln=1, align="R")

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "Additional Notes / Follow-up:", ln=1)
    pdf.set_font("Helvetica", size=10)
    pdf.multi_cell(0, 5, r.additional_notes or "(none)")

    raw = pdf.output(dest="S")
    pdf_bytes = raw.encode("latin-1") if isinstance(raw, str) else bytes(raw)
    return send_file(
        BytesIO(pdf_bytes),
        download_name=f"return_{r.id}.pdf",
        mimetype="application/pdf"
    )