# -*- coding: utf-8 -*-

"""
PySEBAL_dev_v3.8

@author: Tim Hessels, Jonna van Opstal, Patricia Trambauer, Wim Bastiaanssen, Mohamed Faouzi Smiej, Yasir Mohamed, and Ahmed Er-Raji
         UNESCO-IHE
         September 2017

@author Sajid Pareeth
        February 2020

@author Muddasir Shah        
		January 2026
"""
#import pdb
import platform
import sys
import os
import re
import shutil
import numpy as np
import datetime
from osgeo import osr  
from osgeo import gdal  
from math import sin, cos, pi, tan
import time
import subprocess
import numpy.polynomial.polynomial as poly	
# from openpyxl import load_workbook  # NO LONGER NEEDED - USING CONFIG OBJECT
from pyproj import Proj, transform
import warnings
import ee
import requests

def get_landsat_scenes_timeseries(latitude, longitude, buffer_km, start_date, end_date, cloud_cover_max=20):
    """
    Get all available Landsat 8 & 9 scenes for a time period (merged collection)
    
    Returns list of scenes with metadata:
    [{'id': 'LC08_...', 'date': '2024-11-15', 'cloud_cover': 5.2, 'satellite': 'L8'}, ...]
    """
    # Initialize EE
    try:
        ee.data.getInfo(ee.Image(0))
    except:
        service_account = "" #Earth Engine Service Account ID Here 
        gee_key_path = os.path.join(os.path.dirname(__file__), "gee_key.json") # GEE API JSON Key 
        if os.path.exists(gee_key_path):
            credentials = ee.ServiceAccountCredentials(service_account, gee_key_path)
            ee.Initialize(credentials)
        else:
            print("ERROR: GEE key file not found!")
            return []
    
    buffer_meters = buffer_km * 1000
    point = ee.Geometry.Point([longitude, latitude])
    buffer_region = point.buffer(buffer_meters)
    
    # Merge Landsat 8 and Landsat 9 collections
    landsat8 = ee.ImageCollection("LANDSAT/LC08/C02/T1") \
        .filterBounds(buffer_region) \
        .filterDate(start_date, end_date) \
        .filter(ee.Filter.lt('CLOUD_COVER', cloud_cover_max))
    
    landsat9 = ee.ImageCollection("LANDSAT/LC09/C02/T1") \
        .filterBounds(buffer_region) \
        .filterDate(start_date, end_date) \
        .filter(ee.Filter.lt('CLOUD_COVER', cloud_cover_max))
    
    # Merge collections
    merged = landsat8.merge(landsat9).sort('system:time_start')
    
    # Get scene list
    scene_list = merged.toList(merged.size())
    count = scene_list.size().getInfo()
    
    if count == 0:
        return []
    
    scenes = []
    for i in range(count):
        image = ee.Image(scene_list.get(i))
        props = image.getInfo()['properties']
        
        scene_id = props.get('LANDSAT_SCENE_ID', props.get('LANDSAT_PRODUCT_ID', 'Unknown'))
        date_str = props.get('DATE_ACQUIRED', 'Unknown')
        cloud_cover = props.get('CLOUD_COVER', 0)
        satellite = 'L8' if 'LC8' in scene_id else 'L9'
        scene_time = props.get('SCENE_CENTER_TIME', '12:00:00.0000000Z')  # Get actual acquisition time
        
        scenes.append({
            'id': scene_id,
            'date': date_str,
            'cloud_cover': cloud_cover,
            'satellite': satellite,
            'scene_time': scene_time,  # Store scene center time
            'ee_image': image
        })
    
    return scenes


def download_hihydrosoil_data(poi_folder, latitude, longitude, buffer_km):
    """
    Download HiHydroSoil soil property rasters for the POI location
    
    Returns dict with soil raster file paths or None if failed
    """
    # Initialize EE
    try:
        ee.data.getInfo(ee.Image(0))
    except:
        service_account = "ndma-agriportal-sa@ee-muddasir-shah.iam.gserviceaccount.com"
        gee_key_path = os.path.join(os.path.dirname(__file__), "gee_key.json")
        if os.path.exists(gee_key_path):
            credentials = ee.ServiceAccountCredentials(service_account, gee_key_path)
            ee.Initialize(credentials)
        else:
            print("ERROR: GEE key file not found!")
            return None
    
    buffer_meters = buffer_km * 1000
    point = ee.Geometry.Point([longitude, latitude])
    buffer_region = point.buffer(buffer_meters)
    
    try:
        print('Downloading HiHydroSoil soil property rasters (one-time)...')
        
        # HiHydroSoil dataset collections (scale factor: 0.0001)
        scale_factor = 0.0001
        
        # Define soil datasets to download
        soil_datasets = {
            'wcsat': 'projects/sat-io/open-datasets/HiHydroSoilv2_0/wcsat',  # Saturation
            'wcres': 'projects/sat-io/open-datasets/HiHydroSoilv2_0/wcres',  # Residual
            'crit_wilt': 'projects/sat-io/open-datasets/HiHydroSoilv2_0/crit-wilt',  # Wilting point
            'sat_field': 'projects/sat-io/open-datasets/HiHydroSoilv2_0/sat-field'  # Field capacity
        }
        
        soil_files = {}
        
        for name, dataset_path in soil_datasets.items():
            soil_file = os.path.join(poi_folder, f'HiHydroSoil_{name}.tif')
            
            # Skip if already exists
            if os.path.exists(soil_file):
                print(f'  ✓ {name} already exists')
                soil_files[name] = soil_file
                continue
            
            try:
                print(f'  Downloading {name}...')
                
                # Load and apply scale factor
                soil_image = ee.ImageCollection(dataset_path).mosaic().multiply(scale_factor)
                soil_clipped = soil_image.clip(buffer_region)
                
                # Download
                soil_url = soil_clipped.getDownloadUrl({
                    'region': buffer_region,
                    'scale': 250,  # HiHydroSoil native resolution
                    'format': 'GEO_TIFF',
                    'name': f'HiHydroSoil_{name}'
                })
                
                response = requests.get(soil_url, timeout=300)
                with open(soil_file, 'wb') as f:
                    f.write(response.content)
                
                soil_files[name] = soil_file
                print(f'  ✓ {name} downloaded')
                
            except Exception as e:
                print(f'  Warning: Could not download {name}: {str(e)}')
                soil_files[name] = None
        
        # Check if we got all required files
        if all(soil_files.values()):
            print('✓ All HiHydroSoil rasters downloaded')
            return soil_files
        else:
            print('Warning: Some soil rasters failed to download')
            return soil_files if any(soil_files.values()) else None
        
    except Exception as e:
        print(f'Error downloading HiHydroSoil data: {str(e)}')
        print('Will use default soil parameters')
        return None


def download_dem_once(poi_folder, latitude, longitude, buffer_km):
    """
    Download SRTM DEM once for the entire POI (reused across all scenes)
    
    Returns path to DEM file
    """
    # Initialize EE
    try:
        ee.data.getInfo(ee.Image(0))
    except:
        service_account = "ndma-agriportal-sa@ee-muddasir-shah.iam.gserviceaccount.com"
        gee_key_path = os.path.join(os.path.dirname(__file__), "gee_key.json")
        if os.path.exists(gee_key_path):
            credentials = ee.ServiceAccountCredentials(service_account, gee_key_path)
            ee.Initialize(credentials)
        else:
            print("ERROR: GEE key file not found!")
            return None
    
    buffer_meters = buffer_km * 1000
    point = ee.Geometry.Point([longitude, latitude])
    buffer_region = point.buffer(buffer_meters)
    
    # DEM saved at POI root level (shared by all scenes)
    dem_file = os.path.join(poi_folder, 'SRTM_DEM.tif')
    
    if os.path.exists(dem_file):
        print(f'✓ DEM already exists: {dem_file}')
        return dem_file
    
    try:
        print('Downloading SRTM DEM (one-time, shared across all scenes)...')
        srtm = ee.Image("USGS/SRTMGL1_003")
        srtm_clipped = srtm.clip(buffer_region)
        
        dem_url = srtm_clipped.getDownloadUrl({
            'region': buffer_region,
            'scale': 30,
            'format': 'GEO_TIFF',
            'name': 'SRTM_DEM'
        })
        
        response = requests.get(dem_url, timeout=300)
        with open(dem_file, 'wb') as f:
            f.write(response.content)
        print(f'✓ DEM downloaded: {dem_file}')
        return dem_file
        
    except Exception as e:
        print(f'ERROR downloading DEM: {str(e)}')
        return None


def generate_mtl_file(mtl_file, metadata, scene_id, longitude):
    """Generate MTL metadata file from GEE metadata"""
    with open(mtl_file, 'w') as f:
        f.write("GROUP = L1_METADATA_FILE\n")
        
        # METADATA_FILE_INFO group
        f.write("  GROUP = METADATA_FILE_INFO\n")
        f.write(f"    ORIGIN = \"Image courtesy of the U.S. Geological Survey\"\n")
        f.write(f"    REQUEST_ID = \"{metadata.get('REQUEST_ID', 'GEE_DOWNLOAD')}\"\n")
        f.write(f"    LANDSAT_SCENE_ID = \"{scene_id}\"\n")
        f.write(f"    LANDSAT_PRODUCT_ID = \"{metadata.get('LANDSAT_PRODUCT_ID', scene_id)}\"\n")
        f.write(f"    COLLECTION_NUMBER = {metadata.get('COLLECTION_NUMBER', 2):02d}\n")
        f.write(f"    STATION_ID = \"{metadata.get('STATION_ID', 'LGN')}\"\n")
        f.write(f"    PROCESSING_SOFTWARE_VERSION = \"{metadata.get('PROCESSING_SOFTWARE_VERSION', 'LPGS_16.5.0')}\"\n")
        f.write("  END_GROUP = METADATA_FILE_INFO\n")
        
        # PRODUCT_METADATA group
        f.write("  GROUP = PRODUCT_METADATA\n")
        f.write(f"    DATA_TYPE = \"L1TP\"\n")
        f.write(f"    COLLECTION_CATEGORY = \"{metadata.get('COLLECTION_CATEGORY', 'T1')}\"\n")
        f.write(f"    ELEVATION_SOURCE = \"{metadata.get('DATA_SOURCE_ELEVATION', 'GLS2000')}\"\n")
        f.write(f"    OUTPUT_FORMAT = \"GEOTIFF\"\n")
        f.write(f"    SPACECRAFT_ID = \"{metadata.get('SPACECRAFT_ID', 'LANDSAT_8')}\"\n")
        f.write(f"    SENSOR_ID = \"{metadata.get('SENSOR_ID', 'OLI_TIRS')}\"\n")
        f.write(f"    WRS_PATH = {metadata.get('WRS_PATH', 0)}\n")
        f.write(f"    WRS_ROW = {metadata.get('WRS_ROW', 0)}\n")
        f.write(f"    NADIR_OFFNADIR = \"{metadata.get('NADIR_OFFNADIR', 'NADIR')}\"\n")
        f.write(f"    TARGET_WRS_PATH = {metadata.get('TARGET_WRS_PATH', metadata.get('WRS_PATH', 0))}\n")
        f.write(f"    TARGET_WRS_ROW = {metadata.get('TARGET_WRS_ROW', metadata.get('WRS_ROW', 0))}\n")
        f.write(f"    DATE_ACQUIRED = {metadata.get('DATE_ACQUIRED', '2000-01-01')}\n")
        f.write(f"    SCENE_CENTER_TIME = \"{metadata.get('SCENE_CENTER_TIME', '00:00:00.0000000Z')}\"\n")
        f.write(f"    PANCHROMATIC_LINES = {metadata.get('PANCHROMATIC_LINES', 0)}\n")
        f.write(f"    PANCHROMATIC_SAMPLES = {metadata.get('PANCHROMATIC_SAMPLES', 0)}\n")
        f.write(f"    REFLECTIVE_LINES = {metadata.get('REFLECTIVE_LINES', 0)}\n")
        f.write(f"    REFLECTIVE_SAMPLES = {metadata.get('REFLECTIVE_SAMPLES', 0)}\n")
        f.write(f"    THERMAL_LINES = {metadata.get('THERMAL_LINES', 0)}\n")
        f.write(f"    THERMAL_SAMPLES = {metadata.get('THERMAL_SAMPLES', 0)}\n")
        for i in range(1, 12):
            f.write(f"    FILE_NAME_BAND_{i} = \"{scene_id}_B{i}.TIF\"\n")
        f.write(f"    FILE_NAME_BAND_QUALITY = \"{scene_id}_BQA.TIF\"\n")
        f.write(f"    ANGLE_COEFFICIENT_FILE_NAME = \"{scene_id}_ANG.txt\"\n")
        f.write(f"    METADATA_FILE_NAME = \"{scene_id}_MTL.txt\"\n")
        f.write("  END_GROUP = PRODUCT_METADATA\n")
        
        # IMAGE_ATTRIBUTES group
        f.write("  GROUP = IMAGE_ATTRIBUTES\n")
        f.write(f"    CLOUD_COVER = {metadata.get('CLOUD_COVER_LAND', 0.0):.2f}\n")
        f.write(f"    CLOUD_COVER_LAND = {metadata.get('CLOUD_COVER_LAND', 0.0):.2f}\n")
        f.write(f"    IMAGE_QUALITY_OLI = {metadata.get('IMAGE_QUALITY_OLI', 9)}\n")
        f.write(f"    IMAGE_QUALITY_TIRS = {metadata.get('IMAGE_QUALITY_TIRS', 9)}\n")
        f.write(f"    ROLL_ANGLE = {metadata.get('ROLL_ANGLE', 0.0)}\n")
        f.write(f"    SUN_AZIMUTH = {metadata.get('SUN_AZIMUTH', 0.0):.8f}\n")
        f.write(f"    SUN_ELEVATION = {metadata.get('SUN_ELEVATION', 0.0):.8f}\n")
        f.write(f"    EARTH_SUN_DISTANCE = {metadata.get('EARTH_SUN_DISTANCE', 1.0):.7f}\n")
        f.write("  END_GROUP = IMAGE_ATTRIBUTES\n")
        
        # MIN_MAX_RADIANCE, REFLECTANCE, and other groups
        f.write("  GROUP = MIN_MAX_RADIANCE\n")
        for i in range(1, 12):
            mult = metadata.get(f'RADIANCE_MULT_BAND_{i}', 0.0)
            add = metadata.get(f'RADIANCE_ADD_BAND_{i}', 0.0)
            f.write(f"    RADIANCE_MAXIMUM_BAND_{i} = {(65535 * mult) + add:.5f}\n")
        for i in range(1, 12):
            mult = metadata.get(f'RADIANCE_MULT_BAND_{i}', 0.0)
            add = metadata.get(f'RADIANCE_ADD_BAND_{i}', 0.0)
            f.write(f"    RADIANCE_MINIMUM_BAND_{i} = {(1 * mult) + add:.5f}\n")
        f.write("  END_GROUP = MIN_MAX_RADIANCE\n")
        
        f.write("  GROUP = MIN_MAX_REFLECTANCE\n")
        for i in range(1, 10):
            mult = metadata.get(f'REFLECTANCE_MULT_BAND_{i}', 2.0E-05)
            add = metadata.get(f'REFLECTANCE_ADD_BAND_{i}', -0.1)
            f.write(f"    REFLECTANCE_MAXIMUM_BAND_{i} = {(65535 * mult) + add:.6f}\n")
        for i in range(1, 10):
            mult = metadata.get(f'REFLECTANCE_MULT_BAND_{i}', 2.0E-05)
            add = metadata.get(f'REFLECTANCE_ADD_BAND_{i}', -0.1)
            f.write(f"    REFLECTANCE_MINIMUM_BAND_{i} = {(1 * mult) + add:.6f}\n")
        f.write("  END_GROUP = MIN_MAX_REFLECTANCE\n")
        
        f.write("  GROUP = MIN_MAX_PIXEL_VALUE\n")
        for i in range(1, 12):
            f.write(f"    QUANTIZE_CAL_MAX_BAND_{i} = 65535\n")
        for i in range(1, 12):
            f.write(f"    QUANTIZE_CAL_MIN_BAND_{i} = 1\n")
        f.write("  END_GROUP = MIN_MAX_PIXEL_VALUE\n")
        
        f.write("  GROUP = RADIOMETRIC_RESCALING\n")
        for i in range(1, 12):
            f.write(f"    RADIANCE_MULT_BAND_{i} = {metadata.get(f'RADIANCE_MULT_BAND_{i}', 0.0):.4E}\n")
        for i in range(1, 12):
            f.write(f"    RADIANCE_ADD_BAND_{i} = {metadata.get(f'RADIANCE_ADD_BAND_{i}', 0.0):.5f}\n")
        for i in range(1, 10):
            f.write(f"    REFLECTANCE_MULT_BAND_{i} = {metadata.get(f'REFLECTANCE_MULT_BAND_{i}', 2.0E-05):.4E}\n")
        for i in range(1, 10):
            f.write(f"    REFLECTANCE_ADD_BAND_{i} = {metadata.get(f'REFLECTANCE_ADD_BAND_{i}', -0.1):.6f}\n")
        f.write("  END_GROUP = RADIOMETRIC_RESCALING\n")
        
        f.write("  GROUP = TIRS_THERMAL_CONSTANTS\n")
        f.write(f"    K1_CONSTANT_BAND_10 = {metadata.get('K1_CONSTANT_BAND_10', 774.8853):.4f}\n")
        f.write(f"    K2_CONSTANT_BAND_10 = {metadata.get('K2_CONSTANT_BAND_10', 1321.0789):.4f}\n")
        f.write(f"    K1_CONSTANT_BAND_11 = {metadata.get('K1_CONSTANT_BAND_11', 480.8883):.4f}\n")
        f.write(f"    K2_CONSTANT_BAND_11 = {metadata.get('K2_CONSTANT_BAND_11', 1201.1442):.4f}\n")
        f.write("  END_GROUP = TIRS_THERMAL_CONSTANTS\n")
        
        f.write("  GROUP = PROJECTION_PARAMETERS\n")
        f.write(f"    MAP_PROJECTION = \"UTM\"\n")
        f.write(f"    DATUM = \"WGS84\"\n")
        f.write(f"    ELLIPSOID = \"WGS84\"\n")
        f.write(f"    UTM_ZONE = {metadata.get('UTM_ZONE', int((longitude + 180) / 6) + 1)}\n")
        f.write("  END_GROUP = PROJECTION_PARAMETERS\n")
        
        f.write("END_GROUP = L1_METADATA_FILE\n")
        f.write("END\n")


def download_specific_scene(scene_id, input_folder, latitude, longitude, buffer_km):
    """
    Download a specific Landsat scene (8 or 9) and SRTM DEM
    
    Returns True if successful, False otherwise
    """
    import glob
    
    # CRITICAL: Check if a DIFFERENT scene already exists in this folder
    # This prevents mixing bands from multiple scenes in the same folder
    existing_mtl = glob.glob(os.path.join(input_folder, 'LC*_MTL.txt'))
    if existing_mtl:
        existing_scene = os.path.basename(existing_mtl[0]).replace('_MTL.txt', '')
        if existing_scene != scene_id:
            print(f"  WARNING: Folder contains different scene: {existing_scene}")
            print(f"  Cleaning folder before downloading {scene_id}...")
            # Remove all existing Landsat files (bands + MTL) to prevent mixing
            for old_file in glob.glob(os.path.join(input_folder, 'LC*.*')):
                try:
                    os.remove(old_file)
                except Exception as e:
                    print(f"    Error removing {old_file}: {e}")
            print("  ✓ Folder cleaned")
    
    # Initialize EE
    try:
        ee.data.getInfo(ee.Image(0))
    except:
        service_account = "ndma-agriportal-sa@ee-muddasir-shah.iam.gserviceaccount.com"
        gee_key_path = os.path.join(os.path.dirname(__file__), "gee_key.json")
        if os.path.exists(gee_key_path):
            credentials = ee.ServiceAccountCredentials(service_account, gee_key_path)
            ee.Initialize(credentials)
        else:
            print("  ERROR: GEE key file not found!")
            return False
    
    buffer_meters = buffer_km * 1000
    point = ee.Geometry.Point([longitude, latitude])
    buffer_region = point.buffer(buffer_meters)
    
    try:
        # Determine if Landsat 8 or 9 (scene IDs use LC8 and LC9, not LC08/LC09)
        if 'LC8' in scene_id:
            collection = ee.ImageCollection("LANDSAT/LC08/C02/T1")
        elif 'LC9' in scene_id:
            collection = ee.ImageCollection("LANDSAT/LC09/C02/T1")
        else:
            print(f"  ERROR: Unknown satellite type in scene ID: {scene_id}")
            return False
        
        # Find the specific scene
        image = collection.filter(ee.Filter.eq('LANDSAT_SCENE_ID', scene_id)).first()
        
        image_info = image.getInfo()
        if image_info is None:
            print(f'  ERROR: Scene {scene_id} not found')
            return False
        
        # Get metadata
        metadata = image_info['properties']
        
        # Download Landsat bands (only essential ones for SEBAL) (only essential ones for SEBAL)
        # Required: B1-B7 (optical), B10-B11 (thermal), QA (quality)
        # Skip: B8 (panchromatic), B9 (cirrus), VAA, VZA, SAA, SZA (angle bands)
        essential_bands = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B10', 'B11', 'QA_PIXEL']
        
        bands = image.bandNames().getInfo()
        bands_to_download = [b for b in bands if any(essential in b for essential in essential_bands)]
        
        landsat_clipped = image.clip(buffer_region)
        
        print(f'    Downloading {len(bands_to_download)} essential bands (skipping angles)...')
        for band in bands_to_download:
            band_file = os.path.join(input_folder, f'{scene_id}_{band}.TIF')
            
            if os.path.exists(band_file):
                continue
            
            try:
                band_image = landsat_clipped.select(band)
                band_url = band_image.getDownloadUrl({
                    'region': buffer_region,
                    'scale': 30,
                    'format': 'GEO_TIFF',
                    'name': f'{scene_id}_{band}'
                })
                
                response = requests.get(band_url, timeout=300)
                with open(band_file, 'wb') as f:
                    f.write(response.content)
            except Exception as e:
                print(f'    Warning: Could not download {band}: {str(e)}')
        
        print('    ✓ All bands downloaded')
        
        # Generate MTL file with metadata
        mtl_file = os.path.join(input_folder, f'{scene_id}_MTL.txt')
        if not os.path.exists(mtl_file):
            generate_mtl_file(mtl_file, metadata, scene_id, longitude)
            print('    ✓ MTL file generated')
        
        return True
        
    except Exception as e:
        print(f'  ERROR downloading scene: {str(e)}')
        return False


def download_gee_data(input_folder, latitude, longitude, buffer_km=5):
    """Download Landsat 8 and SRTM data from Google Earth Engine to input_folder"""
    
    # Initialize EE if not already initialized
    try:
        ee.data.getInfo(ee.Image(0))
    except:
        service_account = "ndma-agriportal-sa@ee-muddasir-shah.iam.gserviceaccount.com"
        gee_key_path = os.path.join(os.path.dirname(__file__), "gee_key.json")
        if os.path.exists(gee_key_path):
            credentials = ee.ServiceAccountCredentials(service_account, gee_key_path)
            ee.Initialize(credentials)
        else:
            print("GEE key file not found. Skipping GEE data download.")
            return False
    
    # Create input folder if needed
    if not os.path.exists(input_folder):
        os.makedirs(input_folder)
    
    buffer_meters = buffer_km * 1000
    point = ee.Geometry.Point([longitude, latitude])
    buffer_region = point.buffer(buffer_meters)
    
    print('\n--- Downloading data from Google Earth Engine ---')
    
    # Download SRTM DEM
    print('Downloading SRTM DEM...')
    try:
        srtm = ee.Image("USGS/SRTMGL1_003")
        srtm_clipped = srtm.clip(buffer_region)
        
        dem_url = srtm_clipped.getDownloadUrl({
            'region': buffer_region,
            'scale': 30,
            'format': 'GEO_TIFF',
            'name': 'SRTM_DEM'
        })
        
        dem_file = os.path.join(input_folder, 'SRTM_DEM.tif')
        response = requests.get(dem_url, timeout=300)
        with open(dem_file, 'wb') as f:
            f.write(response.content)
        print('  ✓ SRTM DEM downloaded')
    except Exception as e:
        print(f'  Error downloading DEM: {str(e)}')
    
    # Download Landsat 8 bands
    print('Downloading Landsat 8 bands...')
    try:
        landsat_collection = ee.ImageCollection("LANDSAT/LC08/C02/T1")
        
        filtered = landsat_collection \
            .filterBounds(buffer_region) \
            .filterDate('2025-12-01', '2026-01-10') \
            .filter(ee.Filter.lt('CLOUD_COVER', 10)) \
            .first()
        
        image_info = filtered.getInfo()
        if image_info is None:
            print('  No Landsat 8 image found')
            return False
        
        scene_id = filtered.get("LANDSAT_SCENE_ID").getInfo()
        print(f'  Found Landsat scene: {scene_id}')
        
        # Get ALL metadata properties from GEE
        metadata = filtered.getInfo()['properties']
        
        # Download all bands
        bands = filtered.bandNames().getInfo()
        landsat_clipped = filtered.clip(buffer_region)
        
        for band in bands:
            band_file = os.path.join(input_folder, f'{scene_id}_{band}.TIF')
            
            # Skip if already exists
            if os.path.exists(band_file):
                print(f'  ✓ {band} already exists')
                continue
            
            try:
                band_image = landsat_clipped.select(band)
                band_url = band_image.getDownloadUrl({
                    'region': buffer_region,
                    'scale': 30,
                    'format': 'GEO_TIFF',
                    'name': f'{scene_id}_{band}'
                })
                
                response = requests.get(band_url, timeout=300)
                with open(band_file, 'wb') as f:
                    f.write(response.content)
                print(f'  ✓ {band} downloaded')
                time.sleep(1)  # Rate limiting
            except Exception as e:
                print(f'  Error downloading {band}: {str(e)}')
        
        # Generate MTL.txt file from GEE metadata - match exact Landsat format
        print('  Creating MTL metadata file from GEE properties...')
        mtl_file = os.path.join(input_folder, f'{scene_id}_MTL.txt')
        
        with open(mtl_file, 'w') as f:
            f.write("GROUP = L1_METADATA_FILE\n")
            
            # METADATA_FILE_INFO group
            f.write("  GROUP = METADATA_FILE_INFO\n")
            f.write(f"    ORIGIN = \"Image courtesy of the U.S. Geological Survey\"\n")
            f.write(f"    REQUEST_ID = \"{metadata.get('REQUEST_ID', 'GEE_DOWNLOAD')}\"\n")
            f.write(f"    LANDSAT_SCENE_ID = \"{scene_id}\"\n")
            f.write(f"    LANDSAT_PRODUCT_ID = \"{metadata.get('LANDSAT_PRODUCT_ID', scene_id)}\"\n")
            f.write(f"    COLLECTION_NUMBER = {metadata.get('COLLECTION_NUMBER', 2):02d}\n")
            f.write(f"    STATION_ID = \"{metadata.get('STATION_ID', 'LGN')}\"\n")
            f.write(f"    PROCESSING_SOFTWARE_VERSION = \"{metadata.get('PROCESSING_SOFTWARE_VERSION', 'LPGS_16.5.0')}\"\n")
            f.write("  END_GROUP = METADATA_FILE_INFO\n")
            
            # PRODUCT_METADATA group
            f.write("  GROUP = PRODUCT_METADATA\n")
            f.write(f"    DATA_TYPE = \"L1TP\"\n")
            f.write(f"    COLLECTION_CATEGORY = \"{metadata.get('COLLECTION_CATEGORY', 'T1')}\"\n")
            f.write(f"    ELEVATION_SOURCE = \"{metadata.get('DATA_SOURCE_ELEVATION', 'GLS2000')}\"\n")
            f.write(f"    OUTPUT_FORMAT = \"GEOTIFF\"\n")
            f.write(f"    SPACECRAFT_ID = \"{metadata.get('SPACECRAFT_ID', 'LANDSAT_8')}\"\n")
            f.write(f"    SENSOR_ID = \"{metadata.get('SENSOR_ID', 'OLI_TIRS')}\"\n")
            f.write(f"    WRS_PATH = {metadata.get('WRS_PATH', 0)}\n")
            f.write(f"    WRS_ROW = {metadata.get('WRS_ROW', 0)}\n")
            f.write(f"    NADIR_OFFNADIR = \"{metadata.get('NADIR_OFFNADIR', 'NADIR')}\"\n")
            f.write(f"    TARGET_WRS_PATH = {metadata.get('TARGET_WRS_PATH', metadata.get('WRS_PATH', 0))}\n")
            f.write(f"    TARGET_WRS_ROW = {metadata.get('TARGET_WRS_ROW', metadata.get('WRS_ROW', 0))}\n")
            f.write(f"    DATE_ACQUIRED = {metadata.get('DATE_ACQUIRED', '2000-01-01')}\n")
            f.write(f"    SCENE_CENTER_TIME = \"{metadata.get('SCENE_CENTER_TIME', '00:00:00.0000000Z')}\"\n")
            f.write(f"    PANCHROMATIC_LINES = {metadata.get('PANCHROMATIC_LINES', 0)}\n")
            f.write(f"    PANCHROMATIC_SAMPLES = {metadata.get('PANCHROMATIC_SAMPLES', 0)}\n")
            f.write(f"    REFLECTIVE_LINES = {metadata.get('REFLECTIVE_LINES', 0)}\n")
            f.write(f"    REFLECTIVE_SAMPLES = {metadata.get('REFLECTIVE_SAMPLES', 0)}\n")
            f.write(f"    THERMAL_LINES = {metadata.get('THERMAL_LINES', 0)}\n")
            f.write(f"    THERMAL_SAMPLES = {metadata.get('THERMAL_SAMPLES', 0)}\n")
            for i in range(1, 12):
                f.write(f"    FILE_NAME_BAND_{i} = \"{scene_id}_B{i}.TIF\"\n")
            f.write(f"    FILE_NAME_BAND_QUALITY = \"{scene_id}_BQA.TIF\"\n")
            f.write(f"    ANGLE_COEFFICIENT_FILE_NAME = \"{scene_id}_ANG.txt\"\n")
            f.write(f"    METADATA_FILE_NAME = \"{scene_id}_MTL.txt\"\n")
            f.write("  END_GROUP = PRODUCT_METADATA\n")
            
            # IMAGE_ATTRIBUTES group
            f.write("  GROUP = IMAGE_ATTRIBUTES\n")
            f.write(f"    CLOUD_COVER = {metadata.get('CLOUD_COVER_LAND', 0.0):.2f}\n")
            f.write(f"    CLOUD_COVER_LAND = {metadata.get('CLOUD_COVER_LAND', 0.0):.2f}\n")
            f.write(f"    IMAGE_QUALITY_OLI = {metadata.get('IMAGE_QUALITY_OLI', 9)}\n")
            f.write(f"    IMAGE_QUALITY_TIRS = {metadata.get('IMAGE_QUALITY_TIRS', 9)}\n")
            f.write(f"    TIRS_SSM_MODEL = \"{metadata.get('TIRS_SSM_MODEL', 'FINAL')}\"\n")
            f.write(f"    TIRS_SSM_POSITION_STATUS = \"{metadata.get('TIRS_SSM_POSITION_STATUS', 'ESTIMATED')}\"\n")
            if 'DATA_SOURCE_TIRS_STRAY_LIGHT_CORRECTION' in metadata:
                f.write(f"    TIRS_STRAY_LIGHT_CORRECTION_SOURCE = \"{metadata.get('DATA_SOURCE_TIRS_STRAY_LIGHT_CORRECTION')}\"\n")
            f.write(f"    ROLL_ANGLE = {metadata.get('ROLL_ANGLE', 0.0)}\n")
            f.write(f"    SUN_AZIMUTH = {metadata.get('SUN_AZIMUTH', 0.0):.8f}\n")
            f.write(f"    SUN_ELEVATION = {metadata.get('SUN_ELEVATION', 0.0):.8f}\n")
            f.write(f"    EARTH_SUN_DISTANCE = {metadata.get('EARTH_SUN_DISTANCE', 1.0):.7f}\n")
            for i in range(1, 10):
                f.write(f"    SATURATION_BAND_{i} = \"{metadata.get(f'SATURATION_BAND_{i}', 'N')}\"\n")
            f.write(f"    GROUND_CONTROL_POINTS_VERSION = {metadata.get('GROUND_CONTROL_POINTS_VERSION', 5)}\n")
            f.write(f"    GROUND_CONTROL_POINTS_MODEL = {metadata.get('GROUND_CONTROL_POINTS_MODEL', 0)}\n")
            f.write(f"    GEOMETRIC_RMSE_MODEL = {metadata.get('GEOMETRIC_RMSE_MODEL', 0.0):.3f}\n")
            f.write(f"    GEOMETRIC_RMSE_MODEL_Y = {metadata.get('GEOMETRIC_RMSE_MODEL_Y', 0.0):.3f}\n")
            f.write(f"    GEOMETRIC_RMSE_MODEL_X = {metadata.get('GEOMETRIC_RMSE_MODEL_X', 0.0):.3f}\n")
            f.write(f"    GROUND_CONTROL_POINTS_VERIFY = {metadata.get('GROUND_CONTROL_POINTS_VERIFY', 0)}\n")
            f.write(f"    GEOMETRIC_RMSE_VERIFY = {metadata.get('GEOMETRIC_RMSE_VERIFY', 0.0):.3f}\n")
            if 'TRUNCATION_OLI' in metadata:
                f.write(f"    TRUNCATION_OLI = \"{metadata['TRUNCATION_OLI']}\"\n")
            f.write("  END_GROUP = IMAGE_ATTRIBUTES\n")
            
            # MIN_MAX_RADIANCE group - Calculate from MULT/ADD coefficients
            # Formula: Radiance = (DN * MULT) + ADD
            # where DN ranges from 1 (QUANTIZE_CAL_MIN) to 65535 (QUANTIZE_CAL_MAX)
            f.write("  GROUP = MIN_MAX_RADIANCE\n")
            for i in range(1, 12):
                mult = metadata.get(f'RADIANCE_MULT_BAND_{i}', 0.0)
                add = metadata.get(f'RADIANCE_ADD_BAND_{i}', 0.0)
                rad_max = (65535 * mult) + add
                rad_min = (1 * mult) + add
                f.write(f"    RADIANCE_MAXIMUM_BAND_{i} = {rad_max:.5f}\n")
            for i in range(1, 12):
                mult = metadata.get(f'RADIANCE_MULT_BAND_{i}', 0.0)
                add = metadata.get(f'RADIANCE_ADD_BAND_{i}', 0.0)
                rad_min = (1 * mult) + add
                f.write(f"    RADIANCE_MINIMUM_BAND_{i} = {rad_min:.5f}\n")
            f.write("  END_GROUP = MIN_MAX_RADIANCE\n")
            
            # MIN_MAX_REFLECTANCE group - For optical bands 1-9
            f.write("  GROUP = MIN_MAX_REFLECTANCE\n")
            for i in range(1, 10):
                mult = metadata.get(f'REFLECTANCE_MULT_BAND_{i}', 2.0E-05)
                add = metadata.get(f'REFLECTANCE_ADD_BAND_{i}', -0.1)
                refl_max = (65535 * mult) + add
                refl_min = (1 * mult) + add
                f.write(f"    REFLECTANCE_MAXIMUM_BAND_{i} = {refl_max:.6f}\n")
            for i in range(1, 10):
                mult = metadata.get(f'REFLECTANCE_MULT_BAND_{i}', 2.0E-05)
                add = metadata.get(f'REFLECTANCE_ADD_BAND_{i}', -0.1)
                refl_min = (1 * mult) + add
                f.write(f"    REFLECTANCE_MINIMUM_BAND_{i} = {refl_min:.6f}\n")
            f.write("  END_GROUP = MIN_MAX_REFLECTANCE\n")
            
            # MIN_MAX_PIXEL_VALUE group - DN quantization ranges
            f.write("  GROUP = MIN_MAX_PIXEL_VALUE\n")
            for i in range(1, 12):
                f.write(f"    QUANTIZE_CAL_MAX_BAND_{i} = 65535\n")
            for i in range(1, 12):
                f.write(f"    QUANTIZE_CAL_MIN_BAND_{i} = 1\n")
            f.write("  END_GROUP = MIN_MAX_PIXEL_VALUE\n")
            
            # RADIOMETRIC_RESCALING group - ALL calibration coefficients from GEE
            f.write("  GROUP = RADIOMETRIC_RESCALING\n")
            # Radiance multipliers for all 11 bands
            for i in range(1, 12):
                val = metadata.get(f'RADIANCE_MULT_BAND_{i}', 0.0)
                f.write(f"    RADIANCE_MULT_BAND_{i} = {val:.4E}\n")
            # Radiance additives for all 11 bands
            for i in range(1, 12):
                val = metadata.get(f'RADIANCE_ADD_BAND_{i}', 0.0)
                f.write(f"    RADIANCE_ADD_BAND_{i} = {val:.5f}\n")
            # Reflectance multipliers (bands 1-9 only, no thermal)
            for i in range(1, 10):
                val = metadata.get(f'REFLECTANCE_MULT_BAND_{i}', 2.0E-05)
                f.write(f"    REFLECTANCE_MULT_BAND_{i} = {val:.4E}\n")
            # Reflectance additives (bands 1-9 only, no thermal)
            for i in range(1, 10):
                val = metadata.get(f'REFLECTANCE_ADD_BAND_{i}', -0.1)
                f.write(f"    REFLECTANCE_ADD_BAND_{i} = {val:.6f}\n")
            f.write("  END_GROUP = RADIOMETRIC_RESCALING\n")
            
            # TIRS_THERMAL_CONSTANTS group
            f.write("  GROUP = TIRS_THERMAL_CONSTANTS\n")
            f.write(f"    K1_CONSTANT_BAND_10 = {metadata.get('K1_CONSTANT_BAND_10', 774.8853):.4f}\n")
            f.write(f"    K2_CONSTANT_BAND_10 = {metadata.get('K2_CONSTANT_BAND_10', 1321.0789):.4f}\n")
            f.write(f"    K1_CONSTANT_BAND_11 = {metadata.get('K1_CONSTANT_BAND_11', 480.8883):.4f}\n")
            f.write(f"    K2_CONSTANT_BAND_11 = {metadata.get('K2_CONSTANT_BAND_11', 1201.1442):.4f}\n")
            f.write("  END_GROUP = TIRS_THERMAL_CONSTANTS\n")
            
            # PROJECTION_PARAMETERS group
            f.write("  GROUP = PROJECTION_PARAMETERS\n")
            f.write(f"    MAP_PROJECTION = \"{metadata.get('MAP_PROJECTION', 'UTM')}\"\n")
            f.write(f"    DATUM = \"{metadata.get('DATUM', 'WGS84')}\"\n")
            f.write(f"    ELLIPSOID = \"{metadata.get('ELLIPSOID', 'WGS84')}\"\n")
            f.write(f"    UTM_ZONE = {metadata.get('UTM_ZONE', int((longitude + 180) / 6) + 1)}\n")
            f.write(f"    GRID_CELL_SIZE_PANCHROMATIC = {metadata.get('GRID_CELL_SIZE_PANCHROMATIC', 15.0):.2f}\n")
            f.write(f"    GRID_CELL_SIZE_REFLECTIVE = {metadata.get('GRID_CELL_SIZE_REFLECTIVE', 30.0):.2f}\n")
            f.write(f"    GRID_CELL_SIZE_THERMAL = {metadata.get('GRID_CELL_SIZE_THERMAL', 30.0):.2f}\n")
            f.write(f"    ORIENTATION = \"{metadata.get('ORIENTATION', 'NORTH_UP')}\"\n")
            f.write(f"    RESAMPLING_OPTION = \"{metadata.get('RESAMPLING_OPTION', 'CUBIC_CONVOLUTION')}\"\n")
            f.write("  END_GROUP = PROJECTION_PARAMETERS\n")
            
            f.write("END_GROUP = L1_METADATA_FILE\n")
            f.write("END\n")
        
        print(f'  ✓ MTL file created: {mtl_file}')
        
        # Create ANG.txt angle coefficient file - basic structure
        ang_file = os.path.join(input_folder, f'{scene_id}_ANG.txt')
        with open(ang_file, 'w') as f:
            f.write("GROUP = FILE_HEADER\n")
            f.write(f"  LANDSAT_SCENE_ID = \"{scene_id}\"\n")
            f.write(f"  SPACECRAFT_ID = \"{metadata.get('SPACECRAFT_ID', 'LANDSAT_8')}\"\n")
            f.write("  NUMBER_OF_BANDS = 11\n")
            f.write("  BAND_LIST = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)\n")
            f.write("END_GROUP = FILE_HEADER\n")
            f.write("GROUP = PROJECTION\n")
            f.write("  ELLIPSOID_AXES = (6378137.000000, 6356752.314200)\n")
            f.write(f"  MAP_PROJECTION = \"{metadata.get('MAP_PROJECTION', 'UTM')}\"\n")
            f.write("  PROJECTION_UNITS = \"METERS\"\n")
            f.write(f"  DATUM = \"{metadata.get('DATUM', 'WGS84')}\"\n")
            f.write(f"  ELLIPSOID = \"{metadata.get('ELLIPSOID', 'WGS84')}\"\n")
            f.write(f"  UTM_ZONE = {metadata.get('UTM_ZONE', int((longitude + 180) / 6) + 1)}\n")
            f.write("  PROJECTION_PARAMETERS = (0.000000, 0.000000, 0.000000, 0.000000, 0.000000,\n")
            f.write("                           0.000000, 0.000000, 0.000000, 0.000000, 0.000000,\n")
            f.write("                           0.000000, 0.000000, 0.000000, 0.000000, 0.000000)\n")
            f.write("END_GROUP = PROJECTION\n")
            f.write("END\n")
        print(f'  ✓ ANG file created: {ang_file}')
        
        print(f'Landsat scene: {scene_id}')
        return True
        
    except Exception as e:
        print(f'  Error downloading Landsat bands: {str(e)}')
        return False


def fetch_era5_weather(latitude, longitude, date_acquired, scene_time, input_folder):
    """
    Fetch weather data from ERA5-Land dataset via Google Earth Engine.
    Uses DAILY collection for 24h averages and HOURLY collection for instantaneous values.
    Automatically detects timezone based on coordinates and converts times properly.
    
    Parameters:
    - latitude, longitude: Location
    - date_acquired: Date string 'YYYY-MM-DD'
    - scene_time: Time string 'HH:MM:SS' or 'HH:MM:SS.SSSSSSSZ' in UTC (e.g., '10:30:45.1234567Z')
    - input_folder: Path to save cached data
    
    Returns: dict with weather parameters for SEBAL, or None if data not available
    """
    import json
    from datetime import datetime, timedelta
    try:
        from timezonefinder import TimezoneFinder
        import pytz
    except ImportError:
        print('  ⚠ Warning: timezonefinder or pytz not installed')
        print('    Install with: pip install timezonefinder pytz')
        print('    Proceeding with UTC time assumption...')
        TimezoneFinder = None
        pytz = None
    
    # Create ERA5 cache file path
    cache_file = os.path.join(input_folder, f'era5_{date_acquired}.json')
    
    # 1. Check if ERA5 data already cached
    if os.path.exists(cache_file):
        print(f'  ✓ ERA5 weather cache found: {os.path.basename(cache_file)}')
        with open(cache_file, 'r') as f:
            return json.load(f)
    
    print(f'  Fetching weather from ERA5-Land via GEE...')
    
    try:
        # Define point of interest
        poi = ee.Geometry.Point([longitude, latitude])
        
        # Detect timezone for this location
        timezone_str = 'UTC'
        local_tz = None
        if TimezoneFinder and pytz:
            try:
                tf = TimezoneFinder()
                timezone_str = tf.timezone_at(lat=latitude, lng=longitude)
                if timezone_str:
                    local_tz = pytz.timezone(timezone_str)
                else:
                    timezone_str = 'UTC'
                    print(f'  ⚠ Timezone not found for location, using UTC')
            except Exception as e:
                print(f'  ⚠ Timezone detection failed: {str(e)}, using UTC')
                timezone_str = 'UTC'
        
        # Parse date and scene time (UTC)
        date_obj = datetime.strptime(date_acquired, '%Y-%m-%d')
        
        # Extract hour and minute from scene_time (e.g., '05:42:15.1234567Z' from Landsat MTL)
        time_str = scene_time.replace('Z', '').split('.')[0]  # Remove microseconds and Z
        time_parts = time_str.split(':')
        scene_hour_utc = int(time_parts[0])  # Hour in UTC (0-23)
        scene_minute_utc = int(time_parts[1]) if len(time_parts) > 1 else 0
        
        # Create datetime in UTC
        scene_dt_utc = date_obj.replace(hour=scene_hour_utc, minute=scene_minute_utc, tzinfo=pytz.UTC if pytz else None)
        
        # Convert to local timezone
        scene_time_local = "N/A"
        if local_tz and pytz:
            scene_dt_local = scene_dt_utc.astimezone(local_tz)
            scene_time_local = scene_dt_local.strftime('%H:%M %Z')
        
        print(f'  Location: {latitude:.4f}°N, {longitude:.4f}°E → Timezone: {timezone_str}')
        print(f'  Scene time: {scene_hour_utc:02d}:{scene_minute_utc:02d} UTC ({scene_time_local} local)')
        
        # Add 1 day for end date (GEE uses exclusive end dates)
        end_date = (date_obj + timedelta(days=1)).strftime('%Y-%m-%d')
        
        # ========== FETCH DAILY DATA (for 24h averages) ==========
        era5_daily = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR") \
            .filterDate(date_acquired, end_date) \
            .filterBounds(poi)
        
        # Check if daily data exists
        daily_count = era5_daily.size().getInfo()
        if daily_count == 0:
            print(f'  ✗ No ERA5 daily data available for {date_acquired}')
            return None
        
        daily_image = era5_daily.first()
        
        # ========== FETCH HOURLY DATA (for instantaneous values) ==========
        era5_hourly = ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY") \
            .filterDate(date_acquired, end_date) \
            .filterBounds(poi)
        
        # Check if hourly data exists
        hourly_count = era5_hourly.size().getInfo()
        if hourly_count == 0:
            print(f'  ✗ No ERA5 hourly data available for {date_acquired}')
            return None
        
        # Get list of all hourly images
        hourly_list = era5_hourly.toList(24)
        
        # Try to get the image closest to scene hour (UTC)
        # ERA5 hourly data is timestamped at the END of each hour
        # So hour 12 means data for 11:00-12:00
        hourly_image = None
        try:
            # Get the image at the scene hour index (0-23)
            hourly_image = ee.Image(hourly_list.get(scene_hour_utc))
        except:
            # If specific hour fails, use middle of day (noon)
            print(f'  ⚠ Hour {scene_hour_utc} not available, using hour 12 (noon)')
            hourly_image = ee.Image(hourly_list.get(12))
        
        # Extract values at the point (1km buffer for spatial averaging)
        buffer_m = 1000
        scale = 11132  # ERA5-Land native resolution ~11km
        
        daily_sample = daily_image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=poi.buffer(buffer_m),
            scale=scale,
            maxPixels=1e9
        ).getInfo()
        
        hourly_sample = hourly_image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=poi.buffer(buffer_m),
            scale=scale,
            maxPixels=1e9
        ).getInfo()
        
        if not daily_sample or not hourly_sample:
            print(f'  ✗ ERA5 sampling failed for {date_acquired}')
            return None
        
        # ========== EXTRACT AND CONVERT UNITS ==========
        
        # ===== DAILY AVERAGES (from DAILY collection) =====
        
        # TEMPERATURE - Daily average (K to °C)
        temp_2m_daily = daily_sample.get('temperature_2m')
        if temp_2m_daily is None:
            print(f'  ✗ ERA5 daily temperature data missing')
            return None
        Temp_24 = temp_2m_daily - 273.15  # Daily average in °C
        
        # DEWPOINT - Daily (K to °C, for RH_24 calculation)
        dewpoint_2m_daily = daily_sample.get('dewpoint_temperature_2m')
        if dewpoint_2m_daily is None:
            print(f'  ✗ ERA5 daily dewpoint data missing')
            return None
        dewpoint_C_daily = dewpoint_2m_daily - 273.15
        
        # WIND SPEED - Daily average (combine u/v components)
        u_wind_daily = daily_sample.get('u_component_of_wind_10m')  # m/s
        v_wind_daily = daily_sample.get('v_component_of_wind_10m')  # m/s
        if u_wind_daily is None or v_wind_daily is None:
            print(f'  ✗ ERA5 daily wind data missing')
            return None
        import math
        Wind_24 = math.sqrt(u_wind_daily**2 + v_wind_daily**2)  # m/s
        
        # SOLAR RADIATION - Daily average (J/m² to W/m²)
        solar_daily_sum = daily_sample.get('surface_solar_radiation_downwards_sum')  # J/m² (daily total)
        if solar_daily_sum is None:
            print(f'  ✗ ERA5 daily solar radiation data missing')
            return None
        # Convert J/m² (daily total) to W/m² (daily average): divide by 86400 seconds
        Rs_24 = solar_daily_sum / 86400.0  # W/m² (daily average)
        
        # ===== INSTANTANEOUS VALUES (from HOURLY collection at scene hour) =====
        
        # TEMPERATURE - Instantaneous at scene hour (K to °C)
        temp_2m_hourly = hourly_sample.get('temperature_2m')
        if temp_2m_hourly is None:
            print(f'  ✗ ERA5 hourly temperature data missing')
            return None
        Temp_inst = temp_2m_hourly - 273.15  # Instantaneous in °C
        
        # DEWPOINT - Instantaneous (K to °C, for RH_inst calculation)
        dewpoint_2m_hourly = hourly_sample.get('dewpoint_temperature_2m')
        if dewpoint_2m_hourly is None:
            print(f'  ✗ ERA5 hourly dewpoint data missing')
            return None
        dewpoint_C_hourly = dewpoint_2m_hourly - 273.15
        
        # WIND SPEED - Instantaneous (combine u/v components)
        u_wind_hourly = hourly_sample.get('u_component_of_wind_10m')  # m/s
        v_wind_hourly = hourly_sample.get('v_component_of_wind_10m')  # m/s
        if u_wind_hourly is None or v_wind_hourly is None:
            print(f'  ✗ ERA5 hourly wind data missing')
            return None
        Wind_inst = math.sqrt(u_wind_hourly**2 + v_wind_hourly**2)  # m/s
        
        # SOLAR RADIATION - Instantaneous (J/m²/hour to W/m²)
        # ERA5 hourly gives accumulated radiation over the hour
        solar_hourly = hourly_sample.get('surface_solar_radiation_downwards')  # J/m² per hour
        if solar_hourly is None:
            print(f'  ✗ ERA5 hourly solar radiation data missing')
            return None
        
        # Convert J/m²/hour to W/m²: divide by 3600 seconds
        Rs_in_inst_raw = solar_hourly / 3600.0  # W/m²
        
        # ========== SOLAR POSITION AND PHYSICS VALIDATION ==========
        
        def solar_elevation(lat, lon, dt_utc):
            """Calculate solar elevation angle in degrees
            
            Args:
                lat: Latitude in degrees
                lon: Longitude in degrees
                dt_utc: datetime object in UTC
            
            Returns:
                elevation: Solar elevation angle in degrees (negative = below horizon)
            """
            import math
            
            # Day of year
            day_of_year = dt_utc.timetuple().tm_yday
            
            # Solar declination (degrees)
            declination = 23.45 * math.sin(math.radians((360/365.0) * (day_of_year - 81)))
            
            # Equation of time (minutes) - approximation
            B = (360.0/365.0) * (day_of_year - 81)
            EoT = 9.87 * math.sin(math.radians(2*B)) - 7.53 * math.cos(math.radians(B)) - 1.5 * math.sin(math.radians(B))
            
            # Local solar time (decimal hours)
            # UTC hour + longitude correction + equation of time
            time_correction = 4 * lon + EoT  # minutes
            utc_decimal = dt_utc.hour + dt_utc.minute / 60.0
            local_solar_time = utc_decimal + time_correction / 60.0
            
            # Hour angle (degrees from solar noon)
            hour_angle = 15.0 * (local_solar_time - 12.0)
            
            # Solar elevation angle
            lat_rad = math.radians(lat)
            dec_rad = math.radians(declination)
            ha_rad = math.radians(hour_angle)
            
            sin_elevation = (math.sin(lat_rad) * math.sin(dec_rad) + 
                           math.cos(lat_rad) * math.cos(dec_rad) * math.cos(ha_rad))
            elevation = math.degrees(math.asin(max(-1, min(1, sin_elevation))))
            
            return elevation
        
        # Calculate solar elevation for scene time (use full datetime for accuracy)
        solar_elev = solar_elevation(latitude, longitude, scene_dt_utc)
        
        # Determine realistic solar radiation based on sun position
        if solar_elev < 0:
            # Sun is below horizon - nighttime or before sunrise
            Rs_in_inst = 0.0
            print(f'  ⚠ Sun below horizon (elevation {solar_elev:.1f}°)')
            print(f'     Solar radiation set to 0 W/m² (nighttime/before sunrise)')
        elif Rs_in_inst_raw > 1200.0 or Rs_in_inst_raw < 0:
            # ERA5 value is unrealistic, estimate from solar angle and daily average
            # Clear-sky radiation ~ daily_average * sin(elevation) adjustment
            # Approximate: peak radiation = daily_average / 0.5 (half-day sine integral)
            max_clear_sky = Rs_24 / 0.5  # W/m² daily avg to peak (factor ~2)
            Rs_in_inst = max_clear_sky * math.sin(math.radians(max(0, solar_elev)))
            Rs_in_inst = min(1200.0, max(0, Rs_in_inst))  # Clamp to realistic range
            print(f'  ⚠ ERA5 hourly solar ({Rs_in_inst_raw:.0f} W/m²) unrealistic')
            print(f'     Estimated {Rs_in_inst:.0f} W/m² from solar angle ({solar_elev:.1f}°)')
        else:
            # ERA5 value seems reasonable
            Rs_in_inst = Rs_in_inst_raw
            # But double-check against solar elevation
            if Rs_in_inst > 10 and solar_elev < 5:
                # Suspiciously high radiation for low sun angle
                Rs_in_inst = 0.0
                print(f'  ⚠ Low sun angle ({solar_elev:.1f}°), solar set to 0 W/m²')
            else:
                print(f'  ✓ Solar elevation: {solar_elev:.1f}°, radiation: {Rs_in_inst:.0f} W/m²')
        
        
        # RELATIVE HUMIDITY (calculate from temperature and dewpoint)
        # Using August-Roche-Magnus approximation
        # RH = 100 * exp((17.625*Td)/(243.04+Td)) / exp((17.625*T)/(243.04+T))
        def calc_rh(temp_c, dewpoint_c):
            """Calculate RH from temperature and dewpoint"""
            numerator = math.exp((17.625 * dewpoint_c) / (243.04 + dewpoint_c))
            denominator = math.exp((17.625 * temp_c) / (243.04 + temp_c))
            return 100.0 * (numerator / denominator)
        
        RH_24 = calc_rh(Temp_24, dewpoint_C_daily)  # Daily average RH
        RH_inst = calc_rh(Temp_inst, dewpoint_C_hourly)  # Instantaneous RH at scene hour
        
        # ATMOSPHERIC TRANSMISSIVITY (estimated from solar radiation)
        # Transmissivity = actual solar / clear-sky solar
        # Higher solar → higher transmissivity (typical range: 0.5-0.9)
        Transm_24 = min(0.9, max(0.5, Rs_24 / 500.0))  # Based on daily W/m² average (~500 clear sky)
        Transm_inst = min(0.9, max(0.5, Rs_in_inst / 1200.0))  # Based on instantaneous W/m²
        
        # ========== PREPARE RETURN DATA ==========
        weather_data = {
            # Instantaneous values (at scene time)
            'Temp_inst': Temp_inst,        # °C (from hourly K)
            'RH_inst': RH_inst,            # % (calculated from temp + dewpoint)
            'Wind_inst': Wind_inst,        # m/s (from hourly u/v components)
            'Rs_in_inst': Rs_in_inst,      # W/m² (from hourly J/m² or estimated from solar angle)
            'Transm_inst': Transm_inst,    # dimensionless (estimated)
            # Daily averages
            'Temp_24': Temp_24,            # °C (from daily K)
            'RH_24': RH_24,                # % (calculated from temp + dewpoint)
            'Wind_24': Wind_24,            # m/s (from daily u/v components)
            'Rs_24': Rs_24,                # W/m² (daily average from daily J/m²)
            'Transm_24': Transm_24,        # dimensionless (estimated)
            'source': 'ERA5-Land (Daily+Hourly)',
            # Metadata for clarity
            'timezone': timezone_str,
            'scene_time_utc': f'{scene_hour_utc:02d}:{scene_minute_utc:02d}',
            'scene_time_local': scene_time_local,
            'solar_elevation_deg': round(solar_elev, 2),
            'location': f'{latitude:.4f}°N, {longitude:.4f}°E'
        }
        
        # Save to cache
        with open(cache_file, 'w') as f:
            json.dump(weather_data, f, indent=2)
        
        print(f'  ✓ ERA5 weather fetched successfully')
        print(f'    Temp: {Temp_inst:.1f}°C (scene time), {Temp_24:.1f}°C (daily avg)')
        print(f'    RH: {RH_inst:.1f}% (scene time), {RH_24:.1f}% (daily avg)')
        print(f'    Wind: {Wind_inst:.1f} m/s (scene time), {Wind_24:.1f} m/s (daily avg)')
        print(f'    Solar: {Rs_in_inst:.0f} W/m² (scene time), {Rs_24:.0f} W/m² (daily avg)')
        
        return weather_data
        
    except Exception as e:
        print(f'  ✗ ERA5 fetch failed: {str(e)}')
        import traceback
        traceback.print_exc()
        return None


def fetch_weather_data(latitude, longitude, date_acquired, scene_time, input_folder, api_key):
    """
    Fetch weather data with priority: ERA5-Land → OpenWeatherMap API
    Raises error if both sources fail.
    
    Returns: dict with weather parameters for SEBAL, or None if all sources fail
    """
    import json
    from datetime import datetime
    
    # ========== 1. TRY ERA5-LAND FIRST ==========
    print(f'  Weather source priority: ERA5-Land → OpenWeatherMap')
    era5_data = fetch_era5_weather(latitude, longitude, date_acquired, scene_time, input_folder)
    
    if era5_data is not None:
        return era5_data
    
    # ========== 2. FALLBACK TO OPENWEATHERMAP ==========
    print(f'  ERA5 unavailable, trying OpenWeatherMap...')
    
    # Create weather cache file path based on location and date
    cache_file = os.path.join(input_folder, f'weather_openweather_{date_acquired}.json')
    solar_cache_file = os.path.join(input_folder, f'solar_openweather_{date_acquired}.json')
    
    weather_data = {}
    
    # 1. Check if weather data already cached
    if os.path.exists(cache_file):
        print(f'  ✓ Weather data cache found: {cache_file}')
        with open(cache_file, 'r') as f:
            weather_response = json.load(f)
    else:
        print(f'  Fetching weather data from OpenWeatherMap...')
        # Fetch One Call API data
        onecall_url = f'https://api.openweathermap.org/data/3.0/onecall?lat={latitude}&lon={longitude}&exclude=minutely,alerts&appid={api_key}'
        try:
            response = requests.get(onecall_url, timeout=30)
            response.raise_for_status()
            weather_response = response.json()
            
            # Save to cache
            with open(cache_file, 'w') as f:
                json.dump(weather_response, f, indent=2)
            print(f'  ✓ Weather data cached to {cache_file}')
        except Exception as e:
            print(f'  Warning: Could not fetch weather data: {str(e)}')
            print(f'  Using default values instead')
            return None
    
    # 2. Check if solar radiation data already cached
    if os.path.exists(solar_cache_file):
        print(f'  ✓ Solar radiation cache found: {solar_cache_file}')
        with open(solar_cache_file, 'r') as f:
            solar_response = json.load(f)
    else:
        print(f'  Fetching solar radiation data from OpenWeatherMap (costly API)...')
        # Fetch solar radiation data - EXPENSIVE API CALL ($8)
        solar_url = f'https://api.openweathermap.org/energy/2.0/solar/interval_data?lat={latitude}&lon={longitude}&date={date_acquired}&interval=1h&appid={api_key}'
        try:
            response = requests.get(solar_url, timeout=30)
            response.raise_for_status()
            solar_response = response.json()
            
            # Save to cache
            with open(solar_cache_file, 'w') as f:
                json.dump(solar_response, f, indent=2)
            print(f'  ✓ Solar radiation data cached to {solar_cache_file}')
        except Exception as e:
            print(f'  Warning: Could not fetch solar radiation data: {str(e)}')
            print(f'  Using default radiation values instead')
            solar_response = None
    
    # 3. Extract weather parameters for SEBAL
    try:
        # Current (instantaneous) data
        current = weather_response.get('current', {})
        weather_data['Temp_inst'] = current.get('temp', 301.15) - 273.15  # Convert K to C
        weather_data['RH_inst'] = current.get('humidity', 55.0)  # %
        weather_data['Wind_inst'] = current.get('wind_speed', 2.5)  # m/s
        
        # Daily averages from hourly data
        hourly = weather_response.get('hourly', [])
        if hourly:
            temps = [h.get('temp', 295.15) for h in hourly]
            rhs = [h.get('humidity', 60.0) for h in hourly]
            winds = [h.get('wind_speed', 2.0) for h in hourly]
            
            weather_data['Temp_24'] = (sum(temps) / len(temps)) - 273.15  # Convert K to C
            weather_data['RH_24'] = sum(rhs) / len(rhs)
            weather_data['Wind_24'] = sum(winds) / len(winds)
        else:
            # Fallback to daily data
            daily = weather_response.get('daily', [{}])[0]
            weather_data['Temp_24'] = daily.get('temp', {}).get('day', 295.15) - 273.15
            weather_data['RH_24'] = daily.get('humidity', 60.0)
            weather_data['Wind_24'] = daily.get('wind_speed', 2.0)
        
        # 4. Extract solar radiation matching scene acquisition time
        if solar_response and 'intervals' in solar_response:
            # Parse scene_time (format: "HH:MM:SS.SSSSSSSZ") - Z means UTC time
            scene_hour_utc = int(scene_time.split(':')[0])
            scene_minute = int(scene_time.split(':')[1])
            
            # Calculate UTC offset based on longitude (rough estimate: longitude/15)
            # More accurate: use timezone libraries, but this works for most cases
            utc_offset = round(longitude / 15)  # Hours offset from UTC
            
            # Convert UTC to local time
            scene_hour_local = (scene_hour_utc + utc_offset) % 24
            
            print(f'\n  Matching solar radiation to satellite acquisition time:')
            print(f'    Scene time (UTC): {scene_time} → {scene_hour_utc:02d}:{scene_minute:02d} UTC')
            print(f'    UTC offset for longitude {longitude:.2f}°: +{utc_offset} hours')
            print(f'    Local time: {scene_hour_local:02d}:{scene_minute:02d} (Hour {scene_hour_local}:00)')
            
            # Find matching interval using LOCAL time
            ghi_inst_cloudy = 0.0
            ghi_inst_clear = 0.0
            
            for interval in solar_response['intervals']:
                start_hour = int(interval['start'].split(':')[0])
                if start_hour == scene_hour_local:
                    # Extract both cloudy and clear sky values for transmissivity calculation
                    ghi_inst_cloudy = interval['avg_irradiance']['cloudy_sky']['ghi']
                    ghi_inst_clear = interval['avg_irradiance']['clear_sky']['ghi']
                    dni_inst = interval['avg_irradiance']['cloudy_sky']['dni']
                    dhi_inst = interval['avg_irradiance']['cloudy_sky']['dhi']
                    
                    # Use cloudy sky GHI (Global Horizontal Irradiance)
                    # GHI = total solar radiation on horizontal surface
                    # GHI = DNI (Direct Normal) + DHI (Diffuse Horizontal)
                    # We use GHI because SEBAL needs total incoming solar radiation
                    weather_data['Rs_in_inst'] = ghi_inst_cloudy  # W/m2
                    
                    print(f'    Using GHI (Global Horizontal Irradiance) at local hour {scene_hour_local}:00')
                    print(f'      GHI (cloudy sky): {ghi_inst_cloudy:.2f} W/m²')
                    print(f'      GHI (clear sky): {ghi_inst_clear:.2f} W/m²')
                    print(f'      DNI (Direct Normal): {dni_inst:.2f} W/m²')
                    print(f'      DHI (Diffuse Horizontal): {dhi_inst:.2f} W/m²')
                    print(f'      Note: GHI = DNI + DHI (total solar radiation on surface)')
                    break
            
            # Calculate daily average GHI and transmissivity
            daily_ghi_cloudy_sum = 0.0
            daily_ghi_clear_sum = 0.0
            count = 0
            
            for interval in solar_response['intervals']:
                ghi_c = interval['avg_irradiance']['cloudy_sky']['ghi']
                ghi_cl = interval['avg_irradiance']['clear_sky']['ghi']
                daily_ghi_cloudy_sum += ghi_c
                daily_ghi_clear_sum += ghi_cl
                count += 1
            
            if count > 0:
                avg_ghi_w_m2 = daily_ghi_cloudy_sum / count  # W/m² (average)
                
                # Convert W/m² to MJ/m²/day
                # 1 W/m² over 1 second = 1 J/m²
                # 1 W/m² over 24 hours = 86400 J/m² = 0.0864 MJ/m²
                # Average daily W/m² × 0.0864 = MJ/m²/day
                weather_data['Rs_24'] = avg_ghi_w_m2 * 0.0864  # MJ/m²/day
                
                # Calculate transmissivity from actual solar data
                # Transmissivity = GHI_actual / GHI_clear_sky
                if ghi_inst_clear > 0:
                    weather_data['Transm_inst'] = min(ghi_inst_cloudy / ghi_inst_clear, 1.0)
                else:
                    weather_data['Transm_inst'] = 0.75  # Default fallback
                
                if daily_ghi_clear_sum > 0:
                    weather_data['Transm_24'] = min(daily_ghi_cloudy_sum / daily_ghi_clear_sum, 1.0)
                else:
                    weather_data['Transm_24'] = 0.75  # Default fallback
                
                print(f'      Daily average GHI: {avg_ghi_w_m2:.2f} W/m² = {weather_data["Rs_24"]:.2f} MJ/m²/day')
                print(f'      Instantaneous Transmissivity: {weather_data["Transm_inst"]:.3f}')
                print(f'      Daily average Transmissivity: {weather_data["Transm_24"]:.3f}')
            else:
                # Fallback defaults
                weather_data['Rs_in_inst'] = 850.0
                weather_data['Rs_24'] = 22.0
                weather_data['Transm_inst'] = 0.75
                weather_data['Transm_24'] = 0.75
                print(f'    Warning: No solar data available, using defaults')
        else:
            # No solar data - use defaults
            weather_data['Rs_in_inst'] = 850.0
            weather_data['Rs_24'] = 22.0
            weather_data['Transm_inst'] = 0.75
            weather_data['Transm_24'] = 0.75
            print(f'    No solar radiation data available, using defaults')
        
        # Mark source as OpenWeatherMap
        weather_data['source'] = 'OpenWeatherMap'
        
        print(f'\n  ✓ OpenWeatherMap data extracted:')
        print(f'    Temp_inst: {weather_data["Temp_inst"]:.1f}°C')
        print(f'    Temp_24: {weather_data["Temp_24"]:.1f}°C')
        print(f'    RH_inst: {weather_data["RH_inst"]:.1f}%')
        print(f'    Wind_inst: {weather_data["Wind_inst"]:.1f} m/s')
        print(f'    Rs_in_inst: {weather_data["Rs_in_inst"]:.1f} W/m²')
        
        return weather_data
        
    except Exception as e:
        print(f'  ✗ OpenWeatherMap API failed: {str(e)}')
        print(f'  ✗ ERROR: No weather data available - ERA5 unavailable, OpenWeatherMap API exhausted')
        return None


def SEBALcode(config):
    """
    Main SEBAL processing function - now uses config object instead of Excel
    
    Parameters:
    -----------
    config : SEBALConfig
        Configuration object with all SEBAL parameters
    """
    # Do not show warnings
    warnings.filterwarnings('ignore')  
    
    # Extract parameters from config object
    input_folder = config.input_folder
    output_folder = config.output_folder
    Image_Type = config.Image_Type
    
    # AUTO-DOWNLOAD DATA FROM GOOGLE EARTH ENGINE
    # Download Landsat 8 and SRTM data from GEE
    download_gee_data(input_folder, config.latitude, config.longitude, config.buffer_km)
 			
    # Create or empty output folder		
    if os.path.isdir(output_folder):
        shutil.rmtree(output_folder)
    os.makedirs(output_folder)
    
    # Extract the Path to the DEM map from config
    DEM_fileName = config.DEM_fileName
    
    # Print data used
    print ('.................................................................. ')
    print ('......................SEBAL Model running ........................ ')
    print ('.................................................................. ')
    print ('pySEBAL version 3.3.7.1 Github - NO EXCEL DEPENDENCY')
    print ('General Input:')
    print(('Path to DEM file = %s' %str(DEM_fileName)))
    print(('input_folder = %s' %str(input_folder)))
    print(('output_folder = %s' %str(output_folder)))
    print(('Image_Type = %s' %int(Image_Type)))	
    print ('................ Input Maps LS or PROBA-V and VIIRS............... ')

    if Image_Type == 3:		

        # Extract MODIS parameters from config (not fully implemented - placeholder)
        print('MODIS Input:')
        print('MODIS processing not fully implemented in config mode')
        print('Please use Image_Type=1 (Landsat) for now')
        
        # Placeholder variables to avoid errors
        Name_MODIS_Image_Ref = 'MOD09GA.A2025001.h25v05.061'
        Name_MODIS_Image_NDVI = 'MOD13Q1.A2025001.h25v05.061'
        Name_MODIS_Image_LST = 'MOD11A1.A2025001.h25v05.061'
        Hot_Pixel_Constant = 0
        Cold_Pixel_Constant = 0
        pixel_spacing = int(250)
        UTM_Zone = 43.0  # Default, should be set properly
        
        src_FileName_LST = os.path.join(input_folder, '%s.hdf' %Name_MODIS_Image_LST)                            
        src_FileName_NDVI = os.path.join(input_folder, '%s.hdf' %Name_MODIS_Image_NDVI)                                       
        src_FileName_Ref = os.path.join(input_folder, '%s.hdf' %Name_MODIS_Image_Ref)  
    
        # Calibartion constants Hot Pixels
        Hot_Pixel_Constant = 0
        
        # Calibartion constants Cold Pixels
        Cold_Pixel_Constant = 0
        
        # Pixel size of the model
        pixel_spacing = int(250) 	
 		
        # UTM Zone of the end results					
        UTM_Zone = 43.0  # Should be properly determined
	 						
        # Print data used
        print('MODIS Input:')			
        print('Path to MODIS LST image = %s' %str(Name_MODIS_Image_LST))
        print('Path to MODIS NDVI image = %s' %str(Name_MODIS_Image_NDVI))
        print('Path to MODIS Reflectance image = %s' %str(Name_MODIS_Image_Ref))
        print('Hot Pixel Constant MODIS = %s' %(Hot_Pixel_Constant))	
        print('Cold Pixel Constant MODIS = %s' %(Cold_Pixel_Constant))	
        print('UTM Zone = %s' %(UTM_Zone))
        print('Pixel size model = %s (Meters)' %(pixel_spacing))	 
        
    if Image_Type == 2:		
       
        # Extract VIIRS+PROBAV parameters from config (not fully implemented - placeholder)
        print('VIIRS+PROBA-V Input:')
        print('VIIRS+PROBA-V processing not fully implemented in config mode')
        print('Please use Image_Type=1 (Landsat) for now')
							
        # Placeholder variables to avoid errors
        Name_VIIRS_Image_TB = 'VIIRS_SVIO5_npp_d20250101_t1103128'
        Name_VIIRS_Image_QC = 'VIIRS_SVIO5_npp_d20250101_t1103128_QC'
        Name_PROBAV_Image = 'PROBAV_S1_TOC_20250101_100M_V101'
        Hot_Pixel_Constant = 0
        Cold_Pixel_Constant = 0
        pixel_spacing = int(100)
        UTM_Zone = 43.0  # Should be properly determined
	 						
        # Print data used from sheet General_Input
        print('VIIRS PROBA-V Input:')			
        print('Path to Thermal VIIRS image = %s' %str(Name_VIIRS_Image_TB))
        print('Path to Quality VIIRS image = %s' %str(Name_VIIRS_Image_QC))
        print('Hot Pixel Constant VIIRS = %s' %(Hot_Pixel_Constant))	
        print('Cold Pixel Constant VIIRS = %s' %(Cold_Pixel_Constant))	
        print('UTM Zone = %s' %(UTM_Zone))
        print('Pixel size model = %s (Meters)' %(pixel_spacing))							
							
    if Image_Type == 1:	
       
        # Extract Landsat parameters from config
        # Auto-detect Name_Landsat_Image from downloaded files
        import glob
        landsat_files = glob.glob(os.path.join(input_folder, 'LC*_MTL.txt'))
        if landsat_files:
            Name_Landsat_Image = os.path.basename(landsat_files[0]).replace('_MTL.txt', '')
        else:
            Name_Landsat_Image = config.Name_Landsat_Image or 'LC81500372025338LGN00'
        
        Landsat_nr = config.Landsat_nr
        Bands_thermal = config.Bands_thermal
                                    
        # Calibration constants
        Hot_Pixel_Constant = 0
        Cold_Pixel_Constant = 0
        
        # Get pixel selection parameters from config
        NDVIhot_low1 = config.NDVIhot_low
        NDVIhot_high1 = config.NDVIhot_high
        tcoldmin1 = config.tcoldmin
        tcoldmax1 = config.tcoldmax
        temp_lapse = config.temp_lapse
        
        # Pixel size of the model
        pixel_spacing = int(30)
							
        # Print data used from sheet General_Input
        print('Landsat Input:')			
        print('Name of the Landsat Image = %s' %str(Name_Landsat_Image))
        print('Landsat number = %s' %str(Landsat_nr))
        print('Thermal Bands that will be used = %s' %(Bands_thermal))	
        print('Hot Pixel Constant Landsat = %s' %(Hot_Pixel_Constant))
        print('Cold Pixel Constant Landsat = %s' %(Cold_Pixel_Constant))	
        print('Pixel size model = %s' %(pixel_spacing))	

    print('......................... Meteo Data ............................. ')				
			
    # ====================== FETCH REALTIME WEATHER DATA ======================
    if hasattr(config, 'use_realtime_weather') and config.use_realtime_weather:
        print('Fetching real-time weather data from OpenWeatherMap...')
        # Get scene date and time from Landsat metadata
        mtl_file = glob.glob(os.path.join(input_folder, '*_MTL.txt'))[0]
        with open(mtl_file, 'r') as f:
            mtl_content = f.read()
            date_match = re.search(r'DATE_ACQUIRED = (\d{4}-\d{2}-\d{2})', mtl_content)
            time_match = re.search(r'SCENE_CENTER_TIME = "([^"]+)"', mtl_content)
            
            if date_match and time_match:
                date_acquired = date_match.group(1)
                scene_time = time_match.group(1)
                
                weather_data = fetch_weather_data(
                    config.latitude, 
                    config.longitude, 
                    date_acquired, 
                    scene_time,
                    input_folder,
                    config.openweather_api_key
                )
                
                if weather_data:
                    # Override config values with real weather data
                    config.Temp_inst = weather_data['Temp_inst']
                    config.Temp_24 = weather_data['Temp_24']
                    config.RH_inst = weather_data['RH_inst']
                    config.RH_24 = weather_data['RH_24']
                    config.Wind_inst = weather_data['Wind_inst']
                    config.Wind_24 = weather_data['Wind_24']
                    config.Rs_in_inst = weather_data['Rs_in_inst']
                    config.Rs_24 = weather_data['Rs_24']
                    config.Transm_inst = weather_data['Transm_inst']
                    config.Transm_24 = weather_data['Transm_24']
                    print('  ✓ Weather data updated from API')
    
    # Get meteorological data from config object (now potentially updated with real data)
 
    # ---------------------------- Instantaneous Air Temperature ------------
    Temp_inst = config.Temp_inst
    Temp_inst_kind_of_data = config.Temp_inst_kind_of_data
    if Temp_inst_kind_of_data == 0:
        print('Instantaneous Temperature constant value of = %s (Celcius degrees)' %(Temp_inst))
    else:
        Temp_inst_name = config.Temp_inst  # Path if it's a map
        print('Map to the Instantaneous Temperature = %s' %(Temp_inst_name))

    # ---------------------------- Daily Average Air Temperature ------------
    Temp_24 = config.Temp_24
    Temp_24_kind_of_data = config.Temp_24_kind_of_data
    if Temp_24_kind_of_data == 0:
        print('Daily average Temperature constant value of = %s (Celcius degrees)' %(Temp_24))
    else:
        Temp_24_name = config.Temp_24
        print('Map to the Daily average Temperature = %s' %(Temp_24_name))

    # ---------------------------- Instantaneous Relative humidity ------------
    RH_inst = config.RH_inst
    RH_inst_kind_of_data = config.RH_inst_kind_of_data
    if RH_inst_kind_of_data == 0:
        print('Instantaneous Relative humidity constant value of = %s (percentage)' %(RH_inst))
    else:
        RH_inst_name = config.RH_inst
        print('Map to the Instantaneous Relative humidity  = %s' %(RH_inst_name))

    # ---------------------------- daily average Relative humidity ------------
    RH_24 = config.RH_24
    RH_24_kind_of_data = config.RH_24_kind_of_data
    if RH_24_kind_of_data == 0:
        print('Daily average Relative humidity constant value of = %s (percentage)' %(RH_24))
    else:
        RH_24_name = config.RH_24
        print('Map to the Daily average Relative humidity = %s' %(RH_24_name))

    # ---------------------------- instantaneous Wind Speed ------------
    Wind_inst = config.Wind_inst
    Wind_inst_kind_of_data = config.Wind_inst_kind_of_data
    if Wind_inst_kind_of_data == 0:
        print('Instantaneous Wind Speed constant value of = %s (m/s)' %(Wind_inst))
    else:
        Wind_inst_name = config.Wind_inst
        print('Map to the Instantaneous Wind Speed = %s' %(Wind_inst_name))

    # ---------------------------- daily Wind Speed ------------
    Wind_24 = config.Wind_24
    Wind_24_kind_of_data = config.Wind_24_kind_of_data
    if Wind_24_kind_of_data == 0:
        print('Daily Wind Speed constant value of = %s (m/s)' %(Wind_24))
    else:
        Wind_24_name = config.Wind_24
        print('Map to the Daily Wind Speed = %s' %(Wind_24_name))
   
    # Height of the wind speed measurement
    zx = config.zx
    print('Height at which wind speed is measured = %s (m)' %(zx))
   
    # Define the method of radiation (1 or 2)
    Method_Radiation_24 = config.Method_Radiation_24
    print('Method for daily radiation (1=Rs_24, 2=Transm_24) = %s' %(Method_Radiation_24)) 

    # if method radiation == 1
    if Method_Radiation_24 == 1:
        Rs_24 = config.Rs_24
        Rs_24_kind_of_data = config.Rs_24_kind_of_data
        if Rs_24_kind_of_data == 0:
            print('Daily Surface Solar Radiation constant value of = %s (W/m2)' %(Rs_24))
        else:
            Rs_24_name = config.Rs_24
            print('Map to the Daily Surface Solar Radiation = %s' %(Rs_24_name))

    # if method radiation == 2
    if Method_Radiation_24 == 2:
        Transm_24 = config.Transm_24
        Transm_24_kind_of_data = config.Transm_24_kind_of_data
        if Transm_24_kind_of_data == 0:
            print('Daily transmissivity constant value of = %s' %(Transm_24))
        else:
            Transm_24_name = config.Transm_24
            print('Map to the Daily transmissivity = %s' %(Transm_24_name))
   
    # Define the method of instantaneous radiation (1 or 2)
    Method_Radiation_inst = config.Method_Radiation_inst
    
    # if method instantaneous radiation == 1
    if Method_Radiation_inst == 1:
        Rs_in_inst = config.Rs_in_inst
        Rs_in_inst_kind_of_data = config.Rs_in_inst_kind_of_data
        if Rs_in_inst_kind_of_data == 0:
            print('Instantaneous Surface Solar Radiation constant value of = %s (W/m2)' %(Rs_in_inst))
        else:
            Rs_in_inst_name = config.Rs_in_inst
            print('Map to the Instantaneous Surface Solar Radiation = %s' %(Rs_in_inst_name))

    # if method instantaneous radiation == 2
    if Method_Radiation_inst == 2:
        Transm_inst = config.Transm_inst
        Transm_inst_kind_of_data = config.Transm_inst_kind_of_data
        if Transm_inst_kind_of_data == 0:
            print('Instantaneous transmissivity constant value of = %s' %(Transm_inst))
        else:
            Transm_inst_name = config.Transm_inst
            print('Map to the Instantaneous transmissivity = %s' %(Transm_inst_name))

     
    # ------------------------------------------------------------------------
    # General constants that could be changed by the user:
    print('...................... General Constants ......................... ')	  
                               
    # Data for Module 2 - Spectral and Thermal bands
    L_SAVI = 0.5                          # Constant for SAVI 
    print('General constants for Module 2:')			
    print('Constant for SAVI (L) = %s' %(L_SAVI))		
   
    # Data for Module 3 - Vegetation properties
    Apparent_atmosf_transm = 0.89    # This value is used for atmospheric correction of broad band albedo. This value is used for now, would be better to use tsw.
    path_radiance = 0.03             # Recommended, Range: [0.025 - 0.04], based on Bastiaanssen (2000).
    print('General constants for Module 3:')			
    print('Atmospheric correction of broad band albedo = %s' %(Apparent_atmosf_transm))	
    print('Path Radiance = %s' %(path_radiance))	
   
    # Data for Module 4 - Surface temperature, Cloud, Water, and Snow mask
    Rp = 0.91                        # Path radiance in the 10.4-12.5 µm band (W/m2/sr/µm)
    tau_sky = 0.866                  # Narrow band transmissivity of air, range: [10.4-12.5 µm]
    surf_temp_offset = 3             # Surface temperature offset for water 
    Temperature_offset_shadow = -1   # Temperature offset for detecting shadow
    Maximum_shadow_albedo = 0.1      # Minimum albedo value for shadow
    Temperature_offset_clouds = -3   # Temperature offset for detecting clouds
    Minimum_cloud_albedo = 0.4       # Minimum albedo value for clouds
    print('General constants for Module 4:')			
    print('Narrow band transmissivity of air = %s' %(tau_sky))	
    print('Surface temperature offset for water = %s (Kelvin)' %(surf_temp_offset))	
    print('Temperature offset for detecting shadow = %s (Kelvin)' %(Temperature_offset_shadow))	
    print('Maximum albedo value for shadow = %s' %(Maximum_shadow_albedo))	
    print('Temperature offset for detecting clouds = %s (Kelvin)' %(Temperature_offset_clouds))	
    print('Minimum albedo value for clouds = %s' %(Minimum_cloud_albedo))	

    # Data for Module 6 - Turbulence
    print('General constants for Module 6:')	
    surf_roughness_equation_used = 1 # NDVI model = 1, Raupach model = 2
    print('NDVI model(1), Raupach model(2) = %s' %(surf_roughness_equation_used))			
    
    h_obst = config.h_obst
    h_obst_kind_of_data = config.h_obst_kind_of_data
    if h_obst_kind_of_data == 0:
        print('Obstacle height constant value of = %s (Meter)' %(h_obst))
    else:
        h_obst_name = config.h_obst
        print('Map to the Obstacle height = %s' %(h_obst_name))
											
    print('Lower NDVI treshold for hot pixels = %s' %(NDVIhot_low1))			
    print('Higher NDVI treshold for hot pixels = %s' %(NDVIhot_high1))					
			
   
    # Data for Module 12 - Soil moisture
    print('General constants for Module 12:')		
			
    # Get soil parameters from config
    Theta_sat_top = config.Theta_sat_top
    Theta_sat_top_kind_of_data = config.Theta_sat_top_kind_of_data
    if Theta_sat_top_kind_of_data == 0:
        print('Saturated soil moisture content topsoil constant value of = %s (cm3/cm3)' %(Theta_sat_top))
    else:
        Theta_sat_top_name = config.Theta_sat_top
        print('Map to the Saturated soil moisture content topsoil = %s' %(Theta_sat_top_name))

    Theta_sat_sub = config.Theta_sat_sub
    Theta_sat_sub_kind_of_data = config.Theta_sat_sub_kind_of_data
    if Theta_sat_sub_kind_of_data == 0:
        print('Saturated soil moisture content subsoil constant value of = %s (cm3/cm3)' %(Theta_sat_sub))
    else:
        Theta_sat_sub_name = config.Theta_sat_sub
        print('Map to the Saturated soil moisture content subsoil  = %s' %(Theta_sat_sub_name))

    Theta_res_top = config.Theta_res_top
    Theta_res_top_kind_of_data = config.Theta_res_top_kind_of_data
    if Theta_res_top_kind_of_data == 0:
        print('Residual soil moisture content topsoil constant value of = %s (cm3/cm3)' %(Theta_res_top))
    else:
        Theta_res_top_name = config.Theta_res_top
        print('Map to the Residual soil moisture content topsoil = %s' %(Theta_res_top_name))

    Theta_res_sub = config.Theta_res_sub
    Theta_res_sub_kind_of_data = config.Theta_res_sub_kind_of_data
    if Theta_res_sub_kind_of_data == 0:
        print('Residual soil moisture content subsoil constant value of = %s (cm3/cm3)' %(Theta_res_sub))
    else:
        Theta_res_sub_name = config.Theta_res_sub
        print('Map to the residual soil moisture content subsoil = %s' %(Theta_res_sub_name))

    Soil_moisture_wilting_point = config.Wilting_Point
    Soil_moisture_wilting_point_kind_of_data = config.Wilting_Point_kind_of_data
    if Soil_moisture_wilting_point_kind_of_data == 0:
        print('Soil moisture wilting point constant value of = %s (cm3/cm3)' %(Soil_moisture_wilting_point))
    else:
        Soil_moisture_wilting_point_name = config.Wilting_Point
        print('Map to the soil moisture wilting point = %s' %(Soil_moisture_wilting_point_name))
		
    depl_factor = config.Depl_factor
    depl_factor_kind_of_data = config.Depl_factor_kind_of_data
    if depl_factor_kind_of_data == 0:
        print('Depletion factor constant value of = %s' %(depl_factor))
    else:
        depl_factor_name = config.Depl_factor
        print('Map to the Depletion factor = %s' %(depl_factor_name)) 									
		
    Light_use_extinction_factor = 0.5    # Light use extinction factor for Bear's Law
    print('Light use extinction factor for Bears Law = %s' %(Light_use_extinction_factor))	

    Field_Capacity = config.Field_Capacity
    Field_Capacity_kind_of_data = config.Field_Capacity_kind_of_data
    if Field_Capacity_kind_of_data == 0:
        print('Fraction field capacity and saturation constant value= %s' %(Field_Capacity))
    else:
        Field_Capacity_name = config.Field_Capacity
        print('Map to the Fraction field capacity and saturation = %s' %(Field_Capacity_name))
   
    print('General constants for Module 13:')

    LUEmax = config.LUE_max
    LUEmax_kind_of_data = config.LUE_max_kind_of_data
    if LUEmax_kind_of_data == 0:
        print('Light use efficiency constant value = %s' %(LUEmax))
    else:
        LUEmax_name = config.LUE_max
        print('Map to the Light use efficiency = %s' %(LUEmax_name)) 		
 							
    # Data for Module 13 - Biomass production
    # Crop-specific biomass parameters from config
    Biomass_aboveground_factor = config.Biomass_aboveground_factor  # Aboveground biomass fraction
    Th = config.Th_max_temp          # Upper limit of stomatal activity (°C)
    Kt = config.Kt_optimal_temp      # Optimum conductance temperature (°C)
    Tl = config.Tl_min_temp          # Lower limit of stomatal activity (°C)
    rl = 130                         # Bulk stomatal resistance of the well-illuminated leaf (s/m)
	
    print('Crop type: %s' % config.crop_type)
    print('Biomass parameters: LUE=%.1f, Factor=%.3f, Topt=%.1f°C, Tmin=%.1f°C, Tmax=%.1f°C' 
          % (LUEmax, Biomass_aboveground_factor, Kt, Tl, Th))	
    print('Bulk stomatal resistance of the well-illuminated leaf = %s (s/m)' %(rl))	
   
    # ------------------------------------------------------------------------
    # ------------------------------------------------------------------------
    # ---   Extract general info from Landsat or VIIRS metadata: DOY, hour, minutes
   
    if Image_Type == 1:
				
        # the path to the MTL file of landsat				
        Landsat_meta_fileName = os.path.join(input_folder, '%s_MTL.txt' % Name_Landsat_Image)

        # read out the general info out of the MTL file
        year, DOY, mon, day, hour, minutes, UTM_Zone, Sun_elevation = info_general_metadata(Landsat_meta_fileName) # call definiition info_general_metadata

        # define the kind of sensor and resolution of the sensor
        sensor1 = 'L%d' % Landsat_nr
        sensor2 = 'L%d' % Landsat_nr
        sensor3 = 'L%d' % Landsat_nr
        res1 = '30m'
        res2 = '%sm' %int(pixel_spacing)
        res3 = '30m'

    if Image_Type == 2:
							
	    #Get time from the VIIRS dataset name (IMPORTANT TO KEEP THE TEMPLATE OF THE VIIRS NAME CORRECT example: VIIRS_SVIO5_npp_d20160601_t1103128_e1108532_b23808_c20160601170854581426_noaa_ops.tif npp_viirs_i05_20150701_124752_wgs84_fit.tif)
        Total_Day_VIIRS = Name_VIIRS_Image_TB.split('_')[3]
        Total_Time_VIIRS = Name_VIIRS_Image_TB.split('_')[4]
 
        # Get the information out of the VIIRS name
        year = int(Total_Day_VIIRS[1:5])
        month = int(Total_Day_VIIRS[5:7])
        day = int(Total_Day_VIIRS[7:9])
        Startdate = '%d-%02d-%02d' % (year,month,day)
        DOY = datetime.datetime.strptime(Startdate,'%Y-%m-%d').timetuple().tm_yday
        hour = int(Total_Time_VIIRS[1:3])
        minutes = int(Total_Time_VIIRS[3:5])
 
        # define the kind of sensor and resolution of the sensor	
        sensor1 = 'PROBAV'
        sensor2 = 'VIIRS'
        res1 = '375m'
        res2 = '%sm' %int(pixel_spacing)
        res3 = '30m'

    if Image_Type == 3:

	     #Get time from the MODIS dataset name (IMPORTANT TO KEEP THE TEMPLATE OF THE MODIS NAME CORRECT example: MOD13Q1.A2008129.h18v05.006.2015175090913.hdf)
        Total_Day_MODIS = Name_MODIS_Image_LST.split('.')[-4][1:]
 
        # Get the information out of the VIIRS name
        year = int(Total_Day_MODIS[0:4])
        DOY = day = int(Total_Day_MODIS[4:7])
 
        # define the kind of sensor and resolution of the sensor	
        sensor1 = 'MODIS'
        sensor2 = 'MODIS'
        res1 = '1000m'
        res2 = '250m'
        res3 = '500m'        
    #pdb.set_trace()    
    # ------------------------------------------------------------------------
    # Define the output maps names
    proyDEM_fileName = os.path.join(output_folder, 'Output_radiation_balance', 'proy_DEM_%s.tif' %res2)
    slope_fileName = os.path.join(output_folder, 'Output_radiation_balance', 'slope_%s.tif' %res2)
    aspect_fileName = os.path.join(output_folder, 'Output_radiation_balance', 'aspect_%s.tif' %res2)
    radiation_inst_fileName = os.path.join(output_folder, 'Output_radiation_balance', 'Ra_inst_%s_%s_%s_%s_%s.tif' %(res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    phi_fileName = os.path.join(output_folder, 'Output_radiation_balance', 'phi_%s_%s_%s_%s_%s.tif' %(res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    radiation_fileName = os.path.join(output_folder, 'Output_radiation_balance', 'Ra24_mountain_%s_%s_%s_%s_%s.tif' %(res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    cos_zn_fileName = os.path.join(output_folder, 'Output_radiation_balance', 'cos_zn_%s_%s_%s_%s_%s.tif' %(res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    #Atmos_pressure_fileName = os.path.join(output_folder, 'Output_meteo', 'atmos_pressure_%s_%s_%s_%s_%s.tif' %(res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    #Psychro_c_fileName = os.path.join(output_folder, 'Output_meteo', 'psychro_%s_%s_%s_%s_%s.tif' %(res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    water_mask_temp_fileName = os.path.join(output_folder, 'Output_evapotranspiration', '%s_Water_mask_temporary_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    veg_cover_fileName = os.path.join(output_folder, 'Output_vegetation', '%s_vegt_cover_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    lai_fileName = os.path.join(output_folder, 'Output_vegetation', '%s_lai_average_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    #nitrogen_fileName = os.path.join(output_folder, 'Output_vegetation', '%s_nitrogen_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    #tir_emissivity_fileName = os.path.join(output_folder, 'Output_vegetation', '%s_tir_emissivity_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    #fpar_fileName = os.path.join(output_folder, 'Output_vegetation', '%s_fpar_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    #b10_emissivity_fileName = os.path.join(output_folder, 'Output_vegetation', '%s_b10_emissivity_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    cloud_mask_fileName = os.path.join(output_folder, 'Output_cloud_masked', '%s_cloud_mask_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    surf_temp_fileName = os.path.join(output_folder, 'Output_vegetation', '%s_surface_temp_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    temp_surface_sharpened_fileName =  os.path.join(output_folder, 'Output_vegetation', '%s_surface_temp_sharpened_%s_%s_%s_%s_%s.tif' %(sensor1, res1, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    snow_mask_fileName = os.path.join(output_folder, 'Output_evapotranspiration', '%s_snow_mask_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    water_mask_fileName = os.path.join(output_folder, 'Output_evapotranspiration', '%s_water_mask_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    #shadow_mask_fileName = os.path.join(output_folder, 'Output_cloud_masked', '%s_shadow_mask_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    Rn_24_fileName = os.path.join(output_folder, 'Output_evapotranspiration', '%s_Rn_24_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    #rn_inst_fileName = os.path.join(output_folder, 'Output_energy_balance', '%s_Rn_inst_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    #g_inst_fileName = os.path.join(output_folder, 'Output_energy_balance', '%s_G_inst_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    temp_corr_fileName = os.path.join(output_folder, 'Output_vegetation', '%s_temp_corr_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    ts_dem_fileName = os.path.join(output_folder, 'Output_vegetation', '%s_ts_dem_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    #surf_rough_fileName = os.path.join(output_folder, 'Output_vegetation', '%s_surface_roughness_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    hot_pixels_fileName = os.path.join(output_folder, 'Output_evapotranspiration', '%s_hot_pixels_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    cold_pixels_fileName = os.path.join(output_folder, 'Output_evapotranspiration', '%s_cold_pixels_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    #h_inst_fileName = os.path.join(output_folder, 'Output_energy_balance', '%s_h_inst_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    #min_bulk_surf_res_fileName = os.path.join(output_folder, 'Output_evapotranspiration', '%s_%s_min_bulk_surf_resis_24_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    EF_inst_fileName = os.path.join(output_folder, 'Output_evapotranspiration', '%s_EFinst_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    #LE_inst_fileName = os.path.join(output_folder, 'Output_energy_balance', '%s_LEinst_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    ETref_24_fileName = os.path.join(output_folder, 'Output_evapotranspiration', '%s_ETref_24_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    ETA_24_fileName = os.path.join(output_folder, 'Output_evapotranspiration', '%s_ETact_24_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    ETP_24_fileName = os.path.join(output_folder, 'Output_evapotranspiration', '%s_ETpot_24_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    ET_24_deficit_fileName = os.path.join(output_folder, 'Output_evapotranspiration', '%s_ET_24_deficit_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    AF_fileName = os.path.join(output_folder, 'Output_evapotranspiration', '%s_Advection_Factor_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    kc_fileName = os.path.join(output_folder, 'Output_evapotranspiration', '%s_kc_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    kc_max_fileName = os.path.join(output_folder, 'Output_evapotranspiration', '%s_kc_max_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    #bulk_surf_res_fileName = os.path.join(output_folder, 'Output_evapotranspiration', '%s_bulk_surf_resis_24_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    total_soil_moisture_fileName = os.path.join(output_folder, 'Output_soil_moisture', '%s_Total_soil_moisture_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    top_soil_moisture_fileName = os.path.join(output_folder, 'Output_soil_moisture', '%s_Top_soil_moisture_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    RZ_SM_fileName = os.path.join(output_folder, 'Output_soil_moisture', '%s_Root_zone_moisture_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    #SM_stress_trigger_fileName = os.path.join(output_folder, 'Output_soil_moisture', '%s_Moisture_stress_trigger_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    #moisture_stress_biomass_fileName = os.path.join(output_folder, 'Output_biomass_production', '%s_Moisture_stress_biomass_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    irrigation_needs_fileName = os.path.join(output_folder, 'Output_soil_moisture', '%s_irrigation_needs_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    Tact24_fileName = os.path.join(output_folder, 'Output_evapotranspiration', '%s_Tact_24_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    Eact24_fileName = os.path.join(output_folder, 'Output_evapotranspiration', '%s_Eact_24_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    Tpot24_fileName = os.path.join(output_folder, 'Output_evapotranspiration', '%s_Tpot_24_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    T24_deficit_fileName = os.path.join(output_folder, 'Output_evapotranspiration', '%s_T_24_deficit_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))   
    #LUE_fileName = os.path.join(output_folder, 'Output_biomass_production', '%s_LUE_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    Biomass_prod_fileName = os.path.join(output_folder, 'Output_biomass_production', '%s_Biomass_production_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    Biomass_wp_fileName = os.path.join(output_folder, 'Output_biomass_production', '%s_Biomass_wp_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    Biomass_deficit_fileName = os.path.join(output_folder, 'Output_biomass_production', '%s_Biomass_deficit_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
    dst_FileName_DEM = os.path.join(output_folder, 'Output_radiation_balance', 'proyDEM_%s.tif' %res1)
    dst_FileName_Ra_inst = os.path.join(output_folder, 'Output_radiation_balance', 'Ra_inst_%s_%s_%s.tif' %(res1, year, DOY))
    dst_FileName_phi = os.path.join(output_folder, 'Output_radiation_balance', 'phi_%s_%s_%s.tif' %(res1, year, DOY))
 
    # Define name that is only needed in Image type 1 (Landsat)			
    if Image_Type == 1:	   
       ndvi_fileName2 = os.path.join(output_folder, 'Output_vegetation', '%s_NDVI_%s_%s_%s_%s_%s.tif' %(sensor3, res3, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
       QC_Map_fileName = os.path.join(output_folder, 'Output_temporary', '%s_quality_mask_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
       proyDEM_fileName_90 = os.path.join(output_folder, 'Output_temporary', 'proy_DEM_90.tif')

    # Names for PROBA-V and VIIRS option
    if Image_Type == 2:		
         
        proyVIIRS_QC_fileName = os.path.join(output_folder, 'Output_VIIRS', '%s_QC_proy_%s_%s_%s_%s_%s.tif' %(sensor2, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
        #proyPROBAV_Cloud_Mask_fileName = os.path.join(output_folder, 'Output_cloud_masked', '%s_cloud_mask_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
        #proyVIIRS_Cloud_Mask_fileName = os.path.join(output_folder, 'Output_cloud_masked', '%s_cloud_mask_%s_%s_%s_%s_%s.tif' %(sensor2, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
        proyDEM_fileName_375 = os.path.join(output_folder, 'Output_temporary', 'proy_DEM_375.tif')
        proyDEM_fileName_400 = os.path.join(output_folder, 'Output_temporary', 'proy_DEM_400.tif')
 
   # Names for PROBA-V and VIIRS option
    if Image_Type == 3:		
        proyMODIS_QC_fileName = os.path.join(output_folder, 'Output_MODIS', '%s_QC_proy_%s_%s_%s_%s_%s.tif' %(sensor2, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
        proyDEM_fileName_1000 = os.path.join(output_folder, 'Output_temporary', 'proy_DEM_1000.tif')

    # ------------------------------------------------------------------------
    # ------------------------------------------------------------------------
    # ---   Empty folder with output maps before starting -
    # --------------Calulation Landsat----------------------------------------
   
    print('---------------------------------------------------------')
    print('------------------ General info -------------------------')
    print('---------------------------------------------------------')
    print('General info: ')
    print('  DOY: ', DOY)
    
    if not Image_Type == 3:
        print('  Hour: ', hour)
        print('  Minutes: ', '%0.3f' % minutes)
        
    print('  UTM_Zone: ', UTM_Zone)
    
    print('---------------------------------------------------------')
    print('-------------------- Open DEM ---------------------------')
    print('---------------------------------------------------------')
       
    # Open DEM and create Latitude and longitude files
    lat, lon, lat_fileName, lon_fileName = DEM_lat_lon(DEM_fileName, output_folder)
     
    # Reproject from Geog Coord Syst to UTM -
    # 1) DEM - Original DEM coordinates is Geographic: lat, lon
    dest, ulx_dem, lry_dem, lrx_dem, uly_dem, epsg_to = reproject_dataset(
                DEM_fileName, pixel_spacing, UTM_Zone = UTM_Zone)
    band = dest.GetRasterBand(1)   # Get the reprojected dem band
    ncol = dest.RasterXSize        # Get the reprojected dem column size
    nrow = dest.RasterYSize        # Get the reprojected dem row size
    shape = [ncol, nrow]
       
    # Read out the DEM band and print the DEM properties
    data_DEM = band.ReadAsArray(0, 0, ncol, nrow)
    #data_DEM[data_DEM<0] = 1
    print('Projected DEM - ')
    print('   Size: ', ncol, nrow)
    print('   Upper Left corner x, y: ', ulx_dem, ',', uly_dem)
    print('   Lower right corner x, y: ', lrx_dem, ',', lry_dem)
  
    # 2) Latitude File - reprojection
    # Define output name of the latitude file        					
    lat_fileName_rep = os.path.join(output_folder, 'Output_radiation_balance',
                                        'latitude_proj_%s_%s_%s_%s_%s.tif' %(res1, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))

    # reproject latitude to the landsat projection	 and save as tiff file																																
    lat_rep, ulx_dem, lry_dem, lrx_dem, uly_dem, epsg_to = reproject_dataset(
               lat_fileName, pixel_spacing, UTM_Zone=UTM_Zone)
 
    # Get the reprojected latitude data															
    lat_proy = lat_rep.GetRasterBand(1).ReadAsArray(0, 0, ncol, nrow)
     
    # 3) Longitude file - reprojection
    # Define output name of the longitude file  				
    lon_fileName_rep = os.path.join(output_folder, 'Output_radiation_balance', 
								'longitude_proj_%s_%s_%s_%s_%s.tif' %(res1, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))

    # reproject longitude to the landsat projection	 and save as tiff file	
    lon_rep, ulx_dem, lry_dem, lrx_dem, uly_dem, epsg_to = reproject_dataset(lon_fileName, pixel_spacing, UTM_Zone)

    # Get the reprojected longitude data	
    lon_proy = lon_rep.GetRasterBand(1).ReadAsArray(0, 0, ncol, nrow)
       
    # Calculate slope and aspect from the reprojected DEM
    deg2rad, rad2deg, slope, aspect = Calc_Gradient(data_DEM, pixel_spacing)

    # Saving the reprojected maps
    save_GeoTiff_proy(dest, data_DEM, proyDEM_fileName, shape, nband = 1)
    save_GeoTiff_proy(dest, slope, slope_fileName, shape, nband = 1)
    save_GeoTiff_proy(dest, aspect, aspect_fileName, shape, nband = 1)
    save_GeoTiff_proy(lon_rep, lon_proy, lon_fileName_rep, shape, nband = 1)
    save_GeoTiff_proy(lat_rep, lat_proy, lat_fileName_rep, shape, nband = 1)
    
    print('---------------------------------------------------------')
    print('-------------------- Radiation --------------------------')
    print('---------------------------------------------------------')
    #pdb.set_trace()
    if Image_Type == 2:

        # Rounded difference of the local time from Greenwich (GMT) (hours):
        delta_GTM = round(np.sign(lon[nrow/2, ncol/2]) * lon[nrow/2, ncol/2] * 24 / 360)
        if np.isnan(delta_GTM) == True:
             delta_GTM = round(np.nanmean(lon) * np.nanmean(lon)  * 24 / 360)

        hour += delta_GTM
        if hour < 0.0:
            day -= 1
            hour += 24
        if hour >= 24:
            day += 1
            hour -= 24        

    if Image_Type == 3:        

           hour, minutes = Modis_Time(src_FileName_LST, epsg_to, proyDEM_fileName)
           
    # Calculation of extraterrestrial solar radiation for slope and aspect   
    Ra_mountain_24, Ra_inst, cos_zn, dr, phi, delta = Calc_Ra_Mountain(lon, DOY, hour, minutes, lon_proy, lat_proy, slope, aspect)  

    if Image_Type == 2 or Image_Type == 3:
        Sun_elevation = 90 - (np.nanmean(cos_zn) * 180/np.pi) 
 
    # Save files created in module 1
    save_GeoTiff_proy(dest, cos_zn, cos_zn_fileName, shape, nband = 1)
    save_GeoTiff_proy(dest, Ra_mountain_24, radiation_fileName, shape, nband = 1)
    save_GeoTiff_proy(dest, Ra_inst, radiation_inst_fileName, shape, nband = 1 )
    save_GeoTiff_proy(dest, phi, phi_fileName, shape, nband = 1 )

    # Resample DEM related maps to resolution of clipped Landsat images - 30 m
        
    # 2) DEM
    DEM_resh = Reshape_Reproject_Input_data(proyDEM_fileName, dst_FileName_DEM, proyDEM_fileName)
    lsc = gdal.Open(proyDEM_fileName)
    
    #	Get the extend of the remaining landsat file	after clipping based on the DEM file	
    y_size_lsc = lsc.RasterYSize
    x_size_lsc = lsc.RasterXSize    
    shape_lsc = [x_size_lsc, y_size_lsc]   
    
    # 4) Reshaped instantaneous radiation
    Ra_inst = Reshape_Reproject_Input_data(radiation_inst_fileName, dst_FileName_Ra_inst, proyDEM_fileName)
       
    # 5) Reshaped psi
    phi = Reshape_Reproject_Input_data(phi_fileName, dst_FileName_phi, proyDEM_fileName)

    # 6) Reshape meteo data if needed (when path instead of number is input)
      
    # 6a) Instantaneous Temperature
    if Temp_inst_kind_of_data == 1:
        try:
            Temp_inst_fileName = os.path.join(output_folder, 'Output_radiation_balance', 'Temp_inst_input.tif')
            Temp_inst = Reshape_Reproject_Input_data(Temp_inst_name, Temp_inst_fileName, proyDEM_fileName)
        except:
            print('ERROR: Check the instantenious Temperature input path in the meteo excel tab') 
                
    # 6b) Daily Temperature         
    if Temp_24_kind_of_data == 1:
        try:
            Temp_24_fileName = os.path.join(output_folder, 'Output_radiation_balance', 'Temp_24_input.tif')
            Temp_24 = Reshape_Reproject_Input_data(Temp_24_name, Temp_24_fileName, proyDEM_fileName)
        except:
            print('ERROR: Check the daily Temperature input path in the meteo excel tab') 
                
    # 6c) Daily Relative Humidity       
    if RH_24_kind_of_data == 1:
        try:
            RH_24_fileName = os.path.join(output_folder, 'Output_radiation_balance', 'RH_24_input.tif')
            RH_24 = Reshape_Reproject_Input_data(RH_24_name, RH_24_fileName, proyDEM_fileName)
        except:
            print('ERROR: Check the instantenious Relative Humidity input path in the meteo excel tab') 

     # 6d) Instantaneous Relative Humidity      
    if RH_inst_kind_of_data == 1:
        try:
            RH_inst_fileName = os.path.join(output_folder, 'Output_radiation_balance', 'RH_inst_input.tif')
            RH_inst = Reshape_Reproject_Input_data(RH_inst_name, RH_inst_fileName, proyDEM_fileName)  
        except:
            print('ERROR: Check the daily Relative Humidity input path in the meteo excel tab') 
 
     # 6e) Daily wind speed      
    if Wind_24_kind_of_data == 1:
        try:
            Wind_24_fileName = os.path.join(output_folder, 'Output_radiation_balance','Wind_24_input.tif')
            Wind_24 = Reshape_Reproject_Input_data(Wind_24_name, Wind_24_fileName, proyDEM_fileName)
            Wind_24[Wind_24 < 1.5] = 1.5
        except:
            print('ERROR: Check the daily wind input path in the meteo excel tab') 
  
     # 6f) Instantaneous wind speed              
    if Wind_inst_kind_of_data == 1:
        try:
            Wind_inst_fileName = os.path.join(output_folder, 'Output_radiation_balance', 'Wind_inst_input.tif')
            Wind_inst = Reshape_Reproject_Input_data(Wind_inst_name, Wind_inst_fileName, proyDEM_fileName)  
            Wind_inst[Wind_inst < 1.5] = 1.5
        except:
            print('ERROR: Check the instantenious wind input path in the meteo excel tab') 

    # 6g) Daily incoming Radiation      
    if Method_Radiation_24 == 1:    
        if Rs_24_kind_of_data == 1:
            try:
                Net_radiation_daily_fileName = os.path.join(output_folder, 'Output_radiation_balance', 'Ra_24_input.tif')
                Rs_24 = Reshape_Reproject_Input_data(Rs_24_name, Net_radiation_daily_fileName, proyDEM_fileName)
            except:
                print('ERROR: Check the daily net radiation input path in the meteo excel tab') 
 
    # 6h) Instantaneous incoming Radiation    
    if Method_Radiation_inst == 1:            
        if Rs_in_inst_kind_of_data == 1:
            try:
                Net_radiation_inst_fileName = os.path.join(output_folder, 'Output_radiation_balance', 'Ra_in_inst_input.tif')
                Rs_in_inst = Reshape_Reproject_Input_data(Rs_in_inst_name, Net_radiation_inst_fileName, proyDEM_fileName)
            except:
                print('ERROR: Check the instanenious net radiation input path in the meteo excel tab') 
 
    # 6i) Daily Transmissivity
    if Method_Radiation_24 == 2:      
        if Transm_24_kind_of_data == 1:
            try:
                Transm_24_fileName = os.path.join(output_folder, 'Output_radiation_balance', 'Transm_24_input.tif')
                Transm_24 = Reshape_Reproject_Input_data(Transm_24_name, Transm_24_fileName, proyDEM_fileName)
            except:
                print('ERROR: Check the daily transmissivity input path in the meteo excel tab') 

    # 6j) Instantaneous Transmissivity
    if Method_Radiation_inst == 2:     
        if Transm_inst_kind_of_data == 1:
            try:
                Transm_inst_fileName = os.path.join(output_folder, 'Output_radiation_balance', 'Transm_inst_input.tif')
                Transm_inst = Reshape_Reproject_Input_data(Transm_inst_name, Transm_inst_fileName, proyDEM_fileName)
            except:
                print('ERROR: Check the instantenious transmissivity input path in the meteo excel tab') 
 
    # 6k) Theta saturated topsoil    
    if Theta_sat_top_kind_of_data == 1:
        try:
           Theta_sat_top_fileName = os.path.join(output_folder, 'Output_temporary','Theta_sat_top_input.tif')
           Theta_sat_top = Reshape_Reproject_Input_data(Theta_sat_top_name, Theta_sat_top_fileName, proyDEM_fileName)
        except:
           print('ERROR: Check the saturated top soil input path in the soil excel tab') 

    # 6l) Theta saturated subsoil          
    if Theta_sat_sub_kind_of_data == 1:
        try:
            Theta_sat_sub_fileName = os.path.join(output_folder, 'Output_temporary','Theta_sat_sub_input.tif')
            Theta_sat_sub  =Reshape_Reproject_Input_data(Theta_sat_sub_name,Theta_sat_sub_fileName,proyDEM_fileName)
        except:
            print('ERROR: Check the saturated sub soil input path in the soil excel tab') 
               
    # 6m) Theta residual topsoil        
    if Theta_res_top_kind_of_data == 1:
        try:    
            Theta_res_top_fileName = os.path.join(output_folder, 'Output_temporary','Theta_res_top_input.tif')
            Theta_res_top=Reshape_Reproject_Input_data(Theta_res_top_name,Theta_res_top_fileName,proyDEM_fileName)
        except:
            print('ERROR: Check the residual top soil input path in the soil excel tab') 

    # 6n) Theta residual subsoil    
    if Theta_res_sub_kind_of_data == 1:
        try:
            Theta_res_sub_fileName = os.path.join(output_folder, 'Output_temporary','Theta_res_sub_input.tif')
            Theta_res_sub=Reshape_Reproject_Input_data(Theta_res_sub_name,Theta_res_sub_fileName,proyDEM_fileName)
        except:
            print('ERROR: Check the residual sub soil input path in the soil excel tab') 
                
    # 6o) Wilting point    
    if Soil_moisture_wilting_point_kind_of_data == 1:
        try:
            Soil_moisture_wilting_point_fileName = os.path.join(output_folder, 'Output_temporary','Soil_moisture_wilting_point_input.tif')
            Soil_moisture_wilting_point=Reshape_Reproject_Input_data(Soil_moisture_wilting_point_name,Soil_moisture_wilting_point_fileName,proyDEM_fileName)
        except:
            print('ERROR: Check the wilting point input path in the soil excel tab') 

    # 6p) Fraction field capacity        
    if Field_Capacity_kind_of_data == 1:
        try:
            Field_Capacity_fileName = os.path.join(output_folder, 'Output_temporary','Fraction_Field_Capacity_and_Saturation_input.tif')
            Field_Capacity=Reshape_Reproject_Input_data(Field_Capacity_name,Field_Capacity_fileName,proyDEM_fileName)
        except:
            print('ERROR: Check the field capacity input path in the soil excel tab') 

    # 6q) Light Use Efficiency        
    if LUEmax_kind_of_data == 1:
        try:
            LUEmax_fileName = os.path.join(output_folder, 'Output_temporary','LUEmax_input.tif')
            LUEmax=Reshape_Reproject_Input_data(LUEmax_name,LUEmax_fileName,proyDEM_fileName)
        except:
            print('ERROR: Check the LUE input path in the soil excel tab') 

    # 6r) Obstacle height      						
    if h_obst_kind_of_data == 1:
        try:
            h_obst_fileName = os.path.join(output_folder, 'Output_temporary','h_obst_input.tif')
            h_obst=Reshape_Reproject_Input_data(h_obst_name,h_obst_fileName,proyDEM_fileName)
        except:
            print('ERROR: Check the obstacle height input path in the soil excel tab') 
 
    # 6s) deplection factor      						
    if depl_factor_kind_of_data == 1:
        try:
            depl_factor_fileName = os.path.join(output_folder, 'Output_temporary','depl_factor_input.tif')
            depl_factor=Reshape_Reproject_Input_data(depl_factor_name,depl_factor_fileName,proyDEM_fileName)
        except:
            print('ERROR: Check the depletion factor input path in the soil excel tab') 

    print('---------------------------------------------------------')
    print('-------------------- Meteo part 1 -----------------------')
    print('---------------------------------------------------------')
   
    # Computation of some vegetation properties
    # 1)
    #constants:
    Temp_lapse_rate = temp_lapse  # Temperature lapse rate (°K/m) - 0.0065(ORI)
    Gsc = 1367        # Solar constant (W / m2)   
    SB_const = 5.6703E-8  # Stefan-Bolzmann constant (watt/m2/°K4)
        
    # Atmospheric pressure for altitude:
    Pair = 101.3 * np.power((293 - Temp_lapse_rate * DEM_resh) / 293, 5.26)
    print('Pair = ', '%0.3f (kPa)' % np.nanmean(Pair))
    # Psychrometric constant (kPa / °C), FAO 56, eq 8.:
    Psychro_c = 0.665E-3 * Pair
       
    # Saturation Vapor Pressure at the air temperature (kPa):
    esat_inst = 0.6108 * np.exp(17.27 * Temp_inst / (Temp_inst + 237.3))
    esat_24=0.6108 * np.exp(17.27 * Temp_24 / (Temp_24 + 237.3))
      
    # Actual vapour pressure (kPa), FAO 56, eq 19.:
    eact_inst = RH_inst * esat_inst / 100
    eact_24 = RH_24 * esat_24 / 100
    print('Instantaneous Saturation Vapor Pressure = ', '%0.3f (kPa)' % np.nanmean(esat_inst))
    print('Instantaneous Actual vapour pressure =  ', '%0.3f (kPa)' % np.nanmean(eact_inst))
    print('Daily Saturation Vapor Pressure = ', '%0.3f (kPa)' % np.nanmean(esat_24))
    print('Daily Actual vapour pressure =  ', '%0.3f (kPa)' % np.nanmean(eact_24))

    # ------------------------------------------------------------------------
    # ------------------------------------------------------------------------
    #-------------------------Calculations LANDSAT ---------------------------
    if Image_Type == 1:

        print('---------------------------------------------------------')
        print('-------------------- Open Landsat -----------------------')
        print('---------------------------------------------------------')
   
        # Define bands used for each Landsat number
        if Landsat_nr == 5 or Landsat_nr == 7:
            Bands = np.array([1, 2, 3, 4, 5, 7, 6])
        elif Landsat_nr == 8 or Landsat_nr == 9:
           Bands = np.array([2, 3, 4, 5, 6, 7, 10, 11])  
        else:
            print('Landsat image not supported, use Landsat 7 or 8')

        # Open MTL landsat and get the correction parameters   
        Landsat_meta_fileName = os.path.join(input_folder, '%s_MTL.txt' %Name_Landsat_Image)
        Lmin, Lmax, k1_c, k2_c = info_band_metadata(Landsat_meta_fileName, Bands)
        print('Lmin= ', Lmin)
        print('Lmax= ', Lmax)
        print('k1= ', k1_c)
        print('k2= ', k2_c)
        
        # Calibration parameters - comment
        #Lmin_L5 = [-2.8, -1.2, -1.5, -0.37, 1.2378, -0.150]    # REVISE LS 5 TM
        #Lmax_L5 = [296.8, 204.3, 206.2, 27.19, 15.303, 14.38]  # REVISE LS 5 TM
    
        # Mean solar exo-atmospheric irradiance for each band (W/m2/microm)
        # for the different Landsat images (L5, L7, or L8)
        ESUN_L5 = np.array([1983, 1796, 1536, 1031, 220, 83.44])
        ESUN_L7 = np.array([1997, 1812, 1533, 1039, 230.8, 84.9])
        ESUN_L8 = np.array([1973.28, 1842.68, 1565.17, 963.69, 245, 82.106])
    
        # Open one band - To get the metadata of the landsat images only once (to get the extend)
        src_FileName = os.path.join(input_folder, '%s_B2.TIF' %Name_Landsat_Image)  # before 10!
        ls, band_data, ulx, uly, lrx, lry, x_size_ls, y_size_ls = Get_Extend_Landsat(src_FileName)
        print('  Upper Left corner x, y: ', ulx, ', ', uly)
        print('  Lower right corner x, y: ', lrx, ', ', lry)
         
        # Crop  the Landsat images to the DEM extent -
        dst_FileName = os.path.join(output_folder, 'Output_temporary', '%s_cropped_LS_b2_%s_%s_%s.tif' %(sensor1, res1, year, DOY))  # Before 10 !!
        dir_name = os.path.dirname(dst_FileName)  # Directory of the file
     
        # If the directory does not exist, create it.
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
             
        lsc, ulx, uly, lrx, lry, epsg_to = reproject_dataset_example(src_FileName, proyDEM_fileName)											
        
        #	Get the extend of the remaining landsat file	after clipping based on the DEM file	
        y_size_lsc = lsc.RasterYSize
        x_size_lsc = lsc.RasterXSize    
        shape_lsc = [x_size_lsc, y_size_lsc]
        
        print('--- ')
        print('Cropped LANDSAT Image - ')
        print('  Size :', x_size_lsc, y_size_lsc)
        print('  Upper Left corner x, y: ', ulx, ', ',  uly)
        print('  Lower right corner x, y: ', lrx, ', ', lry)
       
        # output names for resampling
        dst_LandsatMask = os.path.join(output_folder, 'Output_temporary', '%s_cropped_LANDSATMASK_%s_%s_%s.tif' %(sensor1, res1, year, DOY))

        # Open Landsat data only if all additional data is not defined.

        # In automated workflow, no additional inputs are provided, so always process Landsat
        if True:  # No additional NDVI/Albedo/Temp files provided					

            # Collect the landsat Thermal and Spectral data
            # 1. Create mask for the landsat images
            # 2. Save the Thermal data in a 3D array
            # 3. Save the Spectral data in a 3D array
        
            #  1.)
            # find clipping extent for landsat images: NTIR is larger than VTIR
            # Open original Landsat image for the band number 11

            # if landsat 5 or 7 is used then first create a mask for removing the no data stripes       
            if Landsat_nr == 5 or Landsat_nr == 7:
                src_FileName = os.path.join(input_folder, '%s_B6.TIF' % (Name_Landsat_Image)) #open smallest band
                if not os.path.exists(src_FileName):
                    src_FileName = os.path.join(input_folder, '%s_B6_VCID_2.TIF' % (Name_Landsat_Image))														
                src_FileName_2 = os.path.join(input_folder, '%s_B1.TIF' % (Name_Landsat_Image)) #open smallest band
                src_FileName_3 = os.path.join(input_folder, '%s_B3.TIF' % (Name_Landsat_Image)) #open smallest band
                src_FileName_4 = os.path.join(input_folder, '%s_B4.TIF' % (Name_Landsat_Image)) #open smallest band
                src_FileName_5 = os.path.join(input_folder, '%s_B7.TIF' % (Name_Landsat_Image)) #open smallest band
                src_FileName_6 = os.path.join(input_folder, '%s_B2.TIF' % (Name_Landsat_Image)) #open smallest band
                src_FileName_7 = os.path.join(input_folder, '%s_B5.TIF' % (Name_Landsat_Image)) #open smallest band
                ls_data=Open_landsat(src_FileName,proyDEM_fileName)
                ls_data_2=Open_landsat(src_FileName_2,proyDEM_fileName)
                ls_data_3=Open_landsat(src_FileName_3,proyDEM_fileName)
                ls_data_4=Open_landsat(src_FileName_4,proyDEM_fileName)
                ls_data_5=Open_landsat(src_FileName_5,proyDEM_fileName)
                ls_data_6=Open_landsat(src_FileName_6,proyDEM_fileName)
                ls_data_7=Open_landsat(src_FileName_7,proyDEM_fileName)
                        
                # create and save the landsat mask for all images based on band 11 (smallest map)
                ClipLandsat=np.ones((shape_lsc[1], shape_lsc[0]))
                ClipLandsat=np.where(np.logical_or(np.logical_or(np.logical_or(np.logical_or(np.logical_or(np.logical_or(ls_data==0,ls_data_2==0),ls_data_3==0),ls_data_4==0),ls_data_5==0),ls_data_6==0),ls_data_7==0),0,1)

            # If landsat 8 then use landsat band 10 and 11
            elif Landsat_nr == 8 or Landsat_nr == 9:
                 src_FileName_11 = os.path.join(input_folder, '%s_B11.TIF' % (Name_Landsat_Image)) #open smallest band
                 ls_data_11=Open_landsat(src_FileName_11,proyDEM_fileName)

                 src_FileName_10 = os.path.join(input_folder, '%s_B10.TIF' % (Name_Landsat_Image)) #open smallest band
                 ls_data_10=Open_landsat(src_FileName_10, proyDEM_fileName)
 
                 # create and save the landsat mask for all images based on band 10 and 11
                 ClipLandsat=np.ones((shape_lsc[1], shape_lsc[0]))
                 ClipLandsat=np.where(np.logical_or(ls_data_11==0, ls_data_10==0),0,1)

            else:
                print('Landsat image not supported, use Landsat 7 or 8')

            # Create Cloud mask is BQA map is available (newer version Landsat images)            
            BQA_LS_Available = 0
            if os.path.exists(os.path.join(input_folder, '%s_QA_PIXEL.TIF' %Name_Landsat_Image)):
                src_FileName_BQA = os.path.join(input_folder, '%s_QA_PIXEL.TIF' %Name_Landsat_Image)
                ls_data_BQA = Open_landsat(src_FileName_BQA,proyDEM_fileName)
                #L8_qa_product = 'LANDSAT_8_C2_L2_QAPixel'
                #with rasterio.open(src_FileName_BQA) as src:
                #    img_qa_data = src.read(1)
                #img_qa_data = rasterio.open(ls_data_BQA)
                #QC_mask_Cloud = unpackqa.unpack_to_array(img_qa_data, 
                #                                   product=L8_qa_product,
                #                                   flags=['Cloud'])
                #QC_mask_Cloud[ls_data_BQA!=1] = 0
                #QC_mask_Cloud[ls_data_BQA==1] = 1
                #print('Original Scene Shape: {}'.format(img_qa_data.shape))
                #print('Cloud and Shadow mask shape: {}'.format(cloud_and_shadow_mask.shape))
                QC_mask_Cloud = np.copy(ls_data_BQA)
                #QC_mask_Cloud = cloud_and_shadow_mask.sum(axis=-1) > 0
                if Landsat_nr == 8 or Landsat_nr == 9:
                    Cloud_Treshold = 30000
                if Landsat_nr == 5 or Landsat_nr == 7:
                    Cloud_Treshold = 700
                #QC_mask_Cloud = np.copy(ls_data_BQA)
                QC_mask_Cloud[ls_data_BQA<Cloud_Treshold] = 0
                QC_mask_Cloud[ls_data_BQA>=Cloud_Treshold] = 1                             
                BQA_LS_Available = 1         
                     
            #pdb.set_trace()

            # Open data of the landsat mask
            ls_data=Open_landsat(src_FileName, proyDEM_fileName)
       
            # Save Landsat mask as a tiff file							
            save_GeoTiff_proy(lsc, ClipLandsat, dst_LandsatMask, shape_lsc, nband=1)
       
            # 2.)          
            # Create 3D array to store the Termal band(s) (nr10(&11) for LS8 and n6 for LS7) 
            therm_data = Landsat_therm_data(Bands,input_folder,Name_Landsat_Image,output_folder,shape_lsc,ClipLandsat, proyDEM_fileName)          
       
            # 3.)
            # Create 3D array to store Spectral radiance and Reflectivity for each band
            Reflect, Spec_Rad = Landsat_Reflect(Bands, input_folder, Name_Landsat_Image, output_folder, shape_lsc, ClipLandsat, Lmax, Lmin, ESUN_L5, ESUN_L7, ESUN_L8, cos_zn, dr, Landsat_nr, proyDEM_fileName)
       
            # save spectral data 
            #for i in range(0,6):							
                #spec_ref_fileName = os.path.join(output_folder, 'Output_radiation_balance','%s_spectral_reflectance_B%s_%s_%s_%s_%s_%s.tif' %(Bands[i], sensor1, res3, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
                #save_GeoTiff_proy(lsc, Reflect[:, :, i], spec_ref_fileName, shape_lsc, nband=1)
          								
            # ------------------------------------------------------------------------
            # ------------------------------------------------------------------------
            # ----   MODULE 3 - Vegetation properties

        print('---------------------------------------------------------')
        print('-------------------- Module 3 ---------------------------')
        print('---------------------------------------------------------')
 						
        # Check NDVI							
        try:
            if False:  # No user files in automated workflow					
                # Output folder NDVI								
                ndvi_fileName2 = os.path.join(output_folder, 'Output_vegetation', 'User_NDVI_%s_%s_%s_%s_%s.tif' %(res3, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
                NDVI=Reshape_Reproject_Input_data(r'%s' %str(ws['B%d' % number].value),ndvi_fileName2,proyDEM_fileName)		 														 

                water_mask_temp = np.zeros((shape_lsc[1], shape_lsc[0]))
                water_mask_temp[NDVI < 0.0] = 1.0
			  								
            else:
                # use the Landsat reflectance to calculate the surface albede, NDVI and SAVI
                NDVI = Calc_NDVI(Reflect)
          
                # save landsat NDVI	
                ndvi_fileName2 = os.path.join(output_folder, 'Output_vegetation', '%s_NDVI_%s_%s_%s_%s_%s.tif' %(sensor3, res3, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))			
                save_GeoTiff_proy(lsc, NDVI, ndvi_fileName2, shape_lsc, nband=1)	
                
                # Calculate temporal water mask
                water_mask_temp=Water_Mask(shape_lsc,Reflect)
                
        except:
            assert "Please check the NDVI input path"
												
        # Check SAVI							
        try:
            if False:  # No user files in automated workflow					
                # Output folder SAVI							
                savi_fileName = os.path.join(output_folder, 'Output_vegetation', 'User_SAVI_%s_%s_%s_%s_%s.tif' %(res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
                SAVI=Reshape_Reproject_Input_data(r'%s' %str(ws['C%d' % number].value),savi_fileName,proyDEM_fileName)		 					
		 									
            else:
                # use the Landsat reflectance to calculate the SAVI
                SAVI = Calc_SAVI(Reflect, L_SAVI)

                # save landsat SAVI	
                savi_fileName = os.path.join(output_folder, 'Output_vegetation', '%s_SAVI_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))				
                save_GeoTiff_proy(lsc, SAVI, savi_fileName, shape_lsc, nband=1)																  

        except:
            assert "Please check the SAVI input path"
  
        # Check Surface albedo	
        try:
            if False:  # No user files in automated workflow					
                # Output folder surface albedo						
                surface_albedo_fileName = os.path.join(output_folder, 'Output_vegetation','User_surface_albedo_%s_%s_%s_%s_%s.tif' %(res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
                Surf_albedo=Reshape_Reproject_Input_data(r'%s' %str(ws['D%d' % number].value),surface_albedo_fileName,proyDEM_fileName)		 					
		 									
            else:
                surface_albedo_fileName = os.path.join(output_folder, 'Output_vegetation','%s_surface_albedo_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))

                # use the Landsat reflectance to calculate the surface albede, NDVI and SAVI
                Surf_albedo = Calc_albedo(Reflect,path_radiance,Apparent_atmosf_transm)
 
                # save landsat surface albedo
                save_GeoTiff_proy(lsc, Surf_albedo, surface_albedo_fileName, shape_lsc, nband=1)																  
        except:
              assert "Please check the Albedo input path"        
	 						
        # calculate vegetation properties
        FPAR,tir_emis,Nitrogen,vegt_cover,LAI,b10_emissivity=Calc_vegt_para(NDVI,SAVI,water_mask_temp,shape_lsc)

        # Save output maps that will be used in SEBAL
        save_GeoTiff_proy(lsc, water_mask_temp, water_mask_temp_fileName, shape_lsc, nband=1)
        #save_GeoTiff_proy(lsc, FPAR, fpar_fileName, shape_lsc, nband=1)
        #save_GeoTiff_proy(lsc, tir_emis, tir_emissivity_fileName, shape_lsc, nband=1)
        #save_GeoTiff_proy(lsc, Nitrogen, nitrogen_fileName, shape_lsc, nband=1)
        save_GeoTiff_proy(lsc, vegt_cover, veg_cover_fileName, shape_lsc, nband=1)
        save_GeoTiff_proy(lsc, LAI, lai_fileName, shape_lsc, nband=1)
        #save_GeoTiff_proy(lsc, b10_emissivity, b10_emissivity_fileName, shape_lsc, nband=1)
   
        # ------------------------------------------------------------------------
        # ------------------------------------------------------------------------
        # ----   MODULE 4  - Surface temperature, Cloud, Water, and Snow mask
     
        print('---------------------------------------------------------')
        print('-------------------- Module 4 ---------------------------')
        print('---------------------------------------------------------')
 
        # Check if a surface temperature dataset is defined. If so use this one instead of the Landsat, otherwise Landsat
 
        # Check Surface temperature	
        try:
            if False:  # No user files in automated workflow				
                # Output folder surface temperature						
                surf_temp_fileName = os.path.join(output_folder, 'Output_vegetation','User_surface_temp_%s_%s_%s_%s_%s.tif' %(res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
                temp_surface_sharpened=Reshape_Reproject_Input_data(r'%s' %str(ws['E%d' % number].value),surf_temp_fileName,proyDEM_fileName)		 					
                cloud_mask = np.zeros([int(np.shape(temp_surface_sharpened)[1]),int(np.shape(temp_surface_sharpened)[0])])
                Thermal_Sharpening_not_needed = 1		 									
            else:
                
                # Calculate surface temperature and create a cloud mask
                Surface_temp,cloud_mask = Calc_surface_temp(Temp_inst, Landsat_nr, Lmax, Lmin, therm_data, b10_emissivity, k1_c, k2_c, eact_inst, shape_lsc, water_mask_temp, Bands_thermal, Rp, tau_sky, surf_temp_offset, Image_Type)    
                Thermal_Sharpening_not_needed = 0	
                
                # Replace clouds mask is a better one is already created
                if BQA_LS_Available == 1:
                    cloud_mask = QC_mask_Cloud
                
                Surface_temp[cloud_mask == 1] = np.nan
                
        except:
            assert "Please check the surface temperature input path"																

        # Perform Thermal sharpening for the thermal LANDSAT image
        if Thermal_Sharpening_not_needed == 0:

		    # Upscale DEM to 90m
            pixel_spacing_upscale=90

            dest_90, ulx_dem_90, lry_dem_90, lrx_dem_90, uly_dem_90, epsg_to = reproject_dataset(
                DEM_fileName, pixel_spacing_upscale, UTM_Zone = UTM_Zone)

            DEM_90 = dest_90.GetRasterBand(1).ReadAsArray()
            Y_raster_size_90 = dest_90.RasterYSize				
            X_raster_size_90 = dest_90.RasterXSize
            shape_90=([X_raster_size_90, Y_raster_size_90])
						
            save_GeoTiff_proy(dest_90, DEM_90, proyDEM_fileName_90, shape_90, nband=1)
	  	
		
            # save landsat surface temperature
            surf_temp_fileName = os.path.join(output_folder, 'Output_vegetation','%s_%s_surface_temp_%s_%s_%s_%s_%s.tif' %(sensor1, sensor2, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
            save_GeoTiff_proy(lsc, Surface_temp, surf_temp_fileName, shape_lsc, nband=1)							

            # Upscale NDVI data																																	
            dest_up, ulx_dem, lry_dem, lrx_dem, uly_dem, epsg_to = reproject_dataset_example(
                                       ndvi_fileName2, proyDEM_fileName_90)
  
            NDVI_Landsat_up = dest_up.GetRasterBand(1).ReadAsArray()

            # Upscale Thermal data
            dest_up, ulx_dem, lry_dem, lrx_dem, uly_dem, epsg_to = reproject_dataset_example(
                                       surf_temp_fileName, proyDEM_fileName_90)
            surface_temp_up = dest_up.GetRasterBand(1).ReadAsArray()
 
            # Define the width of the moving window box
            Box=7	
  
            # Apply thermal sharpening           
            temp_surface_sharpened = Thermal_Sharpening(surface_temp_up, NDVI_Landsat_up, NDVI, Box, dest_up, output_folder, ndvi_fileName2, shape_lsc, lsc, temp_surface_sharpened_fileName)	
			
        # Divide temporal watermask in snow and water mask by using surface temperature
        snow_mask, water_mask, ts_moist_veg_min, NDVI_max, NDVI_std = CalculateSnowWaterMask(NDVI,shape_lsc,water_mask_temp,temp_surface_sharpened)

        # Save the water mask
        save_GeoTiff_proy(lsc, water_mask, water_mask_fileName, shape_lsc, nband=1)
		
        if Thermal_Sharpening_not_needed == 1:
            temp_surface_sharpened[water_mask == 1] = Surface_temp[water_mask == 1]
            
		   # save landsat surface temperature
            surf_temp_fileName = os.path.join(output_folder, 'Output_vegetation','%s_%s_surface_temp_sharpened_%s_%s_%s_%s_%s.tif' %(sensor1, sensor2, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
            save_GeoTiff_proy(lsc, temp_surface_sharpened, surf_temp_fileName, shape_lsc, nband=1)			
        # remove low temperature values
        temp_surface_sharpened[temp_surface_sharpened<=253.0]=np.nan
		
        # Calculate the tempearture of the water       							
        Temperature_water_std=np.nanstd(temp_surface_sharpened[water_mask != 0])
        Temperature_water_mean=np.nanmean(temp_surface_sharpened[water_mask != 0])
      
        print('Mean water Temperature = %0.3f (K)' % Temperature_water_mean)
        print('Standard deviation water temperature = %0.3f (K)' % Temperature_water_std)
        # Check if Quality dataset is defined. If so use this one instead of using Landsat otherwise landsat

        # Check Quality
        try:
            if False:  # No user files in automated workflow					
                # Output folder QC defined by the user							
                QC_Map_fileName = os.path.join(output_folder, 'Output_temporary', 'User_quality_mask_%s_%s_%s.tif' %(res2, year, DOY))
 
                # Reproject and reshape users NDVI  
                QC_Map = Reshape_Reproject_Input_data(r'%s' %str(ws['F%d' % number].value),QC_Map_fileName,proyDEM_fileName)		 														 

		    # if the users QC data cannot be reprojected than use the original Landsat data as imported into SEBAL		
            else:
											
                # if there are no cold water pixels than use cold vegetation pixels       
                if np.isnan(Temperature_water_mean) == True or Temperature_water_mean < 0.0: 
                    ts_cold_land=ts_moist_veg_min
                else:
                    ts_cold_land=Temperature_water_mean
    
                # Make shadow mask
                mask=np.zeros((shape_lsc[1], shape_lsc[0]))
                mask[np.logical_and.reduce((temp_surface_sharpened < (ts_cold_land+Temperature_offset_shadow),Surf_albedo < Maximum_shadow_albedo,water_mask!=1))]=1
                shadow_mask=np.copy(mask)
                shadow_mask = Create_Buffer(shadow_mask)
       
                # Make cloud mask
                if BQA_LS_Available != 1:
                    mask=np.zeros((shape_lsc[1], shape_lsc[0]))
                    mask[np.logical_and.reduce((temp_surface_sharpened < (ts_cold_land+Temperature_offset_clouds),Surf_albedo > Minimum_cloud_albedo,NDVI<0.7,snow_mask!=1))]=1
                    cloud_mask=np.copy(mask)
                    cloud_mask = Create_Buffer(cloud_mask)                
           
                # Save output maps
                save_GeoTiff_proy(lsc, cloud_mask, cloud_mask_fileName, shape_lsc, nband=1)
                #save_GeoTiff_proy(lsc, snow_mask, snow_mask_fileName, shape_lsc, nband=1)                  
                #save_GeoTiff_proy(lsc, shadow_mask, shadow_mask_fileName, shape_lsc, nband=1)
    
                # Total Quality Mask
                QC_Map = np.empty(cloud_mask.shape)
                ClipLandsat_reverse = np.where(ClipLandsat==1,0,1)
                Landsat_Mask = cloud_mask + snow_mask + shadow_mask + ClipLandsat_reverse
                QC_Map[Landsat_Mask>0] = 1								
											
                # Output folder QC defined by the user							
                QC_Map_fileName = os.path.join(output_folder, 'Output_cloud_masked', '%s_quality_mask_%s_%s_%s.tif.tif' %(sensor1, res2, year, DOY))
											
                # Save the PROBA-V NDVI as tif file												
                #save_GeoTiff_proy(lsc, QC_Map, QC_Map_fileName, shape, nband=1)
                #save_GeoTiff_proy(dest, QC_Map, QC_Map_fileName, shape, nband=1)								  

        except:                
            assert "Please check the quality path"									
            
    # ------------------------------------------------------------------------
    # ------------------------------------------------------------------------
    #-------------------------Calculations VIIRS and PROBA-V-----------------------

    if Image_Type == 2:

        print('---------------------------------------------------------')
        print('------------------- Collect PROBA-V data ----------------')
        print('---------------------------------------------------------')
        
        # In automated workflow, no additional inputs are provided
        if True:  # No additional NDVI/Albedo files provided					

            # Define the bands that will be used
            bands=['SM', 'B1', 'B2', 'B3', 'B4']  #'SM', 'BLUE', 'RED', 'NIR', 'SWIR'

            # Set the index number at 0
            index=0
							
            # create a zero array with the shape of the reprojected DEM file						
            data_PROBAV=np.zeros((shape_lsc[1], shape_lsc[0]))
            spectral_reflectance_PROBAV=np.zeros([shape_lsc[1], shape_lsc[0], 5])
        
            # constants
            n188_float=248       # Now it is 248, but we do not exactly know what this really means and if this is for constant for all images.
 
            # write the data one by one to the spectral_reflectance_PROBAV       
            for bandnmr in bands:

                # Translate the PROBA-V names to the Landsat band names                
                Band_number = {'SM':7,'B1':8,'B2':10,'B3':9,'B4':11}

                # Open the dataset 
                Band_PROBAVhdf_fileName = os.path.join(input_folder, '%s.hdf5' % (Name_PROBAV_Image))   
                g=gdal.Open(Band_PROBAVhdf_fileName, gdal.GA_ReadOnly)
                
                # Open the .hdf file              
                name_out = os.path.join(input_folder, '%s_test.tif' % (Name_PROBAV_Image))   
                name_in = g.GetSubDatasets()[Band_number[bandnmr]][0]
   
                # Get environmental variable for windows and Linux 
                if platform.system() == 'Windows':
                    SEBAL_env_paths = os.environ["SEBAL"].split(';')
                    GDAL_env_path = SEBAL_env_paths[0]
                    GDAL_TRANSLATE = os.path.join(GDAL_env_path, 'gdal_translate.exe')
                else:
                    SEBAL_env_paths = os.environ["SEBAL"]
                    GDAL_env_path = SEBAL_env_paths
                    GDAL_TRANSLATE = os.path.join(GDAL_env_path, 'gdal_translate')
                # run gdal translate command               
                FullCmd = '%s -of GTiff %s %s' %(GDAL_TRANSLATE, name_in, name_out)            
                os.system(FullCmd)
                
                # Open data
                dest_PV = gdal.Open(name_out)
                Data = dest_PV.GetRasterBand(1).ReadAsArray()               
                dest_PV = None
                
                # Remove temporary file
                os.remove(name_out)
                
                # Define the x and y spacing
                Meta_data = g.GetMetadata()
                #Lat_Bottom = float(Meta_data['LEVEL3_GEOMETRY_BOTTOM_LEFT_LATITUDE'])
                Lat_Top = float(Meta_data['LEVEL3_GEOMETRY_TOP_RIGHT_LATITUDE'])
                Lon_Left = float(Meta_data['LEVEL3_GEOMETRY_BOTTOM_LEFT_LONGITUDE'])
                #Lon_Right = float(Meta_data['LEVEL3_GEOMETRY_TOP_RIGHT_LONGITUDE'])           
                Pixel_size = float((Meta_data['LEVEL3_GEOMETRY_VNIR_VAA_MAPPING']).split(' ')[-3])
                
                # Define the georeference of the PROBA-V data
                geo_PROBAV=[Lon_Left-0.5*Pixel_size, Pixel_size, 0, Lat_Top+0.5*Pixel_size, 0, -Pixel_size] #0.000992063492063
		 									
                # Define the name of the output file					
                PROBAV_data_name=os.path.join(output_folder, 'Output_PROBAV', '%s_%s.tif' % (Name_PROBAV_Image,bandnmr)) 									
                dir_name_PROBAV = os.path.dirname(PROBAV_data_name)
    
                # If the directory does not exist, make it.
                if not os.path.exists(dir_name_PROBAV):
                    os.mkdir(dir_name_PROBAV)
                    
                # create gtiff output with the PROBA-V band
                fmt = 'GTiff'
                driver = gdal.GetDriverByName(fmt)
                dir_name = os.path.dirname(PROBAV_data_name)
                dst_dataset = driver.Create(PROBAV_data_name, int(Data.shape[1]), int(Data.shape[0]), 1,gdal.GDT_Float32)
                dst_dataset.SetGeoTransform(geo_PROBAV)
            
                # set the reference info
                srs = osr.SpatialReference()
                srs.SetWellKnownGeogCS("WGS84")
                dst_dataset.SetProjection(srs.ExportToWkt())
                
                # write the array in the geotiff band
                dst_dataset.GetRasterBand(1).WriteArray(Data)
                dst_dataset = None
 
                # Open the PROBA-V band in SEBAL											
                g=gdal.Open(PROBAV_data_name.replace("\\","/")) 
                
                # If the data cannot be opened, change the extension											
                if g is None:
                    PROBAV_data_name=os.path.join(input_folder, '%s_%s.tiff' % (Name_PROBAV_Image,bandnmr))  
  
                # Reproject the PROBA-V band  to match DEM's resolution          
                PROBAV, ulx_dem, lry_dem, lrx_dem, uly_dem, epsg_to = reproject_dataset_example(
                              PROBAV_data_name, proyDEM_fileName)
 
                # Open the reprojected PROBA-V band data                         
                data_PROBAV_DN = PROBAV.GetRasterBand(1).ReadAsArray(0, 0, ncol, nrow)
	 										
                # Define the filename to store the cropped Landsat image
                dst_FileName = os.path.join(output_folder, 'Output_PROBAV','proy_PROBAV_%s.tif' % bandnmr)
		 									
                # close the PROBA-V 											
                g=None
                                   
                # If the band data is not SM change the DN values into PROBA-V values and write into the spectral_reflectance_PROBAV                      
                if bandnmr != 'SM':  
                    data_PROBAV[:, :]=data_PROBAV_DN//2000                           
                    spectral_reflectance_PROBAV[:, :, index]=data_PROBAV[:, :]
               
                # If the band data is the SM band than write the data into the spectral_reflectance_PROBAV  and create cloud mask            
                else:
                    data_PROBAV[:, :]=data_PROBAV_DN
                    Cloud_Mask_PROBAV=np.zeros((shape_lsc[1], shape_lsc[0]))
                    Cloud_Mask_PROBAV[data_PROBAV[:,:]!=n188_float]=1
                    spectral_reflectance_PROBAV[:, :, index]=Cloud_Mask_PROBAV
                    #save_GeoTiff_proy(lsc, Cloud_Mask_PROBAV, proyPROBAV_Cloud_Mask_fileName, shape_lsc, nband=1)
 
                # Change the spectral reflectance to meet certain limits                               
                spectral_reflectance_PROBAV[:, :, index]=np.where(spectral_reflectance_PROBAV[:, :, index]<=0,np.nan,spectral_reflectance_PROBAV[:, :, index])   
                spectral_reflectance_PROBAV[:, :, index]=np.where(spectral_reflectance_PROBAV[:, :, index]>=150,np.nan,spectral_reflectance_PROBAV[:, :, index])   
 
                # Save the PROBA-V as a tif file                     
                save_GeoTiff_proy(lsc, spectral_reflectance_PROBAV[:, :, index], dst_FileName, shape_lsc, nband=1)
	 										
                # Go to the next index 									
                index=index+1
    
        else:
            Cloud_Mask_PROBAV=np.zeros((shape_lsc[1], shape_lsc[0]))
            #save_GeoTiff_proy(lsc, Cloud_Mask_PROBAV, proyPROBAV_Cloud_Mask_fileName, shape_lsc, nband=1)
 
     
        print('---------------------------------------------------------')
        print('----------------- Calculate Vegetation data -------------')
        print('---------------------------------------------------------')

        # Bands in PROBAV spectral reflectance
        # 0 = MS
        # 1 = BLUE
        # 2 = NIR
        # 3 = RED
        # 4 = SWIR
      
        # Check if a NDVI, SAVI, or Surface Albedo dataset is defined. If so use this one instead of the PROBAV otherwise PROBAV

        # Check NDVI
        try:
            if False:  # No user files in automated workflow					
                # Output folder NDVI	defined by the user							
                ndvi_fileName = os.path.join(output_folder, 'Output_vegetation', 'User_NDVI_%s_%s_%s_%s_%s.tif' %(res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
 
                # Reproject and reshape users NDVI  
                NDVI=Reshape_Reproject_Input_data(r'%s' %str(ws['B%d' % number].value),ndvi_fileName, proyDEM_fileName)		 														 
                NDVI_PROBAV_MAX = np.nanmax(NDVI)
                NDVI_PROBAV_SD =  np.nanstd(NDVI) 
                print('NDVI User max ' , NDVI_PROBAV_MAX)
                print('NDVI User sd' , NDVI_PROBAV_SD)	

                # Create Water mask based on PROBA-V             
                water_mask = np.zeros((shape_lsc[1], shape_lsc[0])) 
                water_mask[NDVI<0.0]=1
 
            # if the users NDVI data cannot be reprojected than use the original PROBA-V data as imported into SEBAL		
            else:
                # Calculate the NDVI based on PROBA-V     
                n218_memory = spectral_reflectance_PROBAV[:, :, 2] + spectral_reflectance_PROBAV[:, :, 3]
                NDVI = np.zeros((shape_lsc[1], shape_lsc[0]))
                NDVI[n218_memory != 0] =  ( spectral_reflectance_PROBAV[:, :, 3][n218_memory != 0] - spectral_reflectance_PROBAV[:, :, 2][n218_memory != 0] )/ ( spectral_reflectance_PROBAV[:, :, 2][n218_memory != 0] + spectral_reflectance_PROBAV[:, :, 3][n218_memory != 0] )
                NDVI_PROBAV_MAX = np.nanmax(NDVI)
                NDVI_PROBAV_SD =  np.nanstd(NDVI) 
                print('NDVI PROBA-V max ' , NDVI_PROBAV_MAX)
                print('NDVI PROBA-V sd' , NDVI_PROBAV_SD)
  
                # Create Water mask based on PROBA-V             
                water_mask = np.zeros((shape_lsc[1], shape_lsc[0])) 
                water_mask[np.logical_and(spectral_reflectance_PROBAV[:, :, 2] >= spectral_reflectance_PROBAV[:, :, 3],DEM_resh>0)]=1

                # Define users NDVI output name																
                ndvi_fileName = os.path.join(output_folder, 'Output_vegetation', '%s_NDVI_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
		 													
		        # Save the PROBA-V NDVI as tif file												
                save_GeoTiff_proy(lsc, NDVI, ndvi_fileName, shape_lsc, nband=1)
		 														  
        except:                
            assert "Please check the PROBA-V path, was not able to create NDVI"
												
        # Check SAVI	
        try:
            if False:  # No user files in automated workflow					
                # Output folder SAVI	defined by the user					
                savi_fileName = os.path.join(output_folder, 'Output_vegetation', 'User_SAVI_%s_%s_%s_%s_%s.tif' %(res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
															
                # Reproject and reshape users SAVI  															
                SAVI=Reshape_Reproject_Input_data(r'%s' %str(ws['C%d' % number].value),savi_fileName,proyDEM_fileName)		 					

            # if the users SAVI data cannot be reprojected than use the original PROBA-V data as imported into SEBAL													
            else:
                # Calculate SAVI based on PROBA-V
                SAVI = (1+L_SAVI)*(spectral_reflectance_PROBAV[:, :, 3]-spectral_reflectance_PROBAV[:, :, 2])/(L_SAVI+spectral_reflectance_PROBAV[:, :, 2]+spectral_reflectance_PROBAV[:, :, 3])
 
                # Define users SAVI output name	
                savi_fileName = os.path.join(output_folder, 'Output_vegetation', '%s_SAVI_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))	
															
                # Save the PROBA-V SAVI as tif file															
                save_GeoTiff_proy(lsc, SAVI, savi_fileName, shape_lsc, nband=1)																  
        except:
             assert "Please check the PROBA-V path, was not able to create SAVI"       			
								
        # Check surface albedo		
        try:
            if False:  # No user files in automated workflow					
                # Output folder surface albedo						
                surface_albedo_fileName = os.path.join(output_folder, 'Output_vegetation','User_surface_albedo_%s_%s_%s_%s_%s.tif' %(res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))

                # Reproject and reshape users surface albedo 
                Surf_albedo=Reshape_Reproject_Input_data(r'%s' %str(ws['D%d' % number].value),surface_albedo_fileName,proyDEM_fileName)		 					

            # if the users surface albedo data cannot be reprojected than use the original PROBA-V data as imported into SEBAL													
            else:
                # Calculate surface albedo based on PROBA-V
                Surf_albedo = 0.219 * spectral_reflectance_PROBAV[:, :, 1] + 0.361 * spectral_reflectance_PROBAV[:, :, 2] + 0.379 * spectral_reflectance_PROBAV[:, :, 3] + 0.041 * spectral_reflectance_PROBAV[:, :, 4]

                # Set limit surface albedo
                Surf_albedo = np.minimum(Surf_albedo, 0.6)

                # Define users surface albedo output name	             
                surface_albedo_fileName = os.path.join(output_folder, 'Output_vegetation','%s_surface_albedo_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))

			   # Save the PROBA-V surface albedo as tif file
                save_GeoTiff_proy(lsc, Surf_albedo, surface_albedo_fileName, shape_lsc, nband=1)																  
        except:
             assert "Please check the PROBA-V path, was not able to create Albedo"       

        # Calculate the Fpar, TIR, Nitrogen, Vegetation Cover, LAI and b10_emissivity based on PROBA-V      
        FPAR,tir_emis,Nitrogen_PROBAV,vegt_cover,LAI,b10_emissivity_PROBAV=Calc_vegt_para(NDVI,SAVI,water_mask,shape_lsc)
				
        # Save the paramaters as a geotiff
        save_GeoTiff_proy(lsc, water_mask, water_mask_fileName, shape_lsc, nband=1)
        #save_GeoTiff_proy(lsc, tir_emis, tir_emissivity_fileName, shape_lsc, nband=1)
        #save_GeoTiff_proy(lsc, Nitrogen_PROBAV, nitrogen_fileName, shape_lsc, nband=1)
        save_GeoTiff_proy(lsc, vegt_cover, veg_cover_fileName, shape_lsc, nband=1)
        save_GeoTiff_proy(lsc, LAI, lai_fileName, shape_lsc, nband=1)           

        print('---------------------------------------------------------')
        print('------------------- Collect VIIRS data ------------------')
        print('---------------------------------------------------------')

 
        # Open Additional_Input sheet in the excel										
        ws = wb['Additional_Input']

        # end result are reprojected maps of:
        # 1) 							
        # 2) 					

        # 1) Get the VIIRS Thermal map 100m
        # Upscale DEM to 375m
        pixel_spacing_upscale = 375

        dest_375, ulx_dem_375, lry_dem_375, lrx_dem_375, uly_dem_375, epsg_to = reproject_dataset(
                    DEM_fileName, pixel_spacing_upscale, UTM_Zone = UTM_Zone)
                
        DEM_375 = dest_375.GetRasterBand(1).ReadAsArray()
        Y_raster_size_375 = dest_375.RasterYSize				
        X_raster_size_375 = dest_375.RasterXSize
        shape_375=([X_raster_size_375, Y_raster_size_375])
						
        save_GeoTiff_proy(dest_375, DEM_375, proyDEM_fileName_375, shape_375, nband=1)

        try:	
            if False:  # No user files in automated workflow									
               # Define output folder Thermal VIIRS by the user					
                proyVIIRS_fileName_100 = os.path.join(output_folder, 'Output_VIIRS','User_TB_%s_%s_%s.tif' %(res2, year, DOY))
  
                # Reshape and reproject the Thermal data given by the user and resample this to a 375m resolution
                temp_surface_sharpened = Reshape_Reproject_Input_data(r'%s' %str(ws['E%d' % number].value), proyVIIRS_fileName_100, proyDEM_fileName)		 					
 
                Thermal_Sharpening_not_needed = 1	
                
                # Divide temporal watermask in snow and water mask by using surface temperature
                Snow_Mask_PROBAV, water_mask, ts_moist_veg_min, NDVI_max, NDVI_std = CalculateSnowWaterMask(NDVI,shape_lsc,water_mask,temp_surface_sharpened)

                data_VIIRS_QC = np.zeros((shape_lsc[1], shape_lsc[0]))
                data_VIIRS_QC[np.isnan(temp_surface_sharpened)] = 1

            else:
                # Define the VIIRS thermal data name
                VIIRS_data_name=os.path.join(input_folder, '%s' % (Name_VIIRS_Image_TB))
							
                # Reproject VIIRS thermal data								
                VIIRS, ulx_dem, lry_dem, lrx_dem, uly_dem, epsg_to = reproject_dataset_example(
       	                        VIIRS_data_name, proyDEM_fileName)
																	
                # Open VIIRS thermal data																		
                data_VIIRS = VIIRS.GetRasterBand(1).ReadAsArray()    
				
                # Define the thermal VIIRS output name
                proyVIIRS_fileName = os.path.join(output_folder, 'Output_VIIRS','%s_TB_%s_%s_%s.tif' %(sensor2, res2, year, DOY))
	 											
                # Save the thermal VIIRS data 												
                save_GeoTiff_proy(lsc, data_VIIRS, proyVIIRS_fileName, shape_lsc, nband=1)							
               
                Thermal_Sharpening_not_needed = 0
 
        # 2)	Get the VIIRS Quality map 100m	
		
                # Check Quality
                if Name_VIIRS_Image_QC != 'None':
									
                    # Define the VIIRS Quality data name
                    VIIRS_data_name=os.path.join(input_folder, '%s' % (Name_VIIRS_Image_QC))  
		 					
                    # Reproject VIIRS Quality data		
                    VIIRS, ulx_dem, lry_dem, lrx_dem, uly_dem, epsg_to = reproject_dataset_example(
                                                   VIIRS_data_name, proyDEM_fileName)
					 												
                    # Open VIIRS Quality data																	
                    data_VIIRS_QC = VIIRS.GetRasterBand(1).ReadAsArray()

                    # Save the reprojected VIIRS dataset QC
                    save_GeoTiff_proy(lsc, data_VIIRS_QC, proyVIIRS_QC_fileName, shape_lsc, nband=1)
        
                else:
                    data_VIIRS_QC = np.zeros((shape_lsc[1], shape_lsc[0]))	

        except:
             assert "Please check the VIIRS input path"
 
        # ------ Upscale TIR_Emissivity_PROBAV, cloud mask PROBAV and NDVI for LST calculation at 375m resolution ----
      
        if Thermal_Sharpening_not_needed == 0:      

            ##### VIIRS brightness temperature to land surface temperature
       
            # Create cloud mask VIIRS (100m)
            data_VIIRS[NDVI==0]=0
            Cloud_Mask_VIIRS=np.zeros((shape_lsc[1], shape_lsc[0]))
            Cloud_Mask_VIIRS[data_VIIRS_QC!=0]=1
            #save_GeoTiff_proy(lsc, Cloud_Mask_VIIRS, proyVIIRS_Cloud_Mask_fileName, shape_lsc, nband=1)
            
            # Create total VIIRS and PROBA-V cloud mask (100m)       
            QC_Map=np.zeros((shape_lsc[1], shape_lsc[0]))
            QC_Map=np.where(np.logical_or(data_VIIRS_QC==1, Cloud_Mask_PROBAV==1),1,0) 
            
            # Set the conditions for the brightness temperature (100m)
            term_data=data_VIIRS
            term_data=np.where(data_VIIRS>=250, data_VIIRS,0)
            brightness_temp=np.zeros((shape_lsc[1], shape_lsc[0]))
            brightness_temp=np.where(Cloud_Mask_VIIRS==0,term_data,np.nan)

            # Constants
            k1=606.399172
            k2=1258.78
            L_lambda_b10_100=((2*6.63e-34*(3.0e8)**2)/((11.45e-6)**5*(np.exp((6.63e-34*3e8)/(1.38e-23*(11.45e-6)*brightness_temp))-1)))*1e-6
        
            # Get Temperature for 100 and 375m resolution
            Temp_TOA_100 = Get_Thermal(L_lambda_b10_100,Rp,Temp_inst,tau_sky,tir_emis,k1,k2) 
       
            # Conditions for surface temperature (100m)
            n120_surface_temp=np.where(QC_Map==1,np.nan,Temp_TOA_100)
            n120_surface_temp=np.where(n120_surface_temp<=250,np.nan,Temp_TOA_100)
            n120_surface_temp=np.where(n120_surface_temp>450,np.nan,Temp_TOA_100)
        
            # Save the surface temperature of the VIIRS in 100m resolution
            temp_surface_100_fileName_beforeTS = os.path.join(output_folder, 'Output_temporary','%s_%s_surface_temp_before_Thermal_Sharpening_%s_%s_%s.tif' %(sensor1, sensor2, res2, year, DOY))
            save_GeoTiff_proy(lsc, n120_surface_temp, temp_surface_100_fileName_beforeTS, shape_lsc, nband=1)     												
     
            print('---------------------------------------------------------')
            print('-------------------- Downscale VIIRS --------------------')
            print('---------------------------------------------------------')

            ################################ Thermal Sharpening #####################################################

            # Upscale VIIRS and PROBA-V to 400m
            pixel_spacing_upscale = 400

            dest_400, ulx_dem_400, lry_dem_400, lrx_dem_400, uly_dem_400, epsg_to = reproject_dataset(
                    DEM_fileName, pixel_spacing_upscale, UTM_Zone = UTM_Zone)

            DEM_400 = dest_400.GetRasterBand(1).ReadAsArray()
            Y_raster_size_400 = dest_400.RasterYSize				
            X_raster_size_400 = dest_400.RasterXSize
            shape_400=([X_raster_size_400, Y_raster_size_400])
						
            save_GeoTiff_proy(dest_400, DEM_400, proyDEM_fileName_400, shape_400, nband=1)
    																		
            # Upscale thermal band VIIRS from 100m to 400m
            VIIRS_Upscale, ulx_dem, lry_dem, lrx_dem, uly_dem, epsg_to = reproject_dataset_example(
                           temp_surface_100_fileName_beforeTS, proyDEM_fileName_400)
            data_Temp_Surf_400 = VIIRS_Upscale.GetRasterBand(1).ReadAsArray()
 
            # Upscale PROBA-V NDVI from 100m to 400m       
            NDVI_PROBAV_Upscale, ulx_dem, lry_dem, lrx_dem, uly_dem, epsg_to = reproject_dataset_example(
                          ndvi_fileName, proyDEM_fileName_400)
            data_NDVI_400 = NDVI_PROBAV_Upscale.GetRasterBand(1).ReadAsArray()

            # Define the width of the moving window box
            Box=9
       
            # Apply the surface temperature sharpening        
            temp_surface_sharpened = Thermal_Sharpening(data_Temp_Surf_400, data_NDVI_400, NDVI, Box, NDVI_PROBAV_Upscale, output_folder, proyDEM_fileName, shape_lsc, lsc, surf_temp_fileName)	

            # Divide temporal watermask in snow and water mask by using surface temperature
            Snow_Mask_PROBAV, water_mask, ts_moist_veg_min, NDVI_max, NDVI_std = CalculateSnowWaterMask(NDVI,shape_lsc,water_mask,temp_surface_sharpened)

            # Replace water values
            temp_surface_sharpened[water_mask==1] = n120_surface_temp[water_mask == 1]
            temp_surface_sharpened = np.where(np.isnan(temp_surface_sharpened),n120_surface_temp,temp_surface_sharpened)          
            
            surf_temp_fileName = os.path.join(output_folder, 'Output_vegetation','%s_%s_surface_temp_sharpened_%s_%s_%s_%s_%s.tif' %(sensor1, sensor2, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
            save_GeoTiff_proy(lsc, temp_surface_sharpened, surf_temp_fileName, shape_lsc, nband=1)     
            save_GeoTiff_proy(lsc, Snow_Mask_PROBAV, snow_mask_fileName, shape_lsc, nband=1)
            
            # Calculate total quality mask        
            QC_Map=np.where(np.logical_or(data_VIIRS_QC==1, Cloud_Mask_PROBAV==1),1,0) 
				
        ######################################## End Thermal Sharpening ################################################3

        # Check if Quality dataset is defined. If so use this one instead of the PROBAV-VIIRS one 

        # Check Quality
        try: 
            if False:  # No user files in automated workflow					
                # Output folder QC defined by the user							
                QC_fileName = os.path.join(output_folder, 'Output_cloud_masked', 'User_quality_mask_%s_%s_%s.tif.tif' %(res2, year, DOY))
          
                # Reproject and reshape users NDVI  
                QC_Map = Reshape_Reproject_Input_data(r'%s' %str(ws['F%d' % number].value),QC_fileName, proyDEM_fileName)		 														 
      
                 # Save the QC map as tif file												
                save_GeoTiff_proy(lsc, QC_Map, QC_fileName, shape_lsc, nband=1)
             
		    # if the users NDVI data cannot be reprojected than use the original PROBA-V data as imported into SEBAL		
            else:
                
                # Create empty QC map if it not exists
                if not 'QC_Map' in locals():
                    QC_Map = np.zeros((shape_lsc[1], shape_lsc[0]))
					
                # Define users QC output name																
                QC_tot_fileName = os.path.join(output_folder, 'Output_cloud_masked', '%s_quality_mask_%s_%s_%s.tif' %(sensor1, res2, year, DOY))
      										
                 # Save the QC map as tif file											
                save_GeoTiff_proy(lsc, QC_Map, QC_tot_fileName, shape_lsc, nband=1)
												  
        except:                
             assert "Please check the VIIRS path, was not able to create VIIRS QC map"       
 	
        print('---------------------------------------------------------')
        print('-------------------- Collect Meteo Data -----------------')
        print('---------------------------------------------------------')
  
        # Correct vegetation parameters
        NDVI=np.where(QC_Map==1,np.nan,NDVI)
        Surf_albedo=np.where(QC_Map==1,np.nan,Surf_albedo)
        LAI=np.where(QC_Map==1,np.nan,LAI)
        vegt_cover=np.where(QC_Map==1,np.nan,vegt_cover)
        SAVI=np.where(QC_Map==1,np.nan,SAVI)

    # ------------------------------------------------------------------------
    # ------------------------------------------------------------------------
    #-------------------------Calculations MODIS -----------------------------
    
    if Image_Type == 3:
 

        print('---------------------------------------------------------')
        print('----------------- Calculate Vegetation data -------------')
        print('---------------------------------------------------------')

        # Bands in PROBAV spectral reflectance
        # 0 = MS
        # 1 = BLUE
        # 2 = NIR
        # 3 = RED
        # 4 = SWIR
      
        # Check if a NDVI, SAVI, or Surface Albedo dataset is defined. If so use this one instead of the PROBAV otherwise PROBAV
        # In automated workflow, no user files provided
        # Check NDVI
        try:
            if False:  # No user NDVI file in automated workflow					
                # Output folder NDVI	defined by the user							
                ndvi_fileName = os.path.join(output_folder, 'Output_vegetation', 'User_NDVI_%s_%s_%s_%s_%s.tif' %(res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
 
                # Reproject and reshape users NDVI  
                NDVI=Reshape_Reproject_Input_data(r'%s' %str(ws['B%d' % number].value),ndvi_fileName, proyDEM_fileName)		 														 
                NDVI_PROBAV_MAX = np.nanmax(NDVI)
                NDVI_PROBAV_SD =  np.nanstd(NDVI) 
                print('NDVI User max ' , NDVI_PROBAV_MAX)
                print('NDVI User sd' , NDVI_PROBAV_SD)	

                # Create Water mask based on PROBA-V             
                water_mask = np.zeros((shape_lsc[1], shape_lsc[0])) 
                water_mask[NDVI<0.0]=1
 
            # if the users NDVI data cannot be reprojected than use the original PROBA-V data as imported into SEBAL		
            else:
                # Calculate the NDVI based on MODIS  
                NDVI = Open_reprojected_hdf(src_FileName_NDVI, 0, epsg_to, 0.0001, proyDEM_fileName)

                NDVI_MODIS_MAX = np.nanmax(NDVI)
                NDVI_MODIS_SD =  np.nanstd(NDVI) 
                print('NDVI MODIS max ' , NDVI_MODIS_MAX)
                print('NDVI MODIS sd' , NDVI_MODIS_SD)
  
                # Create Water mask based on MODIS           
                water_mask = np.zeros((shape_lsc[1], shape_lsc[0])) 
                water_mask[NDVI < 0]=1

                # Define users NDVI output name																
                ndvi_fileName = os.path.join(output_folder, 'Output_vegetation', '%s_NDVI_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
		 													
		        # Save the PROBA-V NDVI as tif file												
                save_GeoTiff_proy(lsc, NDVI, ndvi_fileName, shape_lsc, nband=1)
		 														  
        except:                
            assert "Please check the PROBA-V path, was not able to create NDVI"
												

        # Check SAVI	
        try:
            if False:  # No user files in automated workflow					
                # Output folder SAVI	defined by the user					
                savi_fileName = os.path.join(output_folder, 'Output_vegetation', 'User_SAVI_%s_%s_%s_%s_%s.tif' %(res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
															
                # Reproject and reshape users SAVI  															
                SAVI=Reshape_Reproject_Input_data(r'%s' %str(ws['C%d' % number].value),savi_fileName,proyDEM_fileName)		 					

            # if the users SAVI data cannot be reprojected than use the original MOD11 data as imported into SEBAL													
            else:

                # Calculate the MOD9 based on MODIS   
                B1_modis = Open_reprojected_hdf(src_FileName_Ref, 11, epsg_to, 0.0001, proyDEM_fileName)

                # Open and reproject B2            
                B2_modis = Open_reprojected_hdf(src_FileName_Ref, 12, epsg_to, 0.0001, proyDEM_fileName)
 
                # Calculate SAVI               
                SAVI = (B2_modis - B1_modis) /(B2_modis + B1_modis + L_SAVI) * (1+L_SAVI)
                
                # Define users SAVI output name	
                savi_fileName = os.path.join(output_folder, 'Output_vegetation', '%s_SAVI_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))	
															
                # Save the PROBA-V SAVI as tif file															
                save_GeoTiff_proy(lsc, SAVI, savi_fileName, shape_lsc, nband=1)																  
        except:
             assert "Please check the PROBA-V path, was not able to create SAVI"       
								
								
        # Check surface albedo		
        try:
            if False:  # No user files in automated workflow					
                # Output folder surface albedo						
                surface_albedo_fileName = os.path.join(output_folder, 'Output_vegetation','User_surface_albedo_%s_%s_%s_%s_%s.tif' %(res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))

                # Reproject and reshape users surface albedo 
                Surf_albedo=Reshape_Reproject_Input_data(r'%s' %str(ws['D%d' % number].value),surface_albedo_fileName,proyDEM_fileName)		 					

            # if the users surface albedo data cannot be reprojected than use the original PROBA-V data as imported into SEBAL													
            else:
                
                # Calculate the MOD9 based on MODIS   
                B1_modis = Open_reprojected_hdf(src_FileName_Ref, 11, epsg_to, 0.0001, proyDEM_fileName)

                # Open and reproject B2            
                B2_modis = Open_reprojected_hdf(src_FileName_Ref, 12, epsg_to, 0.0001, proyDEM_fileName) 
                
                # Open and reproject B3   
                B3_modis = Open_reprojected_hdf(src_FileName_Ref, 13, epsg_to, 0.0001, proyDEM_fileName) 

                # Open and reproject B4            
                B4_modis = Open_reprojected_hdf(src_FileName_Ref, 14, epsg_to, 0.0001, proyDEM_fileName) 

                # Open and reproject B5            
                B5_modis = Open_reprojected_hdf(src_FileName_Ref, 15, epsg_to, 0.0001, proyDEM_fileName) 

                # Open and reproject B6            
                B6_modis = Open_reprojected_hdf(src_FileName_Ref, 16, epsg_to, 0.0001, proyDEM_fileName) 

                # Open and reproject B3            
                B7_modis = Open_reprojected_hdf(src_FileName_Ref, 17, epsg_to, 0.0001, proyDEM_fileName) 

                # Calc surface albedo within shortwave domain using a weighting function (Tasumi et al 2008)
                Surf_albedo = 0.215 * B1_modis + 0.215 * B2_modis + 0.242 * B3_modis + 0.129 * B4_modis + 0.101 * B5_modis + 0.062 * B6_modis + 0.036 * B7_modis
                
                # Define users surface albedo output name	             
                surface_albedo_fileName = os.path.join(output_folder, 'Output_vegetation','%s_surface_albedo_%s_%s_%s_%s_%s.tif' %(sensor1, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))

			   # Save the PROBA-V surface albedo as tif file
                save_GeoTiff_proy(lsc, Surf_albedo, surface_albedo_fileName, shape_lsc, nband=1)																  
        except:
             assert "Please check the PROBA-V path, was not able to create Albedo"       


        # Calculate the Fpar, TIR, Nitrogen, Vegetation Cover, LAI and b10_emissivity based on PROBA-V      
        FPAR, tir_emis, Nitrogen_PROBAV, vegt_cover, LAI, b10_emissivity_PROBAV=Calc_vegt_para(NDVI, SAVI, water_mask, shape_lsc)
				
        # Save the paramaters as a geotiff
        save_GeoTiff_proy(lsc, water_mask, water_mask_fileName, shape_lsc, nband=1)
        #save_GeoTiff_proy(lsc, tir_emis, tir_emissivity_fileName, shape_lsc, nband=1)
        #save_GeoTiff_proy(lsc, Nitrogen_PROBAV, nitrogen_fileName, shape_lsc, nband=1)
        save_GeoTiff_proy(lsc, vegt_cover, veg_cover_fileName, shape_lsc, nband=1)
        save_GeoTiff_proy(lsc, LAI, lai_fileName, shape_lsc, nband=1)           

        print('---------------------------------------------------------')
        print('------------------- Collect MOD9 data -------------------')
        print('---------------------------------------------------------')

 
        # Open Additional_Input sheet in the excel										
        ws = wb['Additional_Input']

        # end result are reprojected maps of:
        # 1) 							
        # 2) 					

        # 1) Get the VIIRS Thermal map 250m
        # Upscale DEM to 1000m
        pixel_spacing_upscale=1000

        dest_1000, ulx_dem_1000, lry_dem_1000, lrx_dem_1000, uly_dem_1000, epsg_to = reproject_dataset(
                    DEM_fileName, pixel_spacing_upscale, UTM_Zone = UTM_Zone)
                
        DEM_1000 = dest_1000.GetRasterBand(1).ReadAsArray()
        Y_raster_size_1000 = dest_1000.RasterYSize				
        X_raster_size_1000 = dest_1000.RasterXSize
        shape_1000=([X_raster_size_1000, Y_raster_size_1000])
						
        save_GeoTiff_proy(dest_1000, DEM_1000, proyDEM_fileName_1000, shape_1000, nband=1)

        try:	
            if False:  # No user files in automated workflow									
               # Define output folder Thermal VIIRS by the user					
                proyMODIS_fileName_250 = os.path.join(output_folder, 'Output_MODIS','User_TB_%s_%s_%s_%s_%s.tif' %(res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
  
                # Reshape and reproject the Thermal data given by the user and resample this to a 375m resolution
                temp_surface_sharpened = Reshape_Reproject_Input_data(r'%s' %str(ws['E%d' % number].value), proyMODIS_fileName_250, proyDEM_fileName)		 					
 
                Thermal_Sharpening_not_needed = 1	
                
                # Divide temporal watermask in snow and water mask by using surface temperature
                Snow_Mask_PROBAV, water_mask, ts_moist_veg_min, NDVI_max, NDVI_std = CalculateSnowWaterMask(NDVI,shape_lsc,water_mask,temp_surface_sharpened)

                MODIS_QC = np.zeros((shape_lsc[1], shape_lsc[0]))
                MODIS_QC[np.isnan(temp_surface_sharpened)] = 1

            else:
                
                # Calculate the MOD9 based on MODIS    
                n120_surface_temp = Open_reprojected_hdf(src_FileName_LST, 0, epsg_to, 0.02, proyDEM_fileName) 
              
                # Define the thermal VIIRS output name
                proyMODIS_fileName = os.path.join(output_folder, 'Output_MODIS','%s_TB_%s_%s_%s_%s_%s.tif' %(sensor2, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
	 											
                # Save the thermal VIIRS data 												
                save_GeoTiff_proy(lsc, n120_surface_temp, proyMODIS_fileName, shape_lsc, nband=1)							
               
                Thermal_Sharpening_not_needed = 0
 
                # 2)	Get the MODIS Quality map 1000m	
									
                # Calculate the MOD9 based on MODIS   
                g=gdal.Open(src_FileName_LST, gdal.GA_ReadOnly)
                
                MODIS_QC = Open_reprojected_hdf(src_FileName_LST, 1, epsg_to, 1, proyDEM_fileName) 
                
                # Define QC 
                MODIS_QC[np.logical_and(np.logical_and(MODIS_QC==5, MODIS_QC==17), MODIS_QC==21)] = 0
                MODIS_QC[MODIS_QC != 0] = 1                        
                
                # Save the reprojected VIIRS dataset QC
                save_GeoTiff_proy(lsc, MODIS_QC, proyMODIS_QC_fileName, shape_lsc, nband=1)
        
        except:
             assert "Please check the MODIS11 input path"
 
        # ------ Upscale TIR_Emissivity_PROBAV, cloud mask PROBAV and NDVI for LST calculation at 375m resolution ----
      
        if Thermal_Sharpening_not_needed == 0:      

            ##### MODIS brightness temperature to land surface temperature
                  
            # Create total VIIRS and PROBA-V cloud mask (100m)       
            QC_Map=np.zeros((shape_lsc[1], shape_lsc[0]))
            QC_Map=np.where(MODIS_QC==1,1,0) 
                    
            # Conditions for surface temperature (100m)
            n120_surface_temp=np.where(QC_Map==1,np.nan,n120_surface_temp)
            n120_surface_temp[n120_surface_temp<273] = np.nan
                             
            # Save the surface temperature of the VIIRS in 100m resolution
            temp_surface_250_fileName_beforeTS = os.path.join(output_folder, 'Output_temporary','%s_%s_surface_temp_before_Thermal_Sharpening_%s_%s_%s_%s_%s.tif' %(sensor1, sensor2, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
            save_GeoTiff_proy(lsc, n120_surface_temp, temp_surface_250_fileName_beforeTS, shape_lsc, nband=1)     												
     
            print('---------------------------------------------------------')
            print('-------------------- Downscale VIIRS --------------------')
            print('---------------------------------------------------------')

            ################################ Thermal Sharpening #####################################################

            # Upscale VIIRS and PROBA-V to 400m
            pixel_spacing_upscale = 1000

            dest_1000, ulx_dem_1000, lry_dem_1000, lrx_dem_1000, uly_dem_1000, epsg_to = reproject_dataset(
                    DEM_fileName, pixel_spacing_upscale, UTM_Zone = UTM_Zone)

            DEM_1000 = dest_1000.GetRasterBand(1).ReadAsArray()
            Y_raster_size_1000 = dest_1000.RasterYSize				
            X_raster_size_1000 = dest_1000.RasterXSize
            shape_1000=([X_raster_size_1000, Y_raster_size_1000])
						
            save_GeoTiff_proy(dest_1000, DEM_1000, proyDEM_fileName_1000, shape_1000, nband=1)
    																		
            # Upscale thermal band VIIRS from 100m to 400m
            MODIS_Upscale, ulx_dem, lry_dem, lrx_dem, uly_dem, epsg_to = reproject_dataset_example(
                           temp_surface_250_fileName_beforeTS, proyDEM_fileName_1000)
            data_Temp_Surf_1000 = MODIS_Upscale.GetRasterBand(1).ReadAsArray()
 
            # Upscale PROBA-V NDVI from 100m to 400m       
            NDVI_MODIS_Upscale, ulx_dem, lry_dem, lrx_dem, uly_dem, epsg_to = reproject_dataset_example(
                          ndvi_fileName, proyDEM_fileName_1000)
            data_NDVI_1000 = NDVI_MODIS_Upscale.GetRasterBand(1).ReadAsArray()

            # Define the width of the moving window box
            Box=9
       
            # Apply the surface temperature sharpening        
            temp_surface_sharpened = Thermal_Sharpening(data_Temp_Surf_1000, data_NDVI_1000, NDVI, Box, NDVI_MODIS_Upscale, output_folder, proyDEM_fileName, shape_lsc, lsc, surf_temp_fileName)	

            # Divide temporal watermask in snow and water mask by using surface temperature
            Snow_Mask_PROBAV, water_mask, ts_moist_veg_min, NDVI_max, NDVI_std = CalculateSnowWaterMask(NDVI,shape_lsc,water_mask,temp_surface_sharpened)

            # Replace water values
            temp_surface_sharpened[water_mask==1] = n120_surface_temp[water_mask == 1]
            temp_surface_sharpened = np.where(np.isnan(temp_surface_sharpened),n120_surface_temp,temp_surface_sharpened)          
            
            surf_temp_fileName = os.path.join(output_folder, 'Output_vegetation','%s_%s_surface_temp_sharpened_%s_%s_%s_%s_%s.tif' %(sensor1, sensor2, res2, year, str(mon).zfill(2), str(day).zfill(2), str(DOY).zfill(3)))
            save_GeoTiff_proy(lsc, temp_surface_sharpened, surf_temp_fileName, shape_lsc, nband=1)     
            save_GeoTiff_proy(lsc, Snow_Mask_PROBAV, snow_mask_fileName, shape_lsc, nband=1)
            
				
        ######################################## End Thermal Sharpening ################################################3

        # Check if Quality dataset is defined. If so use this one instead of the PROBAV-VIIRS one 

        # Check Quality
        try: 
            if False:  # No user files in automated workflow					
                # Output folder QC defined by the user							
                #QC_fileName = os.path.join(output_folder, 'Output_cloud_masked', 'User_quality_mask_%s_%s_%s.tif.tif' %(res2, year, DOY))
          
                # Reproject and reshape users NDVI  
                QC_Map = Reshape_Reproject_Input_data(r'%s' %str(ws['F%d' % number].value),QC_fileName, proyDEM_fileName)		 														 
      
                 # Save the QC map as tif file												
                save_GeoTiff_proy(lsc, QC_Map, QC_fileName, shape_lsc, nband=1)
             
		    # if the users NDVI data cannot be reprojected than use the original PROBA-V data as imported into SEBAL		
            else:
					
                # Define users QC output name																
                #QC_tot_fileName = os.path.join(output_folder, 'Output_cloud_masked', '%s_quality_mask_%s_%s_%s.tif' %(sensor1, res2, year, DOY))
      										
                 # Save the QC map as tif file											
                save_GeoTiff_proy(lsc, QC_Map, QC_tot_fileName, shape_lsc, nband=1)
												  
        except:                
             assert "Please check the VIIRS path, was not able to create VIIRS QC map"       
 	
        print('---------------------------------------------------------')
        print('-------------------- Collect Meteo Data -----------------')
        print('---------------------------------------------------------')
  
        # Correct vegetation parameters
        NDVI=np.where(QC_Map==1,np.nan,NDVI)
        Surf_albedo=np.where(QC_Map==1,np.nan,Surf_albedo)
        LAI=np.where(QC_Map==1,np.nan,LAI)
        vegt_cover=np.where(QC_Map==1,np.nan,vegt_cover)
        SAVI=np.where(QC_Map==1,np.nan,SAVI)      
        
      
    print('---------------------------------------------------------')
    print('----------------------- Meteo ---------------------------')
    print('---------------------------------------------------------')
       
    # Precipitable water in the atmosphere (mm):
    # W = 0.14 * eact_inst * Pair + 2.1   # Garrison and Adler 1990
       
    # Slope of satur vapour pressure curve at air temp (kPa / °C)
    sl_es_24 = 4098 * esat_24 / np.power(Temp_24 + 237.3, 2)
       
    # Daily 24 hr radiation - For flat terrain only !
    ws_angle = np.arccos(-np.tan(phi)*tan(delta))   # Sunset hour angle ws
       
    # Extraterrestrial daily radiation, Ra (W/m2):
    Ra24_flat = (Gsc/np.pi * dr * (ws_angle * np.sin(phi[nrow//2, ncol//2]) * np.sin(delta) +
                    np.cos(phi[nrow//2, ncol//2]) * np.cos(delta) * np.sin(ws_angle)))
       
    # calculate the daily radiation or daily transmissivity or daily surface radiation based on the method defined by the user
    if Method_Radiation_24==1:
       Transm_24 = Rs_24/Ra_mountain_24     
          
    if Method_Radiation_24==2:
       Rs_24 = Ra_mountain_24 * Transm_24   
       
    # Solar radiation from extraterrestrial radiation
    Rs_24_flat = Ra24_flat * Transm_24       
    print('Mean Daily Transmissivity = %0.3f (W/m2)' % np.nanmean(Transm_24))
    print('Mean Daily incoming net Radiation = %0.3f (W/m2)' % np.nanmean(Rs_24))
    print('Mean Daily incoming net Radiation Flat Terrain = %0.3f (W/m2)' % np.nanmean(Rs_24_flat)) 
	 						
    # If method of instantaneous radiation 1 is used than calculate the Transmissivity    
    if Method_Radiation_inst==1:
        Transm_corr=Rs_in_inst/Ra_inst
  
    # If method of instantaneous radiation 2 is used than calculate the instantaneous incomming Radiation        
    if Method_Radiation_inst==2:
        # calculate the transmissivity index for direct beam radiation 
        Transm_corr = Transm_inst + 2e-5 * DEM_resh
        # Instantaneous incoming short wave radiation (W/m2):
        Rs_in_inst = Ra_inst * Transm_corr  
       
    # Atmospheric emissivity, by Bastiaanssen (1995):
    Transm_corr[Transm_corr<0.001]=0.1
    Transm_corr[Transm_corr>1]=1
    atmos_emis = 0.85 * np.power(-np.log(Transm_corr), 0.09) 
      
    # Instantaneous incoming longwave radiation:
    lw_in_inst = atmos_emis * SB_const * np.power(Temp_inst + 273.15, 4) 
    print('Instantaneous longwave incoming radiation = %0.3f (W/m2)' % np.nanmean(lw_in_inst))    
    print('Atmospheric emissivity = %0.3f' % np.nanmean(atmos_emis)) 
        
    # calculates the ground heat flux and the solar radiation
    Rn_24,rn_inst,g_inst,Rnl_24_FAO =Calc_Meteo(Rs_24,eact_24,Temp_24,Surf_albedo,cos_zn,dr,tir_emis,temp_surface_sharpened,water_mask,NDVI,Transm_24,SB_const,lw_in_inst,Rs_in_inst) 

    print('Mean Daily Net Radiation (FAO) = %0.3f (W/m2)' % np.nanmean(Rnl_24_FAO))
    print('Mean Daily Net Radiation = %0.3f (W/m2)' % np.nanmean(Rn_24))
    print('Mean instantaneous Net Radiation = %0.3f (W/m2)' % np.nanmean(rn_inst))
    print('Mean instantaneous Ground Heat Flux = %0.3f (W/m2)' % np.nanmean(g_inst))
       
    # Save output maps
    save_GeoTiff_proy(lsc, Rn_24, Rn_24_fileName, shape_lsc, nband=1)
    #save_GeoTiff_proy(lsc, rn_inst, rn_inst_fileName, shape_lsc, nband=1)
    #save_GeoTiff_proy(lsc, g_inst, g_inst_fileName, shape_lsc, nband=1)
    #save_GeoTiff_proy(lsc, Pair, Atmos_pressure_fileName, shape_lsc, nband=1)
    #save_GeoTiff_proy(lsc, Psychro_c, Psychro_c_fileName, shape_lsc, nband=1)							

    print('---------------------------------------------------------')
    print('-------------------- Hot/Cold Pixels --------------------')
    print('---------------------------------------------------------')
       
    # Temperature at sea level corrected for elevation: ??
    ts_dem,air_dens,Temp_corr=Correct_Surface_Temp(Temp_24,temp_surface_sharpened,Temp_lapse_rate,DEM_resh,Pair,dr,Transm_corr,cos_zn,Sun_elevation,deg2rad,QC_Map)    
    NDVI_land = np.where(NDVI <= 0, np.nan, NDVI)
    NDVIhot_low = np.nanpercentile(NDVI_land, NDVIhot_low1)
    NDVIhot_high = np.nanpercentile(NDVI_land, NDVIhot_high1)
    tcoldmin = np.nanpercentile(ts_dem, tcoldmin1)
    tcoldmax = np.nanpercentile(ts_dem, tcoldmax1)
    print('hot_minpercentile= %0.3f' % NDVIhot_low1, ', hot_maxpercentile= %0.3f' % NDVIhot_high1, ', cold_minpercentile= %0.3f' % tcoldmin1,', cold_maxpercentile= %0.3f' % tcoldmax1)
    print('NDVIhot_low= %0.3f ' % NDVIhot_low, ', NDVIhot_high= %0.3f' % NDVIhot_high, ', tcoldmin= %0.3f (Kelvin)' % tcoldmin,', tcoldmax= %0.3f (Kelvin)' % tcoldmax)
    # Selection of hot and cold pixels
    # Hot pixels
    ts_dem_hot,hot_pixels = Calc_Hot_Pixels(ts_dem,QC_Map, water_mask,NDVI,NDVIhot_low,NDVIhot_high,Hot_Pixel_Constant)
       
    # Cold pixels vegetation
    ts_dem_cold_veg = Calc_Cold_Pixels_Veg(NDVI,NDVI_max,NDVI_std, QC_Map,ts_dem,Image_Type, Cold_Pixel_Constant)
     
    # Cold pixels water						
    ts_dem_cold,cold_pixels,ts_dem_cold_mean = Calc_Cold_Pixels(ts_dem,tcoldmin,tcoldmax,water_mask,QC_Map,ts_dem_cold_veg,Cold_Pixel_Constant)
    if np.isnan(ts_dem_cold) == True:
        ts_dem_cold = Temp_inst
   
    # Save files
    save_GeoTiff_proy(lsc, Temp_corr, temp_corr_fileName, shape_lsc, nband=1)				
    save_GeoTiff_proy(lsc, ts_dem, ts_dem_fileName, shape_lsc, nband=1)
    save_GeoTiff_proy(lsc, hot_pixels, hot_pixels_fileName, shape_lsc, nband=1)
    save_GeoTiff_proy(lsc, cold_pixels, cold_pixels_fileName, shape_lsc, nband=1)
    
    print('---------------------------------------------------------')
    print('----------------- Sensible heat flux --------------------')
    print('---------------------------------------------------------')
       
    # Change the minimum windspeed to prevent high values in further calculations             
    if Wind_inst_kind_of_data == 0:
        if Wind_inst<1.5:
            Wind_inst=1.5
    if Wind_24_kind_of_data == 0:
        if Wind_24<1.5:
            Wind_24=1.5       
       
    # calculate windspeed at the blending height and the friction velocity by using the Raupach model or NDVI
    Surf_roughness,u_200,ustar_1,disp_height=Calc_Wind_Speed_Friction(h_obst,Wind_inst,zx,LAI,NDVI,Surf_albedo,water_mask,surf_roughness_equation_used)
    #save_GeoTiff_proy(lsc, Surf_roughness, surf_rough_fileName, shape_lsc, nband=1) 
       
    # Computation of surface roughness for momentum transport
    k_vk = 0.41      # Von Karman constant
                
    # Sensible heat 1 (Step 5)
    # Corrected value for the aerodynamic resistance (eq 41 with psi2 = psi1):
    rah1 = np.log(2.0/0.01) / (k_vk * ustar_1)
    i=0
    L, psi_m200_stable, psi, psi_m200,h_inst,dT, slope_dt, offset_dt = sensible_heat(
            rah1, ustar_1, rn_inst, g_inst, ts_dem, ts_dem_hot, ts_dem_cold,
            air_dens, temp_surface_sharpened, k_vk,QC_Map, hot_pixels, slope)
    
    # do the calculation iteratively 10 times  
    for i in range(1,10):
        L,psi,psi_m200,psi_m200_stable,h_inst,ustar_corr,rah_corr,dT, slope_dt, offset_dt = Iterate_Friction_Velocity(k_vk,u_200,Surf_roughness,g_inst,rn_inst, ts_dem, ts_dem_hot, ts_dem_cold,air_dens, temp_surface_sharpened,L,psi,psi_m200,psi_m200_stable,QC_Map, hot_pixels, slope)
       
    # Save files
    #save_GeoTiff_proy(lsc, h_inst, h_inst_fileName, shape_lsc, nband=1) 
    
    print('---------------------------------------------------------')
    print('-------------------- Evaporation ------------------------')
    print('---------------------------------------------------------')
   
    # calculate reference net radiation
    Rn_ref, Refl_rad_water, rah_grass=Calc_Rn_Ref(shape_lsc,water_mask,Rn_24,Ra_mountain_24,Transm_24,Rnl_24_FAO,Wind_24)
  
    # Calculate rah of PM for the ET act (dT after iteration) and ETpot (4 degrees)
    rah_pm_act=((np.log((2.0-0.0)/(Surf_roughness*0.1))*np.log((2.0-0.0)/(Surf_roughness)))/(k_vk*1.5**2))*((1-5*(-9.82*dT*(2.0-0.0))/((273.15+Temp_inst)*1.5**2))**(-0.75))
    rah_pm_act[rah_pm_act<25]=25
        
    rah_pm_pot=((np.log((2.0-0.0)/(Surf_roughness*0.1))*np.log((2.0-0.0)/(Surf_roughness)))/(k_vk*1.5**2))*((1-5*(-9.82*4.0*(2.0-0.0))/((273.15+Temp_inst)*1.5**2))**(-0.75)) 
    rah_pm_pot[rah_pm_pot<25]=25
       
    # calculate reference potential evaporation.
    ETpot_24,ETref_24,Lhv,rs_min=Calc_Ref_Pot_ET(LAI,temp_surface_sharpened,sl_es_24,Rn_ref,air_dens,esat_24,eact_24,rah_grass,Psychro_c,Rn_24,Refl_rad_water,rah_pm_pot,rl)
    
    # Instantaneous evapotranspiration
    LE_inst = rn_inst - g_inst - h_inst
    
    # Evaporative fraction
    EF_inst=Calc_instantaneous_ET_fraction(LE_inst,rn_inst,g_inst)
    
    # Daily Evaporation and advection factor
    ETA_24, AF=Calc_ETact(esat_24,eact_24,EF_inst,Rn_24,Refl_rad_water,Lhv)
    
    # Bulk surface resistance (s/m):
    bulk_surf_resis_24=Calc_Bulk_surface_resistance(sl_es_24,Rn_24,Refl_rad_water,air_dens,esat_24,eact_24,rah_pm_act,ETA_24,Lhv,Psychro_c)
     
    # crop factor
    kc = ETA_24 / ETref_24  # Crop factor
    ETP_24 = np.where(ETpot_24 < ETA_24, ETA_24, ETpot_24)
    ET_24_deficit = ETP_24 - ETA_24
    kc_max = ETP_24 / ETref_24

    # Save files   
    #save_GeoTiff_proy(lsc, rs_min, min_bulk_surf_res_fileName, shape_lsc, nband=1)
    save_GeoTiff_proy(lsc, EF_inst, EF_inst_fileName, shape_lsc, nband=1)
    #save_GeoTiff_proy(lsc, LE_inst, LE_inst_fileName, shape_lsc, nband=1)
    save_GeoTiff_proy(lsc, ETref_24, ETref_24_fileName, shape_lsc, nband=1)							
    save_GeoTiff_proy(lsc, ETA_24, ETA_24_fileName, shape_lsc, nband=1)
    save_GeoTiff_proy(lsc, ETP_24, ETP_24_fileName, shape_lsc, nband=1)
    save_GeoTiff_proy(lsc, ET_24_deficit, ET_24_deficit_fileName, shape_lsc, nband=1)
    save_GeoTiff_proy(lsc, AF, AF_fileName, shape_lsc, nband=1)								
    save_GeoTiff_proy(lsc, kc, kc_fileName, shape_lsc, nband=1)
    save_GeoTiff_proy(lsc, kc_max, kc_max_fileName, shape_lsc, nband=1)
    #save_GeoTiff_proy(lsc, bulk_surf_resis_24, bulk_surf_res_fileName, shape_lsc, nband=1)

    print('---------------------------------------------------------')
    print('-------------------- Soil Moisture ----------------------')
    print('---------------------------------------------------------')

    #  Calculate soil properties   
    #SM_stress_trigger, total_soil_moisture, RZ_SM,moisture_stress_biomass,irrigation_needs,top_soil_moisture=Calc_Soil_Moisture(ETA_24,accum_prec_14d,accum_ETo_14d,EF_inst,water_mask,vegt_cover,Theta_sat,Theta_res)
    SM_stress_trigger, total_soil_moisture, root_zone_moisture_first, moisture_stress_biomass_first,top_soil_moisture,RZ_SM_NAN = Calc_Soil_Moisture(ETA_24,EF_inst,QC_Map,water_mask,vegt_cover,Theta_sat_top,Theta_sat_sub, Theta_res_top,Theta_res_sub, depl_factor,Field_Capacity,FPAR, Soil_moisture_wilting_point)
    
    # seperation of E and T
    Eact_24,Tpot_24,Tact_24,moisture_stress_biomass,T24_deficit,beneficial_fraction,root_zone_moisture_final,top_zone_moisture_final=Separate_E_T(Light_use_extinction_factor,LAI,ETP_24,Theta_res_top, Theta_res_sub,Theta_sat_top,Theta_sat_sub,top_soil_moisture,sl_es_24, Psychro_c,moisture_stress_biomass_first,vegt_cover,ETA_24,SM_stress_trigger,root_zone_moisture_first,total_soil_moisture)
     
    # Irrigation:
    irrigation_needs = Classify_Irrigation(moisture_stress_biomass, vegt_cover, top_zone_moisture_final, Theta_sat_top, Field_Capacity, Soil_moisture_wilting_point, water_mask, NDVI)
    
    # Save files
    save_GeoTiff_proy(lsc, Tact_24, Tact24_fileName,shape_lsc, nband=1)
    save_GeoTiff_proy(lsc, Eact_24, Eact24_fileName,shape_lsc, nband=1)                  
    save_GeoTiff_proy(lsc, Tpot_24, Tpot24_fileName,shape_lsc, nband=1)                 
    save_GeoTiff_proy(lsc, T24_deficit, T24_deficit_fileName,shape_lsc, nband=1)                 
    save_GeoTiff_proy(lsc, total_soil_moisture, total_soil_moisture_fileName,shape_lsc, nband=1)
    save_GeoTiff_proy(lsc, top_zone_moisture_final, top_soil_moisture_fileName,shape_lsc, nband=1)
    save_GeoTiff_proy(lsc, root_zone_moisture_final, RZ_SM_fileName, shape_lsc,nband=1)
    #save_GeoTiff_proy(lsc, SM_stress_trigger, SM_stress_trigger_fileName,shape_lsc, nband=1)
    #save_GeoTiff_proy(lsc, moisture_stress_biomass, moisture_stress_biomass_fileName,shape_lsc, nband=1)
    save_GeoTiff_proy(lsc, irrigation_needs, irrigation_needs_fileName,shape_lsc, nband=1)
  
    print('---------------------------------------------------------')
    print('---------------------- Biomass --------------------------')
    print('---------------------------------------------------------')
 
    # calculate biomass production
    LUE,Biomass_prod,Biomass_wp,Biomass_deficit = Calc_Biomass_production(LAI,ETP_24,moisture_stress_biomass,ETA_24,Ra_mountain_24,Transm_24,FPAR,esat_24,eact_24,Th,Kt,Tl,Temp_24,LUEmax,Biomass_aboveground_factor)
    
    # Set water bodies to 0 biomass (aquatic plants not modeled by SEBAL)
    Biomass_prod[water_mask != 0] = 0.0
    Biomass_wp[water_mask != 0] = 0.0
    Biomass_deficit[water_mask != 0] = 0.0
    
    #save_GeoTiff_proy(lsc, LUE, LUE_fileName,shape_lsc, nband=1)    
    save_GeoTiff_proy(lsc, Biomass_prod, Biomass_prod_fileName, shape_lsc, nband=1)
    save_GeoTiff_proy(lsc, Biomass_wp, Biomass_wp_fileName, shape_lsc, nband=1)
    save_GeoTiff_proy(lsc, Biomass_deficit, Biomass_deficit_fileName,shape_lsc, nband=1)
    lsc=None

    print ('---------------------------------------------------------')
    print ('------------Removing Intermediary files------------------')
    print ('---------------------------------------------------------')

    try:
        shutil.rmtree(os.path.join(output_folder, 'Output_temporary'))
        shutil.rmtree(os.path.join(output_folder, 'Output_radiation_balance'))
        shutil.rmtree(os.path.join(output_folder, 'Output_cloud_masked'))
    except OSError as e:
        print ('Error: folder does not exist')

    print ('...................................................................')
    print ('............................DONE!..................................')
    print ('...................................................................')

    # ------------------------------------------------------------------------
    # ------------------------------------------------------------------------
    # FUNCTIONS
    #-------------------------------------------------------------------------

def Create_Buffer(Data_In):
    
   '''
   This function creates a 3D array which is used to apply the moving window
   '''
   Buffer_area = 2 # A block of 2 times Buffer_area + 1 will be 1 if there is the pixel in the middle is 1
   Data_Out=np.empty((len(Data_In),len(Data_In[1])))   
   Data_Out[:,:] = Data_In
   for ypixel in range(1,Buffer_area + 1):
        Data_Out[:,0:-ypixel] += Data_In[:,ypixel:]
        Data_Out[:,ypixel:] += Data_In[:,:-ypixel]
        
        for xpixel in range(1,Buffer_area + 1):
           Data_Out[0:-xpixel,ypixel:] += Data_In[xpixel:,:-ypixel]
           Data_Out[xpixel:,ypixel:] += Data_In[:-xpixel,:-ypixel]
           Data_Out[0:-xpixel,0:-ypixel] += Data_In[xpixel:,ypixel:]
           Data_Out[xpixel:,0:-ypixel] += Data_In[:-xpixel,ypixel:]

           if ypixel==1:
                Data_Out[xpixel:,:] += Data_In[:-xpixel,:]
                Data_Out[:,0:-xpixel] += Data_In[:,xpixel:]


   Data_Out[Data_Out>0.1] = 1
   Data_Out[Data_Out<=0.1] = 0  
           
   return(Data_Out)

def Calc_Biomass_production(LAI,ETP_24,moisture_stress_biomass,ETA_24,Ra_mountain_24,Transm_24,FPAR,esat_24,eact_24,Th,Kt,Tl,Temp_24,LUEmax,biomass_factor):
    """
    Function to calculate the biomass production and water productivity
    biomass_factor: Aboveground biomass fraction (0.864 for C3, 0.72 for C4, 0.5-0.65 for trees)
    """ 
  
    Ksolar = Ra_mountain_24 * Transm_24
    
    # Incident Photosynthetically active radiation (PAR, MJ/m2) per time period
    PAR = 0.48 * Ksolar
    
    # Aborbed Photosynthetical Active Radiation (APAR) by the vegetation:
    APAR = FPAR * PAR

    vapor_stress = 0.88 - 0.183 * np.log(esat_24 - eact_24)
    vapor_stress_biomass = vapor_stress.clip(0.0, 1.0)
    Jarvis_coeff = (Th - Kt) / (Kt - Tl)
    heat_stress_biomass = ((Temp_24 - Tl) * np.power(Th - Temp_24, Jarvis_coeff) / ((Kt - Tl) * np.power(Th - Kt, Jarvis_coeff)))
    print('vapor stress biomass =', '%0.3f' % np.nanmean(vapor_stress_biomass))
    print('heat stress biomass =', '%0.3f' % np.nanmean(heat_stress_biomass))
				
    # Light use efficiency, reduced below its potential value by low
    # temperature or water shortage:
    LUE = (LUEmax * heat_stress_biomass * vapor_stress_biomass * moisture_stress_biomass)
        
    # Dry matter production (kg/ha/d):
    Biomass_prod = APAR * LUE * biomass_factor
    # biomass_factor converts dry matter production to aboveground biomass
    # C3 crops: 0.864, C4 crops: 0.72, Trees/forests: 0.45-0.65
    
    # Ensure biomass is 0 (not NaN) for areas with no vegetation
    # Only water bodies and clouds should be NaN
    Biomass_prod = np.nan_to_num(Biomass_prod, nan=0.0)

    # Water productivity
    Biomass_wp = Biomass_prod/ (ETA_24 * 10)  # C3 vegetation
    Biomass_wp[ETA_24 == 0.0] = 0.0
    Biomass_wp = np.nan_to_num(Biomass_wp, nan=0.0)
    
    # Water deficit
    Biomass_deficit = (Biomass_prod / moisture_stress_biomass - Biomass_prod)
    Biomass_deficit = np.nan_to_num(Biomass_deficit, nan=0.0)
                          
                          
    return(LUE,Biomass_prod,Biomass_wp,Biomass_deficit)

#------------------------------------------------------------------------------    
def Classify_Irrigation(moisture_stress_biomass, vegt_cover, soil_moisture, Theta_sat, Field_Capacity, Wilting_Point, water_mask, NDVI):
   '''
   This function makes a classification with 4 categories which show the irrigation needs
   
   For VEGETATED areas (vegt_cover >= 0.05):
       Based on moisture_stress_biomass ratio (Tact/Tpot):
           - 1.0: No stress (optimal water)
           - 0.9-1.0: Slight stress
           - 0.8-0.9: Moderate stress
           - <0.8: Severe stress
   
   For BARE SOIL (vegt_cover < 0.05, NDVI >= 0.05):
       Based on soil moisture relative to field capacity:
           - Above field capacity: No irrigation needed
           - 70-100% of field capacity: Perhaps irrigate (prepare for sowing)
           - 40-70% of field capacity: Irrigate (dry soil)
           - Below 40% of field capacity: Irrigate immediately (very dry)
   
   Classification:
       0: No need for irrigation (or non-agricultural area)
       1: Perhaps irrigate (slight stress/moderate soil moisture)
       2: Irrigate (moderate stress/dry soil)
       3: Irrigate immediately (severe stress/very dry soil)
   
   Excluded areas (set to 0):
       - Water bodies (water_mask != 0)
       - Buildings/roads/rock (NDVI < 0.05 with vegt_cover < 0.05)
       - Urban/built-up areas
   '''
   irrigation_needs = np.zeros_like(moisture_stress_biomass)
   
   # Calculate soil moisture stress for bare soil areas
   # Available Water = (Soil_Moisture - Wilting_Point) / (Field_Capacity - Wilting_Point)
   available_water = (soil_moisture - Wilting_Point) / (Field_Capacity - Wilting_Point)
   available_water = available_water.clip(0.0, 1.5)  # Can exceed 1.0 if above field capacity
   
   # Define agricultural areas (exclude water, buildings, roads, rock)
   # Buildings/roads: NDVI < 0.05 (very low vegetation index, not even bare soil level)
   # Bare agricultural soil: NDVI 0.05-0.125 (ploughed fields, prepared land)
   # Water: water_mask != 0
   agricultural_bare_soil = (vegt_cover < 0.05) & (NDVI >= 0.05) & (water_mask == 0)
   vegetated = (vegt_cover >= 0.05) & (water_mask == 0)
   
   # VEGETATED AREAS: Use transpiration-based moisture stress
   irrigation_needs[vegetated & (moisture_stress_biomass >= 1.0)] = 0.0  # No stress
   irrigation_needs[vegetated & (moisture_stress_biomass >= 0.9) & (moisture_stress_biomass < 1.0)] = 1.0  # Slight stress
   irrigation_needs[vegetated & (moisture_stress_biomass >= 0.8) & (moisture_stress_biomass < 0.9)] = 2.0  # Moderate stress
   irrigation_needs[vegetated & (moisture_stress_biomass < 0.8)] = 3.0  # Severe stress
   
   # BARE AGRICULTURAL SOIL: Use soil moisture relative to field capacity
   # (Excludes buildings/roads which have NDVI < 0.05)
   irrigation_needs[agricultural_bare_soil & (available_water >= 1.0)] = 0.0  # Above field capacity - no need
   irrigation_needs[agricultural_bare_soil & (available_water >= 0.7) & (available_water < 1.0)] = 1.0  # 70-100% FC - perhaps irrigate
   irrigation_needs[agricultural_bare_soil & (available_water >= 0.4) & (available_water < 0.7)] = 2.0  # 40-70% FC - irrigate
   irrigation_needs[agricultural_bare_soil & (available_water < 0.4)] = 3.0  # Below 40% FC - irrigate immediately
   
   # Everything else (water, buildings, roads, rock) remains 0 (no irrigation needed)
                                 
   return(irrigation_needs)   

#------------------------------------------------------------------------------   
def Separate_E_T(Light_use_extinction_factor,LAI,ETP_24,Theta_res_top,Theta_res_sub, Theta_sat_top, Theta_sat_sub, top_soil_moisture,sl_es_24, Psychro_c,moisture_stress_biomass_first,vegt_cover,ETA_24,SM_stress_trigger,root_zone_moisture_first,total_soil_moisture):
   '''
   Separate the Evapotranspiration into evaporation and Transpiration
   '''
   # constants
      
   Tpot_24_estimate=(1-np.exp(-Light_use_extinction_factor*LAI))*ETP_24

   SE_top = (top_soil_moisture-Theta_res_top)/(Theta_sat_top-Theta_res_top)

   Eact_24_estimate=np.minimum(1,1 / np.power(SE_top + 0.1,-2.0))*(ETP_24-Tpot_24_estimate)
   
   #RS_soil = RS_soil_min * np.power(SE_top,-2.0)
   #Eact_24_estimate=(sl_es_24+Psychro_c*(1+RS_soil_min/Rah_PM))/(sl_es_24+Psychro_c*(1+RS_soil/Rah_PM))*(ETP_24-Tpot_24_estimate)
   n66_memory = moisture_stress_biomass_first * Tpot_24_estimate
   
   # calulate the first estimation of actual daily tranpiration
   Tact_24_estimate = np.copy(n66_memory)
   Tact_24_estimate[n66_memory > 0.99*ETA_24]=ETA_24[n66_memory > 0.99*ETA_24]
   Tact_24_estimate[vegt_cover == 0.0] = 0.0
   
   # calculate the second estimation and end estimation of the actual daily tranpiration
   Tact_24 = np.abs((Tact_24_estimate/(Tact_24_estimate + Eact_24_estimate))*ETA_24)
  
   # calculate the actual daily potential transpiration
   Tpot_24 = np.copy(Tpot_24_estimate)
   Tpot_24[Tpot_24_estimate < Tact_24] = Tact_24[Tpot_24_estimate < Tact_24]
   
   # calculate moisture stress biomass
   moisture_stress_biomass = Tact_24 / Tpot_24
   
   # Calculate root zone moisture final
   Se_Poly=2.23*np.power(moisture_stress_biomass,3)-3.35*np.power(moisture_stress_biomass,2)+1.98*moisture_stress_biomass+0.07
   root_zone_moisture1=Se_Poly*(SM_stress_trigger+0.02-Theta_res_sub)+Theta_res_sub 
   root_zone_moisture_final=np.where(root_zone_moisture1>root_zone_moisture_first,root_zone_moisture1,root_zone_moisture_first)
   
   # Calculate top zone moisture final
   top_zone_moisture1=(total_soil_moisture-root_zone_moisture_final*vegt_cover)/(1-vegt_cover)
   top_zone_moisture_final=top_zone_moisture1.clip(Theta_res_top,Theta_sat_top)
    
   # calculate the actual daily evaporation
   Eact_24 = ETA_24 - Tact_24
   
   # calculate the Transpiration deficit
   T24_deficit = Tpot_24 - Tact_24
   
   # calculate the beneficial fraction
   beneficial_fraction=Tact_24 / ETA_24
   beneficial_fraction[ETA_24 == 0.0] = 0.0
   
   return(Eact_24,Tpot_24,Tact_24,moisture_stress_biomass,T24_deficit,beneficial_fraction,root_zone_moisture_final,top_zone_moisture_final)
  
#------------------------------------------------------------------------------    
def Calc_Soil_Moisture(ETA_24,EF_inst,QC_Map, water_mask,vegt_cover,Theta_sat_top, Theta_sat_sub,Theta_res_top, Theta_res_sub,depl_factor,Field_Capacity,FPAR, Soil_moisture_wilting_point):
    """
    Function to calculate soil characteristics
    """
    # constants:
    Veg_Cover_Threshold_RZ = 0.9 # Threshold vegetation cover for root zone moisture
       
    # Average fraction of TAW that can be depleted from the root zone
    # before stress:
    p_factor = depl_factor + 0.04 * (5.0 - ETA_24)  # page 163 of FAO 56
    # The factor p differs from one crop to another. It normally varies from
    # 0.30 for shallow rooted plants at high rates of ETc (> 8 mm d-1)
    # to 0.70 for deep rooted plants at low rates of ETc (< 3 mm d-1)

    # Critical value under which plants get stressed:
    SM_stress_trigger = Field_Capacity - p_factor * (Field_Capacity - Soil_moisture_wilting_point) 
    
    # Create local copy of EF_inst for soil moisture calculation
    # Scott et al. 2003 equation requires EF <= 1.0 for physical validity
    # We cap at 0.999 to avoid division issues, but don't modify the original array
    EF_soil = np.copy(EF_inst)
    EF_soil[EF_soil >= 1.0] = 0.999    

    # Total soil water content (cm3/cm3):
    total_soil_moisture = Theta_sat_sub * np.exp((EF_soil - 1.0) / 0.421)   # asce paper Scott et al. 2003
    total_soil_moisture[np.logical_or(water_mask == 1.0,QC_Map == 1.0)] = 1.0  # In water and snow is 1                               
    total_soil_moisture[QC_Map == 1.0] = np.nan  # Where clouds no data
    
    # Mask non-agricultural areas (buildings, roads, rock) where NDVI is extremely low
    # These areas don't have soil, so soil moisture is meaningless
    # Use a buffer: if vegt_cover < 0.01 (essentially bare) and not in the agricultural bare soil range
    # This catches buildings/roads but allows ploughed agricultural fields
    non_agricultural = (vegt_cover < 0.01)  # Extremely low vegetation cover
    total_soil_moisture[non_agricultural] = np.nan  # Set to NaN for non-soil areas                              
    
    # Root zone soil moisture:
    RZ_SM = np.copy(total_soil_moisture)
    RZ_SM[vegt_cover <= Veg_Cover_Threshold_RZ] = np.nan
    if np.isnan(np.nanmean(RZ_SM)) == True:
        Veg_Cover_Threshold_RZ = np.nanpercentile(vegt_cover, 80)   
        RZ_SM = np.copy(total_soil_moisture)
        RZ_SM[vegt_cover <= Veg_Cover_Threshold_RZ] = np.nan
        print('No RZ_SM so the vegetation Threshold for RZ is adjusted from 0,9 to =', '%0.3f' % Veg_Cover_Threshold_RZ)
        
    #RZ_SM = RZ_SM.clip(Theta_res, (0.85 * Theta_sat))
    #RZ_SM[np.logical_or(water_mask == 1.0, water_mask == 2.0)] = 1.0                            
    RZ_SM_NAN = np.copy(RZ_SM)
    RZ_SM_NAN[RZ_SM==0] = np.nan
    RZ_SM_min = np.nanmin(RZ_SM_NAN)
    RZ_SM_max = np.nanmax(RZ_SM_NAN)
    RZ_SM_mean = np.nanmean(RZ_SM_NAN)
    print('Root Zone Soil moisture mean =', '%0.3f (cm3/cm3)' % RZ_SM_mean)
    print('Root Zone Soil moisture min =', '%0.3f (cm3/cm3)' % RZ_SM_min)
    print('Root Zone Soil moisture max =', '%0.3f (cm3/cm3)' % RZ_SM_max)
    
    Max_moisture_RZ = vegt_cover * (RZ_SM_max - RZ_SM_mean) + RZ_SM_mean
    
    # Soil moisture in the top (temporary)
    top_soil_moisture_temp = np.copy(total_soil_moisture)
    top_soil_moisture_temp[np.logical_or(vegt_cover <= 0.02, vegt_cover >= 0.1)] = 0
    top_soil_moisture_temp[top_soil_moisture_temp == 0] = np.nan 
    top_soil_moisture_std = np.nanstd(top_soil_moisture_temp)
    top_soil_moisture_mean = np.nanmean(top_soil_moisture_temp)
    print('Top Soil moisture mean =', '%0.3f (cm3/cm3)' % top_soil_moisture_mean)
    print('Top Soil moisture Standard Deviation', '%0.3f (cm3/cm3)' % top_soil_moisture_std)
    
    # calculate root zone moisture
    root_zone_moisture_temp = (total_soil_moisture - (top_soil_moisture_mean + top_soil_moisture_std) * (1-vegt_cover))/vegt_cover # total soil moisture = soil moisture no vegtatation *(1-vegt_cover)+soil moisture root zone * vegt_cover
    try:
        root_zone_moisture_temp[root_zone_moisture_temp <= Theta_res_sub] = Theta_res_sub[root_zone_moisture_temp <= Theta_res_sub]
    except:
        root_zone_moisture_temp[root_zone_moisture_temp <= Theta_res_sub] = Theta_res_sub
 	
		
    root_zone_moisture_temp[root_zone_moisture_temp >= Max_moisture_RZ] = Max_moisture_RZ[root_zone_moisture_temp >= Max_moisture_RZ]
    
    root_zone_moisture_first = np.copy(root_zone_moisture_temp)
    root_zone_moisture_first[np.logical_or(QC_Map ==1.0 ,np.logical_or(water_mask == 1.0, vegt_cover < 0.0))] = 0
    root_zone_moisture_first[non_agricultural] = np.nan  # Mask buildings/roads - they have no root zone!

    # Normalized stress trigger:
    norm_trigger = (root_zone_moisture_first - Soil_moisture_wilting_point)/ (SM_stress_trigger + 0.02 - Soil_moisture_wilting_point)
    norm_trigger[norm_trigger > 1.0] = 1.0
    
    # moisture stress biomass:
    moisture_stress_biomass_first = norm_trigger - (np.sin(2 * np.pi * norm_trigger)) / (2 * np.pi)
    moisture_stress_biomass_first=np.where(moisture_stress_biomass_first<0.5*FPAR,0.5*FPAR,moisture_stress_biomass_first)
    moisture_stress_biomass_first[moisture_stress_biomass_first <= 0.0] = 0
    moisture_stress_biomass_first[moisture_stress_biomass_first > 1.0] = 1.0
    
     # Soil moisture in the top layer - Recalculated ??
    top_soil_moisture = ((total_soil_moisture - root_zone_moisture_first * vegt_cover) / (1.0 - vegt_cover))
    
    try:
        top_soil_moisture[top_soil_moisture > Theta_sat_top] = Theta_sat_top [top_soil_moisture > Theta_sat_top]
    except:
        top_soil_moisture[top_soil_moisture > Theta_sat_top] = Theta_sat_top
 	
    top_soil_moisture[np.logical_or(water_mask == 1.0, QC_Map == 1.0)] = 1.0
    top_soil_moisture[non_agricultural] = np.nan  # Mask buildings/roads

    return(SM_stress_trigger, total_soil_moisture, root_zone_moisture_first, moisture_stress_biomass_first,top_soil_moisture,RZ_SM_NAN)

#------------------------------------------------------------------------------
def Calc_Bulk_surface_resistance(sl_es_24,Rn_24,Refl_rad_water,air_dens,esat_24,eact_24,rah_pm_act,ETA_24,Lhv,Psychro_c):
    """
    Function to calculate the bulk surface resistance
    """
    # Bulk surface resistance (s/m):
    bulk_surf_resis_24 = ((((sl_es_24 * (Rn_24 - Refl_rad_water) + air_dens *
                          1004 * (esat_24 - eact_24) / rah_pm_act) / (ETA_24 * Lhv / 86400) -
                          sl_es_24) / Psychro_c - 1.0) * rah_pm_act)
    bulk_surf_resis_24[ETA_24 <= 0.0] = 100000.0
    bulk_surf_resis_24 = bulk_surf_resis_24.clip(0.0, 100000.0)
    return(bulk_surf_resis_24)

#------------------------------------------------------------------------------
def Calc_ETact(esat_24,eact_24,EF_inst,Rn_24,Refl_rad_water,Lhv):
    """
    Function to calculate the daily evaporation
    """
    # Advection factor ???
    AF = 1 + 0.985 * (np.exp((esat_24 - eact_24) * 0.08) - 1.0) * EF_inst
    # Daily evapotranspiration:
    ETA_24 = EF_inst * AF * (Rn_24 - Refl_rad_water) / (Lhv * 1000) * 86400000
    ETA_24=ETA_24.clip(0,15.0)
    return(ETA_24, AF)
    
#------------------------------------------------------------------------------   
def Calc_instantaneous_ET_fraction(LE_inst,rn_inst,g_inst):   
    """
    Function to calculate the evaporative fraction
    """ 
    EF_inst = LE_inst / (rn_inst - g_inst)    # Evaporative fraction
    EF_inst = EF_inst.clip(0.0, 1.8)
    EF_inst[LE_inst<0] = 0

    return(EF_inst)

#------------------------------------------------------------------------------
def Calc_Ref_Pot_ET(LAI,Surface_temp,sl_es_24,Rn_ref,air_dens,esat_24,eact_24,rah_grass,Psychro_c,Rn_24,Refl_rad_water,rah_pm_pot,rl):
    """
    Function to calculate the reference potential evapotransporation and potential evaporation
    """ 

    # Effective leaf area index involved, see Allen et al. (2006):
    LAI_eff = LAI / (0.3 * LAI + 1.2)
    rs_min = rl / LAI_eff  # Min (Bulk) surface resistance (s/m)
    # Latent heat of vaporization (J/kg):
    # Lhv = (2.501 - 2.361e-3 * (Surface_temp - 273.15)) * 1E6
    Lhv = 2.45 * 1E6

    # Reference evapotranspiration- grass
    # Penman-Monteith of the combination equation (eq 3 FAO 56) (J/s/m2)
    LET_ref_24 = ((sl_es_24 * Rn_ref + air_dens * 1004 * (esat_24 - eact_24) /
                  rah_grass) / (sl_es_24 + Psychro_c * (1 + 70.0/rah_grass)))
    # Reference evaportranspiration (mm/d):
    ETref_24 = LET_ref_24 / (Lhv * 1000) * 86400000

    # Potential evapotranspiration
    # Penman-Monteith of the combination equation (eq 3 FAO 56) (J/s/m2)
    LETpot_24 = ((sl_es_24 * (Rn_24 - Refl_rad_water) + air_dens * 1004 *
               (esat_24 - eact_24)/rah_pm_pot) / (sl_es_24 + Psychro_c * (1 + rs_min/rah_pm_pot)))
    # Potential evaportranspiration (mm/d)
    ETpot_24 = LETpot_24 / (Lhv * 1000) * 86400000
    ETpot_24[ETpot_24 > 15.0] = 15.0
    return(ETpot_24,ETref_24,Lhv,rs_min)
     
#------------------------------------------------------------------------------    
def Calc_Rn_Ref(shape_lsc,water_mask,Rn_24,Ra_mountain_24,Transm_24,Rnl_24_FAO,Wind_24):
    """
    Function to calculate the net solar radiation
    """  
    # constants:
    G24_water = 0.1  # G24 ratio for water - reflectivity?

    # Reflected radiation at water surface: ??
    Refl_rad_water = np.zeros((shape_lsc[1], shape_lsc[0]))
    Refl_rad_water = np.where(water_mask != 0.0, G24_water * Rn_24, 0.0)

    # Aerodynamic resistance (s/m) for grass surface:
    rah_grass = 208.0 / Wind_24
    print('rah_grass=', '%0.3f (s/m)' % np.nanmean(rah_grass))
    # Net radiation for grass Rn_ref, eq 40, FAO56:
    Rn_ref = Ra_mountain_24 * Transm_24 * (1 - 0.23) - Rnl_24_FAO  # Rnl avg(fao-slob)?
    return(Rn_ref, Refl_rad_water,rah_grass)
    

#------------------------------------------------------------------------------
def Iterate_Friction_Velocity(k_vk,u_200,Surf_roughness,g_inst,rn_inst, ts_dem, ts_dem_hot, ts_dem_cold,air_dens, Surface_temp,L,psi,psi_m200,psi_m200_stable,QC_Map, hot_pixels, slope):
    """
    Function to correct the windspeed and aerodynamic resistance for the iterative process the output can be used as the new input for this model
    """    
    # Sensible heat 2 (Step 6)
    # Corrected value for the friction velocity, unstable
    ustar_corr_unstable = (k_vk * u_200 / (np.log(200.0 / Surf_roughness) -
                        psi_m200))
    # Corrected value for the friction velocity, stable
    ustar_corr_stable = (k_vk * u_200 / (np.log(200.0 / Surf_roughness) -
                      psi_m200_stable))
    ustar_corr = np.where(L > 0.0, ustar_corr_stable, ustar_corr_unstable)
    ustar_corr[ustar_corr < 0.02] = 0.02

    rah_corr_unstable = (np.log(2.0/0.01) - psi) / (k_vk * ustar_corr)     # unstable
    rah_corr_stable = (np.log(2.0/0.01) - 0.0) / (k_vk * ustar_corr)       # stable
    rah_corr = np.where(L > 0.0, rah_corr_stable, rah_corr_unstable)
    L_corr, psi_m200_corr_stable, psi_corr, psi_m200_corr,h,dT, slope_dt, offset_dt = sensible_heat(
            rah_corr, ustar_corr, rn_inst, g_inst, ts_dem, ts_dem_hot, ts_dem_cold,
            air_dens, Surface_temp, k_vk,QC_Map, hot_pixels, slope)
    return(L_corr,psi_corr,psi_m200_corr,psi_m200_corr_stable,h,ustar_corr,rah_corr,dT,slope_dt, offset_dt)

#------------------------------------------------------------------------------
def Calc_Wind_Speed_Friction(h_obst,Wind_inst,zx,LAI,NDVI,Surf_albedo,water_mask,surf_roughness_equation_used):    
    """
    Function to calculate the windspeed and friction by using the Raupach or NDVI model
    """    
    
    # constants
    k_vk = 0.41      # Von Karman constant
    h_grass = 0.12   # Grass height (m)
    cd = 53          # Free parameter for displacement height, default = 20.6
    # 1) Raupach model
    zom_Raupach,disp_height=Raupach_Model(h_obst,cd,LAI,Surf_albedo,water_mask,k_vk)

    # 2) NDVI model
    zom_NDVI=NDVI_Model(NDVI,Surf_albedo,water_mask)

    if surf_roughness_equation_used == 1:
        Surf_roughness = zom_NDVI
    else:
        Surf_roughness = zom_Raupach

    zom_grass = 0.123 * h_grass
    # Friction velocity for grass (m/s):
    ustar_grass = k_vk * Wind_inst / np.log(zx / zom_grass)
    print('u*_grass = ', '%0.3f (m/s)' % np.mean(ustar_grass))
    # Wind speed (m/s) at the "blending height" (200m):
    u_200 = ustar_grass * np.log(200 / zom_grass) / k_vk
    print('Wind speed at the blending height, u200 =', '%0.3f (m/s)' % np.mean(u_200))
    # Friction velocity (m/s):
    ustar_1 = k_vk * u_200 / np.log(200 / Surf_roughness)
    return(Surf_roughness,u_200,ustar_1,disp_height)
    
#------------------------------------------------------------------------------
def Raupach_Model(h_obst,cd,LAI,Surf_albedo,water_mask,k_vk):    
    """
    Function for the Raupach model to calculate the surface roughness
    """    
    psi = np.log(2.0) - 1 + np.power(2.0, -1)  # Vegetation influence function
    
    # Displacement height:
    disp_height = h_obst * (1 - (1 - np.exp(-np.power(cd * LAI, 0.5))) /
                            np.power(cd * LAI, 0.5))
    # Drag coefficient
    Cs = np.power(k_vk, 2) / np.power(np.log((h_obst-disp_height) / 0.01) +
                                      psi, 2)
    ratio = np.power(Cs + 0.35 * LAI/2, 0.5)  # uh/u
    zom_Raupach = (h_obst - disp_height) / np.exp(k_vk * ratio - psi)
    return(zom_Raupach, disp_height)
 
#------------------------------------------------------------------------------
def NDVI_Model(NDVI,Surf_albedo,water_mask):
    """
    Function for the NDVI model to calculate the surface roughness
    """    
    zom_NDVI = np.exp(1.096 * NDVI / Surf_albedo - 5.307)
    zom_NDVI[water_mask == 1.0] = 0.001
    zom_NDVI[zom_NDVI > 10.0] = 10.0
    return(zom_NDVI)   
       
#------------------------------------------------------------------------------
def Correct_Surface_Temp(Temp_24,Surface_temp,Temp_lapse_rate,DEM_resh,Pair,dr,Transm_corr,cos_zn,Sun_elevation,deg2rad,ClipLandsat):
    """
    Function to correct the surface temperature based on the DEM map
    """     
    #constants:
    Gsc = 1367        # Solar constant (W / m2)   
    
    cos_zenith_flat = np.cos((90 - Sun_elevation) * deg2rad)
    Temp_corr = Surface_temp + Temp_lapse_rate * DEM_resh  # rescale everything to sea level
    Temp_corr[Surface_temp == 350.0] = 0.0
    #air_dens = 1000 * Pair / (1.01 * Surface_temp * 287)    
    air_dens = 1000 * Pair / (1.01 * (Temp_24 + 273.15) * 287)
    #
    ts_dem = (Temp_corr + (Gsc * dr * Transm_corr * cos_zn -
              Gsc * dr * Transm_corr * cos_zenith_flat) / (air_dens * 1004 * 0.050))
    #(Temp_corr - (Gsc * dr * Transm_corr * cos_zn -
    #          Gsc * dr * Transm_corr * cos_zenith_flat) / (air_dens * 1004 * 0.050))
    ts_dem[ClipLandsat==1]=np.nan
    ts_dem[ts_dem==0]=np.nan
    ts_dem=ts_dem.clip(273,350)         
  
    return(ts_dem,air_dens,Temp_corr)
 
#------------------------------------------------------------------------------
def Calc_Hot_Pixels(ts_dem,QC_Map, water_mask, NDVI,NDVIhot_low,NDVIhot_high,Hot_Pixel_Constant):
    """
    Function to calculates the hot pixels based on the surface temperature and NDVI
    """ 
    for_hot = np.copy(ts_dem)
    for_hot[NDVI <= NDVIhot_low] = np.nan
    for_hot[NDVI >= NDVIhot_high] = np.nan
    for_hot_thres = np.nanpercentile(for_hot, 99.5)
    for_hot[np.logical_or(water_mask != 0.0, QC_Map != 0.0)] = 0.0
    hot_pixels = np.copy(for_hot)
    hot_pixels[for_hot < 273.0] = np.nan
    hot_pixels[for_hot < for_hot_thres] = np.nan
    ts_dem_hot_min = np.nanmin(hot_pixels)    # Max
    ts_dem_hot_max = np.nanmax(hot_pixels)    # Max
    ts_dem_hot_mean = np.nanmean(hot_pixels)  # Mean
    ts_dem_hot_std = np.nanstd(hot_pixels)    # Standard deviation
    #ts_dem_hot = ts_dem_hot_max - 0.25 * ts_dem_hot_std
    #ts_dem_hot = (ts_dem_hot_max + ts_dem_hot_mean)/2
    
   
    ts_dem_hot=ts_dem_hot_mean + Hot_Pixel_Constant * ts_dem_hot_std

    
    print('hot : min= %0.3f (Kelvin)' % ts_dem_hot_min, 'hot : max= %0.3f (Kelvin)' % ts_dem_hot_max, ', sd= %0.3f (Kelvin)' % ts_dem_hot_std, \
           ', mean= %0.3f (Kelvin)' % ts_dem_hot_mean, ', value= %0.3f (Kelvin)' % ts_dem_hot)
    return(ts_dem_hot,hot_pixels)

"""
#------------------------------------------------------------------------------
def Calc_Hot_Pixels(ts_dem,QC_Map, water_mask, NDVI,NDVIhot_low,NDVIhot_high,Hot_Pixel_Constant):

    #Function to calculates the hot pixels based on the surface temperature and NDVI

    for_hot = np.copy(ts_dem)
    for_hot[NDVI <= NDVIhot_low] = np.nan
    for_hot[NDVI >= NDVIhot_high] = np.nan
    for_hot[np.logical_or(water_mask != 0.0, QC_Map != 0.0)] = 0.0
    hot_pixels = np.copy(for_hot)
    hot_pixels[for_hot < 273.0] = np.nan
    ts_dem_hot_max = np.nanmax(hot_pixels)    # Max
    ts_dem_hot_mean = np.nanmean(hot_pixels)  # Mean
    ts_dem_hot_std = np.nanstd(hot_pixels)    # Standard deviation
    #ts_dem_hot = ts_dem_hot_max - 0.25 * ts_dem_hot_std
    #ts_dem_hot = (ts_dem_hot_max + ts_dem_hot_mean)/2  
   
    ts_dem_hot=ts_dem_hot_mean + Hot_Pixel_Constant * ts_dem_hot_std

    
    print('hot : max= %0.3f (Kelvin)' % ts_dem_hot_max, ', sd= %0.3f (Kelvin)' % ts_dem_hot_std, \
           ', mean= %0.3f (Kelvin)' % ts_dem_hot_mean, ', value= %0.3f (Kelvin)' % ts_dem_hot)
    return(ts_dem_hot,hot_pixels)    


#------------------------------------------------------------------------------
def Calc_Hot_Pixels(ts_dem,QC_Map, water_mask, NDVI,NDVIhot_low,NDVIhot_high,Hot_Pixel_Constant):
    
    #Function to calculates the hot pixels based on the surface temperature and NDVI
    
    for_hot = np.copy(ts_dem)
    for_hot[for_hot <= NDVIhot_low] = np.nan
    for_hot[for_hot >= NDVIhot_high] = np.nan
    for_hot[np.logical_or(water_mask != 0.0, QC_Map != 0.0)] = 0.0
    hot_pixels = np.copy(for_hot)
    hot_pixels[for_hot < 273.0] = np.nan
    ts_dem_hot_max = np.nanmax(hot_pixels)    # Max
    ts_dem_hot_mean = np.nanmean(hot_pixels)  # Mean
    ts_dem_hot_std = np.nanstd(hot_pixels)    # Standard deviation
    #ts_dem_hot = ts_dem_hot_max - 0.25 * ts_dem_hot_std
    #ts_dem_hot = (ts_dem_hot_max + ts_dem_hot_mean)/2
    
   
    ts_dem_hot=ts_dem_hot_mean + Hot_Pixel_Constant * ts_dem_hot_std

    
    print('hot : max= %0.3f (Kelvin)' % ts_dem_hot_max, ', sd= %0.3f (Kelvin)' % ts_dem_hot_std, \
           ', mean= %0.3f (Kelvin)' % ts_dem_hot_mean, ', value= %0.3f (Kelvin)' % ts_dem_hot)
    return(ts_dem_hot,hot_pixels)
    
"""
#------------------------------------------------------------------------------    
def Calc_Cold_Pixels(ts_dem,tcoldmin,tcoldmax,water_mask,QC_Map,ts_dem_cold_veg,Cold_Pixel_Constant):
    """
    Function to calculates the the cold pixels based on the surface temperature
    """ 
    for_cold = np.copy(ts_dem)
    for_cold[water_mask != 1.0] = 0.0
    for_cold[QC_Map != 0] = 0.0
    cold_pixels = np.copy(for_cold)
    cold_pixels[for_cold < tcoldmin] = np.nan
    cold_pixels[for_cold > tcoldmax] = np.nan
    # cold_pixels[for_cold < 285.0] = 285.0
    ts_dem_cold_std = np.nanstd(cold_pixels)     # Standard deviation
    ts_dem_cold_min = np.nanmin(cold_pixels)     # Min
    ts_dem_cold_max = np.nanmax(cold_pixels)
    ts_dem_cold_mean = np.nanmean(cold_pixels)   # Mean

    # If average temperature is below zero or nan than use the vegetation cold pixel
    if ts_dem_cold_mean <= 0.0:
        ts_dem_cold = ts_dem_cold_veg
    if np.isnan(ts_dem_cold_mean) == True:
        ts_dem_cold = ts_dem_cold_veg 							
    else:
        ts_dem_cold = ts_dem_cold_mean
	# ts_dem_cold = ts_dem_cold_mean + Cold_Pixel_Constant * ts_dem_cold_std

    if ts_dem_cold > ts_dem_cold_veg:
        ts_dem_cold = ts_dem_cold_veg 
            
    print('cold water: min=%0.3f (Kelvin)' %ts_dem_cold_min , 'max=%0.3f (Kelvin)' %ts_dem_cold_max, ', sd= %0.3f (Kelvin)' % ts_dem_cold_std, \
           ', mean= %0.3f (Kelvin)' % ts_dem_cold_mean, ', value= %0.3f (Kelvin)' % ts_dem_cold) 
    return(ts_dem_cold,cold_pixels,ts_dem_cold_mean)
     
#------------------------------------------------------------------------------
def Calc_Cold_Pixels_Veg(NDVI,NDVI_max,NDVI_std,QC_Map,ts_dem,Image_Type, Cold_Pixel_Constant):
    """
    Function to calculates the the cold pixels based on vegetation
    """   
    cold_pixels_vegetation = np.copy(ts_dem)
    cold_pixels_vegetation[np.logical_or(NDVI <= (NDVI_max-0.1*NDVI_std),QC_Map != 0.0)] = 0.0 #(ORI = 0.1*NDVI_std)
    cold_pixels_vegetation[cold_pixels_vegetation==0.0] = np.nan
    ts_dem_cold_std_veg = np.nanstd(cold_pixels_vegetation)
    ts_dem_cold_min_veg = np.nanmin(cold_pixels_vegetation)
    ts_dem_cold_max_veg = np.nanmax(cold_pixels_vegetation)
    ts_dem_cold_mean_veg = np.nanmean(cold_pixels_vegetation)
    
    if Image_Type == 1:    
            ts_dem_cold_veg = ts_dem_cold_mean_veg + Cold_Pixel_Constant * ts_dem_cold_std_veg
    if Image_Type == 2:    
            ts_dem_cold_veg = ts_dem_cold_mean_veg + Cold_Pixel_Constant * ts_dem_cold_std_veg
    if Image_Type == 3:    
            ts_dem_cold_veg = ts_dem_cold_mean_veg + Cold_Pixel_Constant * ts_dem_cold_std_veg    
            
    print('cold vegetation: min=%0.3f (Kelvin)' %ts_dem_cold_min_veg , 'max=%0.3f (Kelvin)' %ts_dem_cold_max_veg, ',sd= %0.3f (Kelvin)' % ts_dem_cold_std_veg, \
				', mean= %0.3f (Kelvin)' % ts_dem_cold_mean_veg, ', value= %0.3f (Kelvin)' % ts_dem_cold_veg) 
    return(ts_dem_cold_veg)
   
#------------------------------------------------------------------------------   
def Calc_Meteo(Rs_24,eact_24,Temp_24,Surf_albedo,cos_zn,dr,tir_emis,Surface_temp,water_mask,NDVI,Transm_24,SB_const,lw_in_inst,Rs_in_inst):
    """       
    Calculates the instantaneous Ground heat flux and solar radiation.
    """ 
    
    # Net shortwave radiation (W/m2):
    Rns_24 = Rs_24 * (1 - Surf_albedo)


    # Net outgoing longwave radiation (W/m2):
    Rnl_24_FAO = (SB_const * np.power(Temp_24 + 273.15, 4) * (0.34-0.14 *
                  np.power(eact_24, 0.5)) * (1.35 * Transm_24 / 0.8 - 0.35))
                  
    Rnl_24_Slob = 110 * Transm_24            
    print('Mean Daily Net Radiation (Slob) = %0.3f (W/m2)' % np.nanmean(Rnl_24_Slob))    
				
    # Net 24 hrs radiation (W/m2):
    Rn_24_FAO = Rns_24 - Rnl_24_FAO          # FAO equation
    Rn_24_Slob = Rns_24 - Rnl_24_Slob       # Slob equation
    Rn_24 = (Rn_24_FAO + Rn_24_Slob) / 2  # Average
   

    # Instantaneous outgoing longwave radiation:
    lw_out_inst = tir_emis * SB_const * np.power(Surface_temp, 4)
    
    # Instantaneous net radiation
    rn_inst = (Rs_in_inst * (1 - Surf_albedo) + lw_in_inst - lw_out_inst -
               (1 - tir_emis) * lw_in_inst)
    # Instantaneous Soil heat flux
    g_inst = np.where(water_mask != 0.0, 0.4 * rn_inst,
                      ((Surface_temp - 273.15) * (0.0038 + 0.0074 * Surf_albedo) *
                       (1 - 0.978 * np.power(NDVI, 4))) * rn_inst)
    return(Rn_24,rn_inst,g_inst,Rnl_24_FAO)
    
#------------------------------------------------------------------------------    
def Calc_surface_temp(Temp_inst,Landsat_nr,Lmax,Lmin,therm_data,b10_emissivity,k1_c,k2_c,eact_inst,shape_lsc,water_mask_temp,Bands_thermal,Rp,tau_sky,surf_temp_offset,Image_Type):    
    """
    Calculates the surface temperature and create a water mask
    """ 
    
    # Spectral radiance for termal
    if Landsat_nr == 8 or Landsat_nr == 9:
        if Bands_thermal == 1:
            k1 = k1_c[0]
            k2 = k2_c[0]
            L_lambda_b10 = (Lmax[-1] - Lmin[-1]) / (65535-1) * therm_data[:, :, 0] + Lmin[-1]
            
            # Get Temperature
            Temp_TOA = Get_Thermal(L_lambda_b10,Rp,Temp_inst,tau_sky,b10_emissivity,k1,k2) 
                      
        elif Bands_thermal == 2:
            L_lambda_b10 = (Lmax[-2] - Lmin[-2]) / (65535-1) * therm_data[:, :, 0] + Lmin[-2]
            L_lambda_b11 = (Lmax[-1] - Lmin[-1]) / (65535-1) * therm_data[:, :, 1] + Lmin[-1]
    
            # Brightness temperature
            # From Band 10:
            Temp_TOA_10 = (k2_c[0] / np.log(k1_c[0] / L_lambda_b10 + 1.0))
            # From Band 11:
            Temp_TOA_11 = (k2_c[1] / np.log(k1_c[1] / L_lambda_b11 + 1.0))
            # Combined:
            Temp_TOA = (Temp_TOA_10 + 1.378 * (Temp_TOA_10 - Temp_TOA_11) +
                           0.183 * np.power(Temp_TOA_10 - Temp_TOA_11, 2) - 0.268 +
                           (54.30 - 2.238 * eact_inst) * (1 - b10_emissivity))
       
    elif Landsat_nr == 7:
        k1=666.09
        k2=1282.71
        L_lambda_b6 = (Lmax[-1] - Lmin[-1]) / (256-1) * therm_data[:, :, 0] + Lmin[-1]

        # Brightness temperature - From Band 6:
        Temp_TOA = Get_Thermal(L_lambda_b6,Rp,Temp_inst,tau_sky,b10_emissivity,k1,k2) 
        
    elif Landsat_nr == 5:
        k1=607.76
        k2=1260.56
        L_lambda_b6 = ((Lmax[-1] - Lmin[-1]) / (256-1) * therm_data[:, :, 0] +
                       Lmin[-1])
   
       # Brightness temperature - From Band 6:
        Temp_TOA = Get_Thermal(L_lambda_b6,Rp,Temp_inst,tau_sky,b10_emissivity,k1,k2) 
            
    # Surface temperature
    Surface_temp = Temp_TOA
    Surface_temp = Surface_temp.clip(230.0, 360.0)

    # Cloud mask:
    temp_water = np.zeros((shape_lsc[1], shape_lsc[0]))
    temp_water = np.copy(Surface_temp)
    temp_water[water_mask_temp == 0.0] = np.nan
    temp_water_sd = np.nanstd(temp_water)     # Standard deviation
    temp_water_mean = np.nanmean(temp_water)  # Mean
    print('Mean water temperature = ', '%0.3f (Kelvin)' % temp_water_mean)
    print('SD water temperature = ', '%0.3f (Kelvin)' % temp_water_sd)
    cloud_mask = np.zeros((shape_lsc[1], shape_lsc[0]))
    cloud_mask[Surface_temp < np.minimum((temp_water_mean - 1.0 * temp_water_sd -
               surf_temp_offset),290)] = 1.0
                          
    return(Surface_temp,cloud_mask)           


#------------------------------------------------------------------------------
def Get_Thermal(lambda_b10,Rp,Temp_inst,tau_sky,TIR_Emissivity,k1,k2):
    
    # For Landsat 8/9 Collection 2, use simplified approach
    # Step 1: Convert TOA radiance to brightness temperature (without emissivity)
    Temp_brightness = (k2 / np.log(k1 / lambda_b10 + 1.0))
    
    # Step 2: Apply emissivity correction (Artis and Carnahan, 1982)
    # T_surface = T_brightness / ε^(1/4)
    # Simplified: T_surface ≈ T_brightness + (1-ε) * T_brightness / ε
    # Or use the more accurate ASTER TES algorithm variant:
    # T_surface = T_brightness / (1 + (λ * T_brightness / c2) * ln(ε))
    # where λ = 10.9 μm (Band 10 wavelength), c2 = 14388 μm·K
    
    # Using simpler and more stable formula:
    # Just apply emissivity correction to brightness temp
    wavelength = 10.9e-6  # Band 10 wavelength in meters
    c2 = 1.4388e-2  # Second radiation constant (m·K)
    
    # Emissivity correction
    Temp_TOA = Temp_brightness / (1.0 + (wavelength * Temp_brightness / c2) * np.log(TIR_Emissivity))
                       
    return(Temp_TOA)                   
#------------------------------------------------------------------------------
def Calc_vegt_para(NDVI,SAVI,water_mask_temp,shape_lsc):
    """
    Calculates the Fraction of PAR, Thermal infrared emissivity, Nitrogen, Vegetation Cover, LAI, b10_emissivity
    """
    # Fraction of PAR absorbed by the vegetation canopy (FPAR):
    FPAR = -0.161 + 1.257 * NDVI
    FPAR[NDVI < 0.125] = 0.0

    # Termal infrared emissivity
    tir_emis = 1.009 + 0.047 * np.log(NDVI)
    tir_emis[np.logical_or(water_mask_temp == 1.0, water_mask_temp == 2.0)] = 1.0
    tir_emis[np.logical_and(NDVI < 0.125, water_mask_temp == 0.0)] = 0.92

    # Vegetation Index - Regression model from Bagheri et al. (2013)
    VI_NDVI = 38.764 * np.square(NDVI) - 24.605 * NDVI + 5.8103
    VI_SAVI = 6.3707 * np.square(SAVI) - 2.8503 * SAVI + 1.6335
    VI = (VI_NDVI + VI_SAVI) / 2.0  # Average of computed from NDVI and SAVI

    # Nitrogen computation
    Nitrogen = np.copy(VI)
    Nitrogen[VI <= 0.0] = 0.0
    Nitrogen[NDVI <= 0.0] = 0.0
                  
    # Vegetation cover:
    vegt_cover = 1 - np.power((0.8 - NDVI)/(0.8 - 0.125), 0.7)
    vegt_cover[NDVI < 0.125] = 0.0
    vegt_cover[NDVI > 0.8] = 0.99

    # Leaf Area Index (LAI)
    LAI_1 = np.log(-(vegt_cover - 1)) / -0.45
    LAI_1[LAI_1 > 8] = 8.0
    LAI_2 = (9.519 * np.power(NDVI, 3) + 0.104 * np.power(NDVI, 2) +
             1.236 * NDVI - 0.257)
    LAI_3 = 11.0 * np.power(SAVI, 3)
    LAI_3[SAVI >= 0.817] = 6.0
    LAI_4 = -np.log((0.69 - SAVI) / 0.59) / 0.91  # For South. Idaho, empirical
    LAI_4[SAVI < 0.0] = 0.0
    LAI_4[SAVI >= 0.689] = 6.0

    LAI = (LAI_1 + LAI_2 + LAI_3 + LAI_4) / 4.0  # Average LAI
    LAI[LAI < 0.001] = 0.001

    b10_emissivity = np.zeros((shape_lsc[1], shape_lsc[0]))
    b10_emissivity = np.where(LAI <= 3.0, 0.95 + 0.01 * LAI, 0.98)
    b10_emissivity[water_mask_temp != 0.0] = 1.0
                  
    return(FPAR,tir_emis,Nitrogen,vegt_cover,LAI,b10_emissivity)
    
#------------------------------------------------------------------------------    
def Water_Mask(shape_lsc,Reflect):
    """
    Calculates the water and cloud mask
    """
    mask = np.zeros((shape_lsc[1], shape_lsc[0]))
    mask[np.logical_and(Reflect[:, :, 3] < Reflect[:, :, 2],
                        Reflect[:, :, 4] < Reflect[:, :, 1])] = 1.0
    water_mask_temp = np.copy(mask)
    
    return(water_mask_temp)

#------------------------------------------------------------------------------   
def Calc_albedo(Reflect,path_radiance,Apparent_atmosf_transm):
    """
    This function calculates and returns the Surface albedo, NDVI, and SAVI by using the refectance from the landsat image.
    """ 
    # Surface albedo:
    Surf_albedo = (0.254 * Reflect[:, :, 0] + 0.149 * Reflect[:, :, 1] +
                   0.147 * Reflect[:, :, 2] + 0.311 * Reflect[:, :, 3] +
                   0.103 * Reflect[:, :, 4] + 0.036 * Reflect[:, :, 5] -
                   path_radiance) / np.power(Apparent_atmosf_transm, 2)

    # Better tsw instead of Apparent_atmosf_transm ??
    Surf_albedo = Surf_albedo.clip(0.0, 0.6)

    return(Surf_albedo)
#------------------------------------------------------------------------------  
def Calc_NDVI(Reflect):
    """
    This function calculates and returns the Surface albedo, NDVI, and SAVI by using the refectance from the landsat image.
    """ 
    # Computation of Normalized Difference Vegetation Index (NDVI)
    NDVI = ((Reflect[:, :, 3] - Reflect[:, :, 2]) /
            (Reflect[:, :, 3] + Reflect[:, :, 2]))

    return(NDVI)
				
#------------------------------------------------------------------------------   
def Calc_SAVI(Reflect,L):
    """
    This function calculates and returns the Surface albedo, NDVI, and SAVI by using the refectance from the landsat image.
    """ 
    # Computation of Soil Adjusted Vegetation Index (SAVI)
    SAVI = (1 + L) * ((Reflect[:, :, 3] - Reflect[:, :, 2]) /
                      (L + Reflect[:, :, 3] + Reflect[:, :, 2]))
    return(SAVI)				
#------------------------------------------------------------------------------  
def CalculateSnowWaterMask(NDVI,shape_lsc,water_mask_temp,Surface_temp):
   '''
   Devides the temporaly water mask into a snow and water mask by using the surface temperature
   '''
   NDVI_nan=np.copy(NDVI)
   NDVI_nan[NDVI==0]=np.nan
   NDVI_nan=np.float32(NDVI_nan)
   NDVI_std=np.nanstd(NDVI_nan)
   NDVI_max=np.nanmax(NDVI_nan)
   NDVI_treshold_cold_pixels=NDVI_max-0.1*NDVI_std
   print('NDVI treshold for cold pixels = ', '%0.3f' % NDVI_treshold_cold_pixels)
   
   # Safety check: if threshold is NaN or no pixels meet criteria, use fallback
   cold_pixels_mask = NDVI > NDVI_treshold_cold_pixels
   if np.isnan(NDVI_treshold_cold_pixels) or not np.any(cold_pixels_mask):
       # Fallback: use top 10% of NDVI values
       valid_ndvi = NDVI[~np.isnan(NDVI)]
       if len(valid_ndvi) > 0:
           NDVI_treshold_cold_pixels = np.percentile(valid_ndvi, 90)
           cold_pixels_mask = NDVI > NDVI_treshold_cold_pixels
       else:
           # Last resort: use all valid surface temp values
           ts_moist_veg_min = np.nanmin(Surface_temp)
           cold_pixels_mask = None
   
   if cold_pixels_mask is not None and np.any(cold_pixels_mask):
       ts_moist_veg_min = np.nanmin(Surface_temp[cold_pixels_mask])
   else:
       ts_moist_veg_min = np.nanmin(Surface_temp)
   
   # calculate new water mask 
   mask=np.zeros((shape_lsc[1], shape_lsc[0]))
   mask[np.logical_and(np.logical_and(water_mask_temp==1, Surface_temp <= 275),NDVI>=0.3)]=1   
   snow_mask=np.copy(mask)
   
   # calculate new water mask 
   mask=np.zeros((shape_lsc[1], shape_lsc[0]))
   mask[np.logical_and(water_mask_temp==1, Surface_temp > 273)]=1   
   water_mask=np.copy(mask)
   
   return(snow_mask,water_mask,ts_moist_veg_min, NDVI_max, NDVI_std)
       
    
#------------------------------------------------------------------------------    
def Landsat_Reflect(Bands,input_folder,Name_Landsat_Image,output_folder,shape_lsc,ClipLandsat,Lmax,Lmin,ESUN_L5,ESUN_L7,ESUN_L8,cos_zn,dr,Landsat_nr, proyDEM_fileName):
    """
    This function calculates and returns the reflectance and spectral radiation from the landsat image.
    """ 
    
    Spec_Rad = np.zeros((shape_lsc[1], shape_lsc[0], 7))
    Reflect = np.zeros((shape_lsc[1], shape_lsc[0], 7))
    for band in Bands[:-(len(Bands)-6)]:
        # Open original Landsat image for the band number
        src_FileName = os.path.join(input_folder, '%s_B%1d.TIF'
                                    % (Name_Landsat_Image, band))

        ls_data=Open_landsat(src_FileName, proyDEM_fileName)
        ls_data = ls_data*ClipLandsat
        # stats = band_data.GetStatistics(0, 1)

        index = np.where(Bands[:-(len(Bands)-6)] == band)[0][0]
        if Landsat_nr == 8 or Landsat_nr == 9:
            # Spectral radiance for each band:
            L_lambda = Landsat_L_lambda(Lmin, Lmax, ls_data, index, Landsat_nr)
            # Reflectivity for each band:
            rho_lambda = Landsat_rho_lambda(L_lambda, ESUN_L8, index, cos_zn, dr)
        elif Landsat_nr == 7:
            # Spectral radiance for each band:
            L_lambda=Landsat_L_lambda(Lmin, Lmax, ls_data, index, Landsat_nr)
            # Reflectivity for each band:
            rho_lambda = Landsat_rho_lambda(L_lambda, ESUN_L7, index, cos_zn, dr)
        elif Landsat_nr == 5:
            # Spectral radiance for each band:
            L_lambda=Landsat_L_lambda(Lmin, Lmax, ls_data, index, Landsat_nr)
            # Reflectivity for each band:
            rho_lambda =Landsat_rho_lambda(L_lambda, ESUN_L5, index, cos_zn, dr)
        else:
            print('Landsat image not supported, use Landsat 5, 7 or 8')

        Spec_Rad[:, :, index] = L_lambda
        Reflect[:, :, index] = rho_lambda
    Reflect = Reflect.clip(0.0, 1.0)
    return(Reflect,Spec_Rad)
     

#------------------------------------------------------------------------------    
def Landsat_L_lambda(Lmin,Lmax,ls_data,index,Landsat_nr):
    """
    Calculates the lambda from landsat
    """
    if Landsat_nr==8 or Landsat_nr == 9:
        L_lambda = ((Lmax[index] - Lmin[index]) / (65535 - 1) * ls_data + Lmin[index]) 
    elif Landsat_nr == 5 or Landsat_nr ==7:
        L_lambda = (Lmax[index] - Lmin[index]) / 255 * ls_data + Lmin[index]
    return(L_lambda)
    
    
#------------------------------------------------------------------------------   
def Landsat_rho_lambda(L_lambda,ESUN,index,cos_zn,dr):
    """
    Calculates the lambda from landsat
    """
    rho_lambda = np.pi * L_lambda / (ESUN[index] * cos_zn * dr)
    return(rho_lambda)
    
    
#------------------------------------------------------------------------------
def Landsat_therm_data(Bands,input_folder,Name_Landsat_Image,output_folder, shape_lsc,ClipLandsat, proyDEM_fileName):          
    """
    This function calculates and returns the thermal data from the landsat image.
    """                             
    therm_data = np.zeros((shape_lsc[1], shape_lsc[0], len(Bands)-6))
    for band in Bands[-(len(Bands)-6):]:
        # Open original Landsat image for the band number
        src_FileName = os.path.join(input_folder, '%s_B%1d.TIF'
                                    % (Name_Landsat_Image, band))
        if not os.path.exists(src_FileName):
             src_FileName = os.path.join(input_folder, '%s_B%1d_VCID_2.TIF'
                                    % (Name_Landsat_Image, band))		    																																
																																				
        ls_data=Open_landsat(src_FileName, proyDEM_fileName) 																																	
        ls_data = ls_data*ClipLandsat
        index = np.where(Bands[:] == band)[0][0] - 6
        therm_data[:, :, index] = ls_data
								
    return(therm_data)
   
#------------------------------------------------------------------------------   
def Open_landsat(src_FileName, proyDEM_fileName):
    """
    This function opens a landsat image and returns the data array of a specific landsat band.
    """                           
    # crop band to the DEM extent
    ls, ulx, uly, lrx, lry, epsg_to = reproject_dataset_example(src_FileName, proyDEM_fileName)											
    
    # Open the cropped Landsat image for the band number
    ls_data = ls.GetRasterBand(1).ReadAsArray()
    return(ls_data) 
  
#------------------------------------------------------------------------------
def Get_Extend_Landsat(src_FileName):
    """
    This function gets the extend of the landsat image
    """
    ls = gdal.Open(src_FileName)       # Open Landsat image
    print('Original LANDSAT Image - ')
    geo_t_ls = ls.GetGeoTransform()    # Get the Geotransform vector
    x_size_ls = ls.RasterXSize         # Raster xsize - Columns
    y_size_ls = ls.RasterYSize         # Raster ysize - Rows
    print('  Size :', x_size_ls, y_size_ls)
    (ulx, uly) = geo_t_ls[0], geo_t_ls[3]
    (lrx, lry) = (geo_t_ls[0] + geo_t_ls[1] * x_size_ls,
                  geo_t_ls[3] + geo_t_ls[5] * y_size_ls)
    band_data = ls.GetRasterBand(1)
    
    return(ls,band_data,ulx,uly,lrx,lry,x_size_ls,y_size_ls)
    
#------------------------------------------------------------------------------
def Calc_Ra_Mountain(lon,DOY,hour,minutes,lon_proy,lat_proy,slope,aspect):    
    """
    Calculates the extraterrestiral solar radiation by using the date, slope and aspect.
    """
    
    # Constants
    deg2rad = np.pi / 180.0  # Factor to transform from degree to rad
    Min_cos_zn = 0.1  # Min value for cos zenith angle
    Max_cos_zn = 1.0  # Max value for cos zenith angle
    Gsc = 1367        # Solar constant (W / m2)
    try:
        Loc_time = float(hour) + float(minutes)/60  # Local time (hours)
    except:
        Loc_time = np.float64(hour) + np.float64(minutes)/60  # Local time (hours)
    # Rounded difference of the local time from Greenwich (GMT) (hours):
    offset_GTM = round(np.sign(lon[int(lon.shape[0])//2, int(lon.shape[1])//2]) * lon[int(lon.shape[0])//2,int(lon.shape[1])//2] * 24 // 360)
                       
    print('  Local time: ', '%0.3f' % np.nanmean(Loc_time))
    print('  Difference of local time (LT) from Greenwich (GMT): ', offset_GTM)

    # 1. Calculation of extraterrestrial solar radiation for slope and aspect
    # Computation of Hour Angle (HRA = w)
    B = 360./365 * (DOY-81)           # (degrees)
    # Computation of cos(theta), where theta is the solar incidence angle
    # relative to the normal to the land surface
    delta=np.arcsin(np.sin(23.45*deg2rad)*np.sin(np.deg2rad(B))) # Declination angle (radians)
    phi = lat_proy * deg2rad                                     # latitude of the pixel (radians)
    s = slope * deg2rad                                          # Surface slope (radians)
    gamma = (aspect-180) * deg2rad                               # Surface aspect angle (radians)
    w=w_time(Loc_time, lon_proy, DOY)                            # Hour angle (radians)
    a,b,c = Constants(delta,s,gamma,phi)
    cos_zn= AngleSlope(a,b,c,w)
    cos_zn = cos_zn.clip(Min_cos_zn, Max_cos_zn)
    
    print('Average Cos Zenith Angle: ', '%0.3f (Radians)' % np.nanmean(cos_zn))

    dr = 1 + 0.033 * cos(DOY*2*pi/365)  # Inverse relative distance Earth-Sun
    # Instant. extraterrestrial solar radiation (W/m2), Allen et al.(2006):
    Ra_inst = Gsc * cos_zn * dr              

    # 24-hours extraterrestrial radiation
    # 1.) determine if there are one or two periods of sun
    # 2.) calculate the 24-hours extraterrestrial radiation if there are two periods of sun
    # 3.) calculate the 24-hours extraterrestrial radiation if there is one period of sun
    
    #1.) determine amount of sun periods
    Ra_24 = np.zeros(np.shape(lat_proy))*np.nan
    constant=Gsc*dr/(2*np.pi)
    TwoPeriod= TwoPeriods(delta,s,phi)  # all input in radians
    
    #2.) calculate the 24-hours extraterrestrial radiation (2 periods)
    ID = np.where(np.ravel(TwoPeriod==True))
    Ra_24.flat[ID]=TwoPeriodSun(constant,delta,s.flat[ID],gamma.flat[ID],phi.flat[ID])
    
    #3.) calculate the 24-hours extraterrestrial radiation (1 period)
    ID = np.where(np.ravel(TwoPeriod==False))
    Ra_24.flat[ID]=OnePeriodSun(constant,delta,s.flat[ID],gamma.flat[ID],phi.flat[ID])
        
    # Horizontal surface
    ws = np.arccos(-np.tan(delta) * np.tan(phi))  # Sunrise/sunset time angle
    
    # Extraterrestial radiation for a horizontal surface for 24-h period:
    Ra_hor_24 = (Gsc * dr / np.pi * (np.sin(delta) * np.sin(phi) * ws + np.cos(delta) * np.cos(phi) * np.sin(ws)))
    # cos_theta_flat = (np.sin(delta) * np.sin(phi) + np.cos(delta) * np.cos(phi) * np.cos(w))

    # Mountain radiation
    Ra_mountain_24 = np.where(Ra_24 > Min_cos_zn * Ra_hor_24, Ra_24 / np.cos(s),
                           Ra_hor_24)
    Ra_mountain_24[Ra_mountain_24 > 600.0] = 600.0
                  
    return(Ra_mountain_24,Ra_inst,cos_zn,dr,phi,delta)
    
#------------------------------------------------------------------------------    
def OnePeriodSun(constant,delta,s,gamma,phi):
    '''
    Based on Richard G. Allen 2006
    Calculate the 24-hours extraterrestrial radiation when there is one sun period
    '''
    sunrise,sunset = SunHours(delta,s,gamma,phi)    
    Vals=IntegrateSlope(constant,sunrise,sunset,delta,s,gamma,phi)
    
    return(Vals)
    
#------------------------------------------------------------------------------   
def TwoPeriodSun(constant,delta,s,gamma,phi):  
    '''
    Based on Richard G. Allen 2006
    Calculate the 24-hours extraterrestrial radiation when there are two sun period
    '''
    A1, A2 = SunHours(delta,s,gamma,phi)
    a,b,c = Constants(delta,s,gamma,phi)
    riseSlope, setSlope = BoundsSlope(a,b,c)
    B1 = np.maximum(riseSlope,setSlope)
    B2 = np.minimum(riseSlope,setSlope)
    Angle_B1 = AngleSlope(a,b,c,B1)
    Angle_B2 = AngleSlope(a,b,c,B2)
   
    B1[abs(Angle_B1) > 0.001] = np.pi - B1[abs(Angle_B1) > 0.001]  
    B2[abs(Angle_B2) > 0.001] = -np.pi - B2[abs(Angle_B2) > 0.001]    

    # Check if two periods really exist
    ID = np.ravel_multi_index(np.where(np.logical_and(B2 >= A1, B1 >= A2) == True),a.shape)
    Val = IntegrateSlope(constant,B2.flat[ID],B1.flat[ID],delta,s.flat[ID],gamma.flat[ID],phi.flat[ID])
    ID = ID[Val < 0]

    # Finally calculate resulting values
    Vals = np.zeros(B1.shape)

    Vals.flat[ID] = (IntegrateSlope(constant,A1.flat[ID],B2.flat[ID],delta,s.flat[ID],gamma.flat[ID],phi.flat[ID])  + 
                   IntegrateSlope(constant,B1.flat[ID],A2.flat[ID],delta,s.flat[ID],gamma.flat[ID],phi.flat[ID]))
    ID = np.ravel_multi_index(np.where(Vals == 0),a.shape)   
    Vals.flat[ID] = IntegrateSlope(constant,A1.flat[ID],A2.flat[ID],delta,s.flat[ID],gamma.flat[ID],phi.flat[ID])
    
    return(Vals)
    
#------------------------------------------------------------------------------       
def IntegrateSlope(constant,sunrise,sunset,delta,s,gamma,phi):
    '''
    Based on Richard G. Allen 2006 equation 5
    Calculate the 24 hours extraterrestrial radiation
    '''
    # correct the sunset and sunrise angels for days that have no sunset or no sunrise 
    integral=np.zeros(s.shape)
    
    # No sunset - where abs(delta+phi) > pi/2
    NoSunset = (np.abs(delta + phi)) > (np.pi/2)
    ID_NoSunset = np.where(np.ravel(NoSunset))
    if len(ID_NoSunset[0]) > 0:
        sunset1=np.pi
        sunrise1=-np.pi
        integral.flat[ID_NoSunset] = constant * (np.sin(delta)*np.sin(phi.flat[ID_NoSunset])*np.cos(s.flat[ID_NoSunset])*(sunset1-sunrise1) 
            - np.sin(delta)*np.cos(phi.flat[ID_NoSunset])*np.sin(s.flat[ID_NoSunset])*np.cos(gamma.flat[ID_NoSunset])*(sunset1-sunrise1)
            + np.cos(delta)*np.cos(phi.flat[ID_NoSunset])*np.cos(s.flat[ID_NoSunset])*(np.sin(sunset1)-np.sin(sunrise1))
            + np.cos(delta)*np.sin(phi.flat[ID_NoSunset])*np.sin(s.flat[ID_NoSunset])*np.cos(gamma.flat[ID_NoSunset])*(np.sin(sunset1)-np.sin(sunrise1))
            - np.cos(delta)*np.sin(s.flat[ID_NoSunset])*np.sin(gamma.flat[ID_NoSunset])*(np.cos(sunset1)-np.cos(sunrise1)))
   
    # No sunrise - where abs(delta-phi) > pi/2
    NoSunrise = (np.abs(delta - phi)) > (np.pi/2)
    ID_NoSunrise = np.where(np.ravel(NoSunrise))
    if len(ID_NoSunrise[0]) > 0:
        integral.flat[ID_NoSunrise]=constant * (np.sin(delta)*np.sin(phi.flat[ID_NoSunrise])*np.cos(s.flat[ID_NoSunrise])*(0) 
            - np.sin(delta)*np.cos(phi.flat[ID_NoSunrise])*np.sin(s.flat[ID_NoSunrise])*np.cos(gamma.flat[ID_NoSunrise])*(0)
            + np.cos(delta)*np.cos(phi.flat[ID_NoSunrise])*np.cos(s.flat[ID_NoSunrise])*(np.sin(0)-np.sin(0))
            + np.cos(delta)*np.sin(phi.flat[ID_NoSunrise])*np.sin(s.flat[ID_NoSunrise])*np.cos(gamma.flat[ID_NoSunrise])*(np.sin(0)-np.sin(0))
            - np.cos(delta)*np.sin(s.flat[ID_NoSunrise])*np.sin(gamma.flat[ID_NoSunrise])*(np.cos(0)-np.cos(0)))
        
    # Normal case - where both sunrise and sunset occur
    SunOrNoSun = np.logical_or(NoSunset, NoSunrise)
    ID = np.where(np.ravel(SunOrNoSun==False))
    integral.flat[ID] = constant * (np.sin(delta)*np.sin(phi)*np.cos(s)*(sunset-sunrise) 
            - np.sin(delta)*np.cos(phi)*np.sin(s)*np.cos(gamma)*(sunset-sunrise)
            + np.cos(delta)*np.cos(phi)*np.cos(s)*(np.sin(sunset)-np.sin(sunrise))
            + np.cos(delta)*np.sin(phi)*np.sin(s)*np.cos(gamma)*(np.sin(sunset)-np.sin(sunrise))
            - np.cos(delta)*np.sin(s)*np.sin(gamma)*(np.cos(sunset)-np.cos(sunrise)))
    
    return(integral)     

#------------------------------------------------------------------------------    
def TwoPeriods(delta,s,phi):
    '''
    Based on Richard G. Allen 2006
    Create a boolean map with True values for places with two sunsets
    '''
    TwoPeriods = (np.sin(s) > np.ones(s.shape)*np.sin(phi)*np.sin(delta)+np.cos(phi)*np.cos(delta))
    
    return(TwoPeriods)

#------------------------------------------------------------------------------
def SunHours(delta,slope,slopedir,lat):
    # Define sun hours in case of one sunlight period
    
    a,b,c = Constants(delta,slope,slopedir,lat)
    riseSlope, setSlope = BoundsSlope(a,b,c)  
    bound = BoundsHorizontal(delta,lat)  

    Calculated = np.zeros(slope.shape, dtype = bool)    
    RiseFinal = np.zeros(slope.shape)    
    SetFinal = np.zeros(slope.shape)
    
    # First check sunrise is not nan
    # This means that their is either no sunrise (whole day night) or no sunset (whole day light)
    # For whole day light, use the horizontal sunrise and whole day night a zero..
    Angle4 = AngleSlope(a,b,c,-bound)    
    RiseFinal[np.logical_and(np.isnan(riseSlope),Angle4 >= 0)] = -bound[np.logical_and(np.isnan(riseSlope),Angle4 >= 0)]
    Calculated[np.isnan(riseSlope)] = True 
    
    # Step 1 > 4    
    Angle1 = AngleSlope(a,b,c,riseSlope)
    Angle2 = AngleSlope(a,b,c,-bound)    
    
    ID = np.ravel_multi_index(np.where(np.logical_and(np.logical_and(Angle2 < Angle1+0.001 ,Angle1 < 0.001),Calculated == False) == True),a.shape)
    RiseFinal.flat[ID] = riseSlope.flat[ID]
    Calculated.flat[ID] = True
    # step 5 > 7
    Angle3 = AngleSlope(a,b,c,-np.pi - riseSlope)
    
    ID = np.ravel_multi_index(np.where(np.logical_and(np.logical_and(-bound<(-np.pi-riseSlope),Angle3 <= 0.001),Calculated == False) == True),a.shape) 
    RiseFinal.flat[ID] = -np.pi -riseSlope.flat[ID]
    Calculated.flat[ID] = True
    
    # For all other values we use the horizontal sunset if it is positive, otherwise keep a zero   
    RiseFinal[Calculated == False] = -bound[Calculated == False] 
    
    # Then check sunset is not nan or < 0 
    Calculated = np.zeros(slope.shape, dtype = bool)     
    
    Angle4 = AngleSlope(a,b,c,bound)    
    SetFinal[np.logical_and(np.isnan(setSlope),Angle4 >= 0)] = bound[np.logical_and(np.isnan(setSlope),Angle4 >= 0)]
    Calculated[np.isnan(setSlope)] = True     
    
    # Step 1 > 4    
    Angle1 = AngleSlope(a,b,c,setSlope)
    Angle2 = AngleSlope(a,b,c,bound)    
    
    ID = np.ravel_multi_index(np.where(np.logical_and(np.logical_and(Angle2 < Angle1+0.001,Angle1 < 0.001),Calculated == False) == True),a.shape)
    SetFinal.flat[ID] = setSlope.flat[ID]
    Calculated.flat[ID] = True
    # step 5 > 7
    Angle3 = AngleSlope(a,b,c,np.pi - setSlope)
    
    ID = np.ravel_multi_index(np.where(np.logical_and(np.logical_and(bound>(np.pi-setSlope),Angle3 <= 0.001),Calculated == False) == True),a.shape) 
    SetFinal.flat[ID] = np.pi - setSlope.flat[ID]
    Calculated.flat[ID] = True
    
    # For all other values we use the horizontal sunset if it is positive, otherwise keep a zero   
    SetFinal[Calculated == False] = bound[Calculated == False]   
    
    #    Angle4 = AngleSlope(a,b,c,bound)    
    #    SetFinal[np.logical_and(Calculated == False,Angle4 >= 0)] = bound[np.logical_and(Calculated == False,Angle4 >= 0)]

    # If Sunrise is after Sunset there is no sunlight during the day
    SetFinal[SetFinal <= RiseFinal] = 0
    RiseFinal[SetFinal <= RiseFinal] = 0
    
    return(RiseFinal,SetFinal)

#------------------------------------------------------------------------------    
def Constants(delta,s,gamma,phi):
    '''
    Based on Richard G. Allen 2006 equation 11
    determines constants for calculating the exterrestial solar radiation
    '''
    a = np.sin(delta)*np.cos(phi)*np.sin(s)*np.cos(gamma) - np.sin(delta)*np.sin(phi)*np.cos(s)
    b = np.cos(delta)*np.cos(phi)*np.cos(s) + np.cos(delta)*np.sin(phi)*np.sin(s)*np.cos(gamma)
    c = np.cos(delta)*np.sin(s)*np.sin(gamma)
    
    return(a,b,c)

#------------------------------------------------------------------------------
def BoundsSlope(a,b,c):
    '''
    Based on Richard G. Allen 2006 equation 13
    This function calculates candidate values for sunrise and sunset hour angles
    '''
    Div = (b**2+c**2)   
    Div[Div <= 0] = 0.00001
    sinB = (a*c + b*np.sqrt(b**2+c**2-a**2)) / Div
    sinA = (a*c - b*np.sqrt(b**2+c**2-a**2)) / Div

    sinB[sinB < -1] = -1; sinB[sinB > 1] = 1    # Limits see appendix A.2.i
    sinA[sinA < -1] = -1; sinA[sinA > 1] = 1    # Limits see appendix A.2.i

    sunrise = np.arcsin(sinA)
    sunset = np.arcsin(sinB)
    
    return(sunrise,sunset)
    
#------------------------------------------------------------------------------   
def BoundsHorizontal(delta,phi):
    ''''
    Based on Richard G. Allen 2006
    This function calculates sunrise hours based on earth inclination and latitude
    If there is no sunset or sunrise hours the values are either set to 0 (polar night) or pi (polar day)    
    '''
    bound = np.arccos(-np.tan(delta)*np.tan(phi))
    bound[abs(delta+phi) > np.pi/2] = np.pi
    bound[abs(delta-phi) > np.pi/2] = 0
          
    return(bound)

#------------------------------------------------------------------------------
def AngleSlope(a,b,c,w):
    '''
    Based on Richard G. Allen 2006
    Calculate the cos zenith angle by using the hour angle and constants
    '''
    angle = -a + b*np.cos(w) + c*np.sin(w)
    
    return(angle)    

#------------------------------------------------------------------------------
def Calc_Gradient(dataset,pixel_spacing):
    """
    This function calculates the slope and aspect of a DEM map.
    """
    # constants
    deg2rad = np.pi / 180.0  # Factor to transform from degree to rad
    rad2deg = 180.0 / np.pi  # Factor to transform from rad to degree
    
    # Calculate slope		
    x, y = np.gradient(dataset)
    slope = np.arctan(np.sqrt(np.square(x/pixel_spacing) + np.square(y/pixel_spacing))) * rad2deg
    
    # calculate aspect                  
    aspect = np.arctan2(y/pixel_spacing, -x/pixel_spacing) * rad2deg
    aspect = 180 + aspect

    return(deg2rad,rad2deg,slope,aspect)

#------------------------------------------------------------------------------
def DEM_lat_lon(DEM_fileName,output_folder):
    """
    This function retrieves information about the latitude and longitude of the
    DEM map. 
    
    """
    # name for output
    lat_fileName = os.path.join(output_folder, 'Output_radiation_balance','latitude.tif')
    lon_fileName = os.path.join(output_folder, 'Output_radiation_balance','longitude.tif')
                                
    g = gdal.Open(DEM_fileName)     # Open DEM
    geo_t = g.GetGeoTransform()     # Get the Geotransform vector:
    x_size = g.RasterXSize          # Raster xsize - Columns
    y_size = g.RasterYSize          # Raster ysize - Rows
    
    # create a longitude and a latitude array 
    lon = np.zeros((y_size, x_size))
    lat = np.zeros((y_size, x_size))
    for col in np.arange(x_size):
        lon[:, col] = geo_t[0] + col * geo_t[1] + geo_t[1]/2
        # ULx + col*(E-W pixel spacing) + E-W pixel spacing
    for row in np.arange(y_size):
        lat[row, :] = geo_t[3] + row * geo_t[5] + geo_t[5]/2
        # ULy + row*(N-S pixel spacing) + N-S pixel spacing,
        # negative as we will be counting from the UL corner
    
    # Define shape of the raster    
    shape = [x_size, y_size]
    
    # Save lat and lon files in geo- coordinates
    save_GeoTiff_proy(g, lat, lat_fileName, shape, nband=1)
    save_GeoTiff_proy(g, lon, lon_fileName, shape, nband=1)
    
    return(lat,lon,lat_fileName,lon_fileName)

#------------------------------------------------------------------------------
def reproject_dataset(dataset, pixel_spacing, UTM_Zone):
    """
    A sample function to reproject and resample a GDAL dataset from within
    Python. The idea here is to reproject from one system to another, as well
    as to change the pixel size. The procedure is slightly long-winded, but
    goes like this:

    1. Set up the two Spatial Reference systems.
    2. Open the original dataset, and get the geotransform
    3. Calculate bounds of new geotransform by projecting the UL corners
    4. Calculate the number of pixels with the new projection & spacing
    5. Create an in-memory raster dataset
    6. Perform the projection
    """

    # 1) Open the dataset
    g = gdal.Open(dataset)
    if g is None:
        print('input folder does not exist')

     # Define the EPSG code...
    EPSG_code = '326%02d' % UTM_Zone
    epsg_to = int(EPSG_code)

    # 2) Define the UK OSNG, see <http://spatialreference.org/ref/epsg/27700/>
    try:
        proj = g.GetProjection()
        Proj_in=proj.split('EPSG","')
        epsg_from=int((str(Proj_in[-1]).split(']')[0])[0:-1])		  
    except:
        epsg_from = int(4326)    # Get the Geotransform vector:
    geo_t = g.GetGeoTransform()
    
    # Vector components:
    # 0- The Upper Left easting coordinate (i.e., horizontal)
    # 1- The E-W pixel spacing
    # 2- The rotation (0 degrees if image is "North Up")
    # 3- The Upper left northing coordinate (i.e., vertical)
    # 4- The rotation (0 degrees)
    # 5- The N-S pixel spacing, negative as it is counted from the UL corner
    x_size = g.RasterXSize  # Raster xsize
    y_size = g.RasterYSize  # Raster ysize

    epsg_to = int(epsg_to)

    # 2) Define the UK OSNG, see <http://spatialreference.org/ref/epsg/27700/>
    osng = osr.SpatialReference()
    osng.ImportFromEPSG(epsg_to)
    wgs84 = osr.SpatialReference()
    wgs84.ImportFromEPSG(epsg_from)

    inProj = Proj(init='epsg:%d' %epsg_from)
    outProj = Proj(init='epsg:%d' %epsg_to)

    nrow_skip = round((0.07*y_size)/2)
    ncol_skip = round((0.04*x_size)/2)
				
    # Up to here, all  the projection have been defined, as well as a
    # transformation from the from to the to
    ulx, uly = transform(inProj,outProj,geo_t[0], geo_t[3] + nrow_skip * geo_t[5])
    lrx, lry = transform(inProj,outProj,geo_t[0] + geo_t[1] * (x_size-ncol_skip),
                                        geo_t[3] + geo_t[5] * (y_size-nrow_skip))

    # See how using 27700 and WGS84 introduces a z-value!
    # Now, we create an in-memory raster
    mem_drv = gdal.GetDriverByName('MEM')

    # The size of the raster is given the new projection and pixel spacing
    # Using the values we calculated above. Also, setting it to store one band
    # and to use Float32 data type.
    col = int((lrx - ulx)/pixel_spacing)
    rows = int((uly - lry)/pixel_spacing)

    # Re-define lr coordinates based on whole number or rows and columns
    (lrx, lry) = (ulx + col * pixel_spacing, uly -
                  rows * pixel_spacing)
																		
    dest = mem_drv.Create('', col, rows, 1, gdal.GDT_Float32)
    
    if dest is None:
        print('input folder to large for memory, clip input map')
     
   # Calculate the new geotransform
    new_geo = (ulx, pixel_spacing, geo_t[2], uly,
               geo_t[4], - pixel_spacing)
    
    # Set the geotransform
    dest.SetGeoTransform(new_geo)
    dest.SetProjection(osng.ExportToWkt())
      
    # Perform the projection/resampling
    gdal.ReprojectImage(g, dest, wgs84.ExportToWkt(), osng.ExportToWkt(),gdal.GRA_Bilinear)						

    return dest, ulx, lry, lrx, uly, epsg_to
#------------------------------------------------------------------------------
def reproject_dataset_example(dataset, dataset_example, method = 1):
   
    # open example dataset 
    g_ex = gdal.Open(dataset_example)
    try:
        proj = g_ex.GetProjection()
        Proj=proj.split('EPSG","')
        epsg_to=int((str(Proj[-1]).split(']')[0])[0:-1])		
    except:
        epsg_to = int(4326)       
      
    Y_raster_size = g_ex.RasterYSize				
    X_raster_size = g_ex.RasterXSize
				
    Geo = g_ex.GetGeoTransform()	
    ulx = Geo[0]
    uly = Geo[3]
    lrx = ulx + X_raster_size * Geo[1]				
    lry = uly + Y_raster_size * Geo[5]	
 
    # open dataset that must be transformed    
    g_in = gdal.Open(dataset)
    try:
        proj = g_in.GetProjection()
        Proj=proj.split('EPSG","')
        epsg_from=int((str(Proj[-1]).split(']')[0])[0:-1])		   
    except:
        epsg_from = int(4326)

    # Set the EPSG codes
    osng = osr.SpatialReference()
    osng.ImportFromEPSG(epsg_to)
    wgs84 = osr.SpatialReference()
    wgs84.ImportFromEPSG(epsg_from)

    # Create new raster			
    mem_drv = gdal.GetDriverByName('MEM')
    dest1 = mem_drv.Create('', X_raster_size, Y_raster_size, 1, gdal.GDT_Float32)
    dest1.SetGeoTransform(Geo)
    dest1.SetProjection(osng.ExportToWkt())
    
    # Perform the projection/resampling
    if method == 1:
        gdal.ReprojectImage(g_in, dest1, wgs84.ExportToWkt(), osng.ExportToWkt(), gdal.GRA_NearestNeighbour)
    if method == 2:
        gdal.ReprojectImage(g_in, dest1, wgs84.ExportToWkt(), osng.ExportToWkt(), gdal.GRA_Average)

    return(dest1, ulx, lry, lrx, uly, epsg_to)			

#------------------------------------------------------------------------------
def save_GeoTiff_proy(src_dataset, dst_dataset_array, dst_fileName, shape_lsc, nband):
    """
    This function saves an array dataset in GeoTiff, using the parameters
    from the source dataset, in projected coordinates

    """
    dst_dataset_array	= np.float64(dst_dataset_array)		
    dst_dataset_array[dst_dataset_array<-9999] = np.nan					
    geotransform = src_dataset.GetGeoTransform()
    spatialreference = src_dataset.GetProjection()
    
    # create dataset for output
    fmt = 'GTiff'
    driver = gdal.GetDriverByName(fmt)
    dir_name = os.path.dirname(dst_fileName)
    
    # If the directory does not exist, make it.
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)
    dst_dataset = driver.Create(dst_fileName, shape_lsc[0], shape_lsc[1], nband,gdal.GDT_Float32)
    dst_dataset.SetGeoTransform(geotransform)
    dst_dataset.SetProjection(spatialreference)
    dst_dataset.GetRasterBand(1).SetNoDataValue(-9999)				
    dst_dataset.GetRasterBand(1).WriteArray(dst_dataset_array)
    dst_dataset = None

#------------------------------------------------------------------------------
def w_time(LT,lon_proy, DOY):
    """
    This function computes the hour angle (radians) of an image given the
    local time, longitude, and day of the year.

    """
    nrow, ncol = lon_proy.shape
   
    # Difference of the local time (LT) from Greenwich Mean Time (GMT) (hours):
    delta_GTM = np.sign(lon_proy[nrow//2, ncol//2]) * lon_proy[nrow//2, ncol//2] * 24 // 360
    if np.isnan(delta_GTM) == True:
         delta_GTM = np.nanmean(lon_proy) * np.nanmean(lon_proy)  * 24 // 360
    
    
    # Local Standard Time Meridian (degrees):
    LSTM = 15 * delta_GTM
    
    # Ecuation of time (EoT, minutes):
    B = 360./365 * (DOY-81)  # (degrees)
    EoT = 9.87*sin(np.deg2rad(2*B))-7.53*cos(np.deg2rad(B))-1.5*sin(np.deg2rad(B))
   
    # Net Time Correction Factor (minutes) at the center of the image:
    TC = 4 * (lon_proy - LSTM) + EoT     # Difference in time over the longitude
    LST = LT + delta_GTM + TC//60         # Local solar time (hours)
    HRA = 15 * (LST-12)                  # Hour angle HRA (degrees)
    deg2rad = np.pi / 180.0              # Factor to transform from degree to rad
    w = HRA * deg2rad                    # Hour angle HRA (radians)
    return w

#------------------------------------------------------------------------------
def info_general_metadata(filename):
    """
    This function retrieves general information of the Landsat image
    (date and time aquired, UTM zone, sun elevation) from the
    metadata file.

    """
    Landsat_meta = open(filename, "r")  # Open metadata file
    for line in Landsat_meta:
        if re.match("(.*)SCENE_CENTER_TIME(.*)", line): # search in metadata for line SCENE_CENTER_TIME
            words = line.split()# make groups of words which are divided by an open space
            time_list = words[2].split(':', 2) # Take the second word of words and split the word which are divided by :
            if len(time_list[0])== 3: 
                time_list[0]=time_list[0][1:3]
                time_list[2]=time_list[2][0:-1]
            hour = float(time_list[0]) # take the first word of time_list
            minutes = float(time_list[1]) + float(time_list[2][:-1]) / 60 # Take the second and third word of time_list and place :-1 to remove Z behined minutes
    Landsat_meta = open(filename, "r")  # Open metadata file    
    for line in Landsat_meta:
        if re.match("(.*)DATE_ACQUIRED(.*)", line):
            words = line.split()
            DOY = time.strptime(words[2], "%Y-%m-%d").tm_yday
            year = time.strptime(words[2], "%Y-%m-%d").tm_year
            mon = time.strptime(words[2], "%Y-%m-%d").tm_mon
            day = time.strptime(words[2], "%Y-%m-%d").tm_mday
    Landsat_meta = open(filename, "r")  # Open metadata file
    for line in Landsat_meta:
        if re.match("(.*)UTM_ZONE(.*)", line):
            words = line.split()
            UTM_Zone = int(words[2])
    Landsat_meta = open(filename, "r")  # Open metadata file
    for line in Landsat_meta:
        if re.match("(.*)SUN_ELEVATION(.*)", line):
            words = line.split()
            Sun_elevation = float(words[2])

    return year, DOY, mon, day, hour, minutes, UTM_Zone, Sun_elevation

#------------------------------------------------------------------------------
def info_band_metadata(filename, Bands):
    """
    This function retrieves Landsat band information (minimum and maximum
    radiance) from the metadata file.

    """
    Lmin = np.zeros(len(Bands))  # Minimum band radiance, for each band
    Lmax = np.zeros(len(Bands))  # Maximum band radiance, for each band
    k1_const = np.zeros(len(Bands)-6)  # TIRS_Thermal constant k1 ######
    k2_const = np.zeros(len(Bands)-6)  # TIRS_Thermal constant k2 ######
    for band in Bands:
        Landsat_meta = open(filename, "r")  # Open metadata file
        for line in Landsat_meta:
            if re.match("(.*)RADIANCE_MINIMUM_BAND_%1d(.*)" % band, line):
                words = line.split()
                value = float(words[2])
                Lmin[np.where(Bands == band)[0][0]] = value
            if re.match("(.*)RADIANCE_MAXIMUM_BAND_%1d(.*)" % band, line):
                words = line.split()
                value = float(words[2])
                Lmax[np.where(Bands == band)[0][0]] = value
            if re.match("(.*)K1_CONSTANT_BAND_%1d(.*)" % band, line):  # #####
                words = line.split()
                value = float(words[2])
                k1_const[np.where(Bands == band)[0][0]-6] = value
            if re.match("(.*)K2_CONSTANT_BAND_%1d(.*)" % band, line):  # #####
                words = line.split()
                value = float(words[2])
                k2_const[np.where(Bands == band)[0][0]-6] = value
    return Lmin, Lmax, k1_const, k2_const

#------------------------------------------------------------------------------
def sensible_heat(rah, ustar, rn_inst, g_inst, ts_dem, ts_dem_hot, ts_dem_cold,
                  air_dens, Surf_temp, k_vk, QC_Map, hot_pixels, slope):
    """
    This function computes the instantaneous sensible heat given the
    instantaneous net radiation, ground heat flux, and other parameters.

    """
    # Near surface temperature difference (dT):
    dT_ini = (rn_inst - g_inst) * rah / (air_dens * 1004)
    dT_hot = np.copy(dT_ini)
    
    #dT_hot_fileName = os.path.join(output_folder, 'Output_cloud_masked','test.tif')
    #save_GeoTiff_proy(dest, dT_hot, dT_hot_fileName,shape, nband=1)
    
    # dT for hot pixels - hot, (dry) agricultural fields with no green veget.:
    dT_hot[ts_dem <= (ts_dem_hot - 0.5)] = np.nan
    dT_hot[QC_Map == 1] = np.nan
    dT_hot[dT_hot == 0] = np.nan
    if np.isnan(np.nanmean(dT_hot)) == True:
       dT_hot = np.copy(dT_ini)       
       ts_dem_hot = np.nanpercentile(hot_pixels, 99.5)
       dT_hot[ts_dem <= (ts_dem_hot - 0.5)] = np.nan
       dT_hot[dT_hot == 0] = np.nan 
       
    dT_hot=np.float32(dT_hot)
    dT_hot[slope > 10]=np.nan  
      
    #dT_hot_max = np.nanmax(dT_hot)
    #dT_hot_std = np.nanstd(dT_hot)
    #dT_hot_mean = dT_hot_max-0.5*dT_hot_std
    #dT_hot_mean = dT_hot_max-0.5*dT_hot_std
    dT_hot_mean = np.nanmean(dT_hot)
    # print 'dT_hot_mean' , np.mean(dT_hot_mean)
    # Compute slope and offset of linear relationship dT = b + a * Ts
    slope_dt = (dT_hot_mean - 0.0) / (ts_dem_hot - ts_dem_cold)  # EThot = 0.0
    offset_dt = dT_hot_mean - slope_dt * ts_dem_hot
    dT = offset_dt + slope_dt * ts_dem
    # Sensible heat flux:
    h = air_dens * 1004 * dT / rah
    h[QC_Map == 1] = np.nan
    h[h==0]=np.nan
    h[QC_Map != 0] = np.nan
    # Monin-Obukhov length (m):
    L_MO = ((-1.0 * air_dens * 1004 * np.power(ustar, 3) * Surf_temp) /
            (k_vk * 9.81 * h))
    L_MO[L_MO < -1000] = -1000
    # Stability correction for momentum, stable conditions (L_MO >= 0):
    psi_200_stable = -0.05 * 200 / L_MO
    # Stability correction for momentum and heat transport, unstable
    # conditions (L_MO < 0):
    x2 = np.power((1.0 - 16.0 * (2.0/L_MO)), 0.25)  # x at 2m
    x200 = np.power(1.0 - 16.0 * (200/L_MO), 0.25)  # x at 200m
    psi_h = 2 * np.log((1 + np.power(x2, 2))/2)
    psi_m200 = (2 * np.log((1 + x200) / 2) + np.log((1 + np.power(x200, 2)) /
                2) - 2 * np.arctan(x200) + 0.5*np.pi)
    print('Sensible Heat ', np.nanmean(h))
    print('dT' , np.nanmean(dT))

    return L_MO, psi_200_stable, psi_h, psi_m200, h, dT, slope_dt, offset_dt

#------------------------------------------------------------------------------   
    
def Reshape_Reproject_Input_data(input_File_Name, output_File_Name, Example_extend_fileName):

   # Reproject the dataset based on the example       
   data_rep, ulx_dem, lry_dem, lrx_dem, uly_dem, epsg_to = reproject_dataset_example(
       input_File_Name, Example_extend_fileName)
   
   # Get the array information from the new created map
   band_data = data_rep.GetRasterBand(1) # Get the reprojected dem band
   ncol_data = data_rep.RasterXSize
   nrow_data = data_rep.RasterYSize
   shape_data=[ncol_data, nrow_data]
 
   # Save new dataset 
   #stats = band.GetStatistics(0, 1)
   data = band_data.ReadAsArray(0, 0, ncol_data, nrow_data)
   save_GeoTiff_proy(data_rep, data, output_File_Name, shape_data, nband=1)
   
   return(data)

#------------------------------------------------------------------------------   
def Thermal_Sharpening(surface_temp_up, NDVI_up, NDVI, Box, dest_up, output_folder, ndvi_fileName, shape_down, dest_down, temp_surface_sharpened_fileName):

    # Creating arrays to store the coefficients						
    CoefA=np.zeros((len(surface_temp_up),len(surface_temp_up[1])))
    CoefB=np.zeros((len(surface_temp_up),len(surface_temp_up[1])))
    CoefC=np.zeros((len(surface_temp_up),len(surface_temp_up[1])))
  
    # Fit a second polynominal fit to the NDVI and Thermal data and save the coefficients for each pixel  
    # NOW USING FOR LOOPS PROBABLY NOT THE FASTEST METHOD     
    for i in range(0,len(surface_temp_up)):
        for j in range(0,len(surface_temp_up[1])):
            if np.isnan(np.sum(surface_temp_up[i,j]))==False and np.isnan(np.sum(NDVI_up[i,j]))==False:
                x_data=NDVI_up[np.maximum(0,i-(Box-1)//2):np.minimum(len(surface_temp_up),i+(Box-1)//2+1),np.maximum(0,j-(Box-1)//2):np.minimum(len(surface_temp_up[1]),j+(Box-1)//2+1)][np.logical_and(np.logical_not(np.isnan(NDVI_up[np.maximum(0,i-(Box-1)//2):np.minimum(len(surface_temp_up),i+(Box-1)//2+1),np.maximum(0,j-(Box-1)//2):np.minimum(len(surface_temp_up[1]),j+(Box-1)//2+1)])),np.logical_not(np.isnan(surface_temp_up[np.maximum(0,i-(Box-1)//2):np.minimum(len(surface_temp_up),i+(Box-1)//2+1),np.maximum(0,j-(Box-1)//2):np.minimum(len(surface_temp_up[1]),j+(Box-1)//2+1)])))]
                y_data=surface_temp_up[np.maximum(0,i-(Box-1)//2):np.minimum(len(surface_temp_up),i+(Box-1)//2+1),np.maximum(0,j-(Box-1)//2):np.minimum(len(surface_temp_up[1]),j+(Box-1)//2+1)][np.logical_and(np.logical_not(np.isnan(NDVI_up[np.maximum(0,i-(Box-1)//2):np.minimum(len(surface_temp_up),i+(Box-1)//2+1),np.maximum(0,j-(Box-1)//2):np.minimum(len(surface_temp_up[1]),j+(Box-1)//2+1)])),np.logical_not(np.isnan(surface_temp_up[np.maximum(0,i-(Box-1)//2):np.minimum(len(surface_temp_up),i+(Box-1)//2+1),np.maximum(0,j-(Box-1)//2):np.minimum(len(surface_temp_up[1]),j+(Box-1)//2+1)])))]
                if len(x_data)>6:
                    coefs = poly.polyfit(x_data, y_data, 2)
                    CoefA[i,j] = coefs[2]
                    CoefB[i,j] = coefs[1]
                    CoefC[i,j] = coefs[0]
                else:
                    CoefA[i,j] = np.nan
                    CoefB[i,j] = np.nan
                    CoefC[i,j] = np.nan
            else:
                CoefA[i,j] = np.nan
                CoefB[i,j] = np.nan
                CoefC[i,j] = np.nan
            
    # Define the shape of the surface temperature with the resolution of 400m      
    shape_up=[len(surface_temp_up[1]),len(surface_temp_up)]
           
    # Save the coefficients
    CoefA_fileName_Optie2 = os.path.join(output_folder, 'Output_temporary','coef_A.tif')
    save_GeoTiff_proy(dest_up,CoefA, CoefA_fileName_Optie2,shape_up, nband=1)
        
    CoefB_fileName_Optie2 = os.path.join(output_folder, 'Output_temporary','coef_B.tif')
    save_GeoTiff_proy(dest_up,CoefB, CoefB_fileName_Optie2,shape_up, nband=1)
 
    CoefC_fileName_Optie2 = os.path.join(output_folder, 'Output_temporary','coef_C.tif')
    save_GeoTiff_proy(dest_up,CoefC, CoefC_fileName_Optie2,shape_up, nband=1)
       
    # Downscale the fitted coefficients
    CoefA_Downscale, ulx_dem, lry_dem, lrx_dem, uly_dem, epsg_to = reproject_dataset_example(
                                  CoefA_fileName_Optie2, ndvi_fileName)
    CoefA = CoefA_Downscale.GetRasterBand(1).ReadAsArray()
       
    CoefB_Downscale, ulx_dem, lry_dem, lrx_dem, uly_dem, epsg_to = reproject_dataset_example(
                                  CoefB_fileName_Optie2, ndvi_fileName)
    CoefB = CoefB_Downscale.GetRasterBand(1).ReadAsArray()
        
    CoefC_downscale, ulx_dem, lry_dem, lrx_dem, uly_dem, epsg_to = reproject_dataset_example(
                                CoefC_fileName_Optie2, ndvi_fileName)
    CoefC = CoefC_downscale.GetRasterBand(1).ReadAsArray()

    # Calculate the surface temperature based on the fitted coefficents and NDVI
    temp_surface_sharpened=CoefA*NDVI**2+CoefB*NDVI+CoefC
    temp_surface_sharpened[temp_surface_sharpened < 250] = np.nan					
    temp_surface_sharpened[temp_surface_sharpened > 400] = np.nan	
				
    save_GeoTiff_proy(dest_down,temp_surface_sharpened, temp_surface_sharpened_fileName,shape_down, nband=1)	
    return(temp_surface_sharpened)				

#------------------------------------------------------------------------------   

def Check_dT(rn_inst, g_inst, LAI, vegt_cover, z0m, u_200, Temp_inst, RH_inst, air_dens, Psychro_c, rl, rs_min, rsoil_min):    

    esat_inst = 0.6108*np.exp((17.27*Temp_inst)/(237.3+Temp_inst))
    eact_inst = RH_inst*0.01*esat_inst
    u_starr = (0.41*u_200)/np.log(200/z0m)	
    rah = 0.8 * np.log(2/(0.1*z0m))/(0.41*u_starr)		 # 0.8 to skip the iteration part and just assume 80% lower rah end of iteration			
    rs = 1/(vegt_cover/rs_min+(1-vegt_cover)/rsoil_min)
    vpd = esat_inst - eact_inst
    sa_slope = (4098*esat_inst)/np.power(Temp_inst + 237.3, 2)    
    LE = (sa_slope*(rn_inst-g_inst)+air_dens*1004*vpd/rah)/(sa_slope+Psychro_c*(1+rs/rah))
    Aearodynamic_res_SEBAL =np.log(2/0.01)/(0.41*u_starr)								
    H = rn_inst-g_inst-LE		 					
    dT = (H*Aearodynamic_res_SEBAL)/(air_dens*1004)
    T0_DEM = dT + Temp_inst		
    T0_DEM += 273.15
									
    return(dT, T0_DEM)	

#------------------------------------------------------------------------------   
def reproject_MODIS(input_name, output_name, epsg_to):   
    
    '''
    Reproject the merged data file
	
    Keywords arguments:
    output_folder -- 'C:/file/to/path/'
    '''                    
    
    # Get environmental variable
    if platform.system() == 'Windows':
        SEBAL_env_paths = os.environ["SEBAL"].split(';')
        GDAL_env_path = SEBAL_env_paths[0]
        GDALWARP_PATH = os.path.join(GDAL_env_path, 'gdalwarp.exe')
    else:
        SEBAL_env_paths = os.environ["SEBAL"]
        GDAL_env_path = SEBAL_env_paths
        GDAL_TRANSLATE = os.path.join(GDAL_env_path, 'gdal_translate')
    split_input = input_name.split('hdf":')
    inputname = '%shdf":"%s"' %(split_input[0],split_input[1])

    # find path to the executable
    fullCmd = ' '.join(["%s" %(GDALWARP_PATH), '-overwrite -s_srs "+proj=sinu +lon_0=0 +x_0=0 +y_0=0 +a=6371007.181 +b=6371007.181 +units=m +no_defs"', '-t_srs EPSG:%s -of GTiff' %(epsg_to), inputname, output_name])   
    os.system(fullCmd)
				
    return()  

#------------------------------------------------------------------------------   				
def Open_reprojected_hdf(input_name, Band, epsg_to, scale_factor, proyDEM_fileName):

    g=gdal.Open(input_name, gdal.GA_ReadOnly)
    
    folder_out = os.path.dirname(input_name)
    output_name_temp = os.path.join(folder_out, "temporary.tif")
    
    # Open and reproject           
    name_in = g.GetSubDatasets()[Band][0]

    reproject_MODIS(name_in, output_name_temp, epsg_to)

    dest, ulx_dem, lry_dem, lrx_dem, uly_dem, epsg_to = reproject_dataset_example(output_name_temp, proyDEM_fileName)
    Array = dest.GetRasterBand(1).ReadAsArray() * scale_factor

    os.remove(output_name_temp)
                              
    return(Array)  

#------------------------------------------------------------------------------   	

def Modis_Time(src_FileName_LST, epsg_to, proyDEM_fileName):
      
    Time = Open_reprojected_hdf(src_FileName_LST, 2, epsg_to, 0.1, proyDEM_fileName)

    hour = np.floor(Time)
    hour[hour == 0] = np.nan
    minutes = (Time - hour) * 60
    
    return(hour, minutes) 

#------------------------------------------------------------------------------  

def Run_command_window(argument):
    """
    This function runs the argument in the command window without showing cmd window

    Keyword Arguments:
    argument -- string, name of the adf file
    """  
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW		
    
    process = subprocess.Popen(argument, startupinfo=startupinfo, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    process.wait()  
    
    return()
