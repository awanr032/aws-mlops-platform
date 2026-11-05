import json
import os
import sys

import pytest

HERE = os.path.dirname(__file__)
PROJECT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(PROJECT, "pipeline"))
sys.path.insert(0, os.path.join(PROJECT, "etl"))

COLUMNS = json.load(open(os.path.join(PROJECT, "schema", "raw_columns.json")))["columns"]

TYPICAL = {
    "cmplid": "1834001", "odino": "11500001", "mfr_name": "Ford Motor Company", "maketxt": "ford",
    "modeltxt": "Focus", "yeartxt": "2019", "crash": "N", "faildate": "20230105", "fire": "N",
    "injured": "0", "deaths": "0", "compdesc": "ENGINE AND ENGINE COOLING:ENGINE", "city": "AUSTIN",
    "state": "TX", "ldate": "20230110", "miles": "64000", "cdescr": 'ENGINE STALLED ON "HIGHWAY".',
    "cmpl_type": "EVOQ", "police_rpt_yn": "N", "medical_attn": "N", "vehicles_towed_yn": "Y",
    "prod_type": "V", "veh_speed": "65",
}


def make_line(fields: int = 51, **overrides) -> str:
    """One tab-separated line in NHTSA's field order (fields=49 imitates older rows)."""
    values = {**TYPICAL, **overrides}
    return "\t".join(values.get(c, "") for c in COLUMNS[:fields])


@pytest.fixture
def columns():
    return COLUMNS
