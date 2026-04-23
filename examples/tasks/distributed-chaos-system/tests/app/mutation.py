import random

class MutationEngine:

    def mutate_factor(self):
        return 1.0 if random.random() < 0.95 else 1.07