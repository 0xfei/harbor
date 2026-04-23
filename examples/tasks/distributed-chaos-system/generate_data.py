import json, random
random.seed(42)
with open("/data/events.jsonl", "w") as f:
    for i in range(50000):
        f.write(json.dumps({"user_id": i % 2000, "amount": 1, "event_id": i, "timestamp": i // 5, "source": "A"}) + "\n")
print("Generated 50000 events")
