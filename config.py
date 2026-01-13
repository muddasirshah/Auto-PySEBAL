# -*- coding: utf-8 -*-
"""
Configuration for PySEBAL - No Excel Needed
All parameters defined programmatically
"""

class SEBALConfig:
    # ========================================================================
    # CROP-SPECIFIC BIOMASS PARAMETERS
    # ========================================================================
    # Select your crop type by setting CROP_TYPE below
    # Then the model will automatically use the correct parameters
    
    CROP_PARAMETERS = {
        # Crop Name: [LUE_max (g/MJ), Biomass_Factor, Kt_optimal (°C), Tl_min (°C), Th_max (°C), Depl_factor]
        # LUE_max = Maximum Light Use Efficiency
        # Biomass_Factor = Aboveground biomass fraction (for converting DMP to biomass)
        # Kt = Optimal temperature for photosynthesis
        # Tl = Lower temperature limit for growth
        # Th = Upper temperature limit for growth
        # Depl_factor = FAO soil water depletion fraction for no stress (p)
        
        # === C3 CROPS (most common crops) ===
        'winter_wheat':    [2.2, 0.864, 20.0,  0.0, 35.0, 0.55],  # Cool season cereal - FAO p=0.55
        'spring_wheat':    [2.3, 0.864, 23.0,  0.0, 35.0, 0.55],  # Warmer growing season - FAO p=0.55
        'rice':            [2.0, 0.864, 25.0,  8.0, 38.0, 0.20],  # Warm season C3 - FAO p=0.20 (flooded)
        'cotton':          [2.1, 0.864, 28.0, 12.0, 40.0, 0.65],  # Heat tolerant C3 - FAO p=0.65
        'soybean':         [2.4, 0.864, 25.0, 10.0, 38.0, 0.50],  # Legume, high efficiency - FAO p=0.50
        'tobacco':         [2.2, 0.864, 26.0, 10.0, 35.0, 0.40],  # Broadleaf crop - Similar to tomato
        'vegetables':      [2.5, 0.864, 23.0,  5.0, 35.0, 0.40],  # General vegetables - Average
        'potato':          [2.3, 0.864, 20.0,  5.0, 30.0, 0.35],  # Cool season tuber - FAO p=0.35
        'tomato':          [2.4, 0.864, 24.0, 10.0, 32.0, 0.40],  # Warm season vegetable - FAO p=0.40
        'sunflower':       [2.2, 0.864, 25.0,  8.0, 34.0, 0.45],  # Oilseed crop - FAO p=0.45
        'rapeseed':        [2.3, 0.864, 18.0,  0.0, 30.0, 0.60],  # Cool season oilseed - FAO p=0.60 (canola)
        'barley':          [2.1, 0.864, 20.0,  0.0, 32.0, 0.55],  # Cool season cereal - Similar to wheat
        
        # === C4 CROPS (higher photosynthetic efficiency) ===
        'corn':            [3.5, 0.720, 30.0, 10.0, 42.0, 0.55],  # Maize, high efficiency - FAO grain p=0.55
        'sugarcane':       [4.0, 0.720, 32.0, 15.0, 45.0, 0.65],  # Highest LUE, tropical - FAO p=0.65
        'sorghum':         [3.8, 0.720, 32.0, 12.0, 42.0, 0.55],  # Drought tolerant C4 - FAO grain p=0.55
        'millet':          [3.5, 0.720, 30.0, 10.0, 40.0, 0.55],  # Pearl/finger millet - Similar to grain
        'switchgrass':     [3.2, 0.720, 28.0,  8.0, 38.0, 0.50],  # Bioenergy grass - Similar to pasture
        
        # === PERENNIAL CROPS ===
        'fruit_trees':     [2.0, 0.650, 22.0,  5.0, 35.0, 0.50],  # Apple, peach, citrus - FAO deciduous p=0.50
        'citrus':          [2.1, 0.600, 25.0, 10.0, 38.0, 0.50],  # Orange, lemon - FAO citrus p=0.50
        'olive':           [1.8, 0.550, 25.0,  5.0, 40.0, 0.65],  # Mediterranean tree - FAO olive p=0.65
        'grape':           [2.2, 0.700, 25.0,  8.0, 38.0, 0.35],  # Vineyard - FAO table/wine grapes p=0.35/0.45
        'almond':          [2.0, 0.600, 24.0,  5.0, 36.0, 0.40],  # Nut tree - FAO pistachios p=0.40
        'coffee':          [1.9, 0.600, 22.0, 15.0, 30.0, 0.40],  # Shade-grown shrub - Similar to fruit trees
        
        # === FORAGE & PASTURE ===
        'alfalfa':         [2.6, 0.864, 23.0,  5.0, 35.0, 0.55],  # High-quality legume - FAO p=0.55
        'grass_pasture':   [2.4, 0.864, 20.0,  0.0, 32.0, 0.40],  # Cool season grass - FAO pasture p=0.40
        'clover':          [2.5, 0.864, 22.0,  5.0, 30.0, 0.35],  # Legume pasture - FAO clover p=0.35
        
        # === FORESTS ===
        'forest':          [1.8, 0.500, 20.0,  0.0, 35.0, 0.70],  # Temperate forest - FAO coniferous p=0.70
        'tropical_forest': [2.0, 0.450, 26.0, 15.0, 38.0, 0.70],  # Rainforest - Assumed similar
        'coniferous':      [1.6, 0.550, 18.0, -5.0, 32.0, 0.70],  # Pine/spruce - FAO coniferous p=0.70
        'deciduous':       [1.9, 0.500, 22.0,  0.0, 35.0, 0.50],  # Oak/maple - FAO deciduous p=0.50
        
        # === SPECIALTY CROPS ===
        'sugarbeet':       [2.3, 0.864, 22.0,  5.0, 32.0, 0.55],  # Root crop - FAO p=0.55
        'peanut':          [2.4, 0.864, 28.0, 15.0, 38.0, 0.50],  # Legume, warm season - FAO groundnut p=0.50
        'chickpea':        [2.3, 0.864, 22.0,  5.0, 32.0, 0.50],  # Cool season legume - FAO p=0.50
        'lentil':          [2.2, 0.864, 20.0,  5.0, 30.0, 0.50],  # Cool season legume - FAO p=0.50
        'peas':            [2.4, 0.864, 20.0,  5.0, 30.0, 0.35],  # Fresh peas - FAO p=0.35
        'eggplant':        [2.3, 0.864, 24.0, 10.0, 35.0, 0.45],  # Eggplant - FAO p=0.45
        'sweet_pepper':    [2.4, 0.864, 24.0, 10.0, 35.0, 0.30],  # Bell peppers - FAO p=0.30
        'pumpkin':         [2.3, 0.864, 24.0, 10.0, 35.0, 0.35],  # Winter squash - FAO p=0.35
        'zucchini':        [2.4, 0.864, 24.0, 10.0, 35.0, 0.50],  # Squash/zucchini - FAO p=0.50
        'melon':           [2.3, 0.864, 26.0, 12.0, 38.0, 0.40],  # Sweet melons - FAO p=0.40
        'watermelon':      [2.2, 0.864, 26.0, 12.0, 38.0, 0.40],  # Watermelon - FAO p=0.40
        'turnip':          [2.2, 0.864, 18.0,  5.0, 30.0, 0.50],  # Turnip/rutabaga - FAO p=0.50
        'cassava':         [2.0, 0.720, 28.0, 15.0, 40.0, 0.35],  # Cassava year 1 - FAO p=0.35
        'safflower':       [2.2, 0.864, 25.0,  8.0, 35.0, 0.60],  # Safflower - FAO p=0.60
        'sesame':          [2.1, 0.864, 28.0, 15.0, 40.0, 0.60],  # Sesame - FAO p=0.60
    }
    
    def __init__(self):
        # ========== GENERAL INPUTS ==========
        self.input_folder = None  # Will be set by run script
        self.output_folder = None  # Will be set by run script
        self.Image_Type = 1  # 1=Landsat, 2=VIIRS+PROBAV, 3=MODIS
        self.DEM_fileName = None  # Will be set to SRTM_DEM.tif path
        
        # ========== GEE DATA ACQUISITION ==========
        self.latitude = 33.650935  # Study area center latitude
        self.longitude = 73.219159  # Study area center longitude
        self.buffer_km = 5  # Buffer around center point in km
        
        # ========== OPENWEATHERMAP API ==========
        self.openweather_api_key = '' # Replace with your own API key
        self.use_realtime_weather = True  # Set to True to fetch from API, False to use defaults
        
        # ========== LANDSAT INPUTS ==========
        self.Name_Landsat_Image = None  # AUTO-DETECTED from GEE download
        self.Landsat_nr = 8  # AUTO-DETECTED (8 or 9 from scene ID)
        self.Bands_thermal = 1  # Use Band 10 for LS8/LS9 (scientifically validated)
        
        # === SEBAL Anchor Pixel Selection (Scientifically Validated - DO NOT MODIFY) ===
        # These values are from peer-reviewed SEBAL literature (Bastiaanssen et al.)
        self.NDVIhot_low = 5.0  # Hot pixels: bare soil/low vegetation (5th percentile)
        self.NDVIhot_high = 40.0  # Hot pixels: moderately vegetated (40th percentile)
        self.tcoldmin = 5.0  # Cold pixels: minimum temp threshold (5th percentile)
        self.tcoldmax = 20.0  # Cold pixels: maximum temp threshold (20th percentile)
        
        # Standard atmospheric lapse rate - CONSTANT from physics
        self.temp_lapse = 0.0065  # Temperature lapse rate (K/m) - Environmental constant
        
        # ========== METEOROLOGICAL INPUTS ==========
        # NOTE: These are FALLBACK defaults only!
        # Real values are auto-fetched with priority: ERA5-Land → OpenWeatherMap API
        # If both sources fail, processing will stop with error (no hardcoding in production)
        
        # Instantaneous Air Temperature (°C) - AUTO-UPDATED from ERA5 or OpenWeatherMap
        self.Temp_inst = 28.0  # Fallback only
        self.Temp_inst_kind_of_data = 0  # 0=constant, 1=map
        
        # Daily Average Air Temperature (°C) - AUTO-UPDATED from ERA5 or OpenWeatherMap
        self.Temp_24 = 22.0  # Fallback only
        self.Temp_24_kind_of_data = 0
        
        # Instantaneous Relative Humidity (%) - AUTO-CALCULATED from ERA5 dewpoint or OpenWeatherMap
        self.RH_inst = 55.0  # Fallback only
        self.RH_inst_kind_of_data = 0
        
        # Daily Average Relative Humidity (%) - AUTO-CALCULATED from ERA5 dewpoint or OpenWeatherMap
        self.RH_24 = 60.0  # Fallback only
        self.RH_24_kind_of_data = 0
        
        # Instantaneous Wind Speed (m/s) - AUTO-CALCULATED from ERA5 u/v components or OpenWeatherMap
        self.Wind_inst = 2.5  # Fallback only
        self.Wind_inst_kind_of_data = 0
        
        # Daily Average Wind Speed (m/s) - AUTO-CALCULATED from ERA5 u/v components or OpenWeatherMap
        self.Wind_24 = 2.0  # Fallback only
        self.Wind_24_kind_of_data = 0
        
        # === Wind Measurement Settings ===
        # Height at which wind is measured - Default = 2m (standard meteorological height)
        # ERA5 provides wind at 10m, SEBAL adjusts using logarithmic wind profile
        # NOTE: Can be modified for site-specific weather station height
        self.zx = 2.0  # Reference height (m) - Standard = 2.0m
        
        # === RADIATION INPUTS ===
        # NOTE: ERA5-Land provides solar radiation in J/m² (auto-converted to W/m² and MJ/m²/day)
        #       OpenWeatherMap provides W/m² (auto-converted to MJ/m²/day for Rs_24)
        # Method_Radiation: 1=Calculate Transm, 2=Calculate Rs
        self.Method_Radiation_24 = 1
        self.Rs_24 = 22.0  # Daily solar radiation (MJ/m²/day) - AUTO-UPDATED from ERA5/OpenWeatherMap
        self.Rs_24_kind_of_data = 0
        self.Transm_24 = 0.75  # Daily transmissivity - AUTO-CALCULATED from ERA5/API data
        self.Transm_24_kind_of_data = 0
        
        self.Method_Radiation_inst = 1
        self.Rs_in_inst = 850.0  # Instantaneous solar radiation (W/m²) - AUTO-UPDATED from ERA5/API
        self.Rs_in_inst_kind_of_data = 0
        self.Transm_inst = 0.78  # Instantaneous transmissivity - AUTO-CALCULATED from ERA5/API data
        self.Transm_inst_kind_of_data = 0
        
        # === Surface Roughness ===
        # Obstacle height - Average height of obstacles affecting wind flow
        # Default = 0.0 (flat terrain, no obstacles)
        # Increase for urban areas, forests, or areas with buildings/trees
        self.h_obst = 0.0  # Obstacle height (m) - Site-specific, default = 0.0
        self.h_obst_kind_of_data = 0
        
        # ========== SOIL INPUTS ==========
        # NOTE: All soil parameters AUTO-UPDATED from HiHydroSoil v2.0 (GEE)
        # Fallback values used only if HiHydroSoil download fails
        
        self.Theta_sat_top = 0.40  # Saturated soil moisture topsoil - AUTO from HiHydroSoil wcsat
        self.Theta_sat_top_kind_of_data = 0  # AUTO-SET: 0=constant, 1=raster map
        
        self.Theta_sat_sub = 0.40  # Saturated soil moisture subsoil - AUTO from HiHydroSoil wcsat
        self.Theta_sat_sub_kind_of_data = 0  # AUTO-SET: 0=constant, 1=raster map
        
        self.Theta_res_top = 0.05  # Residual soil moisture topsoil - AUTO from HiHydroSoil wcres
        self.Theta_res_top_kind_of_data = 0  # AUTO-SET: 0=constant, 1=raster map
        
        self.Theta_res_sub = 0.05  # Residual soil moisture subsoil - AUTO from HiHydroSoil wcres
        self.Theta_res_sub_kind_of_data = 0  # AUTO-SET: 0=constant, 1=raster map
        
        self.Depl_factor = 0.5  # Depletion factor - AUTO-SET from crop type (FAO values)
        self.Depl_factor_kind_of_data = 0
        
        self.Field_Capacity = 0.33  # Field capacity - AUTO from HiHydroSoil sat_field
        self.Field_Capacity_kind_of_data = 0  # AUTO-SET: 0=constant, 1=raster map
        
        self.Wilting_Point = 0.10  # Wilting point - AUTO from HiHydroSoil crit_wilt
        self.Wilting_Point_kind_of_data = 0  # AUTO-SET: 0=constant, 1=raster map
        
        # ========== CROP/VEGETATION TYPE ==========
        # Choose from the CROP_PARAMETERS table above
        # Examples: 'winter_wheat', 'corn', 'rice', 'cotton', 'sugarcane', 
        #           'soybean', 'vegetables', 'fruit_trees', 'forest', etc.
        self.crop_type = 'corn'  # Currently set for winter wheat
        
        # Automatically set biomass parameters based on crop type
        # Or set manually by changing values below
        crop_params = self.CROP_PARAMETERS.get(self.crop_type, [2.0, 0.864, 23.0, 0.0, 35.0, 0.50])
        
        self.LUE_max = crop_params[0]  # Max light use efficiency (g/MJ)
        self.LUE_max_kind_of_data = 0
        
        self.Biomass_aboveground_factor = crop_params[1]  # Fraction of DMP that is aboveground
        self.Kt_optimal_temp = crop_params[2]  # Optimal temperature for photosynthesis (°C)
        self.Tl_min_temp = crop_params[3]      # Lower temperature limit (°C)
        self.Th_max_temp = crop_params[4]      # Upper temperature limit (°C)
        self.Depl_factor = crop_params[5]      # FAO depletion fraction (p) - AUTO-SET per crop
        self.Depl_factor_kind_of_data = 0
        
        # ========== ADDITIONAL INPUTS (Optional - can skip) ==========
        self.LAI_fileName = None
        self.Surface_Albedo_fileName = None
        self.NDVI_fileName = None
        self.Surf_roughness = None
        self.Surf_roughness_kind_of_data = None
        self.Surface_temp_fileName = None
        
    def set_folders(self, input_folder, output_folder, dem_file=None):
        """Set input/output folders and DEM path"""
        import os
        self.input_folder = input_folder
        self.output_folder = output_folder
        # Use shared DEM if provided, otherwise look in input folder
        self.DEM_fileName = dem_file if dem_file else os.path.join(input_folder, 'SRTM_DEM.tif')
        
    def set_location(self, latitude, longitude, buffer_km=5):
        """Set study area location for GEE data download"""
        self.latitude = latitude
        self.longitude = longitude
        self.buffer_km = buffer_km
        
    def auto_detect_landsat_image(self):
        """Auto-detect Landsat image name from input folder"""
        if self.input_folder is None:
            return None
        import glob
        import os
        landsat_files = glob.glob(os.path.join(self.input_folder, 'LC*_MTL.txt'))
        if landsat_files:
            return os.path.basename(landsat_files[0]).replace('_MTL.txt', '')
        return None

# ============================================================================
# QUICK REFERENCE: CROP PARAMETERS
# ============================================================================
"""
To use a different crop, simply change the 'crop_type' variable above.

CROP PARAMETER SUMMARY TABLE:
┌─────────────────────┬──────────┬───────────┬──────────┬─────────┬─────────┬──────────┐
│ Crop Type           │ LUE_max  │ Biomass   │ Kt_opt   │ Tl_min  │ Th_max  │ Depl_p   │
│                     │ (g/MJ)   │ Factor    │ (°C)     │ (°C)    │ (°C)    │ (FAO)    │
├─────────────────────┼──────────┼───────────┼──────────┼─────────┼─────────┼──────────┤
│ C3 CROPS                                                                              │
├─────────────────────┼──────────┼───────────┼──────────┼─────────┼─────────┼──────────┤
│ winter_wheat        │   2.2    │   0.864   │   20     │    0    │   35    │   0.55   │
│ spring_wheat        │   2.3    │   0.864   │   23     │    0    │   35    │   0.55   │
│ rice                │   2.0    │   0.864   │   25     │    8    │   38    │   0.20   │
│ cotton              │   2.1    │   0.864   │   28     │   12    │   40    │   0.65   │
│ soybean             │   2.4    │   0.864   │   25     │   10    │   38    │   0.50   │
│ tobacco             │   2.2    │   0.864   │   26     │   10    │   35    │   0.40   │
│ vegetables          │   2.5    │   0.864   │   23     │    5    │   35    │   0.40   │
│ potato              │   2.3    │   0.864   │   20     │    5    │   30    │   0.35   │
│ barley              │   2.1    │   0.864   │   20     │    0    │   32    │   0.55   │
│ sunflower           │   2.2    │   0.864   │   25     │    8    │   34    │   0.45   │
├─────────────────────┼──────────┼───────────┼──────────┼─────────┼─────────┼──────────┤
│ C4 CROPS                                                                              │
├─────────────────────┼──────────┼───────────┼──────────┼─────────┼─────────┼──────────┤
│ corn                │   3.5    │   0.720   │   30     │   10    │   42    │   0.55   │
│ sugarcane           │   4.0    │   0.720   │   32     │   15    │   45    │   0.65   │
│ sorghum             │   3.8    │   0.720   │   32     │   12    │   42    │   0.55   │
│ millet              │   3.5    │   0.720   │   30     │   10    │   40    │   0.55   │
├─────────────────────┼──────────┼───────────┼──────────┼─────────┼─────────┼──────────┤
│ PERENNIAL CROPS                                                                       │
├─────────────────────┼──────────┼───────────┼──────────┼─────────┼─────────┼──────────┤
│ fruit_trees         │   2.0    │   0.650   │   22     │    5    │   35    │   0.50   │
│ citrus              │   2.1    │   0.600   │   25     │   10    │   38    │   0.50   │
│ olive               │   1.8    │   0.550   │   25     │    5    │   40    │   0.65   │
│ grape               │   2.2    │   0.700   │   25     │    8    │   38    │   0.35   │
│ almond              │   2.0    │   0.600   │   24     │    5    │   36    │   0.40   │
├─────────────────────┼──────────┼───────────┼──────────┼─────────┼─────────┼──────────┤
│ FORAGE & FOREST                                                                       │
├─────────────────────┼──────────┼───────────┼──────────┼─────────┼─────────┼──────────┤
│ alfalfa             │   2.6    │   0.864   │   23     │    5    │   35    │   0.55   │
│ grass_pasture       │   2.4    │   0.864   │   20     │    0    │   32    │   0.40   │
│ forest              │   1.8    │   0.500   │   20     │    0    │   35    │   0.70   │
│ tropical_forest     │   2.0    │   0.450   │   26     │   15    │   38    │   0.70   │
└─────────────────────┴──────────┴───────────┴──────────┴─────────┴─────────┴──────────┘

PARAMETER DEFINITIONS:
- LUE_max: Maximum Light Use Efficiency - how efficiently the crop converts 
           sunlight to biomass (g dry matter per MJ of absorbed PAR)
- Biomass_Factor: Aboveground biomass fraction - what percentage of total
                  dry matter production is aboveground
- Kt_optimal: Optimal temperature for photosynthesis (°C)
- Tl_min: Lower temperature limit - below this, growth stops (°C)
- Th_max: Upper temperature limit - above this, growth stops (°C)
- Depl_p: FAO soil water depletion fraction (p) for no stress
          Lower value = crop needs more frequent irrigation
          Higher value = crop tolerates more water depletion
          Range: 0.20 (rice, flooded) to 0.70 (deep-rooted trees)

USAGE EXAMPLE:
    config = SEBALConfig()
    config.crop_type = 'corn'  # For C4 corn/maize
    # The model will automatically use: LUE=3.5, Factor=0.72, Kt=30°C, p=0.55
    
    config.crop_type = 'rice'  # For flooded rice
    # Automatically uses: p=0.20 (frequent irrigation needed)

NOTE: 
- ET (evapotranspiration) calculations are GENERIC and work for ALL crops
- Only biomass calculations use these crop-specific parameters
"""


