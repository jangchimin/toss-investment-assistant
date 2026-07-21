import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"

sys.path.insert(
    0,
    str(SRC_PATH),
)

from portfolio import PortfolioAnalyzer


def test_detects_high_concentration():
    """단일 종목 또는 상위 종목 비중이 높으면 경고한다."""

    holdings = [
        {
            "symbol": "AAA",
            "name": "테스트 종목 A",
            "market_country": "US",
            "currency": "USD",
            "quantity": 5,
            "average_purchase_price": 100,
            "last_price": 100,
            "purchase_amount": 500,
            "market_value": 500,
            "profit_loss_amount": 0,
            "profit_loss_rate": 0,
            "daily_profit_loss_amount": 0,
            "daily_profit_loss_rate": 0,
        },
        {
            "symbol": "BBB",
            "name": "테스트 종목 B",
            "market_country": "US",
            "currency": "USD",
            "quantity": 3,
            "average_purchase_price": 100,
            "last_price": 100,
            "purchase_amount": 300,
            "market_value": 300,
            "profit_loss_amount": 0,
            "profit_loss_rate": 0,
            "daily_profit_loss_amount": 0,
            "daily_profit_loss_rate": 0,
        },
        {
            "symbol": "CCC",
            "name": "테스트 종목 C",
            "market_country": "US",
            "currency": "USD",
            "quantity": 2,
            "average_purchase_price": 100,
            "last_price": 100,
            "purchase_amount": 200,
            "market_value": 200,
            "profit_loss_amount": 0,
            "profit_loss_rate": 0,
            "daily_profit_loss_amount": 0,
            "daily_profit_loss_rate": 0,
        },
    ]

    analyzer = PortfolioAnalyzer()

    result = analyzer.analyze(holdings)

    concentration = result[
        "concentration_by_currency"
    ]["USD"]

    assert concentration["level"] == "high"

    assert concentration[
        "largest_position"
    ]["symbol"] == "AAA"

    assert concentration[
        "largest_position"
    ]["weight_percent"] == pytest.approx(50)

    assert concentration[
        "top_3_weight_percent"
    ] == pytest.approx(100)

    assert concentration["warnings"]
    
def test_skips_concentration_for_small_krw_portfolio():
    """10만원 미만의 KRW 포트폴리오는 집중도 판정에서 제외한다."""

    holdings = [
        {
            "symbol": "AAA",
            "name": "소액 테스트 종목 A",
            "market_country": "KR",
            "currency": "KRW",
            "market_value": 40000,
        },
        {
            "symbol": "BBB",
            "name": "소액 테스트 종목 B",
            "market_country": "KR",
            "currency": "KRW",
            "market_value": 10000,
        },
    ]

    analyzer = PortfolioAnalyzer()

    result = analyzer.analyze(holdings)

    concentration = result[
        "concentration_by_currency"
    ]["KRW"]

    assert (
        concentration["level"]
        == "not_applicable"
    )

    assert concentration[
        "total_market_value"
    ] == pytest.approx(50000)

    assert concentration[
        "minimum_market_value"
    ] == pytest.approx(100000)

    assert concentration["warnings"] == []