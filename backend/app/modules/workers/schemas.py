"""Pydantic response models for workers and dispatch queues."""

from pydantic import BaseModel, ConfigDict


class WorkerStateResponse(BaseModel):
    """Derived worker state for one in-flight or recently-finished execution."""

    model_config = ConfigDict(from_attributes=False)

    worker_id: str
    region: str
    state: str  # "running" | "idle" | "finished"
    current_execution_id: str | None
    last_heartbeat: str | None


class DispatchQueueResponse(BaseModel):
    """Derived dispatch queue metrics based on current execution statuses."""

    model_config = ConfigDict(from_attributes=False)

    queue_name: str
    routing_key: str
    broker_status: str
    pending: int
    active: int
    failed: int
