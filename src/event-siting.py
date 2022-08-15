import argparse
import os
import pathlib
import warnings
from typing import Optional
from uuid import uuid4

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import yaml
from adjustText import adjust_text

from utils.geo import create_buffer, create_grid, reaggregate
from utils.scoring import generate_index_score

warnings.simplefilter(action="ignore", category=FutureWarning)


class EventSitingModel:

    # Raw input data
    tracts: gpd.GeoDataFrame
    tract_data: gpd.GeoDataFrame
    pois: gpd.GeoDataFrame
    grid: gpd.GeoDataFrame

    # Derived and intermediate attributes
    housing_outliers: gpd.GeoDataFrame
    tract_buffer: gpd.GeoDataFrame
    potential_cells: gpd.GeoDataFrame
    event_scores_all_cells: gpd.GeoDataFrame
    cells_with_event_score: gpd.GeoDataFrame
    ranked_pois: gpd.GeoDataFrame

    def __init__(
        self,
        county_name: str,
        tract_path: str,
        tract_geoid_varname: str,
        tract_data_path: str,
        tract_data_geoid_varname: str,
        housing_loss_varname: str,
        poi_path: str,
        poi_type_varname: str,
        poi_types: list[str],
        distance_radius_m: int,
        tract_positive_correlation_vars: list[str],
        tract_negative_correlation_vars: list[str],
        grid_path: Optional[str] = None,
        grid_id_varname: Optional[str] = None,
        output_path: Optional[str] = "./event-siting-outputs",
    ) -> None:

        self.run_id = uuid4().hex

        # Save user-provided paths to inputs
        self._tract_path = tract_path
        self._tract_data_path = tract_data_path
        self._poi_path = poi_path
        self._grid_path = grid_path

        # Save names of columns in data sources to reference later
        self._housing_loss_varname = housing_loss_varname
        self._poi_type_varname = poi_type_varname
        self._tract_geoid_varname = tract_geoid_varname
        self._tract_data_geoid_varname = tract_data_geoid_varname
        self._grid_id_varname = grid_id_varname

        # Other parameters to save
        self.county_name = county_name
        self.poi_types = poi_types
        self.distance_radius_m = distance_radius_m
        self.tract_positive_vars = tract_positive_correlation_vars
        self.tract_negative_vars = tract_negative_correlation_vars
        self.output_path = os.path.join(
            output_path, f"{self.run_id}-{self.county_name}"
        )

        # Define plotting parameters
        self.figsize = (12, 12)
        self.cmap = "plasma"

    def run(self) -> None:

        # Load all input data and standardize projections
        print(f"Starting run {self.run_id} for {self.county_name}")
        self._setup_paths()
        self._load_inputs()
        self._standardize_projections()

        # Identify tracts with high housing loss
        print("Identifying census tracts with high housing loss")
        self.housing_outliers = self._get_tracts_of_interest(min_mean_ratio=2)

        # Identify potential grid cell sites
        print("Identifying potential grid cells")
        self.potential_cells = self._get_potential_cells()

        # Create cell-level event siting scores for potential cells
        print("Scoring potential grid cells")
        self.event_scores_all_cells = self._get_cell_event_scores()
        self.cells_with_event_score = self.potential_cells.merge(
            self.event_scores_all_cells.drop(columns=["geometry"]),
            how="left",
            on=self._grid_id_varname,
        )

        # Identify ranked list of POI in cells by event score
        print("Searching points of interest within ranked grid cells")
        self.ranked_pois = self._get_ranked_pois()

        # Output ranked list of POIs
        print("Exporting CSV file of potential sites")
        self._output_ranked_pois()

        # Plot important intermediate stages
        print("Creating plots")
        self._plot_steps()

        print("Run complete!")

    def _setup_paths(self) -> None:

        # Create folder for current run
        pathlib.Path(self.output_path).mkdir(parents=True, exist_ok=True)

    def _load_inputs(self) -> None:
        """Load all input datasets from provided paths and assign names to
        datasets. If no grid shapefile is supplied, a grid GeoDataFrame will be
        created from the census tract boundaries.
        """

        # Load census tract shapefiles
        self.tracts = gpd.read_file(self._tract_path)
        self.tracts._name = "census_tracts"

        # Load FEAT output for selected county and merge onto shapefile
        tract_data_df = pd.read_csv(self._tract_data_path)
        tract_data_df[self._tract_data_geoid_varname] = tract_data_df[
            self._tract_data_geoid_varname
        ].astype(str)
        self.tract_data = self.tracts[[self._tract_geoid_varname, "geometry"]].merge(
            tract_data_df,
            left_on=self._tract_geoid_varname,
            right_on=self._tract_data_geoid_varname,
            how="outer",
        )
        self.tract_data._name = "tract_data"

        # Load county POI data and filter down to selected types
        self.pois = gpd.read_file(self._poi_path)
        self.pois = self.pois[self.pois[self._poi_type_varname].isin(self.poi_types)]
        self.pois._name = "pois"

        # Load or create grid
        if self._grid_path is None:
            self.grid = create_grid(self.tracts, size_in_meters=1000)
        else:
            self.grid = gpd.read_file(self._grid_path)
        self._grid_id_varname = "cell_id"
        self.grid._name = "grid"

    def _standardize_projections(self, target_epsg: int = 4326) -> None:
        """Makes sure all spatial inputs are in the same projection.

        Args:
            target_epsg (int, optional): EPSG code for the projection under which
                to standardize all spatial files. Defaults to 4326.
        """
        for gdf in [self.tracts, self.pois, self.grid]:
            src_crs = gdf.crs
            if src_crs != target_epsg:
                print(f"Reprojecting {gdf._name} from {src_crs} to EPSG:{target_epsg}.")
                gdf = gdf.to_crs(target_epsg)

    def _get_tracts_of_interest(
        self, min_mean_ratio: Optional[float] = None, min_zscore: Optional[float] = None
    ) -> gpd.GeoDataFrame:
        """Selects tracts of interest based on a specified strategy:
        - If min_mean_ratio is provided, then tracts of interest are tracts
        whose housing loss index score is greater than the specified ratio to
        the county mean housing loss index score.
        - If min_zscore is provided, then tracts of interest are tracts that are
        more than the min number of standard deviations away from the mean.

        Args:
            min_mean_ratio (Optional[float], optional): Minimum multiple of
                county mean housing loss index score. Defaults to None.
            min_zscore (Optional[float], optional): Minimum number of standard
                deviations away from the mean housing loss index score. Defaults
                to None.
        """

        # Check that only one argument is provided
        neither_provided = min_mean_ratio is None and min_zscore is None
        both_provided = min_mean_ratio is not None and min_zscore is not None
        if neither_provided or both_provided:
            raise ValueError("Please provide either min_mean_ratio or min_zscore.")

        # Calculate county mean and identify outliers of interest
        hloss_mean = self.tract_data[self._housing_loss_varname].mean()
        if min_mean_ratio is not None:
            mean_ratio = self.tract_data[self._housing_loss_varname] / hloss_mean
            return self.tract_data[mean_ratio > min_mean_ratio]

        if min_zscore is not None:
            hloss_std = self.tract_data[self._housing_loss_varname].std()
            zscore = hloss_mean / hloss_std
            return self.tract_data[zscore > min_zscore]

    def _get_potential_cells(self) -> gpd.GeoDataFrame:
        """Creates a distance buffer of specified radius (self.distance_radius_m)
        around tracts of interest (self.housing_outliers) and then selects only
        grid cells within the buffer (self.grid_in_buffer) containing selected
        POI types (self.poi_types).
        """
        # Create distance buffer and filter grid
        self.tract_buffer = create_buffer(self.housing_outliers, self.distance_radius_m)
        self.tract_buffer = gpd.GeoDataFrame(self.tract_buffer, geometry=0)
        grid_in_buffer = gpd.sjoin(self.grid, self.tract_buffer)
        grid_in_buffer.drop(columns=["index_right"], inplace=True)

        # Filter grid further
        potential_cells = grid_in_buffer.sjoin(
            self.pois[["geometry"]], how="inner"
        ).drop_duplicates()
        potential_cells.drop(columns=["index_right"], inplace=True)

        return potential_cells

    def _get_cell_event_scores(self) -> gpd.GeoDataFrame:
        # Gather all selected vars in config
        all_vars = self.tract_positive_vars + self.tract_negative_vars
        for var in all_vars:
            assert var in self.tract_data.columns, f"{var} not found in data"

        # Reaggregate census tract-level indicators to cell-level indicators
        indicators_by_cell = reaggregate(
            self.tract_data, self.grid, self._grid_id_varname, all_vars
        )

        # Standardize and combine into index
        event_scores = self.grid.copy(deep=True).reset_index(drop=True)
        event_scores["event_score"] = generate_index_score(
            indicators_by_cell, self.tract_positive_vars, self.tract_negative_vars
        )

        return event_scores

    def _get_ranked_pois(self) -> gpd.GeoDataFrame:
        """Get all POIs within selected potential cells and rank by event score"""
        ranked_pois = self.pois.sjoin(
            self.cells_with_event_score, how="inner"
        ).drop_duplicates(subset=["id"])
        ranked_pois.drop(columns=["index_right"], inplace=True)
        ranked_pois["name"].fillna("NAME UNKNOWN", inplace=True)
        return ranked_pois.sort_values(by="event_score", ascending=False)

    def _output_ranked_pois(self) -> None:
        """Saves ranked POIs and other outputs to disk."""

        # Save ranked POI as geojson and csv
        poi_out_path = os.path.join(self.output_path, "potential_event_sites.geojson")
        self.ranked_pois.to_file(poi_out_path, driver="GeoJSON")
        self.ranked_pois.to_csv(poi_out_path.replace("geojson", "csv"))

    def _plot_steps(self) -> None:

        # Plot and save other figures
        self._plot_selected_tracts(n=1)
        self._plot_event_scores(n=2)
        self._plot_cell_event_scores(n=3)
        self._plot_ranked_poi(n=4)

    def _plot_selected_tracts(self, n: int) -> None:

        fig, ax = plt.subplots(figsize=self.figsize)
        title = "\n".join(
            [
                f"{self.county_name}: Census tracts with high housing loss",
                f"Using buffer size of {self.distance_radius_m}m",
            ]
        )
        ax.set_title(title)

        # Plot tract outline
        self.tracts.plot(ax=ax, facecolor="none", edgecolor="gray", alpha=0.2)

        # Plot tract value highlights
        self.housing_outliers.plot(
            ax=ax,
            column=self._housing_loss_varname,
            legend=True,
            legend_kwds={"label": self._housing_loss_varname},
        )

        # Plot 10 mile radius
        self.tract_buffer.dissolve().plot(ax=ax, alpha=0.3)

        # Plot grid cells containing those POI within buffer
        self.potential_cells.plot(ax=ax, facecolor="none", edgecolor="r")

        # Save to file
        out_path = os.path.join(
            self.output_path, f"{str(n).zfill(2)}_selected_tracts.png"
        )
        plt.savefig(out_path)

    def _plot_event_scores(self, n: int) -> None:

        fig, ax = plt.subplots(figsize=self.figsize)
        ax.set_title(
            f"{self.county_name}: Composite index score of FEAT-derived indicators"
        )

        # Plot event scores
        self.event_scores_all_cells.plot(
            ax=ax,
            column="event_score",
            legend=True,
            cmap=self.cmap,
            legend_kwds={"label": "event score"},
        )

        # Plot potential cell outlines
        self.potential_cells.plot(ax=ax, facecolor="none", edgecolor="white")

        # Save to file
        out_path = os.path.join(
            self.output_path, f"{str(n).zfill(2)}_all_event_scores.png"
        )
        plt.savefig(out_path)

    def _plot_cell_event_scores(self, n: int) -> None:

        fig, ax = plt.subplots(figsize=self.figsize)
        ax.set_title(f"{self.county_name}: Event scores for potential grid cells")

        # Plot tract outline
        self.tracts.plot(ax=ax, facecolor="none", edgecolor="grey", alpha=0.2)

        # Plot outlier tracts
        self.housing_outliers.plot(ax=ax, alpha=0.3)

        # Plot cells with event scores
        self.cells_with_event_score.plot(
            ax=ax,
            column="event_score",
            legend=True,
            cmap=self.cmap,
            legend_kwds={"label": "event score"},
            edgecolor="white",
        )

        # Save to file
        out_path = os.path.join(
            self.output_path, f"{str(n).zfill(2)}_potential_site_event_scores.png"
        )
        plt.savefig(out_path)

    def _plot_ranked_poi(self, n: int, top_n: int = 10):

        fig, ax = plt.subplots(figsize=self.figsize)
        ax.set_title(
            f"{self.county_name}: Top {top_n} potential event sites by event site score"
        )

        # Plot tract outline
        self.tracts.plot(ax=ax, facecolor="none", edgecolor="gray", alpha=0.2)

        # Plot outlier tracts
        self.housing_outliers.plot(ax=ax, alpha=0.3)

        # Plot selected POI
        self.ranked_pois.head(top_n).plot(ax=ax, color="red", markersize=20)

        # Annotate names on chart
        poi_site_names = [
            plt.text(
                poi.geometry.x, poi.geometry.y, poi["name"], ha="center", va="center"
            )
            for _, poi in self.ranked_pois.head(top_n).iterrows()
        ]
        adjust_text(
            poi_site_names, arrowprops={"arrowstyle": "-", "color": "red", "lw": 0.5}
        )

        # Save to file
        out_path = os.path.join(
            self.output_path, f"{str(n).zfill(2)}_top{top_n}_ranked_sites.png"
        )
        plt.savefig(out_path)


if __name__ == "__main__":

    # Parse user-supplied path to config
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-f",
        "--file",
        type=pathlib.Path,
        dest="config_path",
        help="Path to the config YAML",
    )
    args = parser.parse_args()

    # Load config YAML as dict
    assert (
        args.config_path is not None
    ), "Did you forget to provide a path to the config with the -f flag?"
    with open(args.config_path, "r") as f:
        config: dict = yaml.safe_load(f)

    # Instantiate model and run
    model = EventSitingModel(
        county_name=config["COUNTY_NAME"],
        tract_path=config["TRACT_PATH"],
        tract_geoid_varname=config["TRACT_GEOID_VARNAME"],
        tract_data_path=config["TRACT_DATA_PATH"],
        tract_data_geoid_varname=config["TRACT_DATA_GEOID_VARNAME"],
        housing_loss_varname=config["HOUSING_LOSS_VARNAME"],
        poi_path=config["POI_PATH"],
        poi_type_varname=config["POI_TYPE_VARNAME"],
        poi_types=config["POI_TYPES"],
        distance_radius_m=config["DISTANCE_RADIUS_M"],
        tract_positive_correlation_vars=config["POS_CORR_VARS"],
        tract_negative_correlation_vars=config["NEG_CORR_VARS"],
    )
    model.run()
