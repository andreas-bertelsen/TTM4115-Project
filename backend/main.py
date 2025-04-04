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

### MAIN PAGE ###
@app.get("/")
def read_root(request: Request):
    """
    Render the main page.

    Args:
        request (Request): The HTTP request object.

    Returns:
        TemplateResponse: The rendered main page.
    """
    session = get_session(request)

    # Retrieve the error message from the cookie (if it exists)
    error = request.cookies.get("booking_error")

    # Render the main page with the error message
    response = templates.TemplateResponse("index.html", {
        "request": request,
        "session": session,
        "error": error
    })

    # Clear the error cookie after retrieving it
    response.delete_cookie("booking_error")

    return response

@app.get("/scooter-locations")
def get_markers():
    """
    Retrieve scooter locations.

    Returns:
        JSONResponse: A list of scooter locations.
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, lat, lng, isBooked, needs_fixing FROM scooters")
    data = [
        {
            "id": row[0],
            "lat": row[1],
            "lng": row[2],
            "isBooked": row[3],
            "needsFixing": row[4]
        }
        for row in cursor.fetchall()
    ]
    conn.close()
    return JSONResponse(content=data)

@app.get("/scooter-data")
def get_marker_info(id: int):
    """
    Retrieve detailed information about a specific scooter.

    Args:
        id (int): The ID of the scooter.

    Returns:
        JSONResponse: Scooter details or an error message.
    """
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
    """
    Book a scooter.

    Args:
        request (Request): The HTTP request object.
        scooter_id (int): The ID of the scooter to book.

    Returns:
        RedirectResponse: Redirects to the bookings page or the main page with an error.
    """
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
        response = RedirectResponse("/", status_code=303)
        response.set_cookie("booking_error", "Scooter is already booked")
        return response

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
        response = RedirectResponse("/", status_code=303)
        response.set_cookie("booking_error", "Failed to book scooter")
        return response

    conn.close()
    return RedirectResponse("/bookings", status_code=303)

### LOGIN/REGISTER ###
@app.get("/login")
def login_page(request: Request):
    """
    Render the login page.

    Args:
        request (Request): The HTTP request object.

    Returns:
        TemplateResponse: The rendered login page.
    """
    session = get_session(request)
    if session:
        return RedirectResponse("/", status_code=303)

    # Retrieve the error message from the cookie (if it exists)
    error = request.cookies.get("login_error")

    # Render the login page with the error message
    response = templates.TemplateResponse("login.html", {"request": request, "session": session, "error": error})

    # Clear the error cookie after retrieving it
    response.delete_cookie("login_error")

    return response

@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    """
    Handle user login.

    Args:
        username (str): The username of the user.
        password (str): The password of the user.

    Returns:
        RedirectResponse: Redirects to the main page or the login page with an error.
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, is_admin FROM users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    conn.close()

    if user:
        session_token = serializer.dumps({"username": username, "user_id": user[0], "is_admin": bool(user[1])})
        response = RedirectResponse("/", status_code=303)
        response.set_cookie("session", session_token)
        return response

    # Redirect to the login page and set an error message in a cookie
    response = RedirectResponse("/login", status_code=303)
    response.set_cookie("login_error", "Invalid username or password")
    return response

@app.get("/register")
def register_page(request: Request):
    """
    Render the registration page.

    Args:
        request (Request): The HTTP request object.

    Returns:
        TemplateResponse: The rendered registration page.
    """
    session = get_session(request)
    if session:
        return RedirectResponse("/", status_code=303)

    # Retrieve the error message from the cookie (if it exists)
    error = request.cookies.get("register_error")

    # Render the register page with the error message
    response = templates.TemplateResponse("register.html", {"request": request, "session": session, "error": error})

    # Clear the error cookie after retrieving it
    response.delete_cookie("register_error")

    return response

@app.post("/register")
def register(
    username: str = Form(...),
    password: str = Form(...),
    email: str = Form(...)
):
    """
    Handle user registration.

    Args:
        username (str): The username of the user.
        password (str): The password of the user.
        email (str): The email of the user.

    Returns:
        RedirectResponse: Redirects to the login page or the registration page with an error.
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Check for duplicate username
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        conn.close()
        response = RedirectResponse("/register", status_code=303)
        response.set_cookie("register_error", "Username already exists")
        return response

    # Check for duplicate email
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    if cursor.fetchone():
        conn.close()
        response = RedirectResponse("/register", status_code=303)
        response.set_cookie("register_error", "Email already exists")
        return response

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
    """
    Handle user logout.

    Returns:
        RedirectResponse: Redirects to the main page.
    """
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("session")
    return response

### FEEDBACK ###
@app.get("/feedback")
def get_feedback(request: Request):
    """
    Render the feedback page.

    Args:
        request (Request): The HTTP request object.

    Returns:
        TemplateResponse: The rendered feedback page.
    """
    session = get_session(request)
    if not session:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("feedback.html", {
        "request": request,
        "session": session
    })

@app.post("/feedback")
def post_feedback(request: Request, scooter_id: int = Form(None)):
    """
    Render the feedback page with a specific scooter ID.

    Args:
        request (Request): The HTTP request object.
        scooter_id (int): The ID of the scooter.

    Returns:
        TemplateResponse: The rendered feedback page.
    """
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
    """
    Submit feedback.

    Args:
        request (Request): The HTTP request object.
        name (str): The name of the user.
        email (str): The email of the user.
        rating (int): The rating given by the user.
        comments (str): The comments provided by the user.
        scooter_id (int): The ID of the scooter.

    Returns:
        RedirectResponse: Redirects to the main page.
    """
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

### BOOKINGS ###
@app.get("/bookings")
def view_bookings(request: Request):
    """
    Render the bookings page.

    Args:
        request (Request): The HTTP request object.

    Returns:
        TemplateResponse: The rendered bookings page.
    """
    session = get_session(request)
    if not session:
        return RedirectResponse("/login", status_code=303)

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    if session.get("is_admin"):
        # Fetch all bookings with usernames for admin
        cursor.execute("""
            SELECT b.id, b.scooter_id, b.status, b.expires_at, s.battery, u.username
            FROM bookings b
            JOIN scooters s ON b.scooter_id = s.id
            JOIN users u ON b.user_id = u.id
        """)
        bookings = [
            {
                "id": row[0],
                "scooter_id": row[1],
                "status": row[2],
                "expires_at": row[3],
                "battery": row[4],
                "username": row[5]
            }
            for row in cursor.fetchall()
        ]
    else:
        # Fetch bookings for the logged-in user
        user_id = session["user_id"]
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

    # Retrieve the error message from the cookie (if it exists)
    error = request.cookies.get("bookings_error")

    # Render the bookings page with the error message
    response = templates.TemplateResponse("bookings.html", {
        "request": request,
        "bookings": bookings,
        "session": session,
        "error": error
    })

    # Clear the error cookie after retrieving it
    response.delete_cookie("bookings_error")

    return response

@app.post("/activate-booking")
async def activate_booking(request: Request, booking_id: int = Form(...)):
    """
    Activate a booking.

    Args:
        request (Request): The HTTP request object.
        booking_id (int): The ID of the booking to activate.

    Returns:
        RedirectResponse: Redirects to the bookings page or the bookings page with an error.
    """
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
        response = RedirectResponse("/bookings", status_code=303)
        response.set_cookie("bookings_error", "Booking not found")
        return response

    expires_at = TIMEZONE.localize(datetime.strptime(booking[0], "%Y-%m-%d %H:%M:%S"))
    activated_at = TIMEZONE.localize(datetime.strptime(datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"), "%Y-%m-%d %H:%M:%S"))
    scooter_id = booking[1]

    # Compare expires_at with the current time
    if expires_at < activated_at:
        conn.close()
        response = RedirectResponse("/bookings", status_code=303)
        response.set_cookie("bookings_error", "Booking has expired or is invalid")
        return response

    try:
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("""
            UPDATE bookings
            SET status = 'active', activated_at = ?
            WHERE id = ?
        """, (activated_at.strftime("%Y-%m-%d %H:%M:%S"), booking_id))

        # Send MQTT start command
        response = await send_command(scooter_id, "start")
        if response != "activated":
            raise Exception("Failed to activate scooter via MQTT")
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        response = RedirectResponse("/bookings", status_code=303)
        response.set_cookie("bookings_error", str(e))
        return response

    conn.close()
    return RedirectResponse("/bookings", status_code=303)

@app.post("/delete-booking")
async def delete_booking(request: Request, booking_id: int = Form(...)):
    """
    Delete a booking.

    Args:
        request (Request): The HTTP request object.
        booking_id (int): The ID of the booking to delete.

    Returns:
        RedirectResponse: Redirects to the bookings page or the bookings page with an error.
    """
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
        response = RedirectResponse("/bookings", status_code=303)
        response.set_cookie("bookings_error", "Booking not found")
        return response

    scooter_id, status, activated_at = booking

    # Boolean to check if the ride was finished
    ride_finished = False

    try:
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
        cursor.execute("UPDATE scooters SET isBooked = 0 WHERE id = ?", (scooter_id,))

        # Send MQTT stop command if the booking was active
        if status == "active":
            response = await send_command(scooter_id, "stop")
            print(f"Response from MQTT: {response}")
            if response not in ("parked_normal_fare", "parked_increased_fare"):
                raise Exception("Failed to stop scooter via MQTT")
            ride_finished = True
            
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        response = RedirectResponse("/bookings", status_code=303)
        response.set_cookie("bookings_error", str(e))
        return response

    conn.close()

    # If the ride was active, calculate receipt details and render a form to submit to /receipt
    if status == "active" and ride_finished:
        activated_at = TIMEZONE.localize(datetime.strptime(activated_at, "%Y-%m-%d %H:%M:%S"))
        stopped_at = TIMEZONE.localize(datetime.strptime(datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"), "%Y-%m-%d %H:%M:%S"))
        duration_minutes = (stopped_at - activated_at).total_seconds() // 60
        duration_seconds = (stopped_at - activated_at).total_seconds() % 60
        cost = duration_minutes * 2.5 + 2.5
        parking_fee = 0

        if response == "parked_increased_fare":
            parking_fee = 10

        # Render a form to submit the receipt data
        html_content = f"""
        <form id="receipt-form" method="post" action="/receipt">
            <input type="hidden" name="scooter_id" value="{scooter_id}">
            <input type="hidden" name="duration" value="{int(duration_minutes)} minutes and {int(duration_seconds)} seconds">
            <input type="hidden" name="cost" value="{cost:.1f} NOK">
            <input type="hidden" name="parking_fee" value="{parking_fee:.0f},- NOK">
            <input type="hidden" name="total_cost" value="{cost + parking_fee:.1f} NOK">
        </form>
        <script>
            document.getElementById('receipt-form').submit();
        </script>
        """
        return HTMLResponse(content=html_content)

    return RedirectResponse("/bookings", status_code=303)

@app.post("/receipt")
def receipt_page(
    request: Request,
    scooter_id: int = Form(...),
    duration: str = Form(...),
    cost: str = Form(...),
    parking_fee: str = Form(...),
    total_cost: str = Form(...)
):
    """
    Render the receipt page.

    Args:
        request (Request): The HTTP request object.
        scooter_id (int): The ID of the scooter.
        duration (str): The duration of the ride.
        cost (str): The cost of the ride.
        parking_fee (str): The parking fee.
        total_cost (str): The total cost.

    Returns:
        TemplateResponse: The rendered receipt page.
    """
    session = get_session(request)
    if not session:
        return RedirectResponse("/login", status_code=303)

    return templates.TemplateResponse("receipt.html", {
        "request": request,
        "scooter_id": scooter_id,
        "duration": duration,
        "cost": cost,
        "parking_fee": parking_fee,
        "total_cost": total_cost,
        "session": session
    })

### ADMIN PAGE ###
@app.get("/admin/maintenance")
def scooters_needing_fix(request: Request):
    """
    Render the maintenance page for scooters needing fixing.

    Args:
        request (Request): The HTTP request object.

    Returns:
        TemplateResponse: The rendered maintenance page.
    """
    session = get_session(request)
    if not session or not session.get("is_admin"):
        return RedirectResponse("/", status_code=303)

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, lat, lng, battery FROM scooters WHERE needs_fixing = 1")
    scooters = [
        {"id": row[0], "lat": row[1], "lng": row[2], "battery": row[3]}
        for row in cursor.fetchall()
    ]
    conn.close()

    # Retrieve the error message from the cookie (if it exists)
    error = request.cookies.get("maintenance_error")

    # Render the maintenance page with the error message
    response = templates.TemplateResponse("maintenance.html", {
        "request": request,
        "scooters": scooters,
        "session": session,
        "error": error
    })

    # Clear the error cookie after retrieving it
    response.delete_cookie("maintenance_error")

    return response

@app.post("/admin/fix-scooter")
async def fix_scooter(request: Request, scooter_id: int = Form(...)):
    """
    Fix a scooter.

    Args:
        request (Request): The HTTP request object.
        scooter_id (int): The ID of the scooter to fix.

    Returns:
        RedirectResponse: Redirects to the maintenance page or the maintenance page with an error.
    """
    session = get_session(request)
    if not session or not session.get("is_admin"):
        return RedirectResponse("/", status_code=303)

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("UPDATE scooters SET needs_fixing = 0 WHERE id = ?", (scooter_id,))

        result = await send_command(scooter_id, "service_checked")
        if result != "parked":
            raise Exception("Failed to send service_checked command via MQTT")
    
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()

        response = RedirectResponse("/admin/maintenance", status_code=303)
        response.set_cookie("maintenance_error", str(e))
        return response
    
    conn.close()
    return RedirectResponse("/admin/maintenance", status_code=303)

def main():
    """
    Main entry point for the backend application.

    Initializes the database and starts the FastAPI server.
    """
    initialize_database()
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

if __name__ == "__main__":
    main()