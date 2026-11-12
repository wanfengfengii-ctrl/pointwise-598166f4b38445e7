"""Static routing only: worker files are deliberately independent databases."""
import hashlib
from .worker import Worker


class Cluster:
    def __init__(self, paths):
        if not paths:
            raise ValueError("WORKERS")
        self.workers = [Worker(path) for path in paths]

    def owner(self, key):
        return int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big") % len(self.workers)

    def apply(self, key, seq, request, changes, fail_at=None):
        return self.workers[self.owner(key)].apply(key, seq, request, changes, fail_at)

    def read(self, key):
        return self.workers[self.owner(key)].read(key)

    def close(self):
        for worker in self.workers:
            worker.close()
