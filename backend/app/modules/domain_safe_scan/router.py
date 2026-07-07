from fastapi import APIRouter, HTTPException
from app.modules.domain_safe_scan.schemas import DomainSafeScanRequest, DomainSafeScanResponse
from app.modules.domain_safe_scan.services import DomainSafeScanService

router = APIRouter(prefix="/domain-safe-scan", tags=["domain-safe-scan"])
service = DomainSafeScanService()

@router.post("/analyze", response_model=DomainSafeScanResponse)
async def analyze_domain(request: DomainSafeScanRequest):
    try:
        return await service.analyze(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
