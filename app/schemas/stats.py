from pydantic import BaseModel


class StatusCounts(BaseModel):
    total: int
    by_status: dict[str, int]


class StatsOut(BaseModel):
    total: int
    by_status: dict[str, int]
    by_category: dict[str, int]
    unassigned: int
    avg_resolution_hours: float | None
