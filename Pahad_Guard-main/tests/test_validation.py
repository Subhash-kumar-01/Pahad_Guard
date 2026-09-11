import pandas as pd

from src.utils.validation import (
    find_duplicate_grid_dates,
    validate_coordinates,
    validate_sikkim_coordinates,
)


def test_invalid_coordinates_are_removed():
    dataframe = pd.DataFrame(
        {
            "latitude": [27.5, 200],
            "longitude": [88.5, 88.5],
        }
    )

    result = validate_coordinates(dataframe)

    assert len(result) == 1


def test_sikkim_filter():
    dataframe = pd.DataFrame(
        {
            "latitude": [27.5, 35.0],
            "longitude": [88.5, 88.5],
        }
    )

    result = validate_sikkim_coordinates(dataframe)

    assert len(result) == 1


def test_duplicate_detection():
    dataframe = pd.DataFrame(
        {
            "latitude": [27.5, 27.5, 27.6],
            "longitude": [88.5, 88.5, 88.6],
            "date": ["2024-07-01", "2024-07-01", "2024-07-02"],
        }
    )

    result = find_duplicate_grid_dates(dataframe)

    assert len(result) == 2