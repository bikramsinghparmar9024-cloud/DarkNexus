"""
Proxy Pool Management & Rotation Endpoints.
"""

from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel
from proxy.pool import proxy_pool
from proxy.validator import validate_proxy
from auth.rbac import require_admin

router = APIRouter(
    prefix="/api/proxies", tags=["Proxy Management"],
    # Every endpoint on this router requires authentication.
    dependencies=[Depends(require_admin)],
)


class AddProxyRequest(BaseModel):
    proxy_url: str  # e.g. http://1.2.3.4:8080 or socks5://1.2.3.4:1080


@router.get("/pool")
async def get_proxy_pool_status():
    """Retrieve full proxy pool metrics and rotation status."""
    return proxy_pool.get_stats()


@router.post("/refresh")
async def refresh_proxy_pool(background_tasks: BackgroundTasks):
    """Trigger background refresh and validation of public proxy pools."""
    background_tasks.add_task(proxy_pool.initialize)
    return {"message": "Proxy pool refresh task scheduled in background"}


@router.post("/test")
async def test_single_proxy(req: AddProxyRequest):
    """Test connection and latency of an arbitrary proxy server."""
    is_alive, latency_ms, detail = await validate_proxy(req.proxy_url)
    return {
        "proxy": req.proxy_url,
        "is_alive": is_alive,
        "latency_ms": latency_ms,
        "detail": detail
    }
