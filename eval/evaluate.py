"""Score the graph against a hand-labelled gold set.

There's no single "correct" answer for relationship extraction, so we score it
the way IE systems are usually scored, with a few choices that fit this task:

People (really, how well resolution works)
    Precision / recall / F1 over the people in each article. Matching is
    resolution-aware: a predicted person counts if its normalized name matches
    the gold one, or if one is the other's last name (same rule the resolver
    uses), so "Altman" vs "Sam Altman" isn't penalised.

Relationships, scored two ways
    * typed:   (source, normalized rel_type, target) all have to match, so a
      wrong direction or a wrong label both cost you.
    * untyped: only (source, target) and direction matter. This separates "did
      we find the connection?" from "did we label it well?", which is fair
      because the label vocabulary is open and several labels can be defensible.

Direction counts: (Musk -> Altman) is not the same as (Altman -> Musk).

What this catches: missed people, made-up people or edges, wrong direction,
and over- or under-merging in resolution. What it doesn't catch: how good the
explanation/evidence text is. For that there's a separate faithfulness check
(check_evidence_grounding) that flags any evidence sentence which doesn't appear
verbatim in the article body, i.e. invented provenance.

Usage:
    python -m eval.evaluate --pred predictions.json --gold eval/gold.json

predictions.json has the same shape as gold but holds predicted people/edges.
You produce it by running the real pipeline and dumping the per-article output.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass

# So you can run this straight from the repo without pip-installing the package.
sys.path.insert(0, ".")
from newskg.resolution import normalize, normalize_rel_type  # noqa: E402


def _people_match(a: str, b: str) -> bool:
    na, nb = normalize(a), normalize(b)
    if na == nb:
        return True
    # same last-name leniency the resolver applies
    ta, tb = na.split(), nb.split()
    if len(ta) == 1 and tb and ta[0] == tb[-1]:
        return True
    if len(tb) == 1 and ta and tb[0] == ta[-1]:
        return True
    return False


def _match_set(pred: list[str], gold: list[str]) -> tuple[int, int, int]:
    """Return (true_positives, num_pred, num_gold) with greedy 1:1 matching."""
    used = set()
    tp = 0
    for g in gold:
        for i, p in enumerate(pred):
            if i in used:
                continue
            if _people_match(p, g):
                used.add(i)
                tp += 1
                break
    return tp, len(pred), len(gold)


def _prf(tp: int, n_pred: int, n_gold: int) -> dict:
    precision = tp / n_pred if n_pred else 0.0
    recall = tp / n_gold if n_gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


@dataclass
class Counts:
    tp: int = 0
    pred: int = 0
    gold: int = 0

    def add(self, t: tuple[int, int, int]):
        self.tp += t[0]
        self.pred += t[1]
        self.gold += t[2]

    def prf(self):
        return _prf(self.tp, self.pred, self.gold)


def _edge_key(e: dict, typed: bool) -> tuple:
    return (
        normalize(e["source"]),
        normalize_rel_type(e["rel_type"]) if typed else "*",
        normalize(e["target"]),
    )


def _edge_match(pred_edges, gold_edges, typed: bool) -> tuple[int, int, int]:
    pred_keys = [_edge_key(e, typed) for e in pred_edges]
    gold_keys = [_edge_key(e, typed) for e in gold_edges]
    used = set()
    tp = 0
    for gk in gold_keys:
        for i, pk in enumerate(pred_keys):
            if i in used:
                continue
            # endpoints use the same lenient people matching
            if _people_match(pk[0], gk[0]) and _people_match(pk[2], gk[2]) and pk[1] == gk[1]:
                used.add(i)
                tp += 1
                break
    return tp, len(pred_keys), len(gold_keys)


def evaluate(predictions: dict, gold: dict) -> dict:
    people = Counts()
    edges_typed = Counts()
    edges_untyped = Counts()

    g_articles = gold["articles"]
    p_articles = predictions.get("articles", {})

    for url, g in g_articles.items():
        p = p_articles.get(url, {"people": [], "edges": []})
        people.add(_match_set(p.get("people", []), g["people"]))
        edges_typed.add(_edge_match(p.get("edges", []), g["edges"], typed=True))
        edges_untyped.add(_edge_match(p.get("edges", []), g["edges"], typed=False))

    return {
        "people": people.prf(),
        "relationships_typed": edges_typed.prf(),
        "relationships_untyped": edges_untyped.prf(),
        "articles_scored": len(g_articles),
    }


def check_evidence_grounding(article_body: str, edges: list[dict]) -> list[dict]:
    """Catch made-up evidence: flag any sentence that isn't in the article."""
    body = " ".join(article_body.split()).lower()
    flagged = []
    for e in edges:
        ev = " ".join(e.get("evidence", "").split()).lower()
        if ev and ev not in body:
            flagged.append({"edge": (e["source"], e["rel_type"], e["target"]), "evidence": e["evidence"]})
    return flagged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True, help="predictions JSON")
    ap.add_argument("--gold", default="eval/gold.json")
    args = ap.parse_args()
    pred = json.loads(open(args.pred, encoding="utf-8").read())
    gold = json.loads(open(args.gold, encoding="utf-8").read())
    print(json.dumps(evaluate(pred, gold), indent=2))


if __name__ == "__main__":
    main()
