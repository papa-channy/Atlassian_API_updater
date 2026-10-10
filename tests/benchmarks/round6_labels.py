"""Round 6 spec §4.3: promotion of the Round 5 hidden set and catalog-fact relabel of the 22 regression records (controller tool).

    python -m tests.benchmarks.round6_labels promote --plain P --bench B --out B2 --ledger W/controller-events.jsonl
    python -m tests.benchmarks.round6_labels relabel-input --bench B --template tests/benchmarks/round6-relabel-prompt.md --out F
    python -m tests.benchmarks.round6_labels check-review --review R --bench B --catalog C
    python -m tests.benchmarks.round6_labels apply --bench B --review A --review B [--review C] --actors X Y [Z] --out B2
    python -m tests.benchmarks.round6_labels closure --bench B --catalog C --out B2
    python -m tests.benchmarks.round6_labels verify --bench B --plain P --catalog C
"""
import argparse, copy, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)) if str(ROOT) not in sys.path else None
from tests.benchmarks import evaluator as ev  # noqa: E402

PROMOTED_SEED_IDS = tuple(f"s-{i:03d}" for i in range(40, 56))
PROMOTED_NEG_IDS = tuple(f"rn-{i:03d}" for i in range(15, 23))
ORIGIN = "promoted-r5"
LABEL_FIELDS = ("no_answer", "label_migration", "legacy_forbidden_top1", "catalog_missing_keys")


def _sorted_union(*lists):
    return sorted(set().union(*(set(x or []) for x in lists)))


def source_identity(src) -> dict:
    d = {k: v for k, v in src.items() if k not in ("id", "origin")}
    d["forbidden_top1"] = _sorted_union(src.get("forbidden_top1"))
    d["expected_top1_any"] = _sorted_union(src.get("expected_top1_any"))
    return d


def promotion_identity(rec) -> dict:
    """spec §4.3: the record without {id, origin, promoted_from} and the relabel fields; relabel-set expected keys dropped, the
    reconciled forbidden list restored (active ∪ legacy), catalog-closure removals restored."""
    d = {k: v for k, v in rec.items() if k not in ("id", "origin", "promoted_from") + LABEL_FIELDS}
    d["forbidden_top1"] = _sorted_union(rec.get("forbidden_top1"), rec.get("legacy_forbidden_top1"))
    d["expected_top1_any"] = [] if "label_migration" in rec else _sorted_union(rec.get("expected_top1_any"), rec.get("catalog_missing_keys"))
    return d


def promote(bench, r5_plain, r5_seal):
    for split in ("held_out", "negative"):
        if ev.canonical_sha256(r5_plain[split]) != r5_seal[f"{split}_sha256"]:
            raise ValueError(f"Round 5 {split} plaintext does not match round5_seal")
    taken = {r["id"] for s in ("seed", "regression_negative", "regression_positive") for r in bench.get(s) or []}
    if taken & (set(PROMOTED_SEED_IDS) | set(PROMOTED_NEG_IDS)):
        raise ValueError(f"promotion ids already used: {sorted(taken & (set(PROMOTED_SEED_IDS) | set(PROMOTED_NEG_IDS)))}")
    out = copy.deepcopy(bench)
    for split, ids, section in (("held_out", PROMOTED_SEED_IDS, "seed"), ("negative", PROMOTED_NEG_IDS, "regression_negative")):
        src = sorted(r5_plain[split], key=lambda r: r["id"])
        if len(src) != len(ids):
            raise ValueError(f"{split}: expected {len(ids)} records, got {len(src)}")
        for new_id, r in zip(ids, src):
            rec = {**copy.deepcopy(r), "id": new_id, "origin": ORIGIN,
                   "promoted_from": {"round": 5, "split": split, "source_id": r["id"], "source_record_sha256": ev.canonical_sha256(r)}}
            if promotion_identity(rec) != source_identity(r):
                raise ValueError(f"{new_id}: promotion_identity differs from the Round 5 record")
            out[section].append(rec)
        if ev.canonical_sha256(out.get(split)) == ev.canonical_sha256(r5_plain[split]):   # observed at D: moved, not copied
            out[split] = []
    return out, {"promotion_payload_sha256": promotion_payload_sha256(out)}


def promotion_payload_sha256(bench) -> str:
    recs = sorted((r for s in ("seed", "regression_negative", "regression_positive") for r in bench.get(s) or [] if r.get("origin") == ORIGIN),
                  key=lambda r: r["id"])
    return ev.canonical_sha256([{"id": r["id"], "promoted_from": r["promoted_from"], "identity": promotion_identity(r)} for r in recs])


def relabel_targets(bench) -> list:
    """spec §4.3: every existing regression_negative record + the 8 promoted negatives = 22; query only."""
    recs = [r for s in ("regression_negative", "regression_positive") for r in bench.get(s) or []]
    return [{"id": r["id"], "query": r["query"]} for r in sorted(recs, key=lambda r: r["id"])]


def render_relabel_input(targets, template_text) -> str:
    return template_text.replace("{RECORDS}", json.dumps(targets, ensure_ascii=False, indent=1))


def check_review(doc, ids, catalog_keys) -> list:
    out = []
    labels = (doc or {}).get("labels") if isinstance(doc, dict) else None
    if not isinstance(labels, dict) or set(labels) != set(ids):
        return [f"labels must cover exactly {sorted(ids)}"]
    for rid in sorted(ids):
        lab = labels[rid]
        if not isinstance(lab, dict) or set(lab) != {"answerable", "acceptable_keys"} or not isinstance(lab["answerable"], bool) \
                or not isinstance(lab["acceptable_keys"], list) or not all(isinstance(k, str) for k in lab["acceptable_keys"]):
            out.append(f"{rid}: label must be {{answerable: bool, acceptable_keys: [str]}}"); continue
        keys = lab["acceptable_keys"]
        if lab["answerable"] != bool(keys):
            out.append(f"{rid}: answerable must be true iff acceptable_keys is non-empty")
        if keys != sorted(set(keys)):
            out.append(f"{rid}: acceptable_keys must be sorted without duplicates")
        missing = [k for k in keys if k not in catalog_keys]
        if missing:
            out.append(f"{rid}: keys not in the Round 6 S catalog: {missing}")
    return out


def _same(x, y) -> bool:
    return x["answerable"] == y["answerable"] and set(x["acceptable_keys"]) == set(y["acceptable_keys"])


def disagreements(a, b) -> list:
    return sorted(i for i in a if not _same(a[i], b[i]))


def final_labels(a, b, c=None) -> dict:
    dis = disagreements(a, b)
    if dis and (c is None or set(c) < set(dis)):
        raise ValueError(f"disagreements need the third review: {dis}")
    return {i: (c[i] if i in dis else a[i]) for i in sorted(a)}


def reconcile_forbidden(rec, acceptable) -> dict:
    """spec §4.3 (review 3 P0-1): forbidden ∩ expected = ∅ — old forbidden keys that are acceptable move to legacy (provenance only)."""
    out = dict(rec)
    acc = set(acceptable)
    out["forbidden_top1"] = [k for k in rec.get("forbidden_top1") or [] if k not in acc]
    legacy = [k for k in rec.get("forbidden_top1") or [] if k in acc]
    if legacy:
        out["legacy_forbidden_top1"] = legacy
    return out


def apply_labels(bench, labels, migration) -> dict:
    out = copy.deepcopy(bench)
    pool = {r["id"]: r for s in ("regression_negative", "regression_positive") for r in out.get(s) or []}
    if set(pool) != set(labels):
        raise ValueError(f"labels must cover exactly the regression records: {sorted(set(pool) ^ set(labels))}")
    pos, neg = [], []
    for rid in sorted(pool):
        rec, lab = {k: v for k, v in pool[rid].items() if k not in LABEL_FIELDS}, labels[rid]
        rec["forbidden_top1"] = _sorted_union(pool[rid].get("forbidden_top1"), pool[rid].get("legacy_forbidden_top1"))
        rec["label_migration"] = migration[rid]
        if lab["answerable"]:
            rec = reconcile_forbidden(rec, lab["acceptable_keys"])
            rec.update(expected_top1_any=list(lab["acceptable_keys"]), no_answer=False); pos.append(rec)
        else:
            rec.update(expected_top1_any=[], no_answer=True); neg.append(rec)
    out["regression_positive"], out["regression_negative"] = pos, neg
    return out


def catalog_closure(bench, catalog_keys):
    out, stop = copy.deepcopy(bench), []
    for s in ("seed", "regression_positive"):
        for r in out.get(s) or []:
            missing = [k for k in r["expected_top1_any"] if k not in catalog_keys]
            if missing:
                r["catalog_missing_keys"] = missing
                r["expected_top1_any"] = [k for k in r["expected_top1_any"] if k in catalog_keys]
                if not r["expected_top1_any"]:
                    stop.append(r["id"])
    return out, sorted(stop)


def training_identity(rec) -> dict:
    """plan review 1 P0-2: the split identity ignores failure_classes (T's classify rewrites them)."""
    return {k: v for k, v in rec.items() if k != "failure_classes"}


def training_split_sha256(bench) -> str:
    return ev.canonical_sha256({s: [training_identity(r) for r in bench.get(s) or []] for s in ev.TRAINING_SECTIONS})


RELABEL_MANAGED = ("expected_top1_any", "no_answer", "forbidden_top1", "legacy_forbidden_top1", "label_migration", "catalog_missing_keys", "failure_classes")


def immutable_split_sha256(bench) -> str:
    """plan review 3 P0-1: what no relabel rerun may change — every seed record (failure_classes aside; closure-removed expected keys
    restored) and every regression record's identity regardless of section (id, query, origin, provenance, historical forbidden
    = active ∪ legacy); relabel-managed fields and the positive/negative placement are excluded."""
    seed = [{**{k: v for k, v in r.items() if k not in ("failure_classes", "catalog_missing_keys")},
             "expected_top1_any": _sorted_union(r.get("expected_top1_any"), r.get("catalog_missing_keys"))} for r in bench.get("seed") or []]
    reg = sorted(({**{k: v for k, v in r.items() if k not in RELABEL_MANAGED},
                   "historical_forbidden": _sorted_union(r.get("forbidden_top1"), r.get("legacy_forbidden_top1"))}
                  for s in ("regression_negative", "regression_positive") for r in bench.get(s) or []), key=lambda r: r["id"])
    return ev.canonical_sha256({"seed": seed, "regression": reg})


def fixture_label_conflicts(bench) -> list:
    """plan review 1 P0-4 (PR-8): r0 records relabeled answerable whose acceptable keys include a historical fixture forbidden key."""
    return sorted(r["id"] for r in bench.get("regression_positive") or [] if r["origin"].endswith("-r0")
                  and set(r["expected_top1_any"]) & (set(r.get("forbidden_top1") or []) | set(r.get("legacy_forbidden_top1") or [])))


_SHA = re.compile(r"[0-9a-f]{64}")


def label_provenance_problems(bench) -> list:
    """plan review 1 P1-5: once relabeled, every regression record carries no_answer and a well-formed label_migration."""
    out = []
    for s, want in (("regression_positive", False), ("regression_negative", True)):
        for r in bench.get(s) or []:
            if r.get("no_answer") is not want:
                out.append(f"{r['id']}: no_answer must be {want}")
            m = r.get("label_migration")
            if not (isinstance(m, dict) and set(m) == {"reviewers", "review_output_sha256s", "adjudicated"} and isinstance(m["adjudicated"], bool)
                    and isinstance(m["reviewers"], list) and len(m["reviewers"]) in (2, 3)
                    and all(isinstance(a, str) and a for a in m["reviewers"]) and len(set(m["reviewers"])) == len(m["reviewers"])
                    and isinstance(m["review_output_sha256s"], list) and len(m["review_output_sha256s"]) == len(m["reviewers"])
                    and all(isinstance(h, str) and _SHA.fullmatch(h) for h in m["review_output_sha256s"])
                    and (len(m["reviewers"]) == 3) == m["adjudicated"]):
                out.append(f"{r['id']}: label_migration must be {{reviewers[2|3], review_output_sha256s (same length), adjudicated (== 3 reviewers)}}")
    return out


def _read(p):
    return json.loads(pathlib.Path(p).expanduser().read_text(encoding="utf-8"))


def _write(p, doc):
    """Benchmark outputs keep round_seal._write_bench's layout (one record per line) so the committed diff stays reviewable."""
    from tests.benchmarks import round_seal as rs
    p = pathlib.Path(p)
    if not p.exists():
        p.write_text("{}\n", encoding="utf-8")
    rs._write_bench(p, doc)


def _catalog_keys(path) -> set:
    doc = _read(path)
    return {r["key"] for r in (doc["operations"] if isinstance(doc, dict) else doc)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("promote", "relabel-input", "check-review", "apply", "closure", "verify"))
    ap.add_argument("--bench", required=True); ap.add_argument("--plain"); ap.add_argument("--out"); ap.add_argument("--catalog")
    ap.add_argument("--template"); ap.add_argument("--review", action="append", default=[]); ap.add_argument("--actors", nargs="*", default=[])
    ap.add_argument("--sealed-payload", default=None, help="promotion_payload_sha256 from the ledger (plan review 1 P1-1)")
    a = ap.parse_args(argv)
    bench = _read(a.bench)
    if a.cmd == "promote":
        out, payload = promote(bench, _read(a.plain), bench["round5_seal"])
        _write(a.out, out); print(json.dumps(payload)); return 0
    if a.cmd == "relabel-input":
        pathlib.Path(a.out).write_text(render_relabel_input(relabel_targets(bench), pathlib.Path(a.template).read_text(encoding="utf-8")), encoding="utf-8")
        print(json.dumps({"records": len(relabel_targets(bench)), "input_sha256": ev.file_sha256(pathlib.Path(a.out))})); return 0
    ids, keys = [t["id"] for t in relabel_targets(bench)], (_catalog_keys(a.catalog) if a.catalog else set())
    if a.cmd == "check-review":
        probs = check_review(_read(a.review[0]), ids, keys)
        print("\n".join(probs) or "ok"); return 1 if probs else 0
    if a.cmd == "apply":
        docs = [_read(r)["labels"] for r in a.review]
        labels = final_labels(docs[0], docs[1], docs[2] if len(docs) > 2 else None)
        dis = set(disagreements(docs[0], docs[1]))
        shas = [ev.file_sha256(pathlib.Path(r)) for r in a.review]
        mig = {i: {"reviewers": a.actors if i in dis else a.actors[:2], "review_output_sha256s": shas if i in dis else shas[:2],
                   "adjudicated": i in dis} for i in labels}
        out = apply_labels(bench, labels, mig); _write(a.out, out)
        print(json.dumps({"positive": len(out["regression_positive"]), "negative": len(out["regression_negative"]), "adjudicated": sorted(dis)})); return 0
    if a.cmd == "closure":
        out, stop = catalog_closure(bench, keys)
        if stop:
            print(json.dumps({"stop": stop})); return 3                                 # spec §4.3: label/catalog migration problem
        _write(a.out, out); print(json.dumps({"training_split_sha256": training_split_sha256(out)})); return 0
    probs = []                                                                          # verify
    plain = _read(a.plain) if a.plain else None
    for r in (x for s in ("seed", "regression_negative", "regression_positive") for x in bench.get(s) or [] if x.get("origin") == ORIGIN):
        src = next((s for s in (plain or {}).get(r["promoted_from"]["split"], []) if s["id"] == r["promoted_from"]["source_id"]), None)
        if plain is not None and (src is None or promotion_identity(r) != source_identity(src)):
            probs.append(f"{r['id']}: promotion_identity differs from its source")
    for r in bench.get("regression_positive") or []:
        if set(r["expected_top1_any"]) & set(r["forbidden_top1"]):
            probs.append(f"{r['id']}: forbidden ∩ expected")
    if a.sealed_payload is not None and promotion_payload_sha256(bench) != a.sealed_payload:
        probs.append("promotion_payload_sha256 differs from the sealed value")
    if bench.get("regression_positive") is not None:
        probs += label_provenance_problems(bench)
        probs += [f"{i}: PR-8 fixture label conflict (STOP_FOR_AMENDMENT)" for i in fixture_label_conflicts(bench)]
    print("\n".join(probs) or "ok"); return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
