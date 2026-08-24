"""
Giveaway Website - Full Featured
Default admin: admin / admin123
"""

import os
import sqlite3
import secrets
import time
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, session, redirect, render_template_string, send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ============================================================
# CONFIG
# ============================================================

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# Database path - uses /tmp on Render for persistence
if os.environ.get('RENDER'):
    DB = "/tmp/giveaway.db"
else:
    DB = "giveaway.db"

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {'.apk', '.lua', '.zip', '.json', '.txt', '.pdf', '.png', '.jpg', '.jpeg', '.gif', '.mp4', '.mp3'}
MAX_CONTENT_LENGTH = 50 * 1024 * 1024

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ============================================================
# DATABASE
# ============================================================

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def setup():
    con = db()
    # Users
    con.execute("""CREATE TABLE IF NOT EXISTS website_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # Giveaways
    con.execute("""CREATE TABLE IF NOT EXISTS giveaways (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        duration_minutes INTEGER DEFAULT 1440,
        end_time TEXT,
        active INTEGER DEFAULT 1,
        max_entries INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # Accounts
    con.execute("""CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_code TEXT NOT NULL UNIQUE,
        status TEXT DEFAULT 'available',
        claimed_by INTEGER,
        claimed_at TEXT,
        account_type TEXT DEFAULT 'Standard',
        claimed_giveaway_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # Entries
    con.execute("""CREATE TABLE IF NOT EXISTS entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        giveaway_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        username TEXT,
        first_name TEXT,
        entered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(giveaway_id, user_id)
    )""")
    
    # User stats
    con.execute("""CREATE TABLE IF NOT EXISTS user_stats (
        user_id INTEGER PRIMARY KEY,
        total_entries INTEGER DEFAULT 0,
        total_claims INTEGER DEFAULT 0,
        last_active TIMESTAMP
    )""")
    
    # Categories
    con.execute("""CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # Files
    con.execute("""CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        original_name TEXT NOT NULL,
        stored_name TEXT NOT NULL,
        file_size INTEGER NOT NULL,
        mime_type TEXT,
        category_id INTEGER,
        description TEXT DEFAULT '',
        version TEXT DEFAULT '',
        active INTEGER DEFAULT 1,
        download_count INTEGER DEFAULT 0,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # Links
    con.execute("""CREATE TABLE IF NOT EXISTS links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        url TEXT NOT NULL,
        category_id INTEGER,
        description TEXT DEFAULT '',
        active INTEGER DEFAULT 1,
        click_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # Announcements
    con.execute("""CREATE TABLE IF NOT EXISTS website_announcements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # Settings
    con.execute("""CREATE TABLE IF NOT EXISTS website_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""")
    
    # Default settings
    defaults = {
        "site_name": "Giveaway Center",
        "site_description": "Enter giveaways and claim rewards.",
        "welcome_title": "Welcome to Giveaway Center",
        "footer": "Giveaway Center",
        "maintenance": "0"
    }
    for key, value in defaults.items():
        if not con.execute("SELECT key FROM website_settings WHERE key=?", (key,)).fetchone():
            con.execute("INSERT INTO website_settings (key,value) VALUES (?,?)", (key, value))
    
    # Default admin
    if not con.execute("SELECT id FROM website_users WHERE is_admin=1 LIMIT 1").fetchone():
        con.execute("INSERT INTO website_users (username,password,is_admin,active) VALUES (?,?,1,1)",
                    ("admin", generate_password_hash("admin123")))
    
    con.commit()
    con.close()

def setting(key):
    con = db()
    row = con.execute("SELECT value FROM website_settings WHERE key=?", (key,)).fetchone()
    con.close()
    return row["value"] if row else ""

def set_setting(key, value):
    con = db()
    con.execute("INSERT INTO website_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    con.commit()
    con.close()

# ============================================================
# SECURITY
# ============================================================

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect("/login")
        if not session.get("is_admin"):
            return "Access denied.", 403
        return f(*args, **kwargs)
    return wrapper

# ============================================================
# TEMPLATE
# ============================================================

BASE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} - {{ site_name }}</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#08090d;color:#f5f5f5;font-family:Arial,sans-serif}
nav{background:#11131a;border-bottom:1px solid #272a35;padding:16px 22px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:15px}
.logo{font-size:21px;font-weight:800;background:linear-gradient(135deg,#635bff,#00a884);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
nav a{color:#bfc2cc;text-decoration:none;margin:4px 7px}
nav a:hover{color:white}
.container{max-width:1150px;margin:auto;padding:25px 18px}
.hero{text-align:center;padding:70px 10px 60px;background:linear-gradient(135deg,rgba(99,91,255,0.05),rgba(0,168,132,0.05));border-radius:20px;margin-bottom:30px}
.hero h1{font-size:44px;margin-bottom:15px}
.hero p{color:#a5a8b3;font-size:17px}
.card{background:#11131a;border:1px solid #272a35;border-radius:16px;padding:22px;margin-bottom:18px}
.card:hover{border-color:#3d404d}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:15px}
.stat{background:#11131a;border:1px solid #272a35;border-radius:15px;padding:20px;text-align:center}
.stat-number{font-size:30px;font-weight:700;margin-bottom:7px;background:linear-gradient(135deg,#635bff,#00a884);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.muted{color:#979aa5}
input,textarea,select{width:100%;background:#090a0f;color:#fff;border:1px solid #343744;border-radius:9px;padding:13px;margin-top:7px;margin-bottom:15px}
input:focus,textarea:focus,select:focus{border-color:#635bff;outline:0}
textarea{min-height:110px;resize:vertical;font-family:inherit}
button,.button{border:0;border-radius:9px;padding:12px 17px;background:#635bff;color:#fff;text-decoration:none;font-weight:700;cursor:pointer;display:inline-block;transition:opacity .2s}
button:hover,.button:hover{opacity:.85}
.green{background:#00a884}
.red{background:#d63031}
.gray{background:#363944}
.notice{background:#171922;border-left:4px solid #635bff;border-radius:9px;padding:15px;margin-bottom:18px}
.success{border-left-color:#00a884}
.error{border-left-color:#d63031}
.badge{display:inline-block;background:#292c37;border-radius:30px;padding:5px 10px;font-size:12px;margin-bottom:8px}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse}
th,td{padding:12px;border-bottom:1px solid #292c37;text-align:left}
th{color:#aeb1bd;font-weight:600}
tr:hover{background:#0d0f15}
footer{text-align:center;color:#777b87;padding:35px 15px}
.admin-subnav{display:flex;flex-wrap:wrap;gap:8px;margin:15px 0 25px}
.admin-subnav a{background:#1a1d26;padding:8px 16px;border-radius:30px;text-decoration:none;color:#bfc2cc;font-size:14px}
.admin-subnav a:hover{background:#2f3342;color:#fff}
.status-active{color:#00a884}
.status-ended{color:#d63031}
@media(max-width:600px){.hero{padding:45px 5px}.hero h1{font-size:32px}nav{justify-content:center}.container{padding:18px 12px}}
</style>
</head>
<body>
<nav>
<div class="logo">🎁 {{ site_name }}</div>
<div>
<a href="/">Home</a>
<a href="/giveaways">Giveaways</a>
<a href="/downloads">Downloads</a>
{% if session.get("user_id") %}
    {% if session.get("is_admin") %}<a href="/admin">Admin</a>{% endif %}
    <a href="/logout">Logout</a>
{% else %}
    <a href="/login">Login</a>
    <a href="/register">Register</a>
{% endif %}
</div>
</nav>
<div class="container">{{ content|safe }}</div>
<footer>{{ footer }}</footer>
</body>
</html>
"""

def page(title, content):
    return render_template_string(BASE, title=title, content=content,
                                   site_name=setting("site_name"),
                                   footer=setting("footer"))

# ============================================================
# PUBLIC ROUTES
# ============================================================

@app.route("/")
def home():
    if setting("maintenance") == "1" and not session.get("is_admin"):
        return page("Maintenance", '<div class="hero"><h1>🔧 Maintenance</h1><p>Website is temporarily unavailable.</p></div>')
    
    con = db()
    announcement = con.execute("SELECT * FROM website_announcements WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()
    giveaways = con.execute("SELECT * FROM giveaways WHERE active=1 ORDER BY id DESC").fetchall()
    total_available = con.execute("SELECT COUNT(*) as count FROM accounts WHERE status='available'").fetchone()["count"]
    con.close()
    
    content = ""
    if announcement:
        content += f'<div class="notice"><h3>📢 {announcement["title"]}</h3><p>{announcement["message"]}</p></div>'
    
    content += f'''
    <div class="hero">
        <h1>{setting("welcome_title")}</h1>
        <p>{setting("site_description")}</p>
        <div style="display:flex;gap:15px;justify-content:center;flex-wrap:wrap;margin-top:20px">
            <a class="button" href="/giveaways">🎁 View Giveaways</a>
            <a class="button green" href="/downloads">📥 Downloads</a>
        </div>
    </div>
    <div class="grid">
        <div class="stat"><div class="stat-number">{len(giveaways)}</div><span class="muted">Active Giveaways</span></div>
        <div class="stat"><div class="stat-number">{total_available}</div><span class="muted">Available Accounts</span></div>
    </div>
    '''
    
    if giveaways:
        content += "<h2>🔥 Active Giveaways</h2>"
        for g in giveaways:
            claimed = con.execute("SELECT COUNT(*) as count FROM accounts WHERE claimed_giveaway_id=?", (g["id"],)).fetchone()["count"] if con else 0
            entries = con.execute("SELECT COUNT(*) as count FROM entries WHERE giveaway_id=?", (g["id"],)).fetchone()["count"] if con else 0
            content += f'''
            <div class="card">
                <span class="badge status-active">ACTIVE</span>
                <h2>{g["title"]}</h2>
                <p class="muted">{g["description"] or "No description"}</p>
                <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(100px,1fr))">
                    <div><span class="muted">Entries:</span> <strong>{entries}</strong></div>
                    <div><span class="muted">Claimed:</span> <strong>{claimed}</strong></div>
                </div>
                <br><a class="button" href="/giveaway/{g["id"]}">View Details</a>
            </div>
            '''
    else:
        content += '<div class="notice">No active giveaways right now.</div>'
    
    return page("Home", content)

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        if len(username) < 3:
            return page("Register", '<div class="notice error">Username must be at least 3 characters.</div>')
        if len(password) < 6:
            return page("Register", '<div class="notice error">Password must be at least 6 characters.</div>')
        con = db()
        try:
            con.execute("INSERT INTO website_users (username,password) VALUES (?,?)",
                        (username, generate_password_hash(password)))
            con.commit()
            con.close()
            return redirect("/login")
        except sqlite3.IntegrityError:
            con.close()
            return page("Register", '<div class="notice error">Username already taken.</div>')
    
    return page("Register", '''
    <h1>👤 Create Account</h1>
    <div class="card">
        <form method="POST">
            <label>Username</label>
            <input name="username" minlength="3" required>
            <label>Password</label>
            <input type="password" name="password" minlength="6" required>
            <button>Create Account</button>
        </form>
        <p class="muted" style="margin-top:15px">Already have an account? <a href="/login" style="color:#635bff">Login</a></p>
    </div>
    ''')

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        con = db()
        user = con.execute("SELECT * FROM website_users WHERE username=? LIMIT 1", (username,)).fetchone()
        con.close()
        if user and check_password_hash(user["password"], password) and user["active"]:
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["is_admin"] = bool(user["is_admin"])
            return redirect("/")
        return page("Login", '<div class="notice error">❌ Incorrect username or password.</div>')
    
    return page("Login", '''
    <h1>🔐 Login</h1>
    <div class="card">
        <form method="POST">
            <label>Username</label>
            <input name="username" required>
            <label>Password</label>
            <input type="password" name="password" required>
            <button>Login</button>
        </form>
        <p class="muted" style="margin-top:15px">Don\'t have an account? <a href="/register" style="color:#635bff">Register</a></p>
    </div>
    ''')

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/giveaways")
def giveaways():
    con = db()
    rows = con.execute("SELECT * FROM giveaways WHERE active=1 ORDER BY id DESC").fetchall()
    con.close()
    
    content = "<h1>🎁 Giveaways</h1>"
    if not rows:
        content += '<div class="notice">No active giveaways.</div>'
    for g in rows:
        content += f'''
        <div class="card">
            <span class="badge status-active">ACTIVE</span>
            <h2>{g["title"]}</h2>
            <p class="muted">{g["description"] or "No description"}</p>
            <br><a class="button" href="/giveaway/{g["id"]}">View Giveaway</a>
        </div>
        '''
    return page("Giveaways", content)

@app.route("/giveaway/<int:gid>")
def giveaway(gid):
    con = db()
    g = con.execute("SELECT * FROM giveaways WHERE id=? AND active=1", (gid,)).fetchone()
    if not g:
        con.close()
        return "Giveaway not found.", 404
    
    entries_count = con.execute("SELECT COUNT(*) as count FROM entries WHERE giveaway_id=?", (gid,)).fetchone()["count"]
    claimed_count = con.execute("SELECT COUNT(*) as count FROM accounts WHERE claimed_giveaway_id=?", (gid,)).fetchone()["count"]
    available = con.execute("SELECT COUNT(*) as count FROM accounts WHERE status='available'").fetchone()["count"]
    remaining = available - claimed_count
    
    claimed = False
    if session.get("user_id"):
        web_user = con.execute("SELECT username FROM website_users WHERE id=?", (session["user_id"],)).fetchone()
        if web_user:
            check = con.execute("SELECT id FROM entries WHERE giveaway_id=? AND username=?", (gid, web_user["username"])).fetchone()
            claimed = check is not None
    
    con.close()
    
    content = f'''
    <div class="card">
        <span class="badge">GIVEAWAY</span>
        <h1>{g["title"]}</h1>
        <p>{g["description"] or "No description"}</p>
        <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(100px,1fr))">
            <div class="stat"><div class="stat-number">{entries_count}</div>Total Entries</div>
            <div class="stat"><div class="stat-number">{claimed_count}</div>Accounts Claimed</div>
            <div class="stat"><div class="stat-number">{remaining}</div>Remaining</div>
        </div>
    '''
    
    if not session.get("user_id"):
        content += '<br><a class="button" href="/login">Login to Claim</a>'
    elif claimed:
        content += '<br><div class="notice success">✅ You already claimed this giveaway!</div>'
    elif remaining <= 0:
        content += '<br><div class="notice">All accounts have been claimed.</div>'
    else:
        content += f'<br><form method="POST" action="/claim/{gid}"><button class="green">🎁 Claim Account</button></form>'
    
    content += "</div>"
    return page(g["title"], content)

@app.route("/claim/<int:gid>", methods=["POST"])
def claim(gid):
    if not session.get("user_id"):
        return redirect("/login")
    
    con = db()
    web_user = con.execute("SELECT username FROM website_users WHERE id=?", (session["user_id"],)).fetchone()
    if not web_user:
        con.close()
        return page("Error", '<div class="notice error">User not found.</div>')
    
    giveaway = con.execute("SELECT * FROM giveaways WHERE id=? AND active=1", (gid,)).fetchone()
    if not giveaway:
        con.close()
        return page("Error", '<div class="notice error">Giveaway not found.</div>')
    
    existing = con.execute("SELECT id FROM entries WHERE giveaway_id=? AND username=?", (gid, web_user["username"])).fetchone()
    if existing:
        con.close()
        return page("Already Claimed", '<div class="notice success">✅ You already claimed this!</div>')
    
    account = con.execute("SELECT * FROM accounts WHERE status='available' ORDER BY id LIMIT 1").fetchone()
    if not account:
        con.close()
        return page("Unavailable", '<div class="notice error">No accounts available.</div>')
    
    now = datetime.now().isoformat()
    con.execute("UPDATE accounts SET status='claimed', claimed_by=?, claimed_at=?, claimed_giveaway_id=? WHERE id=?",
                (session["user_id"], now, gid, account["id"]))
    con.execute("INSERT INTO entries (giveaway_id, user_id, username, first_name, entered_at) VALUES (?,?,?,?,?)",
                (gid, session["user_id"], web_user["username"], web_user["username"], now))
    con.execute("INSERT INTO user_stats (user_id, total_entries, total_claims, last_active) VALUES (?,1,1,?) ON CONFLICT(user_id) DO UPDATE SET total_entries=total_entries+1, total_claims=total_claims+1, last_active=excluded.last_active",
                (session["user_id"], now))
    con.commit()
    con.close()
    
    return page("Claim Successful", f'''
    <div class="card">
        <h1>🎉 Claim Successful!</h1>
        <div class="notice success">
            <strong>Your Account:</strong><br>
            <code style="background:#090a0f;padding:10px;display:block;border-radius:6px;margin-top:10px">{account["account_code"]}</code>
        </div>
        <p class="muted">Type: {account["account_type"]}</p>
        <a class="button" href="/giveaways">Back to Giveaways</a>
    </div>
    ''')

# ============================================================
# DOWNLOADS
# ============================================================

@app.route("/downloads")
def downloads():
    con = db()
    files = con.execute("SELECT * FROM files WHERE active=1 ORDER BY uploaded_at DESC").fetchall()
    links = con.execute("SELECT * FROM links WHERE active=1 ORDER BY created_at DESC").fetchall()
    con.close()
    
    content = "<h1>📥 Downloads</h1>"
    
    if files:
        content += "<h2>📁 Files</h2><div class='grid'>"
        for f in files:
            size_kb = f['file_size'] // 1024
            size_str = f"{size_kb} KB" if size_kb < 1024 else f"{size_kb//1024} MB"
            content += f'''
            <div class="stat">
                <strong>{f['original_name']}</strong>
                <br><span class="muted">{size_str}</span>
                <br><br>
                <a class="button green" href="/download/{f['id']}">⬇ Download</a>
                <span class="muted"> ({f['download_count']} DL)</span>
            </div>
            '''
        content += "</div>"
    
    if links:
        content += "<h2>🔗 Links</h2><div class='grid'>"
        for l in links:
            content += f'''
            <div class="stat">
                <strong>{l['title']}</strong>
                <br><span class="muted">{l['description'] or ''}</span>
                <br><br>
                <a class="button" href="/goto/{l['id']}" target="_blank">Visit Link</a>
                <span class="muted"> ({l['click_count']} clicks)</span>
            </div>
            '''
        content += "</div>"
    
    if not files and not links:
        content += '<div class="notice">No downloads available.</div>'
    
    return page("Downloads", content)

@app.route("/download/<int:fid>")
def download_file(fid):
    con = db()
    file_rec = con.execute("SELECT * FROM files WHERE id=? AND active=1", (fid,)).fetchone()
    con.close()
    if not file_rec:
        abort(404)
    con = db()
    con.execute("UPDATE files SET download_count = download_count + 1 WHERE id=?", (fid,))
    con.commit()
    con.close()
    return send_from_directory(app.config['UPLOAD_FOLDER'], file_rec['stored_name'],
                               as_attachment=True, download_name=file_rec['original_name'])

@app.route("/goto/<int:lid>")
def goto_link(lid):
    con = db()
    link = con.execute("SELECT * FROM links WHERE id=? AND active=1", (lid,)).fetchone()
    con.close()
    if not link:
        abort(404)
    con = db()
    con.execute("UPDATE links SET click_count = click_count + 1 WHERE id=?", (lid,))
    con.commit()
    con.close()
    return redirect(link['url'])

# ============================================================
# ADMIN ROUTES
# ============================================================

@app.route("/admin")
@admin_required
def admin():
    con = db()
    users = con.execute("SELECT COUNT(*) as n FROM website_users").fetchone()["n"]
    giveaways = con.execute("SELECT COUNT(*) as n FROM giveaways").fetchone()["n"]
    accounts = con.execute("SELECT COUNT(*) as n FROM accounts").fetchone()["n"]
    claims = con.execute("SELECT COUNT(*) as n FROM entries").fetchone()["n"]
    available = con.execute("SELECT COUNT(*) as n FROM accounts WHERE status='available'").fetchone()["n"]
    files = con.execute("SELECT COUNT(*) as n FROM files").fetchone()["n"]
    links = con.execute("SELECT COUNT(*) as n FROM links").fetchone()["n"]
    
    recent = con.execute("""
        SELECT e.*, a.account_code, a.account_type
        FROM entries e
        LEFT JOIN accounts a ON a.claimed_giveaway_id = e.giveaway_id AND a.claimed_by = e.user_id
        ORDER BY e.entered_at DESC LIMIT 10
    """).fetchall()
    
    gs = con.execute("SELECT * FROM giveaways ORDER BY id DESC").fetchall()
    con.close()
    
    content = f'''
    <h1>🛠️ Admin Panel</h1>
    <p class="muted">Welcome, {session["username"]}</p>
    <div class="admin-subnav">
        <a href="#settings">⚙️ Settings</a>
        <a href="#account">🔐 Account</a>
        <a href="#giveaway-create">➕ Giveaways</a>
        <a href="#accounts-add">📦 Accounts</a>
        <a href="#files">📁 Files</a>
        <a href="#links">🔗 Links</a>
        <a href="#announcements">📢 Announcements</a>
        <a href="#giveaway-manage">🎁 Manage</a>
    </div>
    <div class="grid">
        <div class="stat"><div class="stat-number">{users}</div>👥 Users</div>
        <div class="stat"><div class="stat-number">{giveaways}</div>🎁 Giveaways</div>
        <div class="stat"><div class="stat-number">{accounts}</div>📦 Accounts</div>
        <div class="stat"><div class="stat-number">{available}</div>🟢 Available</div>
        <div class="stat"><div class="stat-number">{claims}</div>🎯 Claims</div>
        <div class="stat"><div class="stat-number">{files}</div>📄 Files</div>
        <div class="stat"><div class="stat-number">{links}</div>🔗 Links</div>
    </div>
    <br>
    <!-- Settings -->
    <div class="card" id="settings">
        <h2>⚙️ Settings</h2>
        <form method="POST" action="/admin/settings">
            <label>Website Name</label>
            <input name="site_name" value="{setting("site_name")}" required>
            <label>Welcome Title</label>
            <input name="welcome_title" value="{setting("welcome_title")}" required>
            <label>Description</label>
            <textarea name="site_description">{setting("site_description")}</textarea>
            <label>Footer</label>
            <input name="footer" value="{setting("footer")}">
            <label>Maintenance</label>
            <select name="maintenance">
                <option value="0" {"selected" if setting("maintenance")=="0" else ""}>OFF</option>
                <option value="1" {"selected" if setting("maintenance")=="1" else ""}>ON</option>
            </select>
            <button>💾 Save</button>
        </form>
    </div>
    <!-- Admin Account -->
    <div class="card" id="account">
        <h2>🔐 Admin Account</h2>
        <form method="POST" action="/admin/account">
            <label>Username</label>
            <input name="username" value="{session["username"]}" minlength="3" required>
            <label>Current Password</label>
            <input type="password" name="current_password" required>
            <label>New Password</label>
            <input type="password" name="new_password" minlength="6" placeholder="Leave blank to keep current">
            <label>Confirm Password</label>
            <input type="password" name="confirm_password" minlength="6">
            <button>🔒 Save</button>
        </form>
    </div>
    <!-- Create Giveaway -->
    <div class="card" id="giveaway-create">
        <h2>➕ Create Giveaway</h2>
        <form method="POST" action="/admin/create">
            <label>Title</label>
            <input name="title" required>
            <label>Description</label>
            <textarea name="description"></textarea>
            <label>Duration (minutes)</label>
            <input type="number" name="duration" value="1440">
            <button>Create</button>
        </form>
    </div>
    <!-- Add Accounts -->
    <div class="card" id="accounts-add">
        <h2>📦 Add Accounts</h2>
        <p class="muted">One per line. Format: account_code|type</p>
        <form method="POST" action="/admin/accounts/add">
            <textarea name="accounts" placeholder="ACC-001|Premium&#10;ACC-002|Standard" required></textarea>
            <button>Add Accounts</button>
        </form>
    </div>
    <!-- Files -->
    <div class="card" id="files">
        <h2>📁 Upload File</h2>
        <form method="POST" action="/admin/upload" enctype="multipart/form-data">
            <input type="file" name="file" required>
            <label>Description</label>
            <input name="description">
            <label>Version</label>
            <input name="version" placeholder="1.0">
            <button>Upload</button>
        </form>
    </div>
    <!-- Links -->
    <div class="card" id="links">
        <h2>🔗 Add Link</h2>
        <form method="POST" action="/admin/link/add">
            <label>Title</label>
            <input name="title" required>
            <label>URL</label>
            <input name="url" type="url" required>
            <label>Description</label>
            <input name="description">
            <button>Add Link</button>
        </form>
    </div>
    <!-- Announcements -->
    <div class="card" id="announcements">
        <h2>📢 Announcement</h2>
        <form method="POST" action="/admin/announcement">
            <label>Title</label>
            <input name="title" required>
            <label>Message</label>
            <textarea name="message" required></textarea>
            <button>Publish</button>
        </form>
    </div>
    <!-- Giveaway Management -->
    <h2 id="giveaway-manage">🎁 Manage Giveaways</h2>
    '''
    
    for g in gs:
        status = "ACTIVE" if g["active"] else "ENDED"
        status_class = "status-active" if g["active"] else "status-ended"
        entries = con.execute("SELECT COUNT(*) as count FROM entries WHERE giveaway_id=?", (g["id"],)).fetchone()["count"] if con else 0
        content += f'''
        <div class="card">
            <span class="badge {status_class}">{status}</span>
            <h2>#{g["id"]} — {g["title"]}</h2>
            <p class="muted">{g["description"]}</p>
            <div class="stat">Entries: <strong>{entries}</strong></div>
            <br>
            <form method="POST" action="/admin/toggle/{g["id"]}" style="display:inline;">
                <button>{'End' if g["active"] else 'Start'}</button>
            </form>
            <form method="POST" action="/admin/delete/{g["id"]}" style="display:inline;" onsubmit="return confirm('Delete this giveaway?')">
                <button class="red">Delete</button>
            </form>
        </div>
        '''
    
    # Recent claims
    content += '''
    <div class="card">
        <h2>🕐 Recent Claims</h2>
        <div class="table-wrap"><table>
            <tr><th>User</th><th>Account</th><th>Type</th><th>Date</th></tr>
    '''
    for c in recent:
        content += f'''
        <tr>
            <td>{c['username'] or 'Unknown'}</td>
            <td><code>{c['account_code'] or '—'}</code></td>
            <td>{c['account_type'] or '—'}</td>
            <td>{c['entered_at'][:16] if c['entered_at'] else '—'}</td>
        </tr>
        '''
    content += '''
        </table></div>
    </div>
    '''
    
    return page("Admin", content)

# ============================================================
# ADMIN POST ROUTES
# ============================================================

@app.route("/admin/settings", methods=["POST"])
@admin_required
def admin_settings():
    set_setting("site_name", request.form.get("site_name", "Giveaway Center").strip())
    set_setting("welcome_title", request.form.get("welcome_title", "Welcome").strip())
    set_setting("site_description", request.form.get("site_description", "").strip())
    set_setting("footer", request.form.get("footer", "").strip())
    set_setting("maintenance", request.form.get("maintenance", "0"))
    return redirect("/admin")

@app.route("/admin/account", methods=["POST"])
@admin_required
def admin_account():
    username = request.form.get("username", "").strip()
    current = request.form.get("current_password", "")
    new = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")
    
    if len(username) < 3:
        return page("Error", '<div class="notice error">Username too short.</div>')
    
    con = db()
    user = con.execute("SELECT * FROM website_users WHERE id=?", (session["user_id"],)).fetchone()
    if not user or not check_password_hash(user["password"], current):
        con.close()
        return page("Error", '<div class="notice error">Current password is incorrect.</div>')
    
    if new:
        if len(new) < 6 or new != confirm:
            con.close()
            return page("Error", '<div class="notice error">Invalid new password.</div>')
        con.execute("UPDATE website_users SET username=?, password=? WHERE id=?", (username, generate_password_hash(new), user["id"]))
    else:
        con.execute("UPDATE website_users SET username=? WHERE id=?", (username, user["id"]))
    
    con.commit()
    con.close()
    session["username"] = username
    return redirect("/admin")

@app.route("/admin/create", methods=["POST"])
@admin_required
def admin_create():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    duration = int(request.form.get("duration", 1440))
    
    if title:
        now = datetime.now().isoformat()
        end_time = (datetime.now() + timedelta(minutes=duration)).isoformat()
        con = db()
        con.execute("INSERT INTO giveaways (title, description, duration_minutes, end_time, active, created_at) VALUES (?,?,?,?,1,?)",
                    (title, description, duration, end_time, now))
        con.commit()
        con.close()
    return redirect("/admin")

@app.route("/admin/accounts/add", methods=["POST"])
@admin_required
def admin_add_accounts():
    raw = request.form.get("accounts", "")
    items = [x.strip() for x in raw.splitlines() if x.strip()]
    
    con = db()
    added = 0
    skipped = 0
    now = datetime.now().isoformat()
    
    for item in items:
        if "|" in item:
            code, typ = item.split("|", 1)
        else:
            code, typ = item, "Standard"
        code, typ = code.strip(), typ.strip() or "Standard"
        if not code: continue
        
        try:
            con.execute("INSERT INTO accounts (account_code, status, account_type, created_at) VALUES (?, 'available', ?, ?)",
                        (code, typ, now))
            added += 1
        except sqlite3.IntegrityError:
            skipped += 1
    
    con.commit()
    con.close()
    return page("Accounts Added", f'''
    <div class="card">
        <h1>✅ Added {added} accounts</h1>
        <div class="notice success">Skipped (duplicates): {skipped}</div>
        <a class="button" href="/admin">Back to Admin</a>
    </div>
    ''')

@app.route("/admin/toggle/<int:gid>", methods=["POST"])
@admin_required
def admin_toggle(gid):
    con = db()
    con.execute("UPDATE giveaways SET active = CASE WHEN active=1 THEN 0 ELSE 1 END WHERE id=?", (gid,))
    con.commit()
    con.close()
    return redirect("/admin")

@app.route("/admin/delete/<int:gid>", methods=["POST"])
@admin_required
def admin_delete(gid):
    con = db()
    con.execute("DELETE FROM entries WHERE giveaway_id=?", (gid,))
    con.execute("UPDATE accounts SET claimed_giveaway_id = NULL WHERE claimed_giveaway_id=?", (gid,))
    con.execute("DELETE FROM giveaways WHERE id=?", (gid,))
    con.commit()
    con.close()
    return redirect("/admin")

@app.route("/admin/announcement", methods=["POST"])
@admin_required
def admin_announcement():
    title = request.form.get("title", "").strip()
    message = request.form.get("message", "").strip()
    if title and message:
        con = db()
        con.execute("INSERT INTO website_announcements (title,message,active) VALUES (?,?,1)", (title, message))
        con.commit()
        con.close()
    return redirect("/admin")

@app.route("/admin/upload", methods=["POST"])
@admin_required
def admin_upload():
    if 'file' not in request.files:
        return page("Error", '<div class="notice error">No file.</div>')
    file = request.files['file']
    if file.filename == '':
        return page("Error", '<div class="notice error">No file selected.</div>')
    
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return page("Error", '<div class="notice error">File type not allowed.</div>')
    
    orig_name = secure_filename(file.filename) or "file"
    timestamp = int(time.time())
    stored_name = f"{timestamp}_{orig_name}"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], stored_name)
    file.save(file_path)
    file_size = os.path.getsize(file_path)
    description = request.form.get("description", "").strip()
    version = request.form.get("version", "").strip()
    
    con = db()
    con.execute("INSERT INTO files (original_name, stored_name, file_size, mime_type, description, version, active) VALUES (?,?,?,?,?,?,1)",
                (orig_name, stored_name, file_size, file.content_type or '', description, version))
    con.commit()
    con.close()
    return redirect("/admin#files")

@app.route("/admin/link/add", methods=["POST"])
@admin_required
def admin_add_link():
    title = request.form.get("title", "").strip()
    url = request.form.get("url", "").strip()
    description = request.form.get("description", "").strip()
    if title and url:
        con = db()
        con.execute("INSERT INTO links (title, url, description, active) VALUES (?,?,?,1)", (title, url, description))
        con.commit()
        con.close()
    return redirect("/admin#links")

# ============================================================
# STARTUP
# ============================================================

if __name__ == "__main__":
    setup()
    port = int(os.environ.get('PORT', 5000))
    print("\n" + "="*50)
    print("       GIVEAWAY WEBSITE STARTED")
    print("="*50)
    print(f"🔹 URL: http://127.0.0.1:{port}")
    print("\nDefault admin: admin / admin123")
    print("="*50 + "\n")
    
    try:
        from waitress import serve
        print("🚀 Serving with Waitress")
        serve(app, host="0.0.0.0", port=port)
    except ImportError:
        print("⚠️  Using Flask built-in server")
        app.run(host="0.0.0.0", port=port, debug=False)