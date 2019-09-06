import xarray as xr
import numpy as np
import pandas as pd
import toolz
from distutils.version import LooseVersion


def _reindex_spatial_data_to_regions(ds, df):
    """
    Reindexes spatial and segment weight data to regions
    Enables region index-based math operations
    Parameters
    ----------
    ds: xarray Dataset
    df: pandas DataFrame
    Returns
    -------
    Xarray DataArray
    """

    # use vectorized indexing in xarray >= 0.10
    if LooseVersion(xr.__version__) > LooseVersion('0.9.999'):

        lon_indexer = xr.DataArray(df.lon.values, dims=('reshape_index', ))
        lat_indexer = xr.DataArray(df.lat.values, dims=('reshape_index', ))

        return ds.sel(lon=lon_indexer, lat=lat_indexer)

    else:
        res = ds.sel_points(
            'reshape_index',
            lat=df.lat.values,
            lon=df.lon.values)

        return res


def _aggregate_reindexed_data_to_regions(
        ds,
        variable,
        aggwt,
        agglev,
        weights,
        backup_aggwt='areawt'):
    """
    Performs weighted avg for climate variable by region

    Parameters
    ----------

    ds: xarray.DataArray

    variable: str
        name of the data variable

    aggwt: str
        variable to weight by (i.e popwt, areawt, cropwt)

    agglev: str
        indicates which regional id scheme to select in the dataframe

    weights: pd.DataFrame
        pandas DataFrame of weights

    backup_aggwt: str, optional
        aggregation weight to use in regions with no aggwt data (default
        'areawt')

    """

    ds.coords[agglev] = xr.DataArray(
                weights[agglev].values,
                dims={'reshape_index': weights.index.values})

    # format weights
    ds[aggwt] = xr.DataArray(
                weights[aggwt].values,
                dims={'reshape_index': weights.index.values})

    ds[aggwt] = (
        ds[aggwt]
        .where(ds[aggwt] > 0)
        .fillna(weights[backup_aggwt].values))

    weighted = xr.Dataset({
        variable: (
            (
                (ds[variable]*ds[aggwt])
                .groupby(agglev)
                .sum(dim='reshape_index')) /
            (
                ds[aggwt]
                .groupby(agglev)
                .sum(dim='reshape_index')))})

    return weighted


def aggregate_array(arr, weight_df, weight_col, region_cols, lon_name='longitude', lat_name='latitude'):
    extra_dims = [d for d in arr.dims if d not in [lon_name, lat_name]]

    reindexed = arr.sel(**{
        lon_name: weight_df.rename_axis('SEGMENT_INDEX')[lon_name].to_xarray(),
        lat_name: weight_df.rename_axis('SEGMENT_INDEX')[lat_name].to_xarray()})

    for rc in region_cols:
        reindexed[rc] = weight_df.rename_axis('SEGMENT_INDEX')[rc].to_xarray()

    reindexed[weight_col] = weight_df.rename_axis('SEGMENT_INDEX')[weight_col].to_xarray()

    reindexed_df = (
        reindexed.to_dataset(name='__temp_weighting_output_variable__').to_dataframe())

    reindexed_df['__temp_weighted_output_variable__'] = (
        reindexed_df[weight_col] * reindexed_df.__temp_weighting_output_variable__)

    # make sure we don't count weight where we don't have data
    reindexed_df[weight_col] = (
        reindexed_df[weight_col].where(
            pd.notnull(reindexed_df.__temp_weighting_output_variable__)))

    aggregated = (
        reindexed_df.reset_index().groupby(
            region_cols + extra_dims)[[weight_col, '__temp_weighted_output_variable__']].sum())

    return aggregated.__temp_weighted_output_variable__ * ((1. / aggregated[weight_col]).fillna(0))


def weighted_aggregate_grid_to_regions(
        ds,
        variable,
        aggwt,
        agglev,
        weights=None):
    """
    Computes the weighted reshape of gridded data

    Parameters
    ----------
    ds : xr.Dataset
        xarray Dataset to be aggregated. Must have 'lat' and 'lon' in the
        coordinates.

    variable : str
        name of the variable to be aggregated

    aggwt : str
        Weighting variable (e.g. 'popwt', 'areawt'). This must be a column name
        in the weights file.

    agglev : str
        Target regional aggregation level (e.g. 'ISO', 'hierid'). This must be
        a column name in the weights file.

    weights : str, optional
        Regional aggregation weights (default agglomerated-world-new BCSD
        segment weights)

    Returns
    -------
    ds: xr.Dataset
        weighted and averaged dataset based on agglev
    """

    if weights is None:
        weights = _prepare_spatial_weights_data()

    ds = _reindex_spatial_data_to_regions(ds, weights)
    ds = _aggregate_reindexed_data_to_regions(
        ds,
        variable,
        aggwt,
        agglev,
        weights)

    return ds


@toolz.memoize
def _prepare_spatial_weights_data(weights_file=None):
    """
    Rescales the pix_cent_x colum values

    Requires the :py:mod:`datafs` package.

    Parameters
    ----------
    weights_file: str
        location of file used for weighting


    .. note:: unnecessary if we can standardize our input
    """

    import datafs

    if weights_file is None:
        weights_file = WEIGHTS_FILE

        api = datafs.get_api()
        archive = api.get_archive(weights_file)

        with archive.open('r') as f:
            df = pd.read_csv(f)
    else:
        df = pd.read_csv(weights_file)

    # Re-label out-of-bounds pixel centers
    df.set_value((df['pix_cent_x'] == 180.125), 'pix_cent_x', -179.875)

    # probably totally unnecessary
    df.drop_duplicates()
    df.index.names = ['reshape_index']

    df.rename(
        columns={'pix_cent_x': 'lon', 'pix_cent_y': 'lat'},
        inplace=True)

    return df
