import random
import sqlite3

# Database setup
DATABASE = "scooter_app.db"

def initialize_database():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Clear existing data
    cursor.execute("DROP TABLE IF EXISTS feedback")
    cursor.execute("DROP TABLE IF EXISTS scooters")
    cursor.execute("DROP TABLE IF EXISTS users")
    cursor.execute("DROP TABLE IF EXISTS bookings")

    # Create tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        email TEXT NOT NULL,
        is_admin BOOLEAN NOT NULL DEFAULT 0
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scooters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lat REAL NOT NULL,
        lng REAL NOT NULL,
        battery INTEGER NOT NULL,
        isBooked BOOLEAN NOT NULL DEFAULT 0
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        rating INTEGER NOT NULL,
        comments TEXT,
        user_id INTEGER,
        scooter_id INTEGER,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (scooter_id) REFERENCES scooters (id)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        scooter_id INTEGER NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('pending', 'active')),
        expires_at DATETIME NOT NULL,
        created_at DATETIME NOT NULL,
        activated_at DATETIME,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (scooter_id) REFERENCES scooters (id)
    )
    """)

    # Insert initial data
    cursor.execute("""
        INSERT OR IGNORE INTO users (username, password, email, is_admin)
        VALUES ('admin', 'admin123', 'admin@ntnu.no', 1)
    """)
    for i in range(30):
        lat = 63.422 + (random.random() - 0.5) * 0.02
        lng = 10.395 + (random.random() - 0.5) * 0.08
        battery = random.randint(30, 100)
        cursor.execute("""
            INSERT OR IGNORE INTO scooters (lat, lng, battery)
            VALUES (?, ?, ?)
        """, (lat, lng, battery))

    conn.commit()
    conn.close()