from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from .models import (
    BudgetRequest,
    BudgetReservation,
    BudgetSnapshot,
    ReservationStatus,
    Usage,
)


class BudgetError(RuntimeError):
    pass


class BudgetExceededError(BudgetError):
    pass


class ReservationNotFound(BudgetError):
    pass


class InvalidReservationTransition(BudgetError):
    pass


class TokenBudget:
    def __init__(self, input_limit: int, output_limit: int, call_limit: int = 12) -> None:
        self._input_limit = input_limit
        self._output_limit = output_limit
        self._call_limit = call_limit
        self._reservations: dict[str, BudgetReservation] = {}
        self._lock = RLock()

    def reserve(self, request: BudgetRequest) -> BudgetReservation:
        if request.estimated_input_tokens < 0 or request.estimated_output_tokens < 0:
            raise ValueError("estimated token counts must be non-negative")
        with self._lock:
            snapshot = self._snapshot_unlocked()
            if (
                snapshot.reserved_input_tokens
                + snapshot.committed_input_tokens
                + request.estimated_input_tokens
                > self._input_limit
                or snapshot.reserved_output_tokens
                + snapshot.committed_output_tokens
                + request.estimated_output_tokens
                > self._output_limit
                or snapshot.reserved_call_count + snapshot.committed_call_count + 1
                > self._call_limit
            ):
                raise BudgetExceededError("BUDGET_EXCEEDED")
            reservation = BudgetReservation(
                reservation_id=str(uuid4()),
                run_id=request.run_id,
                execution_id=request.execution_id,
                phase=request.phase,
                estimated_input_tokens=request.estimated_input_tokens,
                estimated_output_tokens=request.estimated_output_tokens,
            )
            self._reservations[reservation.reservation_id] = reservation
            return replace(reservation)

    def commit(self, reservation_id: str, actual_usage: Usage | None) -> BudgetReservation:
        with self._lock:
            reservation = self._get(reservation_id)
            if reservation.status is ReservationStatus.COMMITTED:
                return replace(reservation)
            if reservation.status is ReservationStatus.RELEASED:
                raise InvalidReservationTransition("released reservation cannot be committed")
            reservation.status = ReservationStatus.COMMITTED
            if actual_usage is not None:
                reservation.actual_input_tokens = actual_usage.input_tokens
                reservation.actual_output_tokens = actual_usage.output_tokens
            reservation.finished_at = datetime.now(timezone.utc)
            return replace(reservation)

    def release(self, reservation_id: str) -> BudgetReservation:
        with self._lock:
            reservation = self._get(reservation_id)
            if reservation.status is ReservationStatus.RELEASED:
                return replace(reservation)
            if reservation.status is ReservationStatus.COMMITTED:
                raise InvalidReservationTransition("committed reservation cannot be released")
            reservation.status = ReservationStatus.RELEASED
            reservation.finished_at = datetime.now(timezone.utc)
            return replace(reservation)

    def snapshot(self) -> BudgetSnapshot:
        with self._lock:
            return self._snapshot_unlocked()

    def assert_settled(self) -> None:
        with self._lock:
            if any(r.status is ReservationStatus.RESERVED for r in self._reservations.values()):
                raise BudgetError("Run ended with reserved budget")

    def _get(self, reservation_id: str) -> BudgetReservation:
        try:
            return self._reservations[reservation_id]
        except KeyError as exc:
            raise ReservationNotFound(reservation_id) from exc

    def _snapshot_unlocked(self) -> BudgetSnapshot:
        reserved = [r for r in self._reservations.values() if r.status is ReservationStatus.RESERVED]
        committed = [r for r in self._reservations.values() if r.status is ReservationStatus.COMMITTED]
        return BudgetSnapshot(
            reserved_input_tokens=sum(r.estimated_input_tokens for r in reserved),
            committed_input_tokens=sum(r.estimated_input_tokens for r in committed),
            reserved_output_tokens=sum(r.estimated_output_tokens for r in reserved),
            committed_output_tokens=sum(r.estimated_output_tokens for r in committed),
            reserved_call_count=sum(r.reserved_call_count for r in reserved),
            committed_call_count=sum(r.reserved_call_count for r in committed),
        )
