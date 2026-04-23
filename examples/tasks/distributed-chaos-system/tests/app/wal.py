class WAL:
    def __init__(self):
        self.log = []

    def append(self, event):
        self.log.append(event)
