import matplotlib.pyplot as plt
from datetime import datetime
import numpy as np
import pandas as pd
import datacube as dc
import xarray as xr
import utils.data_cube_utilities.data_access_api as dc_api 
from utils.data_cube_utilities.dc_utilities import perform_timeseries_analysis
from utils.data_cube_utilities.dc_mosaic import ls7_unpack_qa
from rasterstats import zonal_stats
from scipy import stats
from scipy.stats import norm
import pylab
import matplotlib as mpl
from scipy.signal import gaussian
from scipy.ndimage import filters
from sklearn import linear_model
from scipy.interpolate import spline
import matplotlib.mlab as mlab
import matplotlib.ticker as ticker
from matplotlib.ticker import FuncFormatter
import calendar, datetime, time
import pytz
from matplotlib.colors import LinearSegmentedColormap

from scipy.interpolate import interp1d

def impute_missing_data_1D(data1D):
    """
    This function returns the data in the same format as it was 
    passed in, but with missing values either masked out or imputed with appropriate values 
    (currently only using a linear trend). Many linear plotting functions for 1D data often 
    (and should) only connect contiguous,  non-nan data points. This leaves gaps in the 
    piecewise linear plot, which are sometimes graphically undesirable.
    
    Parameters
    ----------
    data: numpy.ndarray
        A 1D NumPy array for which missing values are to be masked or imputed 
        suitably for at least matplotlib plotting. If formatting for other libraries such 
        as seaborn or plotly is necessary, add that formatting requirement as a parameter.
    """
    nan_mask = ~np.isnan(data1D)
    x = np.arange(len(data1D))
    x_no_nan = x[nan_mask]
    data_no_nan = data1D[nan_mask]
    if len(x_no_nan) >= 2:
        f = interp1d(x_no_nan, data_no_nan)
        # Select points for interpolation.
        interpolation_x_mask = (x_no_nan[0]<=x) & (x<=x_no_nan[-1])
        interpolation_x = x[interpolation_x_mask]
        data1D_interp = np.arange(len(data1D), dtype=np.float32)
        # The ends of data1D may contain NaNs that must be included.
        end_nan_inds = x[(x<=x_no_nan[0]) | (x_no_nan[-1]<=x)]
        data1D_interp[end_nan_inds] = np.nan
        data1D_interp[interpolation_x_mask] = f(interpolation_x)
        return data1D_interp
    else: # Cannot interpolate with a single non-nan point.
        return data1D

## Datetime functions ##

def n64_to_epoch(timestamp):
    ts = pd.to_datetime(str(timestamp)) 
    ts = ts.strftime('%Y-%m-%d')
    tz_UTC = pytz.timezone('UTC')
    time_format = "%Y-%m-%d"
    naive_timestamp = datetime.datetime.strptime(ts, time_format)
    aware_timestamp = tz_UTC.localize(naive_timestamp)
    epoch = aware_timestamp.strftime("%s")
    return (int) (epoch)

def np_dt64_to_str(np_datetime, fmt='%Y-%m-%d'):
    """Converts a NumPy datetime64 object to a string based on a format string supplied to pandas strftime."""
    return pd.to_datetime(str(np_datetime)).strftime(fmt)

def tfmt(x, pos=None):
    return time.strftime("%Y-%m-%d",time.gmtime(x))

## End datetime functions ##

## Matplotlib colormap functions ##

def create_discrete_color_map(th, colors, alpha, cmap_name='my_cmap'):
    """
    Creates a discrete matplotlib LinearSegmentedColormap with thresholds for color changes.
    
    Parameters
    ----------
    th: list
        Threshold values. Must be between 0.0 and 1.0 - noninclusive.
    colors: list
        Colors to use between thresholds, so `len(colors) == len(th)+1`.
        Colors can be string names of matplotlib colors or 3-tuples of rgb values.
    alpha: float
        The alpha values to use for the colors, so `len(alpha) == len(colors)`.
    cmap_name: str
        The name of the colormap for matplotlib.
    """
    import matplotlib as mpl
    th = [0.0] + th + [1.0]
    cdict = {}
    # These are fully-saturated red, green, and blue - not the matplotlib colors for 'red', 'green', and 'blue'.
    primary_colors = ['red', 'green', 'blue'] 
    # Get the 3-tuples of rgb values for the colors.
    color_rgbs = [(mpl.colors.to_rgb(color) if isinstance(color,str) else color) for color in colors]
    # For each color entry to go into the color dictionary...
    for primary_color_ind, primary_color in enumerate(primary_colors):
        cdict_entry = [None]*len(th)
        # For each threshold (as well as 0.0 and 1.0), specify the values for this primary color.
        for row_ind, th_ind in enumerate(range(len(th))):
            # Get the two colors that this threshold corresponds to.
            th_color_inds = [0,0] if th_ind==0 else \
                            [len(colors)-1, len(colors)-1] if th_ind==len(th)-1 else \
                            [th_ind-1, th_ind]
            primary_color_vals = [color_rgbs[th_color_ind][primary_color_ind] for th_color_ind in th_color_inds]
            cdict_entry[row_ind] = (th[th_ind],) + tuple(primary_color_vals)
        cdict[primary_color] = cdict_entry
    cmap = LinearSegmentedColormap(cmap_name, cdict)
    return cmap

## End matplotlib colormap functions ##

def regression_massage(ds): 
    t_len = len(ds["time"])
    s_len = len(ds["latitude"]) * len(ds["longitude"])
    flat_values = ds.values.reshape(t_len * s_len)
    return list(zip(list(map(n64_to_epoch, ds.time.values)),flat_values))

def remove_nans(aList):
    i = 0
    while i < len(aList):
        if np.isnan(aList[i][1]):
            del aList[i]
            i = 0
        else:
            i+=1
    return aList

def full_linear_regression(ds):
    myList = regression_massage(ds)
    myList = remove_nans(myList)
    myList = sorted(myList, key=lambda tup: tup[0])
    time, value = zip(*myList)
    value = [int(x) for x in value]
    value = np.array(value)
    value.astype(int)
    time = np.array(time)
    time.astype(int)
    return list(zip(time,value))
  
def xarray_plot_data_vars_over_time(dataset, frac_dates=None):
    """
    Plot all data variables in an xarray.Dataset on a shared set of axes. 
    The only dimension and coordinate must be 'time'.
    The `frac_dates` parameter determines the fraction of dates to show on the x axis.
    """
    data_var_names = list(dataset.data_vars)
    len_dataset = dataset.time.size
    nan_mask = np.full(len_dataset, True)
    for data_arr in dataset.data_vars.values():
        nan_mask = nan_mask & data_arr.notnull().values
        plt.plot(data_arr, marker='o')
    plt.legend(data_var_names)
    times = dataset.coords['time'].values
    date_strs = np.array(list(map(lambda time: np_dt64_to_str(time), times)))
    if frac_dates is None:
        frac_dates = min(10/len(date_strs), 1)
    plt.xticks(np.arange(0,len(date_strs))[nan_mask][::int(1/frac_dates)], date_strs[nan_mask][::int(1/frac_dates)], 
               rotation=45, ha='right', rotation_mode='anchor')
    plt.show()

def plot_band(landsat_dataset, dataset, figsize=(20,15), fontsize=24, legend_fontsize=24):
    """
    Plots several statistics over time - including mean, median, linear regression of the 
    means, Gaussian smoothed curve of means, and the band enclosing the 25th percentiles 
    and the 75th percentiles. This is very similar to the output of the Comet Time Series 
    Toolset (https://github.com/CosmiQ/CometTS). 
    
    Parameters
    ----------
    landsat_dataset: xarray.Dataset
        An xarray `Dataset` containing longitude, latitude, and time coordinates.
    dataset: xarray.DataArray
        An xarray `DataArray` containing time, latitude, and longitude coordinates.
    figsize: tuple
        A 2-tuple of the figure size in inches for the entire figure.
    fontsize: int
        The font size to use for text.
    """
    
    #Calculations
    times = dataset.time.values
    times = list(map(n64_to_epoch, times))
    times = np.array(times)
    times = np.sort(times)
    mean  = dataset.mean(dim=['latitude','longitude'],  skipna = True).values
    medians = dataset.median(dim=['latitude','longitude'], skipna = True)
    
    std_dev = np.nanstd(mean)
    plt.figure(figsize=figsize)
    ax = plt.gca()

    #Shaded Area
    quarter = np.nanpercentile(
    dataset.values.reshape((
        landsat_dataset.dims['time'],
        landsat_dataset.dims['latitude'] * landsat_dataset.dims['longitude'])),
        25,
        axis = 1
    )
    three_quarters = np.nanpercentile(
    dataset.values.reshape((
        landsat_dataset.dims['time'],
        landsat_dataset.dims['latitude'] * landsat_dataset.dims['longitude'])),
        75,
        axis = 1
    )
    np.array(quarter)
    np.array(three_quarters)
    ax.grid(color='lightgray', linestyle='-', linewidth=1)
    fillcolor1='gray'
    fillcolor2='brown'
    fillalpha=0.4
    plt.fill_between(times, mean, quarter,  interpolate=False, color=fillcolor1, alpha=fillalpha,label="25th")
    plt.fill_between(times, mean, three_quarters, interpolate=False, color=fillcolor1, alpha=fillalpha,label="75th")
        
    #Medians
    plt.plot(times,medians,color="black",marker="o",linestyle='None', label = "Medians")
    
    #Linear Regression (on everything)
    #Data formatted in a way for needed for Guassian and Linear Regression
    #regression_list = full_linear_regression(dataset)
    #formatted_time, value = zip(*regression_list)
    #formatted_time = np.array(formatted_time)
    
    #The Actual Plot
    plt.plot(times,mean,color="blue",label="Mean")

    #Linear Regression (on mean)
    m, b = np.polyfit(times, mean, 1)
    plt.plot(times, m*times + b, '-', color="red",label="linear regression of mean",linewidth = 3.0)

    #Gaussian Curve
    b = gaussian(len(times), std_dev)
    ga = filters.convolve1d(mean, b/b.sum(),mode="reflect")
    x_smooth = np.linspace(times.min(),times.max(), 200)
    y_smooth = spline(times, ga, x_smooth)
    plt.plot(x_smooth, y_smooth, '-',label="Gaussian Smoothed of mean", alpha=1, color='limegreen',linewidth = 3.0)
    
    
    #Formatting
    ax.grid(color='k', alpha=0.1, linestyle='-', linewidth=1)
    ax.xaxis.set_major_formatter(FuncFormatter(tfmt))
    plt.legend(loc='center left', bbox_to_anchor=(1, 0.5), fontsize=legend_fontsize)
    plt.xticks(rotation=45, fontsize=fontsize)
    plt.yticks(fontsize=fontsize)
    ax.set_xlabel('Time', fontsize=fontsize)
    ax.set_ylabel('Value', fontsize=fontsize)
    plt.show()

def plot_pixel_qa_value(dataset, platform, values_to_plot, bands = "pixel_qa", plot_max = False, plot_min = False):
    times = dataset.time.values
    mpl.style.use('seaborn')
    plt.figure(figsize=(20,15))
    quarters = []
    three_quarters = []
    percentiles = []
   
    for i,v in enumerate(values_to_plot):
        _xarray  = ls7_unpack_qa(dataset.pixel_qa, values_to_plot[i])
        y = _xarray.mean(dim= ['latitude', 'longitude'])
        times = dataset.time.values.astype(float)
        std_dev = np.std(y)
        std_dev = std_dev.values
        b = gaussian(len(times), std_dev)
        ga = filters.convolve1d(y, b/b.sum(),mode="reflect")
        ga=interpolate_gaps(ga, limit=3)
        plt.plot(times, ga, '-',label="Gaussian ", alpha=1, color='black')
        
        x_smooth = np.linspace(times.min(),times.max(), 200)
        y_smooth = spline(times, ga, x_smooth)
        plt.plot(x_smooth, y_smooth, '-',label="Gaussian Smoothed", alpha=1, color='cyan')
        
        for i, q in enumerate(_xarray):
            quarters.append(np.nanpercentile(_xarray, 25))
            three_quarters.append(np.nanpercentile(_xarray, 75))
            #print(q.values.mean())
        
        ax = plt.gca()
        ax.grid(color='lightgray', linestyle='-', linewidth=1)
        fillcolor='gray'
        fillalpha=0.4
        linecolor='gray'
        linealpha=0.6
        plt.fill_between(times, y, quarters,  interpolate=False, color=fillcolor, alpha=fillalpha)
        plt.fill_between(times, y, three_quarters, interpolate=False, color=fillcolor, alpha=fillalpha)
        plt.plot(times,quarters,color=linecolor , alpha=linealpha)
        plt.plot(times,three_quarters,color=linecolor, alpha=linealpha)
        
        medians = _xarray.median(dim=['latitude','longitude'])
        plt.scatter(times,medians,color='mediumpurple', label="medians", marker="D")
        
        m, b = np.polyfit(times, y, 1)
        plt.plot(times, m*times + b, '-', color="red",label="linear regression")
        plt.style.use('seaborn')
        
        plt.plot(times, y, marker="o")
        plt.legend(loc='center left', bbox_to_anchor=(1, 0.5))
        plt.xticks(rotation=90)    