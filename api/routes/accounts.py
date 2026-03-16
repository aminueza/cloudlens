from fastapi import APIRouter, Request

from api.models import AccountListResponse

router = APIRouter(tags=["accounts"])


@router.get("/api/accounts", response_model=AccountListResponse)
async def list_accounts(request: Request) -> AccountListResponse:
    fetcher = request.app.state.fetcher
    products = fetcher.get_discovered_products()
    return AccountListResponse(accounts=products)
