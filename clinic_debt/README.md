# 🏥 MedDebt Tracker — Clinic Level 2 Debt Tracking System

A modular Flask web app for tracking patient debts at a Level 2 clinic.

---

## 📁 Project Structure

```
clinic_debt/
├── run.py                   ← Entry point
├── config.py                ← Config (dev/prod)
├── requirements.txt
├── .env.example
└── app/
    ├── __init__.py          ← App factory
    ├── models.py            ← User, Patient, Debt, Payment
    ├── auth/routes.py       ← Login, register, logout, profile
    ├── main/routes.py       ← Patients, debts, payments (core)
    ├── admin/routes.py      ← Admin panel, users, ledger
    ├── api/routes.py        ← REST API v1
    └── templates/
        ├── base.html
        ├── auth/            login, register, profile
        ├── main/            dashboard, debtors, patient_detail
        └── admin/           panel, users, ledger, payments
```

---

## ⚡ Quick Start (Termux / PythonAnywhere)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and edit your environment file
cp .env.example .env
# Edit .env and set a strong SECRET_KEY

# 3. Create database and seed admin
flask db init
flask db migrate -m "init"
flask db upgrade
flask seed

# 4. Run
python run.py
```

**Default admin credentials:**
- Email: `admin@clinic.ke`
- Password: `admin123`
*(Change immediately after first login!)*

---

## 🌐 REST API — Base URL: `/api/v1`

All endpoints require session login (or adapt to use tokens).

| Method | Endpoint                          | Description             |
|--------|-----------------------------------|-------------------------|
| GET    | `/patients`                       | List patients (filter: `?q=`, `?status=`) |
| GET    | `/patients/:id`                   | Get patient + debts     |
| POST   | `/patients`                       | Create patient          |
| PATCH  | `/patients/:id`                   | Update patient          |
| DELETE | `/patients/:id`                   | Delete patient (admin)  |
| GET    | `/debts`                          | List all debts          |
| GET    | `/debts/:id`                      | Debt + payments         |
| POST   | `/patients/:id/debts`             | Create debt             |
| DELETE | `/debts/:id`                      | Delete debt (admin)     |
| POST   | `/debts/:id/payments`             | Record payment          |
| DELETE | `/payments/:id`                   | Delete payment (admin)  |
| GET    | `/stats`                          | Summary statistics      |

---

## 🗺️ URL Map

| Route                        | View                    |
|-----------------------------|-------------------------|
| `/`                          | Dashboard               |
| `/debtors`                   | Patient list            |
| `/patient/<id>`              | Patient detail + debts  |
| `/auth/login`                | Login                   |
| `/auth/logout`               | Logout                  |
| `/auth/profile`              | Edit profile            |
| `/admin/`                    | Admin panel             |
| `/admin/users`               | Manage users            |
| `/admin/ledger`              | Full debt ledger        |
| `/admin/payments`            | All payments            |
| `/auth/register`             | New user (admin only)   |

---

## 🔒 Roles

- **admin** — Full access: delete records, manage users, view full ledger
- **staff** — Create patients, record debts, record payments; no deletes

---

## 🚀 PythonAnywhere Deployment

In your WSGI file (`/var/www/yourdomain_pythonanywhere_com_wsgi.py`):

```python
import sys, os
sys.path.insert(0, '/home/FelixKirui/clinic_debt')
os.environ['FLASK_ENV'] = 'production'

from run import app as application
```

Set `SECRET_KEY` and `DATABASE_URL` in the PythonAnywhere environment variables panel.
