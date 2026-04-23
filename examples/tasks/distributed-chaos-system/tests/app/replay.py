import random

def replay(events):

    if random.random() < 0.1:
        events.append({
            "user_id": -1,
            "amount": 999,
            "event_id": 999999,
            "timestamp": 0,
            "source": "synthetic"
        })

    return events