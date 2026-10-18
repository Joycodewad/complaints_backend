import enum


class Role(str, enum.Enum):
    STUDENT = "STUDENT"
    ADMIN = "ADMIN"
    COORDINATOR = "COORDINATOR"


class Status(str, enum.Enum):
    SUBMITTED = "SUBMITTED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class Priority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"
