"""Ranking helpers for detected depressions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from karstlab.data.schemas import DepressionResult

DEFAULT_RANK_LIMIT = 25


@dataclass(frozen=True)
class DepressionRanker:
    """Rank depressions by detection importance without mutating inputs."""

    limit: int = DEFAULT_RANK_LIMIT

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("rank limit must be at least 1")

    def rank(self, depressions: Sequence[DepressionResult]) -> list[DepressionResult]:
        return rank_depressions(depressions, limit=self.limit)


def rank_depressions(
    depressions: Sequence[DepressionResult],
    *,
    limit: int = DEFAULT_RANK_LIMIT,
) -> list[DepressionResult]:
    """Return the top ranked depressions with sequential rank values."""
    if limit < 1:
        raise ValueError("rank limit must be at least 1")

    ordered = sorted(
        depressions,
        key=lambda depression: (
            -depression.max_depth_m,
            -depression.area_m2,
            depression.id,
        ),
    )
    return [
        depression.model_copy(update={"rank": rank})
        for rank, depression in enumerate(ordered[:limit], start=1)
    ]


__all__ = ["DEFAULT_RANK_LIMIT", "DepressionRanker", "rank_depressions"]
