from __future__ import annotations

from typing import Any


class PortfolioAnalyzer:
    """보유 종목 데이터를 통화별로 분석하는 클래스."""

    MINIMUM_MARKET_VALUES = {
        "KRW": 100000.0,
        "USD": 50.0,
    }

    def analyze(
        self,
        holdings: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        service.py에서 정리한 보유 종목을 분석한다.

        원화와 달러는 환율 정보 없이 합산하지 않고
        통화별로 나누어 계산한다.
        """

        if not holdings:
            return {
                "summary_by_currency": {},
                "positions": [],
                "concentration_by_currency": {},
            }

        positions: list[dict[str, Any]] = []
        totals_by_currency: dict[
            str,
            dict[str, float],
        ] = {}

        for holding in holdings:
            symbol = str(
                holding.get("symbol", "")
            ).strip().upper()

            name = str(
                holding.get("name", "")
            ).strip()

            currency = str(
                holding.get(
                    "currency",
                    "UNKNOWN",
                )
            ).strip().upper()

            quantity = self._to_float(
                holding.get("quantity")
            )

            average_purchase_price = self._to_float(
                holding.get(
                    "average_purchase_price"
                )
            )

            last_price = self._to_float(
                holding.get("last_price")
            )

            purchase_amount = self._to_float(
                holding.get("purchase_amount")
            )

            market_value = self._to_float(
                holding.get("market_value")
            )

            profit_loss_amount = self._to_float(
                holding.get(
                    "profit_loss_amount"
                )
            )

            profit_loss_rate = self._to_float(
                holding.get(
                    "profit_loss_rate"
                )
            )

            daily_profit_loss_amount = self._to_float(
                holding.get(
                    "daily_profit_loss_amount"
                )
            )

            daily_profit_loss_rate = self._to_float(
                holding.get(
                    "daily_profit_loss_rate"
                )
            )

            if currency not in totals_by_currency:
                totals_by_currency[currency] = {
                    "total_purchase_amount": 0.0,
                    "total_market_value": 0.0,
                    "total_profit_loss_amount": 0.0,
                    "total_daily_profit_loss_amount": 0.0,
                }

            currency_totals = totals_by_currency[
                currency
            ]

            currency_totals[
                "total_purchase_amount"
            ] += purchase_amount

            currency_totals[
                "total_market_value"
            ] += market_value

            currency_totals[
                "total_profit_loss_amount"
            ] += profit_loss_amount

            currency_totals[
                "total_daily_profit_loss_amount"
            ] += daily_profit_loss_amount

            positions.append(
                {
                    "symbol": symbol,
                    "name": name,
                    "market_country": holding.get(
                        "market_country"
                    ),
                    "currency": currency,
                    "quantity": quantity,
                    "average_purchase_price": (
                        average_purchase_price
                    ),
                    "last_price": last_price,
                    "purchase_amount": round(
                        purchase_amount,
                        4,
                    ),
                    "market_value": round(
                        market_value,
                        4,
                    ),
                    "profit_loss_amount": round(
                        profit_loss_amount,
                        4,
                    ),
                    "profit_loss_rate": (
                        profit_loss_rate
                    ),
                    "daily_profit_loss_amount": round(
                        daily_profit_loss_amount,
                        4,
                    ),
                    "daily_profit_loss_rate": (
                        daily_profit_loss_rate
                    ),
                }
            )

        summary_by_currency = {}

        for currency, totals in (
            totals_by_currency.items()
        ):
            total_purchase_amount = totals[
                "total_purchase_amount"
            ]

            total_market_value = totals[
                "total_market_value"
            ]

            total_profit_loss_amount = totals[
                "total_profit_loss_amount"
            ]

            total_profit_loss_rate = (
                total_profit_loss_amount
                / total_purchase_amount
                if total_purchase_amount > 0
                else 0.0
            )

            summary_by_currency[currency] = {
                "total_purchase_amount": round(
                    total_purchase_amount,
                    4,
                ),
                "total_market_value": round(
                    total_market_value,
                    4,
                ),
                "total_profit_loss_amount": round(
                    total_profit_loss_amount,
                    4,
                ),
                "total_profit_loss_rate": round(
                    total_profit_loss_rate,
                    6,
                ),
                "total_daily_profit_loss_amount": (
                    round(
                        totals[
                            "total_daily_profit_loss_amount"
                        ],
                        4,
                    )
                ),
            }

        for position in positions:
            currency = position["currency"]

            currency_market_value = (
                summary_by_currency[
                    currency
                ]["total_market_value"]
            )

            weight = (
                position["market_value"]
                / currency_market_value
                if currency_market_value > 0
                else 0.0
            )

            position["weight"] = round(
                weight,
                6,
            )

            position["weight_percent"] = round(
                weight * 100,
                2,
            )

        positions.sort(
            key=lambda position: (
                position["currency"],
                -position["market_value"],
            )
        )

        concentration_by_currency = (
            self._analyze_concentration(
                positions=positions,
                summary_by_currency=(
                    summary_by_currency
                ),
            )
        )

        return {
            "summary_by_currency": (
                summary_by_currency
            ),
            "positions": positions,
            "concentration_by_currency": (
                concentration_by_currency
            ),
        }

    def _analyze_concentration(
        self,
        positions: list[dict[str, Any]],
        summary_by_currency: dict[
            str,
            dict[str, float],
        ],
    ) -> dict[str, dict[str, Any]]:
        """통화별 종목 집중도를 분석한다."""

        result = {}

        for currency, summary in (
            summary_by_currency.items()
        ):
            currency_positions = [
                position
                for position in positions
                if position["currency"] == currency
            ]

            currency_positions.sort(
                key=lambda position: (
                    -position["market_value"]
                )
            )

            total_market_value = summary[
                "total_market_value"
            ]

            minimum_market_value = (
                self.MINIMUM_MARKET_VALUES.get(
                    currency,
                    0.0,
                )
            )

            if not currency_positions:
                result[currency] = {
                    "level": "not_applicable",
                    "reason": "no_positions",
                    "total_market_value": round(
                        total_market_value,
                        4,
                    ),
                    "minimum_market_value": (
                        minimum_market_value
                    ),
                    "largest_position": None,
                    "top_3_weight": 0.0,
                    "top_3_weight_percent": 0.0,
                    "warnings": [],
                }
                continue

            largest_position = currency_positions[0]
            largest_weight = largest_position["weight"]

            top_3_weight = sum(
                position["weight"]
                for position
                in currency_positions[:3]
            )

            largest_position_result = {
                "symbol": largest_position["symbol"],
                "name": largest_position["name"],
                "weight": round(
                    largest_weight,
                    6,
                ),
                "weight_percent": round(
                    largest_weight * 100,
                    2,
                ),
            }

            if total_market_value < minimum_market_value:
                result[currency] = {
                    "level": "not_applicable",
                    "reason": (
                        "minimum_market_value_not_met"
                    ),
                    "total_market_value": round(
                        total_market_value,
                        4,
                    ),
                    "minimum_market_value": (
                        minimum_market_value
                    ),
                    "largest_position": (
                        largest_position_result
                    ),
                    "top_3_weight": round(
                        top_3_weight,
                        6,
                    ),
                    "top_3_weight_percent": round(
                        top_3_weight * 100,
                        2,
                    ),
                    "warnings": [],
                }
                continue

            level = self._get_concentration_level(
                largest_weight=largest_weight,
                top_3_weight=top_3_weight,
            )

            warnings = (
                self._create_concentration_warnings(
                    largest_position=(
                        largest_position
                    ),
                    largest_weight=(
                        largest_weight
                    ),
                    top_3_weight=top_3_weight,
                )
            )

            result[currency] = {
                "level": level,
                "reason": None,
                "total_market_value": round(
                    total_market_value,
                    4,
                ),
                "minimum_market_value": (
                    minimum_market_value
                ),
                "largest_position": (
                    largest_position_result
                ),
                "top_3_weight": round(
                    top_3_weight,
                    6,
                ),
                "top_3_weight_percent": round(
                    top_3_weight * 100,
                    2,
                ),
                "warnings": warnings,
            }

        return result

    @staticmethod
    def _get_concentration_level(
        largest_weight: float,
        top_3_weight: float,
    ) -> str:
        """프로젝트 내부 기준으로 집중도 등급을 계산한다."""

        if (
            largest_weight >= 0.5
            or top_3_weight >= 0.8
        ):
            return "high"

        if (
            largest_weight >= 0.3
            or top_3_weight >= 0.6
        ):
            return "medium"

        return "low"

    @staticmethod
    def _create_concentration_warnings(
        largest_position: dict[str, Any],
        largest_weight: float,
        top_3_weight: float,
    ) -> list[str]:
        """집중도 기준을 넘은 경우 설명 가능한 경고를 생성한다."""

        warnings = []

        if largest_weight >= 0.5:
            symbol = largest_position["symbol"]

            warnings.append(
                f"{symbol} 단일 종목 비중이 "
                "50% 이상입니다."
            )

        if top_3_weight >= 0.8:
            warnings.append(
                "상위 3개 종목의 합산 비중이 "
                "80% 이상입니다."
            )

        if (
            not warnings
            and largest_weight >= 0.3
        ):
            symbol = largest_position["symbol"]

            warnings.append(
                f"{symbol} 단일 종목 비중이 "
                "30% 이상입니다."
            )

        if (
            not warnings
            and top_3_weight >= 0.6
        ):
            warnings.append(
                "상위 3개 종목의 합산 비중이 "
                "60% 이상입니다."
            )

        return warnings

    @staticmethod
    def _to_float(value: Any) -> float:
        """숫자 또는 숫자 문자열을 float로 변환한다."""

        if value in (None, ""):
            return 0.0

        try:
            return float(
                str(value).replace(",", "")
            )
        except (TypeError, ValueError):
            return 0.0