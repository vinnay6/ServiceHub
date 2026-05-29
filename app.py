from flask import Flask, render_template, request, redirect, make_response, session, send_file
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import razorpay
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import A4
import io
from werkzeug.utils import secure_filename
from flask import request
from dotenv import load_dotenv
import os
from math import radians, cos, sin, asin, sqrt
from flask_mail import Mail, Message
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)

from reportlab.lib.styles import (
    getSampleStyleSheet,
    ParagraphStyle
)

from reportlab.lib import colors

from reportlab.lib.pagesizes import A4

from reportlab.lib.enums import TA_CENTER

import io




app = Flask(__name__)
load_dotenv()
app.secret_key = os.getenv("SECRET_KEY")

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ✅ Make sure folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)



BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

#----Mail-Route
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")


mail = Mail(app)


def send_email(to_email, subject, body):
    msg = Message(
        subject,
        sender=app.config["MAIL_USERNAME"],
        recipients=[to_email]
    )
    msg.body = body
    mail.send(msg)




# ---------------- DATABASE ----------------
def get_db():
    print("USING DATABASE:", DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""

CREATE TABLE IF NOT EXISTS providers (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    name TEXT,

    service TEXT,

    city TEXT,

    email TEXT,

    password TEXT,

    phone TEXT,

    price REAL,

    logo TEXT,

    about TEXT,

    status TEXT DEFAULT 'pending'

)

""")
    c.execute("""

CREATE TABLE IF NOT EXISTS bookings (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    provider_id INTEGER,

    customer_id INTEGER,

    date TEXT,

    status TEXT DEFAULT 'pending',

    total_amount REAL,

    commission REAL,

    provider_amount REAL,

    handling_charge REAL,

    final_amount REAL,

    FOREIGN KEY(provider_id) REFERENCES providers(id),

    FOREIGN KEY(customer_id) REFERENCES customers(id)

)

""")

   
    c.execute("""
    CREATE TABLE IF NOT EXISTS provider_images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider_id INTEGER NOT NULL,
        image_path TEXT NOT NULL,
        FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE
    )
    """)
    


    c.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        phone TEXT
    )
    """)

    c.execute("""

CREATE TABLE IF NOT EXISTS reviews (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    booking_id INTEGER,

    provider_id INTEGER,

    customer_id INTEGER,

    rating INTEGER,

    comment TEXT,

    image TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

)

""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        role TEXT,
        message TEXT,
        is_read INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.execute("""

    CREATE TABLE IF NOT EXISTS reports (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        provider_id INTEGER,

        message TEXT

    )


    """)

    c.execute("""

    CREATE TABLE IF NOT EXISTS admins (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        email TEXT,

        password TEXT

    )

    """)
 
    
# Create default admin if not exists

    # Default admin create

admin = conn.execute(
    "SELECT * FROM admins WHERE email=?",
    ("admin@gmail.com",)
).fetchone()

if not admin:

    conn.execute("""
    INSERT INTO admins (email, password)
    VALUES (?, ?)
    """, (
        "admin@gmail.com",
        "admin123"
    ))
    conn.commit()
    conn.close()
init_db()

# ---------------- GPS ----------------

def distance(lat1, lon1, lat2, lon2):

    lon1 = radians(lon1)
    lon2 = radians(lon2)
    lat1 = radians(lat1)
    lat2 = radians(lat2)

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))

    km = 6371 * c
    return km


from flask import session, redirect

@app.route("/select-location")
def select_location():
    return render_template("location.html")


from flask import session, request, redirect
#-------------------LOACTION-DETECTION-MANUL------------------------------
@app.route("/set-location", methods=["POST"])
def set_location():

    session["city"] = request.form["city"]

    return redirect("/loading")
#-------------------LOACTION-DETECTION-AUTO-------------------------------
@app.route("/detect-location", methods=["POST"])
def detect_location():

    data = request.get_json()

    lat = data["lat"]
    lon = data["lon"]

    import requests

    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"

    res = requests.get(url).json()

    city = res["address"].get("city") or res["address"].get("town")

    session["city"] = city

    return {"status":"ok"}

@app.route("/loading")
def loading():
    return render_template("loading.html")

@app.route("/providers")
def providers():

    city = session.get("city")

    conn = get_db()

    providers = conn.execute(
        "SELECT * FROM providers WHERE city=?",
        (city,)
    ).fetchall()

    conn.close()

    return render_template("providers.html", providers=providers)
# ---------------- RAZORPAY ----------------
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")


client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# ---------------- LOGIN DECORATOR ----------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "provider_id" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

# ---------------- ROLE SELECTION ----------------
@app.route("/")
def home():
    return render_template("home.html")


# ---------------- MARKETPLACE ----------------
from flask import session, redirect

@app.route("/services")
def services():

    # agar location set nahi hai
    if "city" not in session:
        return redirect("/select-location")

    conn = get_db()

    providers = conn.execute(
        "SELECT * FROM providers WHERE city=?",
        (session["city"],)
    ).fetchall()

    conn.close()

    return render_template("index.html", providers=providers)


# ---------------- ONBOARD ----------------
@app.route("/onboard", methods=["GET", "POST"])
def onboard():
    if request.method == "POST":

        logo = request.files["logo"]
        images = request.files.getlist("images")

        logo_filename = None
        if logo and logo.filename != "":
            logo_filename = secure_filename(logo.filename)
            logo.save(os.path.join(app.config["UPLOAD_FOLDER"], logo_filename))

        conn = get_db()
        c = conn.cursor()

        # Provider insert
        c.execute("""
        INSERT INTO providers 
        (name, service, city, email, password, phone, price, logo, about)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form["name"],
            request.form["service"],
            request.form["city"],
            request.form["email"],
            generate_password_hash(request.form["password"]),
            request.form["phone"],
            int(request.form["price"]),
            logo_filename,
            request.form["about"]
        ))

        provider_id = c.lastrowid

        # 🔔 ADMIN NOTIFICATION
        conn.execute("""
        INSERT INTO notifications (user_id, role, message)
        VALUES (?, ?, ?)
        """, (
            1,
            "admin",
            f"New provider {request.form['name']} registered and waiting for approval"
        ))

        # Save gallery images
        for file in images:
            if file and file.filename != "":
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

                c.execute("""
                INSERT INTO provider_images (provider_id, image_path)
                VALUES (?, ?)
                """, (provider_id, filename))

        conn.commit()
        conn.close()

        return redirect("/login")

    return render_template("onboard.html")

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        conn = get_db()

        provider = conn.execute(
            "SELECT * FROM providers WHERE email=?",
            (request.form["email"],)
        ).fetchone()

        conn.close()

        if provider and check_password_hash(provider["password"], request.form["password"]):

            # 🔴 Admin approval check
            if provider["status"] != "approved":
                return "Your account is waiting for admin approval"

            session["provider_id"] = provider["id"]

            return redirect(f"/dashboard/{provider['id']}")

        return "Invalid Login"

    return render_template("login.html")

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------------- CUSTOMER ROUTE ---------------

@app.route("/customer-login", methods=["GET", "POST"])
def customer_login():

    if request.method == "POST":

        conn = get_db()
        c = conn.cursor()

        c.execute("SELECT * FROM customers WHERE email = ?", (request.form["email"],))
        customer = c.fetchone()

        conn.close()

        if customer and check_password_hash(customer[3], request.form["password"]):

            session["customer_id"] = customer[0]
            session["customer_name"] = customer[1]

            # 👇 yaha magic
            next_url = session.pop("next_url", None)

            if next_url:
                return redirect(next_url)

            return redirect("/customer-dashboard")

        return "Invalid email or password"

    return render_template("customer_login.html")


def customer_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "customer_id" not in session:
            session["next_url"] = request.url
            return redirect("/customer-login")
        return f(*args, **kwargs)
    return decorated_function

     #customer-logout


@app.route("/customer-logout")
def customer_logout():
    session.pop("customer_id", None)
    session.pop("customer_name", None)
    return redirect("/")


# ---------------- CUSTOMER-DASHBOARD ----------------

@app.route("/customer-dashboard")
def customer_dashboard():

    if "customer_id" not in session:
        return redirect("/customer-login")

    conn = get_db()

    notifications = conn.execute("""
    SELECT * FROM notifications
    WHERE user_id=? AND role='customer'
    ORDER BY created_at DESC
    """, (session["customer_id"],)).fetchall()

    c = conn.cursor()

    c.execute("""
    SELECT 
        bookings.id,
        providers.name,
        providers.service,
        bookings.status,
        reviews.id
    FROM bookings
    JOIN providers ON bookings.provider_id = providers.id
    LEFT JOIN reviews ON bookings.id = reviews.booking_id
    WHERE bookings.customer_id = ?
    ORDER BY bookings.id DESC
    """, (session["customer_id"],))

    bookings = c.fetchall()
    conn.close()

    return render_template(
        "customer_dashboard.html",
        bookings=bookings,
        customer_name=session["customer_name"]
    )
# ---------------- CUSTOMER-REGISTER ----------------

@app.route("/customer-register", methods=["GET", "POST"])
def customer_register():
    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        conn = get_db()
        c = conn.cursor()

        c.execute("INSERT INTO customers (name, email, password) VALUES (?, ?, ?)",
                  (name, email, password))

        conn.commit()
        conn.close()

        return redirect("/customer-login")

    return render_template("customer_register.html")
# ---------------- PROVIDER DETAIL ----------------
@app.route("/provider/<int:id>")
def provider_detail(id):

    conn = get_db()

    # provider info
    provider = conn.execute(
        "SELECT * FROM providers WHERE id=?",
        (id,)
    ).fetchone()

    # agar provider exist nahi karta
    if not provider:
        conn.close()
        return "Provider not found"

    # provider images
    images = conn.execute(
        "SELECT * FROM provider_images WHERE provider_id=?",
        (id,)
    ).fetchall()

    # reviews with customer name
    reviews = conn.execute("""
        SELECT r.*, c.name
        FROM reviews r
        JOIN customers c ON r.customer_id = c.id
        WHERE r.provider_id = ?
        ORDER BY r.created_at DESC
    """, (id,)).fetchall()

    # average rating
    avg_rating = conn.execute("""
        SELECT ROUND(AVG(rating),1)
        FROM reviews
        WHERE provider_id = ?
    """, (id,)).fetchone()[0]

    if avg_rating is None:
        avg_rating = 0

    conn.close()

    return render_template(
        "provider.html",
        provider=provider,
        images=images,
        reviews=reviews,
        avg_rating=avg_rating
    )      

# ---------------- billing route ----------------

@app.route("/billing/<int:booking_id>", methods=["GET", "POST"])
def billing_page(booking_id):

    if "customer_id" not in session:
        return redirect("/customer-login")

    conn = get_db()

    booking = conn.execute("""

    SELECT
        bookings.*,

        providers.name AS provider_name,

        providers.phone AS provider_phone,

        providers.service AS service_name

    FROM bookings

    LEFT JOIN providers
    ON bookings.provider_id = providers.id

    WHERE bookings.id=?

""", (booking_id,)).fetchone()

    if not booking:
        conn.close()
        return "Booking not found"

    # ORIGINAL SERVICE PRICE
    service_amount = float(booking["total_amount"])

    # TAXES & FEES
    tax = round(service_amount * 0.18, 2)

    commission = round(service_amount * 0.10, 2)

    handling = 30

    delivery = 0

    # DEFAULT DISCOUNT
    discount = 0

    # APPLY COUPON
    if request.method == "POST":

        coupon = request.form.get("coupon")

        if coupon and coupon.upper() == "SAVE35":

            # 35% DISCOUNT
            discount = round(service_amount * 0.35, 2)

            session["discount"] = discount

        else:

            discount = 0

            session["discount"] = 0

    else:

        # GET SAVED DISCOUNT
        discount = session.get("discount", 0)

    # SUBTOTAL
    subtotal = service_amount + tax + handling

    # FINAL TOTAL
    total = round(subtotal - discount, 2)

    # ADMIN REVENUE
    admin_revenue = round(commission + handling, 2)

    # PROVIDER EARNING
    provider_amount = round(total - admin_revenue, 2)

    # UPDATE DATABASE
    conn.execute("""
        UPDATE bookings
        SET final_amount=?,
            commission=?,
            provider_amount=?,
            status='Paid'
        WHERE id=?
    """, (
        total,
        admin_revenue,
        provider_amount,
        booking_id
    ))

    conn.commit()

    conn.close()

    return render_template(
        "billing.html",

        booking=booking,

        service_amount=service_amount,

        tax=tax,

        commission=commission,

        handling=handling,

        delivery=delivery,

        discount=discount,

        subtotal=subtotal,

        total=total,

        provider_amount=provider_amount
    )
# ---------------- BOOK ----------------
# ---------------- BOOK ----------------
@app.route("/book/<int:provider_id>", methods=["GET", "POST"])
def book(provider_id):

    # Customer login check
    if "customer_id" not in session:
        session["next_url"] = request.url
        return redirect("/customer-login")

    conn = get_db()

    # Provider fetch
    provider = conn.execute(
        "SELECT * FROM providers WHERE id=?",
        (provider_id,)
    ).fetchone()

    # Provider not found
    if not provider:
        conn.close()
        return "Provider not found"

    # Form submit
    if request.method == "POST":

        # Booking date
        date = request.form["date"]

        # Provider price
        provider_price = int(provider["price"])

        # Platform Commission (10%)
        commission = provider_price * 0.10

        # Handling charge (5%)
        handling_charge = provider_price * 0.05

        # Provider earning
        provider_amount = (
            provider_price
            - commission
            - handling_charge
        )

        c = conn.cursor()

        # Insert booking
        c.execute("""
        INSERT INTO bookings
        (
            provider_id,
            customer_id,
            date,
            status,
            total_amount,
            commission,
            provider_amount,
            handling_charge
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            provider_id,
            session["customer_id"],
            date,
            "pending",
            provider_price,
            commission,
            provider_amount,
            handling_charge
        ))

        booking_id = c.lastrowid

        conn.commit()

        # Notification for provider
        conn.execute("""
        INSERT INTO notifications
        (user_id, role, message)
        VALUES (?, ?, ?)
        """, (
            provider_id,
            "provider",
            f"New booking received for {date}"
        ))

        conn.commit()

        # Provider Email
        provider_email = provider["email"]

        # Send Email
        send_email(
            provider_email,
            "New Booking Received",
            f"You have received a new booking for {date}. Please login to confirm."
        )

        conn.close()

        # Go to billing page
        return redirect(f"/billing/{booking_id}")

    conn.close()

    return render_template(
        "book.html",
        provider=provider
    )


# ---------------- PAYMENT ----------------
@app.route("/payment/<int:booking_id>", methods=["GET", "POST"])
def payment(booking_id):

    conn = get_db()

    booking = conn.execute(
        "SELECT * FROM bookings WHERE id=?",
        (booking_id,)
    ).fetchone()

    if not booking:
        return "Booking not found"

    final_amount = booking["final_amount"]

    if not final_amount:
        return "Amount not calculated. Go to billing first."

    amount = int(float(final_amount) * 100)  # Razorpay wants paise

    if request.method == "POST":
        if request.form.get("payment_type") == "cod":
            conn.execute(
                "UPDATE bookings SET status='COD Selected' WHERE id=?",
                (booking_id,)
            )
            conn.commit()
            conn.close()
            return "Order placed with COD ✅"

    order = client.order.create({
        "amount": amount,
        "currency": "INR",
        "payment_capture": 1
    })

    conn.close()

    return render_template("payment.html",
                           order_id=order["id"],
                           amount=amount,
                           key_id=RAZORPAY_KEY_ID,
                           booking_id=booking_id)





# ------------- Review se related

@app.route("/add-review/<int:booking_id>", methods=["POST"])
def add_review(booking_id):

    if "customer_id" not in session:
        return redirect("/customer-login")

    rating = request.form["rating"]
    comment = request.form["comment"]

    image = request.files.get("image")
    filename = None

    if image and image.filename != "":
        filename = secure_filename(image.filename)
        image.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    conn = get_db()

    booking = conn.execute(
        "SELECT provider_id FROM bookings WHERE id=?",
        (booking_id,)
    ).fetchone()

    if not booking:
        return "Booking not found"

    provider_id = booking["provider_id"]

    conn.execute("""
    INSERT INTO reviews
    (booking_id, provider_id, customer_id, rating, comment, image)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        booking_id,
        provider_id,
        session["customer_id"],
        rating,
        comment,
        filename
    ))

    conn.commit()
    conn.close()

    return redirect(f"/provider/{provider_id}")

#REVIEW

@app.route("/review/<int:booking_id>")
def review_page(booking_id):

    if "customer_id" not in session:
        return redirect("/customer-login")

    conn = get_db()

    booking = conn.execute("""
        SELECT b.id, p.name, p.id as provider_id
        FROM bookings b
        JOIN providers p ON b.provider_id = p.id
        WHERE b.id=?
    """, (booking_id,)).fetchone()

    conn.close()

    return render_template("review.html", booking=booking)

#SUBMIT-REVIEW
@app.route("/submit_review", methods=["POST"])
def submit_review():

    if "customer_id" not in session:
        return redirect("/customer-login")

    booking_id = request.form["booking_id"]
    provider_id = request.form["provider_id"]
    rating = request.form["rating"]
    comment = request.form["comment"]

    conn = get_db()

    conn.execute("""
        INSERT INTO reviews (booking_id, provider_id, customer_id, rating, comment)
        VALUES (?, ?, ?, ?, ?)
    """, (booking_id, provider_id, session["customer_id"], rating, comment))

    conn.commit()
    conn.close()

    return redirect("/customer-dashboard")

#--------------------REPORT------------

@app.route("/report-provider/<int:provider_id>", methods=["POST"])
def report_provider(provider_id):

    message = request.form["message"]

    conn = get_db()

    # Save report
    conn.execute(
        "INSERT INTO reports (provider_id, message) VALUES (?,?)",
        (provider_id, message)
    )

    # Admin notification
    conn.execute("""
    INSERT INTO notifications (user_id, role, message)
    VALUES (?, ?, ?)
    """, (
        1,
        "admin",
        f"Provider {provider_id} has been reported"
    ))

    conn.commit()
    conn.close()

    return redirect(f"/provider/{provider_id}")

# ---------------- BOOKING-SUCCESS-ROUTE ----------------
@app.route("/booking-success/<int:booking_id>")
def booking_success(booking_id):

    conn = get_db()
    data = conn.execute(
        "SELECT * FROM bookings WHERE id=?",
        (booking_id,)
    ).fetchone()

    print(dict(data)) 

    conn.close()

    return render_template("price.html", data=data)

# ---------------- DASHBOARD ----------------
@app.route("/dashboard/<int:id>")
@login_required
def dashboard(id):
    if session["provider_id"] != id:
        return redirect("/login")

    conn = get_db()
    notifications = conn.execute("""
    SELECT * FROM notifications
    WHERE user_id=? AND role='provider'
    ORDER BY created_at DESC
    """, (session["provider_id"],)).fetchall()

    
    provider = conn.execute("SELECT * FROM providers WHERE id=?", (id,)).fetchone()
    bookings = conn.execute("SELECT * FROM bookings WHERE provider_id=?", (id,)).fetchall()

    total_revenue = sum(b["total_amount"] or 0 for b in bookings)
    total_commission = sum(b["commission"] or 0 for b in bookings)
    provider_earnings = sum(b["provider_amount"] or 0 for b in bookings)

    conn.close()

    return render_template("dashboard.html",
                           provider=provider,
                           bookings=bookings,
                           total_bookings=len(bookings),
                           total_revenue=total_revenue,
                           total_commission=total_commission,
                           provider_earnings=provider_earnings)






# ---------------- BOOKING-Status-ROUTES ----------------

#confirm
@app.route("/confirm-booking/<int:booking_id>")
def confirm_booking(booking_id):

    if "provider_id" not in session:
        return redirect("/login")

    conn = get_db()

    booking = conn.execute("""
        SELECT * FROM bookings
        WHERE id=? AND provider_id=?
    """, (booking_id, session["provider_id"])).fetchone()

    if not booking:
        conn.close()
        return "Booking not found"

    customer_id = booking["customer_id"]

    # Update booking status
    conn.execute("""
        UPDATE bookings
        SET status='confirmed'
        WHERE id=? AND provider_id=?
    """, (booking_id, session["provider_id"]))

    # Notification
    conn.execute("""
        INSERT INTO notifications (user_id, role, message)
        VALUES (?, ?, ?)
    """, (
        customer_id,
        "customer",
        "Your booking has been confirmed."
    ))

    # Customer details
    customer = conn.execute(
        "SELECT * FROM customers WHERE id=?",
        (customer_id,)
    ).fetchone()

    if customer:
        send_email(
            customer["email"],
            "Booking Confirmed",
            "Your booking has been confirmed. Thank you!"
        )

    conn.commit()
    conn.close()

    return redirect(f"/dashboard/{session['provider_id']}")

#complete
@app.route("/complete-booking/<int:booking_id>")
def complete_booking(booking_id):

    if "provider_id" not in session:
        return redirect("/login")

    conn = get_db()


   

    conn.execute("""
        UPDATE bookings
        SET status='completed'
        WHERE id=? AND provider_id=?
    """, (booking_id, session["provider_id"]))

    conn.commit()
    conn.close()

    return redirect(f"/dashboard/{session['provider_id']}")



#delete
@app.route("/delete-booking/<int:booking_id>")
def delete_booking(booking_id):

    if "provider_id" not in session:
        return redirect("/login")

    conn = get_db()
    conn.execute("""
        DELETE FROM bookings
        WHERE id=? AND provider_id=?
    """, (booking_id, session["provider_id"]))

    conn.commit()
    conn.close()

    return redirect(f"/dashboard/{session['provider_id']}")

# ---------------- ADMIN  ----------------
@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        admin = conn.execute(
            "SELECT * FROM admins WHERE email=? AND password=?",
            (email, password)
        ).fetchone()
        conn.close()

        if admin:
            session["admin_id"] = admin["id"]
            return redirect("/admin-dashboard")
        else:
            return "Invalid Credentials"

    return render_template("admin_login.html")

# ADMIN_DASHBOARD
@app.route("/admin-dashboard")
def admin_dashboard():

    if "admin_id" not in session:
        return redirect("/admin-login")

    conn = get_db()

    total_providers = conn.execute(
        "SELECT COUNT(*) FROM providers"
    ).fetchone()[0]

    total_customers = conn.execute(
        "SELECT COUNT(*) FROM customers"
    ).fetchone()[0]

    total_bookings = conn.execute(
        "SELECT COUNT(*) FROM bookings"
    ).fetchone()[0]

    total_revenue = conn.execute(
        "SELECT SUM(total_amount) FROM bookings WHERE status='confirmed'"
    ).fetchone()[0] or 0

    total_commission = conn.execute(
        "SELECT SUM(commission) FROM bookings WHERE status='confirmed'"
    ).fetchone()[0] or 0

    pending_providers = conn.execute(
        "SELECT * FROM providers WHERE status='pending'"
    ).fetchall()

    notifications = conn.execute("""
    SELECT message, created_at
    FROM notifications
    WHERE role='admin'
    ORDER BY created_at DESC
    LIMIT 10
    """).fetchall()

    conn.close()

    return render_template(
        "admin_dashboard.html",
        total_providers=total_providers,
        total_customers=total_customers,
        total_bookings=total_bookings,
        total_revenue=total_revenue,
        total_commission=total_commission,
        pending_providers=pending_providers,
        notifications=notifications
    )
#route for approve

@app.route("/approve-provider/<int:id>")
def approve_provider(id):

    conn = get_db()

    conn.execute(
        "UPDATE providers SET status='approved' WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/admin-dashboard")

#Route for delte
@app.route("/reject-provider/<int:id>")
def reject_provider(id):

    conn = get_db()

    conn.execute(
        "DELETE FROM providers WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/admin-dashboard")
#provider info by admin


@app.route("/admin-providers")
def admin_providers():

    if "admin_id" not in session:
        return redirect("/admin-login")

    conn = get_db()

    providers = conn.execute(
        "SELECT * FROM providers"
    ).fetchall()

    conn.close()

    return render_template("admin_providers.html", providers=providers)



#delete providr 


@app.route("/delete-provider/<int:id>")
def delete_provider(id):

    conn = get_db()

    conn.execute(
        "DELETE FROM providers WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/admin-providers")


#booking mangement 

@app.route("/admin-bookings")
def admin_bookings():

    if "admin_id" not in session:
        return redirect("/admin-login")

    conn = get_db()

    bookings = conn.execute("""
    SELECT bookings.*, providers.name, customers.name
    FROM bookings
    JOIN providers ON bookings.provider_id = providers.id
    JOIN customers ON bookings.customer_id = customers.id
    """).fetchall()

    conn.close()

    return render_template("admin_bookings.html", bookings=bookings)



#Revnue check for admin


@app.route("/admin-revenue")
def admin_revenue():

    conn = get_db()

    total_revenue = conn.execute(
        "SELECT SUM(total_amount) FROM bookings"
    ).fetchone()[0] or 0

    total_commission = conn.execute(
        "SELECT SUM(commission) FROM bookings"
    ).fetchone()[0] or 0

    conn.close()

    return render_template(
        "admin_revenue.html",
        revenue=total_revenue,
        commission=total_commission
    )

# ---------------- PDF ----------------
@app.route("/download-pdf/<int:booking_id>")
def download_pdf(booking_id):

    conn = get_db()

    data = conn.execute("""

    SELECT
        bookings.*,

        providers.name AS provider_name,

        providers.phone AS provider_phone,

        providers.service AS service_name

    FROM bookings

    LEFT JOIN providers
    ON bookings.provider_id = providers.id

    WHERE bookings.id=?

    """, (booking_id,)).fetchone()

    conn.close()

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=30
    )

    styles = getSampleStyleSheet()

    elements = []

    # CUSTOM STYLES

    title_style = ParagraphStyle(
        'title',
        parent=styles['Heading1'],
        fontSize=28,
        textColor=colors.HexColor("#2563eb"),
        alignment=TA_CENTER,
        spaceAfter=20
    )

    subtitle_style = ParagraphStyle(
        'subtitle',
        parent=styles['BodyText'],
        fontSize=12,
        textColor=colors.grey,
        alignment=TA_CENTER,
        spaceAfter=30
    )

    section_style = ParagraphStyle(
        'section',
        parent=styles['Heading2'],
        fontSize=18,
        textColor=colors.HexColor("#111827"),
        spaceAfter=15
    )

    normal_style = styles['BodyText']

    # HEADER

    elements.append(
        Paragraph(
            "ServiceHub",
            title_style
        )
    )

    elements.append(
        Paragraph(
            "Professional Home Services Platform",
            subtitle_style
        )
    )

    # PAID BADGE

    elements.append(
        Paragraph(
            "<font color='green'><b>✔ PAYMENT SUCCESSFUL</b></font>",
            styles['Heading3']
        )
    )

    elements.append(Spacer(1, 20))

    # BOOKING INFO

    elements.append(
        Paragraph(
            "Invoice Information",
            section_style
        )
    )

    info_data = [

        ["Invoice ID", f"#{data['id']}"],

        ["Booking Date", str(data["date"])],

        ["Status", str(data["status"])],

        ["Customer", "Valued Customer"]

    ]

    info_table = Table(
        info_data,
        colWidths=[200, 250]
    )

    info_table.setStyle(TableStyle([

        ('BACKGROUND', (0,0), (-1,0), colors.white),

        ('TEXTCOLOR', (0,0), (-1,-1), colors.black),

        ('GRID', (0,0), (-1,-1), 1, colors.HexColor("#e5e7eb")),

        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),

        ('FONTSIZE', (0,0), (-1,-1), 12),

        ('BOTTOMPADDING', (0,0), (-1,-1), 12),

        ('BACKGROUND', (0,0), (0,-1), colors.HexColor("#f3f4f6"))

    ]))

    elements.append(info_table)

    elements.append(Spacer(1, 30))

    # BILLING SECTION

    elements.append(
        Paragraph(
            "Billing Summary",
            section_style
        )
    )

    billing_data = [

        ["Description", "Amount"],

        [
            "Professional Service Charges",
            f"₹ {data['total_amount']:.2f}"
        ],

        [
            "Platform Charges",
            f"₹ {data['handling_charge']:.2f}"
        ],

        [
            "GST Included",
            "18%"
        ],

        [
            "Final Amount Paid",
            f"₹ {data['final_amount']:.2f}"
        ]

    ]

    billing_table = Table(
        billing_data,
        colWidths=[300, 150]
    )

    billing_table.setStyle(TableStyle([

        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2563eb")),

        ('TEXTCOLOR', (0,0), (-1,0), colors.white),

        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),

        ('FONTSIZE', (0,0), (-1,-1), 12),

        ('GRID', (0,0), (-1,-1), 1, colors.HexColor("#d1d5db")),

        ('BOTTOMPADDING', (0,0), (-1,0), 14),

        ('BACKGROUND', (0,1), (-1,-1), colors.white),

        ('BOTTOMPADDING', (0,1), (-1,-1), 12),

        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),

        ('TEXTCOLOR', (0,-1), (-1,-1), colors.HexColor("#16a34a"))

    ]))

    elements.append(billing_table)

    elements.append(Spacer(1, 40))

    # FOOTER

    elements.append(
        Paragraph(
            """
            <para align=center>
            <font size=14>
            <b>Thank You For Choosing ServiceHub ❤️</b>
            </font>
            <br/><br/>
            <font color=grey>
            This is a digitally generated invoice and does not require a signature.
            </font>
            </para>
            """,
            normal_style
        )
    )

    # BUILD PDF

    doc.build(elements)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"ServiceHub_Invoice_{booking_id}.pdf",
        mimetype='application/pdf'
    )





# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)