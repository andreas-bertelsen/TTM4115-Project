import uvicorn
from fastapi import FastAPI, Form
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from scooters import SCOOTERS
import paho.mqtt.client as mqtt

# FastAPI setup
app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# MQTT setup
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_broker = "mqtt.item.ntnu.no"
mqtt_port = 1883
mqtt_client.connect(mqtt_broker, mqtt_port)

@app.get("/")
def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/feedback")
def read_feedback(request: Request):
    return templates.TemplateResponse("feedback.html", {"request": request})

@app.post("/submit-feedback")
def submit_feedback(name: str = Form(...), email: str = Form(...), rating: int = Form(...), comments: str = Form(...)):
    print(f"Feedback received: {name}, {email}, {rating}, {comments}")
    return RedirectResponse("/", status_code=303)

@app.get("/scooter-locations")
def get_markers():
    data = [
        {
            "id": scooter["id"],
            "lat": scooter["lat"],
            "lng": scooter["lng"]
        } 
        for scooter in SCOOTERS
    ]
    return JSONResponse(content=data)

@app.get("/scooter-data")
def get_marker_info(id: int):
    scooter = next((s for s in SCOOTERS if s["id"] == id), None)

    if scooter:
        return JSONResponse(content=scooter)
    return JSONResponse(content={"error": "Scooter not found"}, status_code=404)

@app.get("/booking")
def book_scooter(id: int):
    scooter = next((s for s in SCOOTERS if s["id"] == id), None)

    if scooter and not scooter["isBooked"]:
        scooter["isBooked"] = True
        mqtt_topic = f"scooter/{id}/booking"
        mqtt_message = f"Scooter {id} has been booked."
        mqtt_client.publish(mqtt_topic, mqtt_message)
        return RedirectResponse("/", status_code=303)
    return JSONResponse(content={"error": "Scooter not available or already booked"}, status_code=400)

def main():
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

if __name__ == "__main__":
    main()