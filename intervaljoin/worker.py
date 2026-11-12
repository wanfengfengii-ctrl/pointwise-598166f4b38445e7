"""One SQLite transaction owns each complete key in the fixed layout."""
import json
import sqlite3
from .model import canonical, normalize, revise, materialize, delta


class Worker:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS heads(k TEXT PRIMARY KEY, seq INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS rows(k TEXT, side TEXT, id TEXT, body TEXT,
                                       PRIMARY KEY(k,side,id));
        CREATE TABLE IF NOT EXISTS outputs(k TEXT, body TEXT, PRIMARY KEY(k,body));
        CREATE TABLE IF NOT EXISTS receipts(k TEXT, request TEXT, digest TEXT, response TEXT,
                                           PRIMARY KEY(k,request));
        CREATE TABLE IF NOT EXISTS journal(k TEXT, seq INTEGER, request TEXT, changes TEXT,
                                          PRIMARY KEY(k,seq));
        """)

    def close(self):
        self.db.close()

    def _rows(self, key):
        values = [json.loads(x[0]) for x in self.db.execute("SELECT body FROM rows WHERE k=?", (key,))]
        return {(x["side"], x["id"]): x for x in values}

    def read(self, key):
        self.db.execute("BEGIN")
        try:
            head = self.db.execute("SELECT seq FROM heads WHERE k=?", (key,)).fetchone()
            output = [json.loads(x[0]) for x in self.db.execute("SELECT body FROM outputs WHERE k=? ORDER BY body", (key,))]
            self.db.execute("COMMIT")
            return {"key": key, "seq": head[0] if head else 0, "rows": output}
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def apply(self, key, seq, request, changes, fail_at=None):
        if not isinstance(key, str) or not key or not isinstance(request, str) or not request:
            raise ValueError("IDENTITY")
        if type(seq) is not int or seq <= 0:
            raise ValueError("SEQ")
        changes = normalize(changes)
        binding = canonical({"seq": seq, "changes": changes})
        self.db.execute("BEGIN IMMEDIATE")
        try:
            old = self.db.execute("SELECT digest,response FROM receipts WHERE k=? AND request=?", (key,request)).fetchone()
            if old:
                if old[0] != binding:
                    raise ValueError("REQUEST_CONFLICT")
                self.db.execute("COMMIT")
                return json.loads(old[1])
            head = self.db.execute("SELECT seq FROM heads WHERE k=?", (key,)).fetchone()
            if seq != (head[0] if head else 0) + 1:
                raise ValueError("SEQ_GAP")
            before = [json.loads(x[0]) for x in self.db.execute("SELECT body FROM outputs WHERE k=?", (key,))]
            updated, accepted = revise(self._rows(key), changes)
            after = materialize(updated)
            diff = delta(before, after)
            for c in accepted:
                self.db.execute("INSERT OR REPLACE INTO rows VALUES(?,?,?,?)", (key,c["side"],c["id"],canonical(c)))
            self.db.execute("DELETE FROM outputs WHERE k=?", (key,))
            self.db.executemany("INSERT INTO outputs VALUES(?,?)", [(key,canonical(row)) for row in after])
            if fail_at == "after_state":
                raise RuntimeError("INJECTED")
            response = {"key": key, "seq": seq, **diff}
            self.db.execute("INSERT OR REPLACE INTO heads VALUES(?,?)", (key,seq))
            self.db.execute("INSERT INTO journal VALUES(?,?,?,?)", (key,seq,request,canonical(changes)))
            self.db.execute("INSERT INTO receipts VALUES(?,?,?,?)", (key,request,binding,canonical(response)))
            if fail_at == "after_receipt":
                raise RuntimeError("INJECTED")
            self.db.execute("COMMIT")
            return response
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def export_key(self, key):
        self.db.execute("BEGIN")
        try:
            head = self.db.execute("SELECT seq FROM heads WHERE k=?", (key,)).fetchone()
            rows = sorted(self._rows(key).values(), key=lambda c: (c["side"],c["id"]))
            receipts = [list(x) for x in self.db.execute("SELECT request,digest,response FROM receipts WHERE k=? ORDER BY request", (key,))]
            journal = [list(x) for x in self.db.execute("SELECT seq,request,changes FROM journal WHERE k=? ORDER BY seq", (key,))]
            self.db.execute("COMMIT")
            return {"key": key, "seq": head[0] if head else 0, "rows": rows, "receipts": receipts, "journal": journal}
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
