"""Round 6 spec §3.5: scorer-rule counterexample. Summary-as-query corpus over the bound snapshot S; OFF (no rules) vs ON (R0–R3)
at the SAME constants and aliases; loss = OFF recommended the query's own operation and ON does not."""
import dataclasses
import hashlib
import pathlib
from types import MappingProxyType
from unittest import mock

from tests.benchmarks import evaluator as ev
from tools.atlassian_docs.intelligence import policy, search

GENERATOR = pathlib.Path(__file__)


def corpus(state) -> list:
    out = []
    for name in sorted(state.registry.sources):
        for op in sorted(state.registry.sources[name].operations, key=lambda o: o.key):
            if (op.summary or "").strip():
                out.append({"query": op.summary.strip(), "key": op.key})
    return out


def corpus_metadata(state, items) -> dict:
    return {"registry_fingerprint": state.registry.fingerprint, "operation_count": sum(len(sr.operations) for sr in state.registry.sources.values()),
            "corpus_sha256": ev.canonical_sha256(items), "generator_sha256": hashlib.sha256(GENERATOR.read_bytes()).hexdigest()}


def scorer_rule_ok(losses: int, eligible: int) -> bool:
    return eligible > 0 and 100 * losses <= eligible


def _rp_at(rp, point):
    return dataclasses.replace(rp, constants=MappingProxyType(dict(point)), sha256=policy.canonical_sha256({"tuning_point": dict(point)}))


def usage_with(state, rp, point, alias_policy, enabled):
    rpp = _rp_at(rp, point)

    def fn(q):
        with mock.patch.object(policy, "ranking", return_value=rpp), mock.patch.object(policy, "aliases", return_value=alias_policy), \
                search.scorer_rules(enabled):
            out = search.search_operations(state, q, limit=5)
        return [r["key"] for r in out.get("results", [])], out.get("recommended_operation"), out.get("abstain_reason")
    return fn


def _rank(keys, key):
    return keys.index(key) + 1 if key in keys else None


def _run(state, rp, point, alias_policy, items, on_rules, usage_factory=None):
    """usage_factory(enabled) -> fn(query) -> (ranked, recommended, abstain_reason): an equivalent fast path (the tuning selector's
    memoized GridEvaluator); default = production search_operations."""
    if usage_factory is not None:
        off, on = usage_factory(()), usage_factory(tuple(on_rules))
    else:
        off, on = usage_with(state, rp, point, alias_policy, ()), usage_with(state, rp, point, alias_policy, on_rules)
    losses, gains, eligible, loss_list = 0, 0, 0, []
    for it in items:
        k_off, r_off, _ = off(it["query"]); k_on, r_on, why = on(it["query"])
        if r_off == it["key"]:
            eligible += 1
            if r_on != it["key"]:
                losses += 1
                loss_list.append({"key": it["key"], "off_recommended": r_off, "on_recommended": r_on, "on_abstain_reason": why,
                                  "off_rank": _rank(k_off, it["key"]), "on_rank": _rank(k_on, it["key"])})   # spec §3.5: key + reason
        elif r_on == it["key"]:
            gains += 1
    return losses, gains, eligible, loss_list


def compare(state, rp, point, alias_policy, items, *, bound_fingerprint, aliases_sha256, on_rules=search.RULES, usage_factory=None) -> dict:
    if state.registry.fingerprint != bound_fingerprint:
        raise ValueError(f"registry {state.registry.fingerprint} is not the bound Round 6 S {bound_fingerprint}")
    losses, gains, eligible, loss_list = _run(state, rp, point, alias_policy, items, on_rules, usage_factory)
    write = sum(1 for l in loss_list if l["key"].split(":")[1] in search.WRITE_METHODS)
    return {"registry_fingerprint": state.registry.fingerprint, "ranking_structure_sha256": rp.structure_sha256,
            "verb_methods_sha256": policy.canonical_sha256({k: list(v) for k, v in rp.verb_method_order.items()}),   # == sha of the raw verb_methods
            "aliases_sha256": aliases_sha256, "constants": dict(point), "enabled_rules": list(on_rules),
            "corpus_sha256": ev.canonical_sha256(items), "losses": losses, "gains": gains, "eligible": eligible,
            "losses_write": write, "losses_read": losses - write, "loss_list": loss_list, "ok": scorer_rule_ok(losses, eligible)}


def per_rule_off(state, rp, point, alias_policy, items, **kw) -> dict:
    """Diagnostic only (spec §3.5): ON minus one rule, per rule."""
    return {r: compare(state, rp, point, alias_policy, items, on_rules=tuple(x for x in search.RULES if x != r), **kw) for r in search.RULES}
