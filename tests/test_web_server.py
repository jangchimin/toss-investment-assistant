import sys
from pathlib import Path

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"

sys.path.insert(
    0,
    str(SRC_PATH),
)

import web_server


client = TestClient(web_server.app)


def test_health_endpoint():
    """서버 상태 확인 API가 정상 응답하는지 검사한다."""

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
    }


def test_portfolio_analysis_endpoint(
    monkeypatch,
):
    """포트폴리오 분석 API가 분석 결과를 반환하는지 검사한다."""

    expected_result = {
        "summary_by_currency": {
            "USD": {
                "total_purchase_amount": 1000,
                "total_market_value": 1100,
                "total_profit_loss_amount": 100,
                "total_profit_loss_rate": 0.1,
                "total_daily_profit_loss_amount": 10,
            }
        },
        "positions": [
            {
                "symbol": "TEST",
                "currency": "USD",
                "weight": 1.0,
                "weight_percent": 100.0,
            }
        ],
    }

    def fake_get_portfolio_analysis():
        return expected_result

    monkeypatch.setattr(
        web_server,
        "get_portfolio_analysis",
        fake_get_portfolio_analysis,
    )

    response = client.get(
        "/portfolio/analysis"
    )

    assert response.status_code == 200
    assert response.json() == expected_result


def test_portfolio_analysis_handles_error(
    monkeypatch,
):
    """분석 중 오류가 발생하면 500 응답을 반환하는지 검사한다."""

    def fake_get_portfolio_analysis():
        raise RuntimeError(
            "테스트용 포트폴리오 분석 오류"
        )

    monkeypatch.setattr(
        web_server,
        "get_portfolio_analysis",
        fake_get_portfolio_analysis,
    )

    response = client.get(
        "/portfolio/analysis"
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "테스트용 포트폴리오 분석 오류",
    }