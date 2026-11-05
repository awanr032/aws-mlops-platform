import pytest

import athena


class FakeAthena:
    def __init__(self, state="SUCCEEDED", statement="DML", rows=None, scanned=2_500_000):
        self.state, self.statement, self.scanned = state, statement, scanned
        self.rows = rows or [["component_group", "complaints"], ["ENGINE", "120"], ["AIR BAGS", "45"]]
        self.polls = 0

    def start_query_execution(self, QueryString, WorkGroup):
        self.sql, self.workgroup = QueryString, WorkGroup
        return {"QueryExecutionId": "q-1"}

    def get_query_execution(self, QueryExecutionId):
        self.polls += 1
        state = "RUNNING" if self.polls < 3 else self.state
        return {"QueryExecution": {"Status": {"State": state, "StateChangeReason": "SYNTAX_ERROR: line 1"},
                                   "StatementType": self.statement,
                                   "Statistics": {"DataScannedInBytes": self.scanned,
                                                  "EngineExecutionTimeInMillis": 900}}}

    def get_paginator(self, name):
        rows = self.rows

        class Pages:
            def paginate(self, QueryExecutionId):
                return [{"ResultSet": {"ResultSetMetadata": {"ColumnInfo": [{"Name": "component_group"},
                                                                             {"Name": "complaints"}]},
                                       "Rows": [{"Data": [{"VarCharValue": v} for v in r]} for r in rows]}}]
        return Pages()


def test_successful_select_waits_and_strips_header_row():
    fake = FakeAthena()
    result = athena.run("SELECT 1", athena=fake, workgroup="wg", sleep=lambda s: None)
    assert fake.polls == 3 and fake.workgroup == "wg"
    assert result["columns"] == ["component_group", "complaints"]
    assert result["rows"] == [["ENGINE", "120"], ["AIR BAGS", "45"]]
    assert result["scanned_bytes"] == 2_500_000
    assert result["cost_usd"] == pytest.approx(2.5e6 / 1e12 * 5)


def test_ddl_returns_no_rows():
    result = athena.run("DROP TABLE x", athena=FakeAthena(statement="DDL"), workgroup="wg", sleep=lambda s: None)
    assert result["rows"] == [] and result["columns"] == []


def test_failure_raises_with_reason_and_sql():
    with pytest.raises(athena.QueryFailed, match="SYNTAX_ERROR"):
        athena.run("SELEC 1", athena=FakeAthena(state="FAILED"), workgroup="wg", sleep=lambda s: None)


def test_formatting_helpers():
    assert athena.human_bytes(512) == "512 B"
    assert athena.human_bytes(2_500_000) == "2.5 MB"
    assert athena.human_bytes(1.2e9) == "1.2 GB"
    text = athena.table({"columns": ["a", "bb"], "rows": [["1", None], ["22", "x"]]})
    assert text.splitlines()[0] == "a   bb" and text.splitlines()[2] == "1     "
