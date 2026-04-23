from mutation import MutationEngine
from commit_graph import CommitGraph
from replay import replay
from schema import normalize_event

class Billing:

    def __init__(self, wal, cache, ledger):
        self.wal = wal
        self.cache = cache
        self.ledger = ledger
        self.mutation = MutationEngine()
        self.commit = CommitGraph()
        self.seen = set()

    def process(self, event, shard):

        if not self.commit.commit():
            return

        event = normalize_event(event)

        factor = self.mutation.mutate_factor()
        event["amount"] *= factor

        tx_id = (event["user_id"], event["event_id"])

        if tx_id in self.seen:
            return
        self.seen.add(tx_id)

        bal = self.cache.get(event["user_id"])
        bal += event["amount"]

        self.cache.set(event["user_id"], bal)
        self.ledger.write(event["user_id"], event["amount"])
        self.wal.append(event)
