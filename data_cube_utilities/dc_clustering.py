from datetime import datetime
from sklearn.manifold import TSNE
from sklearn.cluster import KMeans, AgglomerativeClustering, DBSCAN, Birch
import numpy as np
from collections import OrderedDict
import xarray as xr
import matplotlib.pyplot as plt

def clustering_pre_processing(dataset_in, bands):
    array_from = []
    for band in bands:
        array_from.append(dataset_in[band].values.flatten())

    np_array = np.array(array_from)
    np_array = np.swapaxes(np_array, 0, 1)

    np.set_printoptions(suppress=True)
    return array_from, np_array

def clustering_post_processing(classified, dataset_in, bands):
    classified_data = OrderedDict()

    classification = classified.labels_.reshape((dataset_in[bands[0]].shape[0], dataset_in[bands[0]].shape[1]))
    classified_data['classification'] = (['latitude', 'longitude'], classification)

    dataset_out = xr.Dataset(
        classified_data, coords={'latitude': dataset_in.latitude,
                                 'longitude': dataset_in.longitude})
    return dataset_out

def kmeans_cluster_dataset(dataset_in, bands=['red', 'green', 'blue', 'swir1', 'swir2', 'nir'], n_clusters=4):
    array_from, np_array = clustering_pre_processing(dataset_in, bands)
    """
    classified = AgglomerativeClustering(n_clusters=n_clusters).fit(np_array)
    classified = Birch(n_clusters=n_clusters).fit(np_array)
    classified = DBSCAN(eps=0.005, min_samples=5, n_jobs=-1).fit(np_array)
    """    
    classified = KMeans(n_clusters=n_clusters, n_jobs=-1).fit(np_array)
    return clustering_post_processing(classified, dataset_in, bands)

def birch_cluster_dataset(dataset_in, bands=['red', 'green', 'blue', 'swir1', 'swir2', 'nir'], n_clusters=4):
    array_from, np_array = clustering_pre_processing(dataset_in, bands)
    """
    classified = AgglomerativeClustering(n_clusters=n_clusters, n_jobs=-1).fit(np_array)
    classified = DBSCAN(eps=0.005, min_samples=5, n_jobs=-1).fit(np_array)
    classified = KMeans(n_clusters=n_clusters, n_jobs=-1).fit(np_array)
    """  
    classified = Birch(n_clusters=n_clusters, threshold=0.00001).fit(np_array)
    return clustering_post_processing(classified, dataset_in, bands)

def plot_kmeans_next_to_mosaic(da_a, da_b):  
    def mod_rgb(dataset,
        at_index = 0,
        bands = ['red', 'green', 'blue'],
        paint_on_mask = [],
        max_possible = 3500,
        width = 10
       ):    
        ### < Dataset to RGB Format, needs float values between 0-1 
        rgb = np.stack([dataset[bands[0]],
                        dataset[bands[1]],
                        dataset[bands[2]]], axis = -1).astype(np.int16)

        rgb[rgb<0] = 0    
        rgb[rgb > max_possible] = max_possible # Filter out saturation points at arbitrarily defined max_possible value

        rgb = rgb.astype(float)
        rgb *= 1 / np.max(rgb)
        ### > 

        ### < takes a T/F mask, apply a color to T areas  
        for mask, color in paint_on_mask:        
            rgb[mask] = np.array(color)/ 255.0
        ### > 

        if 'time' in dataset:
            plt.imshow((rgb[at_index]))
        else:
            plt.imshow(rgb)  

    fig = plt.figure(figsize =  (15,8))
    a=fig.add_subplot(1,2,1) 
    a.set_title('Kmeans')
    plt.imshow(da_a.values, cmap = "magma_r")

    b=fig.add_subplot(1,2,2)
    mod_rgb(da_b)
    b.set_title('RGB Composite')
