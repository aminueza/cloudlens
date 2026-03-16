from fastapi import APIRouter

from api.models import AccountListResponse
from config.settings import PRODUCTS

router = APIRouter(tags=["accounts"])


@router.get("/api/accounts", response_model=AccountListResponse)
async def list_accounts():
    return {"accounts": PRODUCTS}
