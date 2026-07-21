import os
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"

sys.path.insert(
    0,
    str(SRC_PATH),
)

from service import get_portfolio_analysis


RUN_LIVE_TESTS = (
    os.getenv("RUN_LIVE_TESTS") == "1"
)


pytestmark = pytest.mark.skipif(
    not RUN_LIVE_TESTS,
    reason=(
        "실제 토스 API 테스트는 "
        "RUN_LIVE_TESTS=1일 때만 실행합니다."
    ),
)


def test_live_portfolio_analysis():
    """실제 토스 보유 종목을 읽기 전용으로 분석한다."""

    result = get_portfolio_analysis()

    assert isinstance(result, dict)

    assert "summary_by_currency" in result
    assert "positions" in result

    summary_by_currency = result[
        "summary_by_currency"
    ]

    positions = result["positions"]

    assert isinstance(
        summary_by_currency,
        dict,
    )

    assert isinstance(
        positions,
        list,
    )

    for currency, summary in (
        summary_by_currency.items()
    ):
        assert isinstance(currency, str)
        assert currency

        assert (
            summary["total_purchase_amount"]
            >= 0
        )

        assert (
            summary["total_market_value"]
            >= 0
        )

        assert isinstance(
            summary["total_profit_loss_amount"],
            float,
        )

        assert isinstance(
            summary["total_profit_loss_rate"],
            float,
        )

    for position in positions:
        assert position["symbol"]
        assert position["currency"]

        assert position["quantity"] >= 0
        assert position["market_value"] >= 0

        assert 0 <= position["weight"] <= 1

        assert (
            0
            <= position["weight_percent"]
            <= 100
        )

    for currency, summary in (
        summary_by_currency.items()
    ):
        if summary["total_market_value"] <= 0:
            continue

        currency_weights = [
            position["weight"]
            for position in positions
            if position["currency"] == currency
        ]

        assert sum(
            currency_weights
        ) == pytest.approx(
            1.0,
            abs=0.001,
        )