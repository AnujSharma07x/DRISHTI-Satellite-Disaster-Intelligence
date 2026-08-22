"""
tests/fakes.py — minimal DB-API-style test doubles for impact.py.

These deliberately implement only what impact.py actually calls
(cursor(), execute(), fetchone(), fetchall(), commit(), rollback(), and the
cursor context-manager protocol) — enough to unit-test the query-building
and control-flow logic in impact.py without a live Supabase/Postgres
connection, per the review's requirement that impact.py tests not need a
real database.
"""

from typing import Any, List, Optional, Sequence, Tuple


class FakeCursor:
    """
    Records every executed query/params pair, and returns pre-scripted
    results from fetchone()/fetchall() in call order.

    `fetchone_results` / `fetchall_results` are queues: each call pops the
    next scripted return value. This mirrors how impact.py issues a small,
    deterministic sequence of queries per function, so tests can assert on
    both "what was asked" (executed_queries) and "what came back" (the
    scripted results) independently.
    """

    def __init__(
        self,
        fetchone_results: Optional[Sequence[Optional[Tuple[Any, ...]]]] = None,
        fetchall_results: Optional[Sequence[Sequence[Tuple[Any, ...]]]] = None,
        raise_on_execute: Optional[BaseException] = None,
    ):
        self._fetchone_results: List[Optional[Tuple[Any, ...]]] = list(fetchone_results or [])
        self._fetchall_results: List[Sequence[Tuple[Any, ...]]] = list(fetchall_results or [])
        self.raise_on_execute = raise_on_execute
        self.executed_queries: List[Tuple[str, Optional[tuple]]] = []

    def execute(self, query: str, params: Optional[tuple] = None) -> None:
        self.executed_queries.append((query, params))
        if self.raise_on_execute is not None:
            raise self.raise_on_execute

    def fetchone(self) -> Optional[Tuple[Any, ...]]:
        if self._fetchone_results:
            return self._fetchone_results.pop(0)
        return None

    def fetchall(self) -> Sequence[Tuple[Any, ...]]:
        if self._fetchall_results:
            return self._fetchall_results.pop(0)
        return []

    # DB-API cursors used as `with conn.cursor() as cur:` need the context
    # manager protocol; a real psycopg2 cursor closes itself on exit, which
    # we don't need to simulate for these unit tests.
    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        return False


class FakeConnection:
    """
    Fake connection that always hands back the same FakeCursor instance —
    intentional, so a test can inspect every query issued across an entire
    impact.py call (which may open the "cursor" more than once internally,
    e.g. calculate_buildings_affected() calling buildings_table_exists())
    from one place: `cursor.executed_queries`.
    """

    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True
