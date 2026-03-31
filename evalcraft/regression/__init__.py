"""Regression detection — find behavioral drift in agent runs."""

from evalcraft.regression.detector import (
    RegressionDetector,
    Regression,
    RegressionReport,
    Severity,
)
from evalcraft.regression.trend import (
    TrendDetector,
    TrendRegression,
    TrendReport,
)

__all__ = [
    "RegressionDetector",
    "Regression",
    "RegressionReport",
    "Severity",
    "TrendDetector",
    "TrendRegression",
    "TrendReport",
]
