from eval.evaluate import check_evidence_grounding, evaluate

GOLD = {
    "articles": {
        "u1": {
            "people": ["Elon Musk", "Sam Altman"],
            "edges": [{"source": "Elon Musk", "rel_type": "sues", "target": "Sam Altman"}],
        }
    }
}


def test_perfect_prediction_scores_one():
    pred = {"articles": {"u1": {
        "people": ["Musk", "Sam Altman"],  # last-name leniency
        "edges": [{"source": "Musk", "rel_type": "sues", "target": "Altman"}],
    }}}
    res = evaluate(pred, GOLD)
    assert res["people"]["f1"] == 1.0
    assert res["relationships_typed"]["f1"] == 1.0


def test_wrong_label_hits_typed_not_untyped():
    pred = {"articles": {"u1": {
        "people": ["Elon Musk", "Sam Altman"],
        "edges": [{"source": "Elon Musk", "rel_type": "praises", "target": "Sam Altman"}],
    }}}
    res = evaluate(pred, GOLD)
    assert res["relationships_typed"]["f1"] == 0.0
    assert res["relationships_untyped"]["f1"] == 1.0


def test_wrong_direction_fails():
    pred = {"articles": {"u1": {
        "people": ["Elon Musk", "Sam Altman"],
        "edges": [{"source": "Sam Altman", "rel_type": "sues", "target": "Elon Musk"}],
    }}}
    assert evaluate(pred, GOLD)["relationships_untyped"]["f1"] == 0.0


def test_evidence_grounding_flags_fabrication():
    body = "Musk sued OpenAI over its for-profit shift."
    edges = [
        {"source": "A", "rel_type": "sues", "target": "B", "evidence": "Musk sued OpenAI"},
        {"source": "A", "rel_type": "sues", "target": "B", "evidence": "a fabricated quote"},
    ]
    flagged = check_evidence_grounding(body, edges)
    assert len(flagged) == 1
