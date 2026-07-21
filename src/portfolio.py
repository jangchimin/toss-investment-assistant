from __future__ import annotations

from typing import Any


class PortfolioAnalyzer:
    """보유 종목 데이터를 분석하는 클래스."""

    def analyze(self, holdings: list[dict[str, Any]]) -> dict[str, Any]:
        """
        보유 종목 목록을 분석해 종목별 결과와 전체 요약을 반환한다.

        예상 입력 예시:
        [
            {
                "ticker": "PLTR",
                "quantity": 10,
                "avg_price": 150,
                "current_price": 165,
            }
        ]
        """
        if not holdings:
            return {
                "summary": {
                    "total_purchase_amount": 0.0,
                    "total_market_value": 0.0,
                    "total_profit": 0.0,
                    "total_profit_rate": 0.0,
                },
                "positions": [],
            }

        positions: list[dict[str, Any]] = []

        total_purchase_amount = 0.0
        total_market_value = 0.0

        for holding in holdings:
            ticker = str(holding.get("ticker", "")).strip()
            quantity = self._to_float(holding.get("quantity"))
            avg_price = self._to_float(holding.get("avg_price"))
            current_price = self._to_float(holding.get("current_price"))

            purchase_amount = quantity * avg_price
            market_value = quantity * current_price
            profit = market_value - purchase_amount

            profit_rate = (
                profit / purchase_amount * 100
                if purchase_amount > 0
                else 0.0
            )

            total_purchase_amount += purchase_amount
            total_market_value += market_value

            positions.append(
                {
                    "ticker": ticker,
                    "quantity": quantity,
                    "avg_price": avg_price,
                    "current_price": current_price,
                    "purchase_amount": round(purchase_amount, 2),
                    "market_value": round(market_value, 2),
                    "profit": round(profit, 2),
                    "profit_rate": round(profit_rate, 2),
                }
            )

        total_profit = total_market_value - total_purchase_amount

        total_profit_rate = (
            total_profit / total_purchase_amount * 100
            if total_purchase_amount > 0
            else 0.0
        )

        for position in positions:
            weight = (
                position["market_value"] / total_market_value * 100
                if total_market_value > 0
                else 0.0
            )
            position["weight"] = round(weight, 2)

        return {
            "summary": {
                "total_purchase_amount": round(total_purchase_amount, 2),
                "total_market_value": round(total_market_value, 2),
                "total_profit": round(total_profit, 2),
                "total_profit_rate": round(total_profit_rate, 2),
            },
            "positions": positions,
        }

    @staticmethod
    def _to_float(value: Any) -> float:
        """숫자 또는 숫자 문자열을 float로 변환한다."""
        if value in (None, ""):
            return 0.0

        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return 0.0