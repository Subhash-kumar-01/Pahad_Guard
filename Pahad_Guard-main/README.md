# Pahad_Guard
this project show and priortise the risk of landslide according to some geological features.

# The following steps to run this project :-
bash  python -m venv venv

Windows:
bash  .\venv\Scripts\Activate.ps1
bash  where.exe python
bash  python -m pip --version
bash  python -m pip install --upgrade pip


Linux/macOS:
bash  source venv/bin/activate


Install packages:
bash  pip install -r requirements.txt


Generate data:
bash  python -m src.data.generate_demo_data


Train the model:
bash  python -m src.model.train


Run tests:
bash  pytest -q


Start the dashboard:
bash  streamlit run app.py

Then open:

http://localhost:8501

# Login / Sign up
The dashboard is behind a login/sign-up screen. On first run, use the
"Sign Up" tab to create an account (name, email, password) — accounts are
stored locally in `data/users.db` (SQLite, password hashed with salted
PBKDF2, never stored in plain text). After that, use the "Login" tab.

Both the Login and Sign Up tabs start with a role picker and always require
an **email address**:

- **👤 User** — full name, email, password (sign up) / email, password
  (login).
- **🏛️ Department** — the same fields, **plus a mandatory Department ID**
  on both Sign Up and Login. The Department ID is set once at sign-up and
  must be re-entered on every future login for that account.
- **🛡️ Admin** — sign-up is not self-service (see below); at **login**,
  Admin accounts must additionally enter the mandatory shared
  **Admin Secret ID** (`ADMIN_SECRET_ID` in `.env`, default
  `PAHAD-ADMIN-2024`).

Every login/signup attempt (success or failure, wrong role, wrong
Department ID, wrong Secret ID, etc.) is written to an audit log, viewable
by admins on the Database page.

# Roles (user / admin / department)
The dashboard is split into three access levels, decided by the account's
role:

- **👤 User** — what a citizen needs: Overview (with the personal location
alert), Risk Map and Alerts. No zone-level internals.
- **🏛️ Department** — full operational dashboard: everything except the
admin panel (Zone Analysis, Coordinate Analysis, Alerts, Rainfall
Simulator).
- **🛡️ Admin** — everything the department sees, plus a **Database** page:
user list, role management, the full monitoring dataset, the
login/signup audit log, and the geographic/prediction history (see below).

Demo accounts are seeded automatically on first run (only while no admin
exists, so your real users are never touched):

| Role       | Email                    | Password  | Extra field required at login          |
| ---------- | ------------------------ | --------- | --------------------------------------- |
| Admin      | `admin@pahadguard.com`   | `admin123`| Admin Secret ID: `PAHAD-ADMIN-2024`     |
| Department | `department@pahadguard.com` | `dept123`  | Department ID: `DEPT-0001`          |
| User       | `user@pahadguard.com`    | `user123`  | —                                        |

New sign-ups start as **User** or **Department** (Department requires
choosing a Department ID at sign-up time); Admin accounts are granted by an
existing admin via the Database page. The system refuses to demote the last
remaining admin.

# Database page — logs, history & invoices (Admin only)
Beyond user management and the raw monitoring dataset, the Database page
now shows:

- **Login/signup logs** — every attempt by every User and Department
  account, with timestamp, email, name, role, action, status and details.
- **Geographic data & prediction history** — every coordinate analysis run
  and every rainfall-simulation scenario a user chooses to save, with the
  full location, weather/terrain inputs and the resulting risk
  score/level/alert.

Both logs can be downloaded as CSV, and the prediction/geographic history
can also be downloaded as a formatted PDF **invoice** (via the "🧾 Download
as invoice (PDF)" button), suitable for record-keeping or handing to a
department that doesn't have dashboard access.

# Email notifications (Brevo)
Every login and sign-up can send you an email notification via Brevo's
transactional email API. To enable it:

1. Create a free account at https://www.brevo.com and grab an API key from
   Settings → SMTP & API → API Keys.
2. Copy `.env.example` to `.env` and fill in:
   - `BREVO_API_KEY` — your Brevo API key
   - `NOTIFY_EMAIL` — the email address that should receive notifications
   - `BREVO_SENDER_EMAIL` — a verified sender in your Brevo account
   - `BREVO_SENDER_NAME` — display name for the sender (optional)

If these aren't configured, login/sign-up still work as normal — the app
just skips sending the notification email and shows a small info note.

# Location-based risk alerts
After logging in, a pop-up asks how you'd like to share your location:

- **📍 Current Location** — looks up your position once via the browser's
  GPS/geolocation.
- **🔴 Live Location** — keeps re-checking your position every ~15 seconds
  so the alert stays current as you move.
- **Skip for now** — dismisses the pop-up; no location alert is shown.

Whichever option you pick, the dashboard's **Overview** page shows a
"Your location" block with a short description of where you are (e.g.
"Gangtok, East Sikkim") and a live risk gauge/alert for that exact point,
using the same nearest-zone + Open-Meteo pipeline as Coordinate Analysis.
You can switch modes any time with the **Change** button on that block.

Notes:
- Browsers only allow the Geolocation API over **HTTPS or localhost** — if
  you deploy over plain HTTP, ask users to enter coordinates manually
  instead (an "Enter coordinates manually" option is always available).
- Turning a coordinate into a place name uses OpenStreetMap's free
  Nominatim service and needs outbound internet access; if it's
  unreachable, the app just shows the raw coordinates instead.
- Live mode uses `streamlit-autorefresh`; if it isn't installed the app
  falls back to a manual "Refresh my live location" button.
