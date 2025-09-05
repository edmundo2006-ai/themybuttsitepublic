# The MY Buttsite 🍔

The MY Buttsite is a full-stack web app I built to streamline buttery operations at **Pauli Murray College, Yale University**. Instead of staff using messy spreadsheets, students can order online, and buttery staff get live order updates with a real-time dashboard.

> **Status:** Pending final rollout — currently deployed at [themybuttsite.com](https://themybuttsite.com).

---

## 🔑 Features

- **Full ordering system** — students browse menus, customize items, and place orders.
- **Real-time staff dashboard** — live order updates via **Flask-SocketIO**; no page refresh needed.
- **Role-based auth** — **Firebase Authentication** restricted to `@yale.edu`; staff vs. student roles live in the DB.
- **Database efficiency** — orders stored in three layers (order → items → ingredients) with optimized SQL joins to avoid N+1 queries.
- **Google Sheets backup** — orders mirrored via **Google Sheets API** as a failsafe; API client is cached for performance.
- **Deployment** — hosted on **Render**; database on **Supabase (PostgreSQL)**.
- **Frontend** — **Jinja** templates, **Tailwind CSS**, and some vanilla **JavaScript**.
- **Mock Stripe checkout** — test card `4242 4242 4242 4242` for demo only (disabled in production per admin).

---

## ⚙️ Tech Stack

### Frontend
- HTML, Tailwind CSS  
- Jinja2 (templating)  
- JavaScript (dynamic UI + fetch)

### Backend
- Flask + Flask-SocketIO (real-time)
- REST endpoints for order fetch/update
- SQLAlchemy ORM + Supabase (PostgreSQL)
- Google Sheets API (order backups)
- Firebase Authentication (Yale emails only)

### Infra / Dev
- Render (app hosting)
- Supabase (managed Postgres)
- GitHub (version control)

---

## 🖼️ Screenshots


![Student Menu](screenshots/menu.png)  
![Orders](screenshots/orders.png) 
![Staff](screenshots/staff.png)   
![Stock Updates](screenshots/stock.png)  
![Special Items](screenshots/special.png)  

---

## 🚀 Setup (Local)

**Prereqs:** Python 3.10+, pip, a Supabase project (Postgres), and a Firebase web app (for Auth).  
> Don’t commit secrets. Use a .env file for keys.

```bash
git clone https://github.com/edmundo2006-ai/themybuttsitepublic.git
cd themybuttsitepublic
pip install -r requirements.txt
python app.py
```
The app will start and show a local URL to open in your browser.

## 🔧 Configuration
Create a `.env` (or use environment variables) with the values your app expects. Example:

```dotenv
# Flask
SECRET_KEY=replace_me

# Database (choose one style your app uses)
DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST:PORT/DBNAME
# or Supabase-style
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=replace_me

# Firebase (client config is public; backend checks domain/claims)
FIREBASE_API_KEY=replace_me
FIREBASE_AUTH_DOMAIN=themybuttsite-xxxx.firebaseapp.com
FIREBASE_PROJECT_ID=themybuttsite-xxxx

# Google Sheets API (service account)
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service_account.json
```
Note: Firebase web config is OK to be public, but service accounts and any private keys must stay secret.

## 🛠️ Usage

### Students
- Sign in with a **Yale email**.
- Browse the menu, pick ingredients (out-of-stock items are hidden/flagged).
- Place orders; get live status updates (“Pending” → “Ready”).

### Staff
- Sign in as **staff** (role-based access).
- See incoming orders in real time (WebSockets).
- Update order status, manage stock, edit menu.
- Orders mirror to Google Sheets automatically for backup.

---

## 💳 Test Payments (Mock Only)

- Use Stripe test card **`4242 4242 4242 4242`** with any future date & any CVC.  
- **Production rollout does not include Stripe** (admin restrictions).

---

## 🔮 Rollout & Impact

The system is pending final approval at Pauli Murray. Once launched, it’s designed to handle **hundreds of orders weekly**, cut down manual errors, and give staff a faster workflow than spreadsheets.

---

## ⚠️ Notes

- Set strict auth/role checks on the backend (even though Firebase config is public).  
- Avoid N+1 queries by using proper `selectin`/`joinedload` patterns or explicit joins (already implemented).  
- Cache Google API clients to reduce latency (already implemented).

---

## 📜 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
