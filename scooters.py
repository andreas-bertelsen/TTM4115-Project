import random

SCOOTERS = [
    {
        "id": i,
        "lat": 63.4305 + (random.random() - 0.5) * 0.02,
        "lng": 10.3951 + (random.random() - 0.5) * 0.02,
        "isBooked": True if random.random() > 0.5 else False,
        "battery": f"{random.randint(10, 100)}%"
    }
    for i in range(10)
]