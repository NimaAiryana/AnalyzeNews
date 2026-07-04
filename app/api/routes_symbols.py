"""Symbol CRUD endpoints - the dynamic list of coins the engine accepts."""

from fastapi import APIRouter, HTTPException, status

from app.schemas.requests import AddSymbolRequest, UpdateSymbolRequest
from app.schemas.responses import SymbolResponse
from app.services import symbol_service
from app.services.symbol_service import SymbolAlreadyExistsError, SymbolNotFoundError

router = APIRouter(prefix="/api/v1/symbols", tags=["symbols"])


def _to_response(doc: dict) -> SymbolResponse:
    return SymbolResponse(
        symbol=doc["symbol"],
        name=doc["name"],
        aliases=doc.get("aliases", []),
        enabled=doc.get("enabled", True),
        created_at=doc.get("created_at"),
    )


@router.post("", response_model=SymbolResponse, status_code=status.HTTP_201_CREATED)
async def create_symbol(body: AddSymbolRequest):
    try:
        doc = await symbol_service.add_symbol(body.symbol, body.name, body.aliases, body.enabled)
    except SymbolAlreadyExistsError:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Symbol '{body.symbol}' already exists")
    return _to_response(doc)


@router.get("", response_model=list[SymbolResponse])
async def get_symbols():
    return [_to_response(d) for d in await symbol_service.list_symbols()]


@router.get("/{symbol}", response_model=SymbolResponse)
async def get_one_symbol(symbol: str):
    try:
        return _to_response(await symbol_service.get_symbol(symbol))
    except SymbolNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Symbol '{symbol}' not found")


@router.patch("/{symbol}", response_model=SymbolResponse)
async def patch_symbol(symbol: str, body: UpdateSymbolRequest):
    try:
        doc = await symbol_service.update_symbol(symbol, body.model_dump(exclude_unset=True))
    except SymbolNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Symbol '{symbol}' not found")
    return _to_response(doc)


@router.delete("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_symbol(symbol: str):
    try:
        await symbol_service.delete_symbol(symbol)
    except SymbolNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Symbol '{symbol}' not found")
