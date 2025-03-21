import uvicorn
from fastapi import FastAPI, Form
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import random

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

scooters = [
    {
        "id": i,
        "lat": 63.4305 + (random.random() - 0.5) * 0.02,
        "lng": 10.3951 + (random.random() - 0.5) * 0.02,
        "isBooked": True if random.random() > 0.5 else False,
        "battery": f"{random.randint(10, 100)}%"
    }
    for i in range(10)
]

@app.get("/")
def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/booking")
def read_booking(request: Request, id: int):
    return templates.TemplateResponse("booking.html", {"request": request})

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
        for scooter in scooters
    ]
    return JSONResponse(content=data)

@app.get("/scooter-data")
def get_marker_info(id: int):
    scooter = next((s for s in scooters if s["id"] == id), None)
    if scooter:
        return JSONResponse(content=scooter)
    return JSONResponse(content={"error": "Scooter not found"}, status_code=404)

def main():
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

if __name__ == "__main__":
    main()