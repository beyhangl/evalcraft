"""Regression detection — find behavioral drift in agent runs."""

from evalcraft.regression.detector import (
    RegressionDetector,
    Regression,
    RegressionReport,
    Severity,
)

__all__ = ["RegressionDetector", "Regression", "RegressionReport", "Severity"]
