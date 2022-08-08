import pandas as pd


def standardize(ds: pd.Series) -> pd.Series:
    """Standardizes an array of data to produce element-wise z-scores, i.e. number
    of standard deviations away from the mean, such that the output always has
    mean of 0 and std deviation of 1.

    Args:
        ds (pd.Series): Series of data to standardize.

    Returns:
        pd.Series: Input series that has been standardized.
    """
    return (ds - ds.mean()) / ds.std()


def normalize(ds: pd.Series) -> pd.Series:
    """Normalizes an array of data to produce a compressed range. Output will
    always have max value of 1 and min value of 0.

    Args:
        ds (pd.Series): Series of data to normalize.

    Returns:
        pd.Series: Input series that has been normalized.
    """
    return (ds - ds.min()) / (ds.max() - ds.min())


def generate_index_score(
    df: pd.DataFrame, pos_vars: list, neg_vars: list, std_method: str = "standardize"
) -> pd.Series:
    """Combines variables with positive and negative correlations with a target
    outcome to create a composite index score.

    Args:
        df (pd.DataFrame): Dataframe containing variables to combine
        pos_vars (list): List of column names in df with positive correlation
            with desired outcome.
        neg_vars (list): List of column names in df with negative correlation
            with desired outcome.
        std_method (str): Method used to standardize component columns.

    Returns:
        pd.Series: Index scores for each row in df that are a composite of all
            columns in pos_vars and neg_vars taking direction of correlation
            into account.
    """

    # Load selected standardization function
    std_func_all = {"standardize": standardize, "normalize": normalize}
    std_func = std_func_all[std_method]

    # Standardize component variables, flipping sign for neg correlations
    all_vars = pos_vars + neg_vars
    for var in all_vars:
        df[var] = std_func(df[var])
        if var in neg_vars:
            df[var] = -df[var]

    return df[all_vars].mean(axis=1)
