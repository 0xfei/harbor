class Dedup:
    def __init__(self):
        self.seen = set()

    def check(self, x):
        if x in self.seen:
            return False
        self.seen.add(x)
        return True