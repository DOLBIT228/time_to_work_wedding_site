"""Виявлення аномально довгих SLA (метод Тʼюкі / IQR)."""

from __future__ import annotations

import pandas as pd

# 3.0 — "екстремальні" викиди за Тʼюкі: відсікаються лише явні аномалії,
# а не просто повільні угоди.
DEFAULT_MULTIPLIER = 3.0
# Нижче цього значення (хв) угода ніколи не вважається аномалією.
DEFAULT_MIN_THRESHOLD = 30.0
# Для малої вибірки поріг ненадійний, тому не відсікаємо нічого.
DEFAULT_MIN_COUNT = 10


def outlier_threshold(
    values,
    multiplier: float = DEFAULT_MULTIPLIER,
    min_threshold: float = DEFAULT_MIN_THRESHOLD,
    min_count: int = DEFAULT_MIN_COUNT,
) -> float | None:
    """Return the upper fence Q3 + multiplier * IQR, or None if data is scarce."""
    series = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    if len(series) < min_count:
        return None

    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    fence = q3 + multiplier * (q3 - q1)
    return max(float(fence), float(min_threshold))


def mark_anomalies(values, threshold: float | None) -> pd.Series:
    """Return a boolean Series: True where the value exceeds the threshold."""
    series = pd.to_numeric(pd.Series(values), errors="coerce")
    if threshold is None:
        return pd.Series(False, index=series.index)
    return series > threshold
