from __future__ import annotations

import pytest

from karstlab.business.depression_ranker import DepressionRanker, rank_depressions
from karstlab.data.schemas import DepressionResult


def depression(
    depression_id: str,
    *,
    max_depth_m: float,
    area_m2: float,
    rank: int | None = None,
) -> DepressionResult:
    return DepressionResult.model_validate(
        {
            "id": depression_id,
            "rank": rank,
            "max_depth_m": max_depth_m,
            "area_m2": area_m2,
            "centroid": {"lat": 44.1, "lon": 1.2},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [1.19, 44.09],
                        [1.21, 44.09],
                        [1.21, 44.11],
                        [1.19, 44.11],
                        [1.19, 44.09],
                    ]
                ],
            },
        }
    )


def test_rank_depressions_returns_top_25_from_50() -> None:
    depressions = [
        depression(f"doline-{index:02d}", max_depth_m=float(index), area_m2=100.0)
        for index in range(50)
    ]

    ranked = rank_depressions(depressions)

    assert len(ranked) == 25
    assert [item.id for item in ranked[:3]] == ["doline-49", "doline-48", "doline-47"]
    assert ranked[-1].id == "doline-25"


def test_rank_depressions_assigns_sequential_ranks() -> None:
    depressions = [
        depression("c", max_depth_m=1.0, area_m2=10.0),
        depression("a", max_depth_m=3.0, area_m2=10.0),
        depression("b", max_depth_m=2.0, area_m2=10.0),
    ]

    ranked = rank_depressions(depressions)

    assert [item.rank for item in ranked] == [1, 2, 3]
    assert [item.id for item in ranked] == ["a", "b", "c"]


def test_rank_depressions_does_not_mutate_inputs() -> None:
    original = depression("already-ranked", max_depth_m=10.0, area_m2=50.0, rank=7)

    ranked = rank_depressions([original])

    assert original.rank == 7
    assert ranked[0].rank == 1
    assert ranked[0] is not original


def test_rank_depressions_uses_deterministic_tie_breaks() -> None:
    depressions = [
        depression("c", max_depth_m=5.0, area_m2=20.0),
        depression("a", max_depth_m=5.0, area_m2=20.0),
        depression("b", max_depth_m=5.0, area_m2=30.0),
        depression("d", max_depth_m=6.0, area_m2=1.0),
    ]

    ranked = rank_depressions(depressions, limit=4)

    assert [item.id for item in ranked] == ["d", "b", "a", "c"]


def test_depression_ranker_uses_configured_limit() -> None:
    depressions = [
        depression(f"doline-{index}", max_depth_m=float(index), area_m2=100.0)
        for index in range(5)
    ]

    ranked = DepressionRanker(limit=2).rank(depressions)

    assert [item.id for item in ranked] == ["doline-4", "doline-3"]
    assert [item.rank for item in ranked] == [1, 2]


def test_rank_depressions_rejects_invalid_limit() -> None:
    with pytest.raises(ValueError, match="rank limit"):
        rank_depressions([], limit=0)

    with pytest.raises(ValueError, match="rank limit"):
        DepressionRanker(limit=0)
