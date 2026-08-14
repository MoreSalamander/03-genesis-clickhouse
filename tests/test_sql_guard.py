"""SELECT-only enforcement (locked §2.3: read permission, enforced in code)."""
import pytest

from app.governance.sql_guard import SQLRejected, ensure_select_only


def test_select_passes():
    assert ensure_select_only("SELECT 1").startswith("SELECT")


def test_with_cte_passes():
    assert ensure_select_only("WITH x AS (SELECT 1) SELECT * FROM x")


def test_trailing_semicolon_stripped():
    assert not ensure_select_only("SELECT 1;").endswith(";")


@pytest.mark.parametrize("sql", [
    "DROP TABLE genesis_institutional.projects",
    "INSERT INTO t VALUES (1)",
    "SELECT 1; DROP TABLE t",
    "ALTER TABLE t DELETE WHERE 1",
    "CREATE TABLE t (x Int8) ENGINE = Memory",
    "TRUNCATE TABLE t",
    "",
])
def test_writes_rejected(sql):
    with pytest.raises(SQLRejected):
        ensure_select_only(sql)


def test_comment_smuggling_rejected():
    with pytest.raises(SQLRejected):
        ensure_select_only("SELECT 1 /* */ ; INSERT INTO t VALUES (1)")
