import json
import os

import pytest

import train


def test_writes_model_and_metrics(model_dir):
    assert sorted(os.listdir(model_dir)) == ["metrics.json", "model.joblib"]


def test_metrics_content(model_dir):
    metrics = json.load(open(os.path.join(model_dir, "metrics.json")))
    assert metrics["accuracy"] > 0.9
    assert set(metrics["recall_per_class"]) == {"healthy", "inner_race_fault", "outer_race_fault", "ball_fault"}
    assert metrics["test_rows"] == 400
    assert metrics["hyperparameters"]["n_estimators"] == 60
    assert len(metrics["confusion_matrix"]["rows"]) == 4


def test_prints_line_sagemaker_graphs(channels, tmp_path, capsys):
    train.main(["--train", str(channels / "input/data/train"), "--test", str(channels / "input/data/test"),
                "--model-dir", str(tmp_path), "--n-estimators", "10"])
    out = capsys.readouterr().out
    assert "test_accuracy=" in out and "min_recall=" in out


def test_reads_a_folder_or_a_file(channels):
    X, y = train.read_csv(str(channels / "input/data/test"))
    X2, _ = train.read_csv(str(channels / "input/data/test/test.csv"))
    assert X.shape == (400, 5) and len(y) == 400 and (X == X2).all()


def test_missing_column_is_a_clear_error(tmp_path):
    (tmp_path / "bad.csv").write_text("condition,rms\nhealthy,0.3\n")
    with pytest.raises(ValueError, match="missing columns"):
        train.read_csv(str(tmp_path))


def test_empty_folder_is_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        train.read_csv(str(tmp_path))


def test_hyperparameters_from_sagemaker_and_unknown_args_ignored():
    args = train.parse_args(["--n-estimators", "75", "--max-depth", "8", "--something-new", "x"])
    assert args.n_estimators == 75 and args.max_depth == 8
