from anomalies import mark_anomalies, outlier_threshold


def test_extreme_value_is_marked():
    values = [5, 6, 7, 8, 9, 10, 10, 11, 12, 15, 900]
    limit = outlier_threshold(values)
    assert mark_anomalies(values, limit).tolist() == [False] * 10 + [True]


def test_threshold_is_never_below_minimum():
    assert outlier_threshold([1] * 20) == 30.0


def test_small_sample_has_no_threshold():
    assert outlier_threshold([1, 2, 500]) is None
    assert not mark_anomalies([1, 2, 500], None).any()


def test_missing_values_are_ignored():
    values = [None, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 1000]
    marks = mark_anomalies(values, outlier_threshold(values))
    assert marks.tolist() == [False] * 11 + [True]
