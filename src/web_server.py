from fastapi import FastAPI, HTTPException

from service import get_holding, get_portfolio


app = FastAPI(
    title="Toss Investment Assistant API",
    description=(
        "토스증권 계좌와 보유 종목을 조회하는 "
        "읽기 전용 REST API"
    ),
    version="0.1.0",
)


@app.get("/")
def read_root() -> dict:
    """서버의 실행 상태를 확인한다."""

    return {
        "service": "Toss Investment Assistant API",
        "status": "running",
        "read_only": True,
    }


@app.get("/health")
def read_health() -> dict:
    """서버 상태 확인용 엔드포인트."""

    return {
        "status": "ok",
    }


@app.get("/portfolio")
def read_portfolio() -> dict:
    """전체 자산 요약과 보유 종목을 조회한다."""

    try:
        return get_portfolio()
    except RuntimeError as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error


@app.get("/holdings/{symbol}")
def read_holding(symbol: str) -> dict:
    """특정 티커 또는 종목 심벌을 조회한다."""

    try:
        holding = get_holding(symbol)
    except RuntimeError as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error

    if holding is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"{symbol.upper()} 종목을 "
                "현재 보유하고 있지 않습니다."
            ),
        )

    return holding