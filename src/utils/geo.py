import geopandas as gpd
import numpy as np
from shapely import geometry


def create_buffer(gdf: gpd.GeoDataFrame, size_in_meters: int) -> gpd.GeoSeries:
    """Create a buffer of equal radius around polygons in a GeoDataFrame.
    Buffer will be in the same projection as the input gdf.

    Args:
        gdf (gpd.GeoDataFrame): geopandas GeoDataFrame containing polygons
            around which to create a buffer.
        size_in_meters (int): Radius of buffer in meters.

    Returns:
        gpd.GeoSeries: geopandas GeoSeries of buffer polygons.
    """

    # Buffer will be created in CRS 3857 and reprojected back to this
    src_crs = gdf.crs

    # Create buffer polygon and convert to GeoSeries
    buffer_poly = gdf.to_crs(3857).buffer(size_in_meters).unary_union
    buffer = gpd.GeoSeries(buffer_poly).set_crs(3857).to_crs(src_crs)

    return buffer


def create_grid(
    gdf: gpd.GeoDataFrame, size_in_meters: int, filter: bool = True
) -> gpd.GeoDataFrame:
    """Creates a grid over a given polygon as a GeoDataFrame. Grid will be in
    the same projection as the input gdf.

    Args:
        gdf (gpd.GeoDataFrame): geopandas GeoDataFrame containing polygon
            over which to create a grid.
        size_in_meters (int): Width and height of each grid cell in meters.
        filter (bool): If True, filters the output grid down to only the area
            intersecting the input gdf. Defaults to False.

    Returns:
        gpd.GeoDataFrame: geopandas GeoDataFrame of a grid, where each row is a
            grid cell polygon.
    """

    # Grid will be created in CRS 3857 and reprojected back to this
    src_crs = gdf.crs

    # Reproject to pseudo-mercator and get polygon bounds
    min_x, min_y, max_x, max_y = gdf.to_crs(3857).total_bounds

    # Round bounds coords to two decimal places and calculate coords of grid cells
    cols = _create_grid_coords_1d(min_x, max_x, size_in_meters)
    rows = _create_grid_coords_1d(min_y, max_y, size_in_meters)

    # Coordinates start in the top-left and increase in the negative-y direction
    rows = rows[::-1]

    # Create grid indexed by coordinate of top-left corner of cell
    polygons = []
    for x in cols:
        for y in rows:

            # Create a Polygon for every possible row-column coord combination
            polygons.append(
                geometry.Polygon(
                    [
                        (x, y),
                        (x + size_in_meters, y),
                        (x + size_in_meters, y - size_in_meters),
                        (x, y - size_in_meters),
                    ]
                )
            )

    # Create gdf of polygons and reproject back to original crs
    grid = gpd.GeoDataFrame({"geometry": polygons}).set_crs(3857).to_crs(src_crs)
    grid["cell_id"] = grid.index

    # Optionally filter down to intersection with input gdf
    if filter:
        grid = gpd.sjoin(grid, gdf[["geometry"]].dissolve(), how="inner")
        grid = grid.drop(columns=["index_right"])

    return grid


def _create_grid_coords_1d(
    start: float, end: float, size: int, decimals: int = 2
) -> np.ndarray:
    """Creates an array of equally-sized grid cell coordinates in 1 dimension.

    Args:
        start (float): Minimum coordinate value for grid
        end (float): Maximum coordinate value for grid
        size (int): Size of interval in the same units as start/end
        decimals (int): Number of decimal places to round coordinates to

    Returns:
        np.ndarray: An array of equally-sized grid cell coordinates
    """

    rounding_factor = 10**decimals
    start_rounded = np.floor(start * rounding_factor) / rounding_factor
    end_rounded = np.ceil(end * rounding_factor) / rounding_factor

    return np.arange(start_rounded, end_rounded, size)


def reaggregate(
    src_gdf: gpd.GeoDataFrame, dst_gdf: gpd.GeoDataFrame, dst_id: str, agg_vars: list
) -> gpd.GeoDataFrame:
    """Reaggregates an input set of variables from one spatial aggregation level
    (e.g. census tracts) to another (e.g. grid cells). Note: Requires the
    assumption that variables are uniformly distributed over space.

    Args:
        src_gdf (gpd.GeoDataFrame): Input geodataframe with a different spatial
            aggregation level from dst_gdf.
        dst_gdf (gpd.GeoDataFrame): Output empty geodataframe only containing
            polygons at the desired spatial aggregation level and IDs.
        dst_id (str): Name of column in dst_gdf that uniquely identifies rows.
        agg_vars (list): List of column names in src_gdf to reaggregate.

    Returns:
        gpd.GeoDataFrame: A geodataframe with the same geometry as dst_gdf,
            with all agg_vars redistributed to the new spatial aggregation level.
    """

    # Align both geodataframes with the CRS of the output
    if dst_gdf.crs != src_gdf.crs:
        src_gdf = src_gdf.to_crs(dst_gdf.crs)

    # Create combination of both GDFs as unique land fragments
    fragment_df = dst_gdf.overlay(src_gdf, how="union")

    # Calculate weight of each fragment in dst polygon units
    fragment_df["fragment_area"] = fragment_df["geometry"].to_crs(3857).area
    dst_unit_areas = (
        fragment_df.groupby(dst_id)
        .sum()["fragment_area"]
        .reset_index()
        .rename(columns={"fragment_area": "dst_unit_area"})
    )
    fragment_df = fragment_df.merge(dst_unit_areas, on=dst_id, how="inner")
    fragment_df["fragment_area_pct"] = (
        fragment_df["fragment_area"] / fragment_df["dst_unit_area"]
    )

    # Redistribute vars over dst polygon units by area weight
    for var in agg_vars:
        fragment_df[var] *= fragment_df["fragment_area_pct"]

    agg_df = fragment_df[agg_vars + [dst_id]].groupby(dst_id).sum().reset_index()
    out_gdf = dst_gdf.merge(agg_df, on=dst_id, how="left")

    return out_gdf
