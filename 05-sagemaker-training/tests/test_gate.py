from gate import check

GOOD = {"accuracy": 0.99, "recall_per_class": {"healthy": 1.0, "inner_race_fault": 0.99,
                                               "outer_race_fault": 0.97, "ball_fault": 0.99}}


def test_good_model_passes():
    passed, reasons = check(GOOD)
    assert passed and "0.990" in reasons[0]


def test_low_accuracy_fails():
    passed, reasons = check({**GOOD, "accuracy": 0.85})
    assert not passed and "accuracy 0.850" in reasons[0]


def test_one_weak_class_fails_even_with_good_accuracy():
    # The real story from project 04: 90.7% accuracy but only 78% recall on outer-race faults.
    weak = {"accuracy": 0.907, "recall_per_class": {**GOOD["recall_per_class"], "outer_race_fault": 0.78}}
    passed, reasons = check(weak)
    assert not passed and reasons == ["recall for outer_race_fault is 0.780, below 0.80"]


def test_every_problem_is_listed():
    bad = {"accuracy": 0.5, "recall_per_class": {"healthy": 0.5, "ball_fault": 0.4}}
    assert len(check(bad)[1]) == 3


def test_missing_metrics_fail():
    assert check({})[0] is False
