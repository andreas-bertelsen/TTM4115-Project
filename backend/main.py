import secrets
from datetime import datetime, timedelta

import pytz
import sqlite3
import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeSerializer

from db_setup import initialize_database, DATABASE
from scheduled_task import lifespan
from mqtt_handler import send_command
import asyncio

TIMEZONE = pytz.timezone("Europe/Oslo")

# FastAPI setup
app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Add custom Jinja2 filters
def datetimeformat(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").strftime("%d %b %Y, %H:%M")

def capitalize(value: str) -> str:
    return value.capitalize()

templates.env.filters['datetimeformat'] = datetimeformat
templates.env.filters['capitalize'] = capitalize

# Session setup using itsdangerous
SECRET_KEY = secrets.token_urlsafe(32)
serializer = URLSafeSerializer(SECRET_KEY)

def get_session(request: Request):
    session_token = request.cookies.get("session")
    if session_token:
        try:
            return serializer.loads(session_token)
        except Exception:
            return {}
    return {}

@app.get("/")
def read_root(request: Request):
    session = get_session(request)
    return templates.TemplateResponse("index.html", {"request": request, "session": session})

@app.get("/login")
def login_page(request: Request):
    session = get_session(request)
    if session:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "session": session})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    conn.close()

    if user:
        session_token = serializer.dumps({"username": username, "user_id": user[0]})
        response = RedirectResponse("/", status_code=303)
        response.set_cookie("session", session_token)
        return response
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid username or password", "session": {}})

@app.get("/register")
def register_page(request: Request):
    session = get_session(request)
    if session:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("register.html", {"request": request, "session": session})

@app.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    email: str = Form(...)
):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Check for duplicate username
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        conn.close()
        return templates.TemplateResponse("register.html", {"request": request, "error": "Username already exists", "session": {}})

    # Check for duplicate email
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    if cursor.fetchone():
        conn.close()
        return templates.TemplateResponse("register.html", {"request": request, "error": "Email already exists", "session": {}})

    # Insert new user
    cursor.execute("""
        INSERT INTO users (username, password, email)
        VALUES (?, ?, ?)
    """, (username, password, email))
    conn.commit()
    conn.close()
    return RedirectResponse("/login", status_code=303)

@app.get("/logout")
def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("session")
    return response

@app.get("/bookings")
def view_bookings(request: Request):
    session = get_session(request)
    if not session:
        return RedirectResponse("/login", status_code=303)

    user_id = session["user_id"]
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Fetch bookings for the logged-in user, including battery percentage
    cursor.execute("""
        SELECT b.id, b.scooter_id, b.status, b.expires_at, s.battery
        FROM bookings b
        JOIN scooters s ON b.scooter_id = s.id
        WHERE b.user_id = ?
    """, (user_id,))
    bookings = [
        {
            "id": row[0],
            "scooter_id": row[1],
            "status": row[2],
            "expires_at": row[3],
            "battery": row[4]
        }
        for row in cursor.fetchall()
    ]
    conn.close()

    return templates.TemplateResponse("bookings.html", {"request": request, "bookings": bookings, "session": session})

@app.get("/feedback")
def get_feedback(request: Request):
    session = get_session(request)
    if not session:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("feedback.html", {
        "request": request,
        "session": session
    })

@app.post("/feedback")
def post_feedback(request: Request, scooter_id: int = Form(None)):
    session = get_session(request)
    if not session:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("feedback.html", {
        "request": request,
        "scooter_id": scooter_id,
        "session": session
    })

@app.post("/submit-feedback")
def submit_feedback(
    request: Request,
    name: str = Form(...), 
    email: str = Form(...), 
    rating: int = Form(...), 
    comments: str = Form(...),
    scooter_id: int = Form(None)
):
    session = get_session(request)
    if not session:
        return RedirectResponse("/login", status_code=303)

    user_id = session["user_id"]
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO feedback (name, email, rating, comments, user_id, scooter_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, email, rating, comments, user_id, scooter_id))
    conn.commit()
    conn.close()
    return RedirectResponse("/", status_code=303)

@app.get("/scooter-locations")
def get_markers():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, lat, lng, isBooked FROM scooters")
    data = [{"id": row[0], "lat": row[1], "lng": row[2], "isBooked": row[3]} for row in cursor.fetchall()]
    conn.close()
    return JSONResponse(content=data)

@app.get("/scooter-data")
def get_marker_info(id: int):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scooters WHERE id = ?", (id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        scooter = {
            "id": row[0],
            "lat": row[1],
            "lng": row[2],
            "battery": row[3],
            "isBooked": bool(row[4])
        }
        return JSONResponse(content=scooter)
    return JSONResponse(content={"error": "Scooter not found"}, status_code=404)

@app.post("/book-scooter")
def book_scooter(request: Request, scooter_id: int = Form(...)):
    session = get_session(request)
    if not session:
        return RedirectResponse("/login", status_code=303)

    user_id = session["user_id"]
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Ensure the scooter is not already booked
    cursor.execute("SELECT isBooked FROM scooters WHERE id = ?", (scooter_id,))
    row = cursor.fetchone()
    if not row or row[0]:
        conn.close()
        return templates.TemplateResponse("index.html", {"request": request, "error": "Scooter is already booked", "session": session})

    # Mark the scooter as booked and create a pending booking
    created_at = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    expires_at = (datetime.now(TIMEZONE) + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("UPDATE scooters SET isBooked = 1 WHERE id = ?", (scooter_id,))
        cursor.execute("""
            INSERT INTO bookings (user_id, scooter_id, status, expires_at, created_at)
            VALUES (?, ?, 'pending', ?, ?)
        """, (user_id, scooter_id, expires_at, created_at))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        return templates.TemplateResponse("index.html", {"request": request, "error": "Failed to book scooter", "session": session})

    conn.close()
    return RedirectResponse("/bookings", status_code=303)

@app.post("/activate-booking")
async def activate_booking(request: Request, booking_id: int = Form(...)):
    session = get_session(request)
    if not session:
        return RedirectResponse("/login", status_code=303)

    user_id = session["user_id"]
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Activate the booking if it is still valid
    cursor.execute("""
        SELECT expires_at, scooter_id FROM bookings
        WHERE id = ? AND user_id = ? AND status = 'pending'
    """, (booking_id, user_id))
    booking = cursor.fetchone()
    if not booking:
        conn.close()
        return templates.TemplateResponse("bookings.html", {"request": request, "error": "Booking not found", "session": session})

    expires_at = TIMEZONE.localize(datetime.strptime(booking[0], "%Y-%m-%d %H:%M:%S"))
    activated_at = TIMEZONE.localize(datetime.strptime(datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"), "%Y-%m-%d %H:%M:%S"))
    scooter_id = booking[1]

    # Compare expires_at with the current time
    if expires_at < activated_at:
        conn.close()
        return templates.TemplateResponse("bookings.html", {"request": request, "error": "Booking has expired or is invalid", "session": session})

    try:
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("""
            UPDATE bookings
            SET status = 'active', activated_at = ?
            WHERE id = ?
        """, (activated_at.strftime("%Y-%m-%d %H:%M:%S"), booking_id))
        conn.commit()

        # Send MQTT start command
        response = await send_command(scooter_id, "start")
        if response != "activated":
            raise Exception("Failed to activate scooter via MQTT")
    except Exception as e:
        conn.rollback()
        conn.close()
        return templates.TemplateResponse("bookings.html", {"request": request, "error": str(e), "session": session})

    conn.close()
    return RedirectResponse("/bookings", status_code=303)

@app.post("/delete-booking")
async def delete_booking(request: Request, booking_id: int = Form(...)):
    session = get_session(request)
    if not session:
        return RedirectResponse("/login", status_code=303)

    user_id = session["user_id"]
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Fetch booking details
    cursor.execute("""
        SELECT scooter_id, status, activated_at FROM bookings
        WHERE id = ? AND user_id = ?
    """, (booking_id, user_id))
    booking = cursor.fetchone()
    if not booking:
        conn.close()
        return templates.TemplateResponse("bookings.html", {"request": request, "error": "Booking not found", "session": session})

    scooter_id, status, activated_at = booking

    try:
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
        cursor.execute("UPDATE scooters SET isBooked = 0 WHERE id = ?", (scooter_id,))
        conn.commit()

        # Send MQTT stop command if the booking was active
        if status == "active":
            response = await send_command(scooter_id, "stop")
            if response != "parked":
                raise Exception("Failed to stop scooter via MQTT")
    except Exception as e:
        conn.rollback()
        conn.close()
        return templates.TemplateResponse("bookings.html", {"request": request, "error": str(e), "session": session})

    conn.close()

    # If the ride was active, calculate receipt details and render a form to submit to /receipt
    if status == "active" and activated_at:
        activated_at = TIMEZONE.localize(datetime.strptime(activated_at, "%Y-%m-%d %H:%M:%S"))
        stopped_at = TIMEZONE.localize(datetime.strptime(datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"), "%Y-%m-%d %H:%M:%S"))
        duration_minutes = (stopped_at - activated_at).total_seconds() // 60
        duration_seconds = (stopped_at - activated_at).total_seconds() % 60
        cost = duration_minutes * 5

        # Render a form to submit the receipt data
        html_content = f"""
        <form id="receipt-form" method="post" action="/receipt">
            <input type="hidden" name="scooter_id" value="{scooter_id}">
            <input type="hidden" name="duration" value="{int(duration_minutes)} minutes and {int(duration_seconds)} seconds">
            <input type="hidden" name="cost" value="{cost:.0f},- NOK">
        </form>
        <script>
            document.getElementById('receipt-form').submit();
        </script>
        """
        return HTMLResponse(content=html_content)

    return RedirectResponse("/bookings", status_code=303)

@app.post("/receipt")
def receipt_page(request: Request, scooter_id: int = Form(...), duration: str = Form(...), cost: str = Form(...)):
    session = get_session(request)
    if not session:
        return RedirectResponse("/login", status_code=303)

    return templates.TemplateResponse("receipt.html", {
        "request": request,
        "scooter_id": scooter_id,
        "duration": duration,
        "cost": cost,
        "session": session
    })

def main():
    initialize_database()
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

if __name__ == "__main__":
    main()