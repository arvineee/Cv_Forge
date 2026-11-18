from app import db, login
from flask_login import UserMixin
from datetime import datetime, date


# ─── USER ─────────────────────────────────────────────────────────────────────
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    email      = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password   = db.Column(db.String(256), nullable=False)
    role       = db.Column(db.String(20), default="staff")   # admin | staff
    is_active  = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # back-refs
    debts_created    = db.relationship("Debt",    backref="created_by_user", lazy="dynamic", foreign_keys="Debt.created_by")
    payments_recorded = db.relationship("Payment", backref="recorded_by_user", lazy="dynamic", foreign_keys="Payment.recorded_by")

    @property
    def is_admin(self):
        return self.role == "admin"

    def __repr__(self):
        return f"<User {self.email}>"


@login.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─── PATIENT ──────────────────────────────────────────────────────────────────
class Patient(db.Model):
    __tablename__ = "patients"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(150), nullable=False, index=True)
    phone      = db.Column(db.String(30), nullable=False)
    email      = db.Column(db.String(150), nullable=True)
    id_number  = db.Column(db.String(50), nullable=True, unique=True)   # National ID / passport
    dob        = db.Column(db.Date, nullable=True)
    gender     = db.Column(db.String(10), nullable=True)
    address    = db.Column(db.Text, nullable=True)
    notes      = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    debts = db.relationship("Debt", backref="patient", lazy="dynamic", cascade="all, delete-orphan")

    @property
    def total_owed(self):
        return sum(d.balance for d in self.debts if d.balance > 0)

    @property
    def total_paid(self):
        return sum(p.amount for d in self.debts for p in d.payments)

    @property
    def has_overdue(self):
        return any(d.status == "overdue" for d in self.debts)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "phone": self.phone,
            "email": self.email, "id_number": self.id_number,
            "total_owed": self.total_owed, "total_paid": self.total_paid,
            "has_overdue": self.has_overdue,
        }

    def __repr__(self):
        return f"<Patient {self.name}>"


# ─── DEBT ─────────────────────────────────────────────────────────────────────
class Debt(db.Model):
    __tablename__ = "debts"

    id           = db.Column(db.Integer, primary_key=True)
    patient_id   = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False, index=True)
    service      = db.Column(db.String(255), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    due_date     = db.Column(db.Date, nullable=False)
    notes        = db.Column(db.Text, nullable=True)
    created_by   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    payments = db.relationship("Payment", backref="debt", lazy="dynamic", cascade="all, delete-orphan")

    @property
    def total_paid(self):
        return sum(p.amount for p in self.payments)

    @property
    def balance(self):
        return max(self.total_amount - self.total_paid, 0)

    @property
    def pct_paid(self):
        if self.total_amount == 0:
            return 100
        return min(round((self.total_paid / self.total_amount) * 100, 1), 100)

    @property
    def days_left(self):
        return (self.due_date - date.today()).days

    @property
    def status(self):
        if self.balance <= 0:
            return "paid"
        if self.days_left < 0:
            return "overdue"
        if self.total_paid > 0:
            return "partial"
        return "pending"

    def to_dict(self):
        return {
            "id": self.id, "service": self.service,
            "patient_id": self.patient_id, "patient_name": self.patient.name,
            "total_amount": self.total_amount, "total_paid": self.total_paid,
            "balance": self.balance, "pct_paid": self.pct_paid,
            "due_date": str(self.due_date), "days_left": self.days_left,
            "status": self.status, "notes": self.notes,
        }

    def __repr__(self):
        return f"<Debt {self.id} – {self.patient.name}>"


# ─── PAYMENT ──────────────────────────────────────────────────────────────────
PAYMENT_METHODS = ["M-Pesa", "Cash", "Bank Transfer", "Insurance", "Card", "Cheque"]


class Payment(db.Model):
    __tablename__ = "payments"

    id          = db.Column(db.Integer, primary_key=True)
    debt_id     = db.Column(db.Integer, db.ForeignKey("debts.id"), nullable=False, index=True)
    amount      = db.Column(db.Float, nullable=False)
    method      = db.Column(db.String(50), nullable=False, default="Cash")
    reference   = db.Column(db.String(100), nullable=True)
    note        = db.Column(db.Text, nullable=True)
    date        = db.Column(db.Date, nullable=False, default=date.today)
    recorded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "debt_id": self.debt_id, "amount": self.amount,
            "method": self.method, "reference": self.reference,
            "note": self.note, "date": str(self.date),
        }

    def __repr__(self):
        return f"<Payment KES {self.amount} – {self.method}>"
