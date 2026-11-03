"""Pipeline logic that can be checked without AWS, including a local imitation of batch transform."""

import json

import pytest

import batch_score
import common
import inference
import train_and_register


def test_datasets_have_header_and_expected_rows():
    train_csv, test_csv = train_and_register.make_datasets()
    assert train_csv.splitlines()[0] == "condition,rms,kurtosis,crest_factor,peak_freq_hz,shaft_speed_hz"
    assert len(train_csv.splitlines()) == 4000 + 1
    assert len(test_csv.splitlines()) == 1000 + 1
    assert train_csv != test_csv


def test_source_package_contains_training_and_inference_code():
    archive = common.package_source()
    assert b"def main" in common.read_from_tar(archive, "train.py")
    assert b"def model_fn" in common.read_from_tar(archive, "inference.py")
    with pytest.raises(KeyError):
        common.read_from_tar(archive, "data.py")


def test_training_request_uses_script_mode_and_safety_limit():
    req = train_and_register.training_request("job-1", "arn:role", "img:tag", "bkt", "s3://bkt/code/x.tar.gz")
    hp = req["HyperParameters"]
    # SageMaker passes hyperparameters to the script as JSON-encoded strings.
    assert json.loads(hp["sagemaker_program"]) == "train.py"
    assert json.loads(hp["n-estimators"]) == 150
    assert all(isinstance(v, str) for v in hp.values())
    assert [c["ChannelName"] for c in req["InputDataConfig"]] == ["train", "test"]
    assert req["StoppingCondition"]["MaxRuntimeInSeconds"] <= 900


def test_batch_file_has_ids_and_no_header():
    csv_text, truth = batch_score.make_batch()
    lines = csv_text.splitlines()
    assert len(lines) == len(truth) == 200
    assert lines[0].startswith("BRG-0001,") and len(lines[0].split(",")) == 6
    assert len(set(truth.values())) == 4


def imitate_batch_transform(input_csv, model):
    """What SageMaker does with InputFilter '$[1:]' and JoinSource 'Input'."""
    lines = input_csv.splitlines()
    features = "\n".join(line.split(",", 1)[1] for line in lines)
    out = inference.output_fn(inference.predict_fn(inference.input_fn(features, "text/csv"), model), "text/csv")
    return "\n".join(f"{i},{o}" for i, o in zip(lines, out.strip().split("\n")))


def test_batch_scoring_end_to_end_locally(model_dir):
    input_csv, truth = batch_score.make_batch()
    output = imitate_batch_transform(input_csv, inference.model_fn(model_dir))
    result = batch_score.summarise(output, truth)
    assert result["rows_out"] == 200 and not result["missing"]
    assert result["accuracy"] >= batch_score.MIN_BATCH_ACCURACY


def test_summary_reports_mistakes_and_missing_rows():
    truth = {"BRG-0001": "healthy", "BRG-0002": "ball_fault", "BRG-0003": "healthy"}
    output = ("BRG-0001,0.3,3,3.5,30,30,healthy,0.98\n"
              "BRG-0002,0.5,4.6,4.6,72,30,outer_race_fault,0.55\n")
    result = batch_score.summarise(output, truth)
    assert result["accuracy"] == 0.5
    assert result["missing"] == ["BRG-0003"]
    assert result["mistakes"] == [("BRG-0002", "ball_fault", "outer_race_fault", 0.55)]


def test_unexpected_output_shape_is_an_error():
    with pytest.raises(ValueError):
        batch_score.summarise("BRG-0001,healthy,0.9\n", {"BRG-0001": "healthy"})


def test_missing_setting_stops_with_a_hint(monkeypatch):
    monkeypatch.delenv("BUCKET", raising=False)
    with pytest.raises(SystemExit, match="Run 'apply' first"):
        common.setting("BUCKET")
