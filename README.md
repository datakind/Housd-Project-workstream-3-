# Event Siting Tool developed for Housd and Bright Community Trust

A python-based tool to identify and rank potential sites where Housd and Bright Community Trust might hold community outreach events.

# What's in this repo?

```
.
├── README.md - you are here
├── configs - folder of config YAMLs for each county
├── data - put input data here
├── environment.yml - conda environment file
├── event-siting-all-counties.bash - helper script to run event siting tool for 4 Florida counties
├── notebooks - example jupyter notebooks demonstrating workflows
├── pytest.ini - pytest configuration file
├── requirements.txt - pip environment file
├── src - main project code
└── test - tests for project code
```

# Usage

1. Follow Steps 1 and 2 in `Development Setup` below to install and activate the virtual environment.
2. Assemble your input datasets:
    - Places-of-interest data for potential event sites (see `example-notebooks/build-poi-dataset.ipynb`)
    - Census tract-level data for scoring potential event sites, such as the outputs from the [DataKind New America Housing Loss Analysis tool](https://github.com/datakind/new-america-housing-loss-public)
    - Census tract-level shapefiles for mapping and visualization (see `example-notebooks/filter-county-specific-shapefiles.ipynb`)
    - Other visualization files (e.g. road shapefiles, see `example-notebooks/create-road-layer.ipynb`)
3. Create a config file from the template provided (`configs/template-config.yaml`), enter paths to your input datasets, and fill in other parameters
4. In the root directory of this repo, run the following command, specifying the config file that you created in step 1:
```bash
python3 src/event-siting.py -f <config-file>
```
5. The event siting tool will create a `event-siting-outputs` directory and save results there.

A bash script (`event-siting-all-counties.bash`) and 4 pre-written configs (`configs/*-config.yaml`) have been provided for convenience. When run, the bash script runs the event siting tool for Lake, Orange, Seminole and Osceola counties in Florida. To run the bash script alone:

```bash
sh event-siting-all-counties.bash
```

# Development Setup

To start working on this project, please follow instructions for the following:
1. (optional) Create a virtual environment
2. Install all dependencies
3. Install pre-commit hooks
4. Run unit tests

## 1. (optional) Create a virtual environment

pyenv, venv, virtualenv, conda are all good options.

## 2. Install all dependencies

Make sure the environment is activated before installing dependencies.

### 2.1 Installation with pip

Install dependencies with `pip install -r requirements.txt`.

### 2.2 Installation with conda

Install dependencies with `conda env create`.

> Note: It will automatically detect and install from `environment.yml`. To specify a different conda YAML file, specify the file name with the `-f` flag like so: `conda env create -f <conda-env-yaml>`\

## 3. Install pre-commit hooks

We use [pre-commit hooks](https://pre-commit.com/) to perform routine formatting and linting on commit.
- Configure specific hooks within `.pre-commit-config.yaml`
- Then install the hooks with `pre-commit install`

### 4. Running unit tests

Unit tests can be run via [`pytest`](https://docs.pytest.org/en/7.0.x/getting-started.html).

1. Run `python3 -m pytest` from the root directory of the repo.
2. Ensure all tests pass (output is green or yellow)

New unit tests may be added to the `test` directory.
