"""Shared benchmark evaluator (spec §7.1): one record schema for seed / held_out / negative."""


def evaluate(records, search_fn):
    failed = []
    for rec in records:
        expected = rec.get("expected_top1_any") or []
        forbidden = rec.get("forbidden_top1") or []
        if not expected and not forbidden:
            raise ValueError(f"benchmark record {rec.get('query')!r} must set expected_top1_any or forbidden_top1")
        ranked = search_fn(rec["query"])
        top1 = ranked[0] if ranked else None
        ok = (not expected or top1 in expected) and (top1 not in forbidden)
        if not ok:
            failed.append({"query": rec["query"], "top1": top1, "expected_top1_any": expected, "forbidden_top1": forbidden})
    return {"passed": len(records) - len(failed), "failed": failed, "total": len(records)}
