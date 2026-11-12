import json
import sys
from pathlib import Path
from intervaljoin import Cluster


def sample():
    return json.loads(Path(__file__).with_name("samples.json").read_text(encoding="utf-8"))


def run(mode):
    data = sample()
    key, txs = data["key"], data["transactions"]
    c = Cluster([":memory:", ":memory:"])
    try:
        receipts = []
        history = []
        for tx in txs:
            response = c.apply(key, **tx)
            receipts.append(response)
            history.append(c.read(key))
        expected = [
            [["l1", "r1", 5, 10, {"reading": 9}, {"quality": "ok"}]],
            [["l1", "r1", 5, 10, {"reading": 9}, {"quality": "ok"}],
             ["l2", "r2", 25, 30, {"reading": 8}, {"quality": "ok"}]],
            [["l1", None, 0, 10, {"reading": 9}, None],
             ["l2", "r1", 22, 27, {"reading": 8}, {"quality": "revised"}],
             ["l2", "r2", 25, 30, {"reading": 8}, {"quality": "ok"}]],
            [["l1", None, 0, 10, {"reading": 9}, None],
             ["l2", "r1", 22, 27, {"reading": 8}, {"quality": "revised"}]],
            [["l1", None, 0, 10, {"reading": 9}, None],
             ["l2", "r1", 45, 50, {"reading": 8}, {"quality": "revised"}]],
            [["l1", None, 0, 10, {"reading": 9}, None],
             ["l2", None, 40, 50, {"reading": 8}, None]],
            [["l1", None, 0, 10, {"reading": 9}, None],
             ["l2", "r2", 42, 48, {"reading": 8}, {"quality": "back"}]]
        ]
        from intervaljoin.model import canonical
        for at, rows in zip(history, expected):
            assert at["rows"] == sorted(rows, key=canonical), at
        assert c.apply(key, **txs[0]) == receipts[0]
        before = c.read(key)
        conflict = dict(txs[0])
        conflict["seq"] = 999
        try:
            c.apply(key, **conflict)
        except ValueError as exc:
            assert str(exc) == "REQUEST_CONFLICT"
        else:
            raise AssertionError("conflict accepted")
        for fault in ("after_state", "after_receipt"):
            try:
                c.apply(key, 8, "retry", [], fail_at=fault)
            except RuntimeError as exc:
                assert str(exc) == "INJECTED"
            else:
                raise AssertionError("fault missing")
            assert c.read(key) == before
        assert c.apply(key, 8, "retry", []) == {"key": key, "seq": 8, "remove": [], "add": []}
        stale = dict(txs[0]["changes"][0])
        stale["rev"] = 1
        stale["value"] = {"different": True}
        try:
            c.apply(key, 9, "bad-rev", [stale])
        except ValueError as exc:
            assert str(exc) == "REVISION_CONFLICT"
        else:
            raise AssertionError("revision conflict accepted")
        assert c.read(key)["seq"] == 8
        assert c.read("unrelated") == {"key": "unrelated", "seq": 0, "rows": []}
        if mode == "demo":
            print(json.dumps({"history": history, "move_delta": receipts[2],
                              "replay": c.apply(key, **txs[0]),
                              "export": c.workers[c.owner(key)].export_key(key)}, ensure_ascii=False, sort_keys=True))
        else:
            print(json.dumps({"normal": "NORMAL_REGRESSION_OK", "final": c.read(key)}, ensure_ascii=False, sort_keys=True))
    finally:
        c.close()


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("normal", "demo"):
        raise SystemExit("usage: python3 checks.py normal|demo")
    run(sys.argv[1])
