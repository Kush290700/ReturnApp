from datetime import datetime
from passlib.hash import bcrypt
from flask_login import UserMixin
from sqlalchemy.orm import synonym

from .extensions import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id        = db.Column(db.Integer, primary_key=True)
    username  = db.Column(db.String(120), unique=True, nullable=False)
    name      = db.Column(db.String(120))
    password  = db.Column(db.String(255), nullable=False)
    role      = db.Column(db.String(20), default="sales", nullable=False)  # sales|warehouse|manager|admin
    is_active = db.Column(db.Boolean, default=False, nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    # alias username as email for notifications
    email = synonym("username")

    def set_password(self, raw):
        self.password = bcrypt.hash(raw)

    def check_password(self, raw):
        return bcrypt.verify(raw, self.password)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class Return(db.Model):
    __tablename__ = "returns"

    id               = db.Column(db.Integer, primary_key=True)
    rep_name         = db.Column(db.String(120))
    date_submitted   = db.Column(db.Date, nullable=False)
    order_number     = db.Column(db.String(50))
    customer_name    = db.Column(db.String(120))
    date_shipped     = db.Column(db.Date)
    return_type      = db.Column(db.String(50))
    advised_customer = db.Column(db.String(255))
    additional_notes = db.Column(db.Text)
    status           = db.Column(db.String(20), default="Pending", nullable=False)

    # two-step approval fields
    wh_approved_by   = db.Column(db.Integer, db.ForeignKey("users.id"))
    wh_approved_at   = db.Column(db.DateTime)
    mgr_approved_by  = db.Column(db.Integer, db.ForeignKey("users.id"))
    mgr_approved_at  = db.Column(db.DateTime)

    approved_by_id   = db.Column(db.Integer, db.ForeignKey("users.id"))
    approved_at      = db.Column(db.DateTime)

    created_by       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    date_created     = db.Column(db.DateTime, default=datetime.utcnow)

    # relationships
    wh_approver = db.relationship('User', foreign_keys=[wh_approved_by], backref='warehouse_approvals')
    mgr_approver = db.relationship('User', foreign_keys=[mgr_approved_by], backref='manager_approvals')
    approver = db.relationship('User', foreign_keys=[approved_by_id], backref='approvals')
    creator = db.relationship('User', foreign_keys=[created_by], backref='returns_created')

    items = db.relationship(
        "ReturnItem",
        backref="return",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )
    attachments = db.relationship(
        "Attachment",
        backref="return",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )
    comments = db.relationship(
        "Comment",
        backref="return",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )

    def __repr__(self):
        return f"<Return #{self.id} status={self.status}>"


class ReturnItem(db.Model):
    __tablename__ = "return_items"

    id                = db.Column(db.Integer, primary_key=True)
    return_id         = db.Column(db.Integer, db.ForeignKey("returns.id"), nullable=False)

    product_code      = db.Column(db.String(50))
    product_desc      = db.Column(db.String(255))
    price_per_lb      = db.Column(db.Numeric(10, 2))
    weight_lb         = db.Column(db.Numeric(10, 3))
    credit_amount     = db.Column(db.Numeric(12, 2))
    product_returning = db.Column(db.String(50))
    reason_for_return = db.Column(db.String(100))
    follow_up_action  = db.Column(db.String(100))
    supplier_credit   = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<ReturnItem {self.product_code} x {self.weight_lb}lb>"


class Attachment(db.Model):
    __tablename__ = "attachments"

    id          = db.Column(db.Integer, primary_key=True)
    return_id   = db.Column(db.Integer, db.ForeignKey("returns.id"), nullable=False)
    filename    = db.Column(db.String(255), nullable=False)
    mimetype    = db.Column(db.String(50), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Attachment {self.filename}>"


class Comment(db.Model):
    __tablename__ = "comments"

    id         = db.Column(db.Integer, primary_key=True)
    return_id  = db.Column(db.Integer, db.ForeignKey("returns.id"), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    body       = db.Column(db.Text, nullable=False)
    timestamp  = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='comments')

    def __repr__(self):
        return f"<Comment by user={self.user_id} on return={self.return_id}>"
