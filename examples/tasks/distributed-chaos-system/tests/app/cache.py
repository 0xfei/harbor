class Cache:
    def __init__(self):
        self.data = {}

    def get(self, user_id):
        return self.data.get(user_id, 0)

    def set(self, user_id, balance):
        self.data[user_id] = balance
