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


def test_empty_holdings_returns_empty_result():
    """보유 종목이 없으면 빈 분석 결과를 반환한다."""

    analyzer = PortfolioAnalyzer()

    result = analyzer.analyze([])

    assert result == {
        "summary_by_currency": {},
        "positions": [],
    }


def test_calculates_profit_and_weight():
    """동일 통화 종목의 손익과 비중을 계산한다."""

    holdings = [
        {
            "symbol": "AAA",
            "name": "테스트 종목 A",
            "market_country": "US",
            "currency": "USD",
            "quantity": 6,
            "average_purchase_price": 100,
            "last_price": 100,
            "purchase_amount": 500,
            "market_value": 600,
            "profit_loss_amount": 100,
            "profit_loss_rate": 0.2,
            "daily_profit_loss_amount": 10,
            "daily_profit_loss_rate": 0.01,
        },
        {
            "symbol": "BBB",
            "name": "테스트 종목 B",
            "market_country": "US",
            "currency": "USD",
            "quantity": 4,
            "average_purchase_price": 125,
            "last_price": 100,
            "purchase_amount": 500,
            "market_value": 400,
            "profit_loss_amount": -100,
            "profit_loss_rate": -0.2,
            "daily_profit_loss_amount": -5,
            "daily_profit_loss_rate": -0.01,
        },
    ]

    analyzer = PortfolioAnalyzer()

    result = analyzer.analyze(holdings)

    usd_summary = result[
        "summary_by_currency"
    ]["USD"]

    assert usd_summary[
        "total_purchase_amount"
    ] == pytest.approx(1000)

    assert usd_summary[
        "total_market_value"
    ] == pytest.approx(1000)

    assert usd_summary[
        "total_profit_loss_amount"
    ] == pytest.approx(0)

    assert usd_summary[
        "total_profit_loss_rate"
    ] == pytest.approx(0)

    assert usd_summary[
        "total_daily_profit_loss_amount"
    ] == pytest.approx(5)

    positions = result["positions"]

    assert positions[0]["symbol"] == "AAA"
    assert positions[0]["weight"] == pytest.approx(0.6)
    assert positions[0]["weight_percent"] == pytest.approx(60)

    assert positions[1]["symbol"] == "BBB"
    assert positions[1]["weight"] == pytest.approx(0.4)
    assert positions[1]["weight_percent"] == pytest.approx(40)


def test_separates_krw_and_usd():
    """원화와 달러 종목을 서로 합산하지 않는다."""

    holdings = [
        {
            "symbol": "005930",
            "name": "삼성전자",
            "market_country": "KR",
            "currency": "KRW",
            "quantity": 1,
            "average_purchase_price": 70000,
            "last_price": 75000,
            "purchase_amount": 70000,
            "market_value": 75000,
            "profit_loss_amount": 5000,
            "profit_loss_rate": 0.0714,
            "daily_profit_loss_amount": 1000,
            "daily_profit_loss_rate": 0.0135,
        },
        {
            "symbol": "TEST",
            "name": "미국 테스트 종목",
            "market_country": "US",
            "currency": "USD",
            "quantity": 1,
            "average_purchase_price": 100,
            "last_price": 110,
            "purchase_amount": 100,
            "market_value": 110,
            "profit_loss_amount": 10,
            "profit_loss_rate": 0.1,
            "daily_profit_loss_amount": 2,
            "daily_profit_loss_rate": 0.02,
        },
    ]

    analyzer = PortfolioAnalyzer()

    result = analyzer.analyze(holdings)

    assert set(
        result["summary_by_currency"]
    ) == {"KRW", "USD"}

    krw_summary = result[
        "summary_by_currency"
    ]["KRW"]

    usd_summary = result[
        "summary_by_currency"
    ]["USD"]

    assert krw_summary[
        "total_market_value"
    ] == pytest.approx(75000)

    assert usd_summary[
        "total_market_value"
    ] == pytest.approx(110)

    krw_position = next(
        position
        for position in result["positions"]
        if position["currency"] == "KRW"
    )

    usd_position = next(
        position
        for position in result["positions"]
        if position["currency"] == "USD"
    )

    assert krw_position[
        "weight_percent"
    ] == pytest.approx(100)

    assert usd_position[
        "weight_percent"
    ] == pytest.approx(100)


def test_handles_missing_and_invalid_numbers():
    """누락되거나 잘못된 숫자가 있어도 중단되지 않는다."""

    holdings = [
        {
            "symbol": "ERROR",
            "name": "오류 테스트 종목",
            "market_country": "US",
            "currency": "USD",
            "quantity": None,
            "average_purchase_price": "",
            "last_price": "숫자 아님",
            "purchase_amount": None,
            "market_value": "",
            "profit_loss_amount": "잘못된 값",
            "profit_loss_rate": None,
            "daily_profit_loss_amount": None,
            "daily_profit_loss_rate": "",
        }
    ]

    analyzer = PortfolioAnalyzer()

    result = analyzer.analyze(holdings)

    usd_summary = result[
        "summary_by_currency"
    ]["USD"]

    assert usd_summary[
        "total_purchase_amount"
    ] == 0

    assert usd_summary[
        "total_market_value"
    ] == 0

    assert usd_summary[
        "total_profit_loss_rate"
    ] == 0

    assert result["positions"][0][
        "weight_percent"
    ] == 0