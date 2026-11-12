"""Exact per-key full outer interval join; no storage dependencies."""
import json


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def normalize(changes):
    if not isinstance(changes, list):
        raise ValueError("CHANGES")
    seen = set()
    result = []
    for c in changes:
        if not isinstance(c, dict) or set(c) != {"side", "id", "rev", "start", "end", "value", "deleted"}:
            raise ValueError("ROW")
        if c["side"] not in ("L", "R") or not isinstance(c["id"], str) or not c["id"]:
            raise ValueError("IDENTITY")
        if any(type(c[k]) is not int for k in ("rev", "start", "end")):
            raise ValueError("INTEGER")
        if c["rev"] <= 0 or c["start"] >= c["end"] or type(c["deleted"]) is not bool:
            raise ValueError("RANGE")
        if not isinstance(c["value"], dict):
            raise ValueError("VALUE")
        ident = (c["side"], c["id"])
        if ident in seen:
            raise ValueError("DUPLICATE")
        seen.add(ident)
        result.append(json.loads(canonical(c)))
    return result


def revise(rows, changes):
    result = dict(rows)
    accepted = []
    for c in changes:
        ident = (c["side"], c["id"])
        old = result.get(ident)
        if old and c["rev"] < old["rev"]:
            continue
        if old and c["rev"] == old["rev"]:
            if old != c:
                raise ValueError("REVISION_CONFLICT")
            continue
        result[ident] = c
        accepted.append(c)
    return result, accepted


def materialize(rows):
    left = sorted((c for c in rows.values() if c["side"] == "L" and not c["deleted"]), key=lambda c: c["id"])
    right = sorted((c for c in rows.values() if c["side"] == "R" and not c["deleted"]), key=lambda c: c["id"])
    matched_l, matched_r, output = set(), set(), []
    for l in left:
        for r in right:
            lo, hi = max(l["start"], r["start"]), min(l["end"], r["end"])
            if lo < hi:
                matched_l.add(l["id"])
                matched_r.add(r["id"])
                output.append([l["id"], r["id"], lo, hi, l["value"], r["value"]])
    for side, matched in ((left, matched_l), (right, matched_r)):
        for row in side:
            if row["id"] not in matched:
                if row["side"] == "L":
                    output.append([row["id"], None, row["start"], row["end"], row["value"], None])
                else:
                    output.append([None, row["id"], row["start"], row["end"], None, row["value"]])
    return sorted(output, key=canonical)


def delta(before, after):
    a = {canonical(row): row for row in before}
    b = {canonical(row): row for row in after}
    return {"remove": [a[k] for k in sorted(a.keys() - b.keys())],
            "add": [b[k] for k in sorted(b.keys() - a.keys())]}
