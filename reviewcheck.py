"""Replay only the fixed-owner baseline; never simulates a target resharder."""
import contextlib
import io
import json
import re
import sys
from pathlib import Path
from checks import run, sample
from intervaljoin import Cluster


def replay():
    data = sample()
    c = Cluster([":memory:", ":memory:"])
    try:
        history, responses = [], []
        for tx in data["transactions"]:
            responses.append(c.apply(data["key"], **tx))
            history.append(c.read(data["key"]))
        repeated = c.apply(data["key"], **data["transactions"][2])
        return {"history": history, "responses": responses, "repeated_move": repeated,
                "head_after_replay": c.read(data["key"])["seq"]}
    finally:
        c.close()


def verify():
    with contextlib.redirect_stdout(io.StringIO()):
        run("normal")
    text = Path("DESIGN.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```json baseline-evidence\n(.*?)\n```", text, re.S)
    assert len(blocks) == 1, "one baseline-evidence JSON block required"
    actual = replay()
    assert json.loads(blocks[0]) == actual, "report baseline evidence differs from original calls"
    refs = re.findall(r"(intervaljoin/(?:model|worker|cluster)\.py):([0-9]+)", text)
    assert refs, "source line references required"
    for path, line in refs:
        assert 1 <= int(line) <= len(Path(path).read_text(encoding="utf-8").splitlines()), (path,line)
    print(json.dumps({"report_evidence": "REPORT_REPLAY_OK", "actual": actual}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("replay", "verify"):
        raise SystemExit("usage: python3 reviewcheck.py replay|verify")
    if sys.argv[1] == "replay":
        print(json.dumps(replay(), ensure_ascii=False, sort_keys=True))
    else:
        verify()
