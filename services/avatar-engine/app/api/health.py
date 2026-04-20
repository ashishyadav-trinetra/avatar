"""Health check endpoint."""
from fastapi import APIRouter
from pydantic import BaseModel
import torch

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    device: str
    gpu_name: str | None
    vram_free_gb: float | None
    active_sessions: int


@router.get("/health", response_model=HealthResponse)
async def health(request=None):
    from fastapi import Request
    gpu_name = None
    vram_free = None
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        free, total = torch.cuda.mem_get_info(0)
        vram_free = round(free / 1e9, 2)

    sessions = 0
    # request may be None in direct health-check calls
    return HealthResponse(
        status="ok",
        device="cuda" if torch.cuda.is_available() else "cpu",
        gpu_name=gpu_name,
        vram_free_gb=vram_free,
        active_sessions=sessions,
    )
