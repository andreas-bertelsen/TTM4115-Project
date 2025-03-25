import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

import pytz
import sqlite3
from fastapi import FastAPI

from db_setup import DATABASE

TIMEZONE = pytz.timezone("Europe/Oslo")

# Lifespan context manager for startup and shutdown tasks
@asynccontextmanager
async def lifespan(app: FastAPI):
    async def cleanup_expired_bookings():
        """
        Periodically clean up expired bookings and free up scooters.
        """
        while True:
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()

            # Find and delete expired bookings
            cursor.execute("""
                SELECT id, scooter_id, expires_at FROM bookings
                WHERE status = 'pending'
            """)
            expired_bookings = cursor.fetchall()

            for booking in expired_bookings:
                booking_id, scooter_id, expires_at = booking

                # Convert expires_at to timezone-aware datetime
                expires_at_dt = TIMEZONE.localize(datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S"))
                time_now = TIMEZONE.localize(datetime.strptime(datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"), "%Y-%m-%d %H:%M:%S"))

                if expires_at_dt < time_now:
                    try:
                        cursor.execute("BEGIN TRANSACTION")
                        cursor.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
                        cursor.execute("UPDATE scooters SET isBooked = 0 WHERE id = ?", (scooter_id,))
                        conn.commit()
                    except Exception as e:
                        conn.rollback()

            conn.close()

            # Wait for 30 seconds before the next cleanup
            await asyncio.sleep(30)

    # Start the periodic task
    task = asyncio.create_task(cleanup_expired_bookings())

    yield  # Yield control to the application

    # Cancel the periodic task on shutdown
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        print("Periodic cleanup task cancelled.")