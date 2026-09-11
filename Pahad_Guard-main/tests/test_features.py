import pandas as pd

from src.features.engineering import prepare_features


def test_land_cover_is_encoded():
    dataframe = pd.DataFrame(
        {
            "land_cover": ["forest"],
            "rainfall_24h": [100],
            "rainfall_3day": [200],
            "rainfall_7day": [300],
            "soil_moisture": [0.7],
            "elevation": [1500],
            "slope": [30],
            "historical_landslide": [1],
        }
    )

    result = prepare_features(dataframe)

    assert "land_cover_encoded" in result.columns
    assert result.iloc[0]["land_cover_encoded"] == 0
    assert bool(result.iloc[0]["data_complete"]) is True