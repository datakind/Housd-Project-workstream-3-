
"""
- produces geo-coded addresses

- input : csv file with columns corresponding to :
        ['Unique ID', 'Street address', 'City', 'State', 'ZIP']

- output : csv file with geo-coded addresses, output columns:
        id,geocoded_address,is_match,is_exact,returned_address,coordinates,tiger_line,side,
        state_fips,county_fips,tract,block,long,lat

- this uses same geocoder (US Census) as used in the FEAT tool
        https://geocoding.geo.census.gov/geocoder/geographies/addressbatch'

- by default, this method will use multiprocessing, using all available processors (n-1) on OS

"""

# ... -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
# ... imports
# ... -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-

import io
import os
import numpy as np
import pandas as pd
import requests

import concurrent.futures as cf
import multiprocessing
from collections import deque

# ... -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
# ... set some constants for the geo-coding
# ... -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-

GEOCODE_PAYLOAD = {
                'benchmark': 'Public_AR_Current',
                'vintage': 'Current_Current',
                'response': 'json',
                }
GEOCODE_RESPONSE_HEADER = [
                'id',
                'geocoded_address',
                'is_match',
                'is_exact',
                'returned_address',
                'coordinates',
                'tiger_line',
                'side',
                'state_fips',
                'county_fips',
                'tract',
                'block',
                ]

GEOCODE_URL = 'https://geocoding.geo.census.gov/geocoder/geographies/addressbatch'

# ... -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
# ... set some directories and files
# ... -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-

COLS_TO_GEOCODE_FROM = ['org_ein', 'addr', 'city', 'state', 'zip']

ADDRESS_DIR = os.path.join(".", "..", "data/IRS990xml_2021/")
ADDRESS_PATH = os.path.join(ADDRESS_DIR, 'IRS990_2021_mp_fl.csv')

OUT_PATH = os.path.join(ADDRESS_DIR, 'IRS990_2021_fl_geocoded.csv')

# ... -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
# ... multi-processor function
# ... -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-


def make_df_to_geocode(input_file_path, cols_to_keep)-> pd.DataFrame:
    """
    reads in csv file of addresses to geo-code
    retains only the columns needed for geocoding
    renames columns to standard geocoder expected names

    :param input_file_path: (str) file path for .csv with addresses
    :param cols_to_keep: (list) column names that correspond to the
            geocoder standard names: ['Unique ID', 'Street address', 'City', 'State', 'ZIP']
    :return: (pd.DataFrame) dataframe in standard form for geo-coding
    """

    df_to_code = pd.read_csv(input_file_path)
    df_to_code = df_to_code[cols_to_keep]

    # these are the columns anticipated to geocode by geocoder
    # ... rename incoming data columns to match these column names
    df_to_code.columns = ['Unique ID', 'Street address', 'City', 'State', 'ZIP']

    return df_to_code


# ... -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
# ... US Census geocoder
# ... -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-

def census_geocode_records(df_chunk: pd.DataFrame) -> pd.DataFrame:
    """
    US Census geocode API function call
    :param df_chunk: (pd.DataFrame) cleaned address ready for geocoding
    :return: (pd.DataFrame) the geocoded addresses
    """

    df_text = df_chunk.to_csv(index=False, header=None)

    files = {"addressFile": ("chunk.csv", df_text, "text/csv")}

    r = requests.post(GEOCODE_URL, files=files, data=GEOCODE_PAYLOAD)

    df_geocoded = pd.read_csv(io.StringIO(r.text), names=GEOCODE_RESPONSE_HEADER, low_memory=False)

    df_geocoded[["long", "lat"]] = (df_geocoded["coordinates"].astype("str").str.split(",", expand=True))

    return df_geocoded


# ... -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
# ... multi-processor function
# ... -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-

def mp_geocoder(df: pd.DataFrame) -> pd.DataFrame:
    """
    uses ProcessPoolExecutor to multiprocess geocoding request
    creates n-1 processors, where n is number of processors identified
    from multiprocessing.cpu_count()

    :param df: (pd.DataFrame) cleaned address ready for geocoding
    :return: (pd.DataFrame) the geocoded addresses
    """

    cpus = min(multiprocessing.cpu_count() - 1, len(df))

    procs = deque()
    df_splits = np.array_split(df, cpus)

    with cf.ProcessPoolExecutor(max_workers=cpus) as executor:
        for df_slice in df_splits:
            procs.append(
                executor.submit(census_geocode_records, df_slice)
            )

    results = (future.result() for future in cf.as_completed(procs))

    df_coded = pd.DataFrame()
    for df_slice in results:
        df_coded = pd.concat([df_coded, df_slice])

    return df_coded


# ... -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
# ... geo-coder main function
# ... -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-


if __name__ == '__main__':

    # ... read the input csv file, formats to standard column names
    df_to_geocode = make_df_to_geocode(ADDRESS_PATH, COLS_TO_GEOCODE_FROM)

    # ... do the geo-coding, using multiprocessor
    df_geo_results = mp_geocoder(df_to_geocode)

    # ... write the results
    df_geo_results.to_csv(OUT_PATH, index=False)


