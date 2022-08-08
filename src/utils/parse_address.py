from collections import ChainMap
from itertools import groupby
from operator import itemgetter
from typing import Dict, List, Set, Tuple

import pandas as pd
import usaddress

# This maps between usaddress tags and required FEAT address fields
FEAT_CROSSWALK = {
    "Street_Address_1": [
        "USPSBoxGroupType",
        "USPSBoxGroupID",
        "USPSBoxType",
        "USPSBoxID",
        "AddressNumberPrefix",
        "AddressNumber",
        "AddressNumberSuffix",
        "StreetNamePreDirectional",
        "StreetNamePreType",
        "StreetNamePreModifier",
        "StreetName",
        "StreetNamePostModifier",
        "StreetNamePostType",
        "StreetNamePostDirectional",
    ],
    "Street_Address_2": [
        "OccupancyType",
        "OccupancyIdentifier",
        "SubaddressType",
        "SubaddressIdentifier",
    ],
    "City": ["PlaceName"],
    "State": ["StateName"],
    "Zip": ["ZipCode", "ZipPlus4"],
    "Country": ["CountryName"],
    "_other": [
        "Recipient",
        "BuildingName",
        "CornerOf",
        "IntersectionSeparator",
        "LandmarkName",
        "NotAddress",
    ],
}


class AddressParser:
    @classmethod
    def parse_series(
        cls, col: pd.Series, crosswalk: Dict[str, list], fillna: bool = True
    ) -> pd.DataFrame:
        """Takes a pandas Series as input, parses out all the address strings
        in the series, and outputs a dataframe where each column is an address
        element (e.g. Street_Address, City, Zip).

        Args:
            col (pd.Series): Contains address strings to be parsed
            crosswalk (Dict[str, list]): Dictionary mapping output keys to
                usaddress-provided addresss element tags.
            fillna (Optional[bool]): If True, fills all NaN elements in col with
                empty strings before parsing, else parsing can fail if given a
                NaN value. Defaults to True.

        Returns:
            pd.DataFrame: Contains parsed address strings separated out into
                their respective address elements.
        """
        if fillna:
            col = col.fillna("")

        parsed_series = col.map(lambda x: cls.parse(x, crosswalk=crosswalk))

        return pd.DataFrame(parsed_series.tolist())

    @classmethod
    def parse(
        cls,
        address: str,
        crosswalk: Dict[str, list],
        verbose: bool = False,
    ) -> Dict[str, str]:
        """Parses a single address string into a dictionary of address elements.
        If keys in the crosswalk are not present in the parsed address, they
        are included with a None value in the output dict.

        Args:
            address (str): Address to parse
            crosswalk (Dict[str, list]): Dictionary mapping output keys to
                usaddress-provided addresss element tags.
            verbose (bool, optional): If true, prints out intermediate data
                transformations. Defaults to False.

        Returns:
            Dict[str, str]: A parsed address separated into address elements
                as specified by the crosswalk.
        """

        # Parse initial Address string into tuples of (element, tag)
        tagged = usaddress.parse(address.replace(",", ""))
        if verbose:
            print(f"{tagged=}" + "\n")

        # Reverse address elements so tag is first element in tuple
        reverse = [(y, x) for x, y in tagged]
        if verbose:
            print(f"{reverse=}" + "\n")

        # Merge elements by tag and convert to tuple of (tag, element)
        combined_by_tag = cls._merge_tuples_by_key(reverse)
        if verbose:
            print(f"{combined_by_tag=}" + "\n")

        # Replace original usaddress tags with categories from crosswalk
        reverse_crosswalk = cls._reverse_crosswalk(crosswalk)
        replaced = [(reverse_crosswalk[x], y) for x, y in combined_by_tag]
        if verbose:
            print(f"{replaced=}" + "\n")

        # Merge new tuples by new keys from crosswalk
        merged = cls._merge_tuples_by_key(replaced)
        if verbose:
            print(f"{merged=}" + "\n")

        # Transform tuple of (key, list) to dict of key: joined_list
        parsed = cls._tuple_with_list_to_dict(merged)
        if verbose:
            print(f"{parsed=}" + "\n")

        # Make sure all keys in crosswalk are present
        result = cls._enforce_crosswalk_keys(parsed, crosswalk, verbose)

        return result

    @classmethod
    def list_uncategorized_tags(
        cls, col: pd.Series, crosswalk: Dict[str, list]
    ) -> Set[str]:
        """If unsure if your crosswalk already categorized all the usaddress
        output tags into FEAT address elements, use this method with an existing
        crosswalk dict to show if any tags have yet to be inserted into the
        crosswalk.

        Args:
            col (pd.Series): Contains address strings to be parsed
            crosswalk (Dict[str, list]): Dictionary mapping output keys to
                usaddress-provided addresss element tags.

        Returns:
            Set[str]: Set of uncategorized tags. Returns empty set if there
                are no uncategorized tags.
        """

        all_tags = cls.get_unique_tags(col)
        categorized = set(y for x in crosswalk.values() for y in x)
        return all_tags - categorized

    @classmethod
    def get_unique_tags(cls, col: pd.Series, fillna: bool = True) -> Set[str]:
        """Outputs a list of unique tags to categorize via your crosswalk dict.

        Args:
            col (pd.Series): Contains address strings to be parsed
            fillna (Optional[bool]): If True, fills all NaN elements in col with
                empty strings before parsing, else parsing can fail if given a
                NaN value. Defaults to True.

        Returns:
            List[str]: List of unique tags for a given address column
        """
        if fillna:
            col = col.fillna("")

        parsed = col.map(usaddress.parse)
        all_keys = set(z for x in parsed for y, z in x)

        return all_keys

    @classmethod
    def _merge_tuples_by_key(cls, tups: List[Tuple[str, str]]):
        """Merge elements by tag and convert to dict of tag:element"""
        return list(
            (keys, [i for _, i in sub])
            for keys, sub in groupby(tups, key=itemgetter(0))
        )

    @classmethod
    def _reverse_crosswalk(cls, crosswalk: Dict[str, list]) -> Dict[str, str]:
        """Reverses the crosswalk from {str: list} to {list-element: str}.
        This is to enable easy string-replace operations when applying the
        crosswalk.
        """
        return dict(ChainMap(*[{i: k for i in v} for k, v in crosswalk.items()]))

    @classmethod
    def _tuple_with_list_to_dict(cls, tup: Tuple[str, list]) -> Dict[str, str]:
        """Converts a tuple of (key, list[list]) to a dict of {key: joined_list}.
        Helpful when you have a list of lists that needs to be flattened.
        """
        return {k: " ".join(sum(v, [])) for k, v in tup}

    @classmethod
    def _enforce_crosswalk_keys(
        cls, out_dict: Dict[str, list], crosswalk: Dict[str, list], verbose: bool
    ) -> Dict[str, list]:
        """Make sure all keys in crosswalk are present"""
        for i in crosswalk.keys():
            if i not in out_dict.keys() and i != "_other":
                if verbose:
                    print(f"Adding {i} to output dict")
                out_dict[i] = None
        return out_dict
