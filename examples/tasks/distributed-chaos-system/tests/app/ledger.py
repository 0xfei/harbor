class Ledger:
    def __init__(self):
        self.records = []

    def write(self, user_id, amount):
        self.records.append((user_id, amount))
