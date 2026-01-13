#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Automated SEBAL Time-Series Run Script

This script:
1. Creates input/output folders
2. Downloads Landsat 8 & 9 data from Nov 1, 2024 to present
3. Runs SEBAL for each available date (SEQUENTIALLY)
4. Saves outputs in date-wise subfolders (POI_1/YYYY_MM_DD_L8 or YYYY_MM_DD_L9)
5. Generates all ET and biomass outputs for winter wheat
"""
import os
import sys
import traceback
from datetime import datetime, timedelta

# Import SEBAL and config
from config import SEBALConfig
import pysebal_py3

def main():
    print('='*70)
    print('SEBAL TIME-SERIES PIPELINE - Landsat 8 & 9 Merged')
    print('='*70)
    
    # Setup folders
    base_dir = os.path.dirname(os.path.abspath(__file__))
    poi_folder = os.path.join(base_dir, 'POI_1')  # Main POI folder
    
    if not os.path.exists(poi_folder):
        os.makedirs(poi_folder)
        print(f'✓ Created POI folder: {poi_folder}')
    
    # Initialize configuration
    config = SEBALConfig()
    
    # Set study area location
    config.set_location(
        latitude=33.650935,   # Center latitude
        longitude=73.219159,  # Center longitude
        buffer_km=5           # Buffer in km
    )
    
    # Crop type is already set to winter_wheat in config.py
    
    # Time series parameters
    start_date = '2025-06-01'  
    end_date = datetime.now().strftime('%Y-%m-%d')  # Today
    
    print(f'\nPOI folder: {poi_folder}')
    print(f'Study area: Lat={config.latitude}, Lon={config.longitude}')
    print(f'Buffer: {config.buffer_km} km')
    print(f'Crop type: {config.crop_type}')
    print(f'Time period: {start_date} to {end_date}')
    print(f'Satellites: Landsat 8 (LC08) + Landsat 9 (LC09) merged')
    print('\n' + '='*70)
    
    try:
        # Get available Landsat scenes for the time period
        print('\nSearching for available Landsat 8 & 9 scenes...')
        scenes = pysebal_py3.get_landsat_scenes_timeseries(
            latitude=config.latitude,
            longitude=config.longitude,
            buffer_km=config.buffer_km,
            start_date=start_date,
            end_date=end_date,
            cloud_cover_max=20  # Max 20% cloud cover
        )
        
        if not scenes:
            print('\n⚠️  No Landsat scenes found for the specified period!')
            print('    Try adjusting the date range or cloud cover threshold.')
            sys.exit(1)
        
        print(f'\n✓ Found {len(scenes)} Landsat scenes')
        print('\nScenes to process:')
        for i, scene in enumerate(scenes, 1):
            satellite = 'L8' if 'LC08' in scene['id'] else 'L9'
            print(f'  {i}. {scene["date"]} - {satellite} - Cloud: {scene["cloud_cover"]:.1f}%')
        
        print('\n' + '='*70)
        print('STARTING TIME-SERIES PROCESSING (Sequential - One at a time)')
        print('='*70)
        
        # Download DEM once (shared across all scenes)
        print('\n' + '-'*70)
        dem_file = pysebal_py3.download_dem_once(
            poi_folder=poi_folder,
            latitude=config.latitude,
            longitude=config.longitude,
            buffer_km=config.buffer_km
        )
        
        if not dem_file:
            print('\n⚠️  Failed to download DEM! Cannot proceed.')
            sys.exit(1)
        
        # Download HiHydroSoil soil properties once (shared across all scenes)
        soil_files = pysebal_py3.download_hihydrosoil_data(
            poi_folder=poi_folder,
            latitude=config.latitude,
            longitude=config.longitude,
            buffer_km=config.buffer_km
        )
        
        # Update config with soil raster files if available
        if soil_files:
            # Set raster file paths
            config.Theta_sat_top = soil_files.get('wcsat', 0.40)
            config.Theta_sat_sub = soil_files.get('wcsat', 0.40)
            config.Theta_res_top = soil_files.get('wcres', 0.05)
            config.Theta_res_sub = soil_files.get('wcres', 0.05)
            config.Wilting_Point = soil_files.get('crit_wilt', 0.10)
            config.Field_Capacity = soil_files.get('sat_field', 0.33)
            
            # Set kind_of_data to 1 (raster mode) for parameters that have files
            config.Theta_sat_top_kind_of_data = 1 if soil_files.get('wcsat') else 0
            config.Theta_sat_sub_kind_of_data = 1 if soil_files.get('wcsat') else 0
            config.Theta_res_top_kind_of_data = 1 if soil_files.get('wcres') else 0
            config.Theta_res_sub_kind_of_data = 1 if soil_files.get('wcres') else 0
            config.Wilting_Point_kind_of_data = 1 if soil_files.get('crit_wilt') else 0
            config.Field_Capacity_kind_of_data = 1 if soil_files.get('sat_field') else 0
            
            print('  ✓ Config updated with HiHydroSoil rasters')
        else:
            print('  ⚠️  Using default soil parameters (rasters not available)')
        
        print('-'*70)
        
        # Process scenes in parallel batches of 4
        successful = 0
        failed = 0
        
        def process_scene(scene_info):
            """Process a single scene (called in parallel)"""
            i, scene = scene_info
            scene_id = scene['id']
            scene_date = scene['date']
            satellite = 'L8' if 'LC8' in scene_id else 'L9'
            
            # Create date-wise output folder
            folder_name = f"{scene_date.replace('-', '_')}_{satellite}"
            input_folder = os.path.join(poi_folder, folder_name, 'input')
            output_folder = os.path.join(poi_folder, folder_name, 'output')
            
            print(f'\n[{i}/{len(scenes)}] Processing {scene_date} ({satellite})')
            print('-' * 70)
            
            try:
                # Setup folders for this scene
                os.makedirs(input_folder, exist_ok=True)
                os.makedirs(output_folder, exist_ok=True)
                
                # Create a config copy for this scene
                scene_config = SEBALConfig()
                scene_config.set_location(config.latitude, config.longitude, config.buffer_km)
                scene_config.set_folders(input_folder, output_folder, dem_file=dem_file)  # Use shared DEM
                
                # Copy crop parameters
                scene_config.crop_type = config.crop_type
                scene_config.LUE_max = config.LUE_max
                scene_config.Biomass_aboveground_factor = config.Biomass_aboveground_factor
                scene_config.Kt_optimal_temp = config.Kt_optimal_temp
                scene_config.Tl_min_temp = config.Tl_min_temp
                scene_config.Th_max_temp = config.Th_max_temp
                
                # Copy soil parameters (raster paths)
                scene_config.Theta_sat_top = config.Theta_sat_top
                scene_config.Theta_sat_sub = config.Theta_sat_sub
                scene_config.Theta_res_top = config.Theta_res_top
                scene_config.Theta_res_sub = config.Theta_res_sub
                scene_config.Wilting_Point = config.Wilting_Point
                scene_config.Field_Capacity = config.Field_Capacity
                
                # Copy kind_of_data flags
                scene_config.Theta_sat_top_kind_of_data = config.Theta_sat_top_kind_of_data
                scene_config.Theta_sat_sub_kind_of_data = config.Theta_sat_sub_kind_of_data
                scene_config.Theta_res_top_kind_of_data = config.Theta_res_top_kind_of_data
                scene_config.Theta_res_sub_kind_of_data = config.Theta_res_sub_kind_of_data
                scene_config.Wilting_Point_kind_of_data = config.Wilting_Point_kind_of_data
                scene_config.Field_Capacity_kind_of_data = config.Field_Capacity_kind_of_data
                
                # Fetch weather data for this specific scene date
                scene_time_utc = scene.get('scene_time', '12:00:00.0000000Z')  # Get actual scene time from GEE
                print(f'  Fetching weather for {scene_date}...')
                weather_data = pysebal_py3.fetch_weather_data(
                    latitude=config.latitude,
                    longitude=config.longitude,
                    date_acquired=scene_date,
                    scene_time=scene_time_utc,  # Use actual scene acquisition time (UTC)
                    input_folder=input_folder,
                    api_key=config.openweather_api_key
                )
                
                # Update config with real weather data
                if weather_data:
                    weather_source = weather_data.get('source', 'Unknown')
                    scene_config.Temp_inst = weather_data.get('Temp_inst', scene_config.Temp_inst)
                    scene_config.Temp_24 = weather_data.get('Temp_24', scene_config.Temp_24)
                    scene_config.RH_inst = weather_data.get('RH_inst', scene_config.RH_inst)
                    scene_config.RH_24 = weather_data.get('RH_24', scene_config.RH_24)
                    scene_config.Wind_inst = weather_data.get('Wind_inst', scene_config.Wind_inst)
                    scene_config.Wind_24 = weather_data.get('Wind_24', scene_config.Wind_24)
                    scene_config.Rs_in_inst = weather_data.get('Rs_in_inst', scene_config.Rs_in_inst)
                    scene_config.Rs_24 = weather_data.get('Rs_24', scene_config.Rs_24)  # Now in MJ/m²/day
                    scene_config.Transm_inst = weather_data.get('Transm_inst', scene_config.Transm_inst)
                    scene_config.Transm_24 = weather_data.get('Transm_24', scene_config.Transm_24)
                    print(f'  ✓ Weather auto-updated from {weather_source}: T={scene_config.Temp_inst:.1f}°C, Rs={scene_config.Rs_in_inst:.0f}W/m²')
                else:
                    # Weather data fetch failed completely
                    print(f'  ✗ CRITICAL ERROR: No weather data available for {scene_date}')
                    print(f'  ✗ ERA5-Land unavailable AND OpenWeatherMap API exhausted')
                    print(f'  ✗ Skipping this scene - cannot process without weather data')
                    return False
                
                # Download data for this scene
                print(f'  Downloading {satellite} data...')
                download_success = pysebal_py3.download_specific_scene(
                    scene_id=scene_id,
                    input_folder=input_folder,
                    latitude=config.latitude,
                    longitude=config.longitude,
                    buffer_km=config.buffer_km
                )
                
                if not download_success:
                    print(f'  ✗ Failed to download data for {scene_date}')
                    return False
                
                # Run SEBAL for this scene
                print(f'  Running SEBAL model...')
                pysebal_py3.SEBALcode(scene_config)
                
                print(f'  ✓ Successfully processed {scene_date} ({satellite})')
                print(f'  ✓ Outputs saved to: {output_folder}')
                return True
                
            except Exception as e:
                print(f'  ✗ Error processing {scene_date}: {str(e)}')
                return False
        
        # Process scenes sequentially (safer, no race conditions)
        print(f'\n\n{"="*70}')
        print(f'SEQUENTIAL PROCESSING - {len(scenes)} scenes')
        print(f'{"="*70}')
        
        for i, scene in enumerate(scenes, 1):
            if process_scene((i, scene)):
                successful += 1
            else:
                failed += 1
        
        # Final summary
        print('\n' + '='*70)
        print('TIME-SERIES PROCESSING COMPLETED')
        print('='*70)
        print(f'\nSuccessful: {successful}/{len(scenes)}')
        print(f'Failed: {failed}/{len(scenes)}')
        print(f'\nAll outputs saved to: {poi_folder}')
        print('\nOutput structure:')
        print(f'  POI_1/')
        print(f'    ├─ 2024_11_02_L8/')
        print(f'    │   ├─ input/  (Landsat bands, DEM)')
        print(f'    │   └─ output/ (ET, biomass, soil moisture, etc.)')
        print(f'    ├─ 2024_11_15_L9/')
        print(f'    │   ├─ input/')
        print(f'    │   └─ output/')
        print(f'    └─ ...')
        print('\nKey outputs in each date folder:')
        print('  - ETact_24 (Actual ET)')
        print('  - ETpot_24 (Potential ET)')
        print('  - ET_deficit (Water deficit)')
        print('  - Biomass_prod (Biomass production)')
        print('  - Biomass_deficit (Yield loss)')
        print('  - Irrigation_needs (0-3 classification)')
        print('  - Soil_moisture (Root zone & total)')
        
    except Exception as e:
        print('\n' + '='*70)
        print('SEBAL TIME-SERIES PROCESSING FAILED')
        print('='*70)
        print(f'\nError: {str(e)}\n')
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()

