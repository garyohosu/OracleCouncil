import threading

import pytest

from oracle_council.budget import (
    BudgetError,
    BudgetExceededError,
    InvalidReservationTransition,
    TokenBudget,
)
from oracle_council.models import BudgetRequest, ReservationStatus, Usage


def request(execution_id="exec-1", input_tokens=100, output_tokens=20):
    return BudgetRequest("run-1", execution_id, "respond", input_tokens, output_tokens)


def test_reserve_commit_lifecycle():
    budget = TokenBudget(input_limit=1000, output_limit=200)
    reservation = budget.reserve(request())
    assert reservation.status is ReservationStatus.RESERVED

    committed = budget.commit(reservation.reservation_id, Usage(90, 15))
    assert committed.status is ReservationStatus.COMMITTED
    assert committed.actual_input_tokens == 90

    snapshot = budget.snapshot()
    assert snapshot.committed_call_count == 1
    assert snapshot.reserved_call_count == 0
    # Budget accounting keeps using the conservative estimate, not the actual.
    assert snapshot.committed_input_tokens == 100


def test_release_returns_capacity():
    budget = TokenBudget(input_limit=100, output_limit=20)
    reservation = budget.reserve(request())
    with pytest.raises(BudgetExceededError):
        budget.reserve(request("exec-2"))
    budget.release(reservation.reservation_id)
    budget.commit(budget.reserve(request("exec-2")).reservation_id, None)


def test_released_reservation_cannot_be_committed():
    budget = TokenBudget(input_limit=1000, output_limit=200)
    reservation = budget.reserve(request())
    budget.release(reservation.reservation_id)
    with pytest.raises(InvalidReservationTransition):
        budget.commit(reservation.reservation_id, None)


def test_call_limit_rejects_thirteenth_call():
    budget = TokenBudget(input_limit=10**6, output_limit=10**6, call_limit=12)
    for i in range(12):
        budget.commit(budget.reserve(request(f"exec-{i}")).reservation_id, None)
    with pytest.raises(BudgetExceededError):
        budget.reserve(request("exec-13"))


def test_retry_uses_separate_reservation_without_double_count():
    budget = TokenBudget(input_limit=250, output_limit=100)
    first = budget.reserve(request("exec-1"))
    budget.commit(first.reservation_id, None)  # failed execution still consumed
    retry = budget.reserve(request("exec-1-retry"))
    budget.commit(retry.reservation_id, Usage(80, 10))
    snapshot = budget.snapshot()
    assert snapshot.committed_call_count == 2
    assert snapshot.committed_input_tokens == 200


def test_parallel_reserve_never_oversubscribes():
    budget = TokenBudget(input_limit=1000, output_limit=1000, call_limit=10)
    granted = []

    def worker(i):
        try:
            granted.append(budget.reserve(request(f"exec-{i}")))
        except BudgetExceededError:
            pass

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(granted) == 10
    assert budget.snapshot().reserved_call_count == 10


def test_assert_settled_raises_on_dangling_reservation():
    budget = TokenBudget(input_limit=1000, output_limit=200)
    budget.reserve(request())
    with pytest.raises(BudgetError):
        budget.assert_settled()
