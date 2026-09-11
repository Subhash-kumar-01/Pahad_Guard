import pandas as pd


def validate_coordinates(
    dataframe: pd.DataFrame,
    min_lat: float = -90,
    max_lat: float = 90,
    min_lon: float = -180,
    max_lon: float = 180,
) -> pd.DataFrame:
    result = dataframe.copy()

    valid_latitude = result["latitude"].between(min_lat, max_lat)
    valid_longitude = result["longitude"].between(min_lon, max_lon)

    return result[valid_latitude & valid_longitude].copy()


def validate_sikkim_coordinates(dataframe: pd.DataFrame) -> pd.DataFrame:
    return validate_coordinates(
        dataframe,
        min_lat=27.0,
        max_lat=28.3,
        min_lon=87.8,
        max_lon=89.0,
    )


def find_duplicate_grid_dates(dataframe: pd.DataFrame) -> pd.DataFrame:
    return dataframe[
        dataframe.duplicated(
            subset=["latitude", "longitude", "date"],
            keep=False,
        )
    ].copy()


def missing_value_report(dataframe: pd.DataFrame) -> pd.DataFrame:
    report = dataframe.isnull().sum().reset_index()
    report.columns = ["column", "missing_values"]
    report["missing_percentage"] = (
        report["missing_values"] / len(dataframe) * 100
    )
    return report.sort_values("missing_values", ascending=False)