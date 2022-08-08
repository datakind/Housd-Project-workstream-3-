from typing import Dict

import pandas as pd
import pytest

from src.utils.parse_address import FEAT_CROSSWALK, AddressParser


@pytest.fixture
def crosswalk():
    return FEAT_CROSSWALK


class TestAddressParser:
    def test_parse_string(self, crosswalk: Dict[str, list]):
        # Arrange
        address = "705 W. EMMETT ST KISSIMMEE FL 34741"
        expected = {
            "Street_Address_1": "705 W. EMMETT ST",
            "Street_Address_2": None,
            "City": "KISSIMMEE",
            "State": "FL",
            "Zip": "34741",
            "Country": None,
        }

        # Act
        result = AddressParser.parse(address, crosswalk)

        # Assert
        assert result == expected

    def test_parse_series(self, crosswalk: Dict[str, list]):
        # Arrange
        address_series = pd.Series(
            [
                "1600 Pennsylvania Avenue NW, Washington, DC 20500",
                "11 WALL STREET, NEW YORK, NY 10005",
                "350 Fifth Avenue #2B New York, NY 10118",
            ]
        )
        expected = pd.DataFrame(
            {
                "Street_Address_1": [
                    "1600 Pennsylvania Avenue NW",
                    "11 WALL STREET",
                    "350 Fifth Avenue",
                ],
                "Street_Address_2": [None, None, "# 2B"],
                "City": ["Washington", "NEW YORK", "New York"],
                "State": ["DC", "NY", "NY"],
                "Zip": ["20500", "10005", "10118"],
                "Country": [None, None, None],
            }
        )

        # Act
        result = AddressParser.parse_series(address_series, crosswalk)

        # Assert
        assert result.sort_index(axis=1).equals(expected.sort_index(axis=1))
