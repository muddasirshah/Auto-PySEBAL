#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SEBAL Time-Series Visualization Tool

Interactive Tkinter GUI for visualizing SEBAL outputs:

FEATURES:
---------
1. Time-series charts for multiple variables:
   - Evapotranspiration (Actual, Potential, Reference)
   - Biomass production and water productivity
   - Soil moisture (top layer and root zone)
   - Energy fluxes (H, LE, Rn, G)
   - Surface temperature, NDVI, Albedo

2. Flexible spatial extraction:
   - Point extraction (Longitude, Latitude)
   - Polygon extraction (GeoJSON or Shapefile)
   - Aggregation methods: Mean, Sum, Median

3. Export and visualization:
   - Interactive matplotlib charts
   - CSV export for further analysis
   - Raster preview for any date/variable

USAGE:
------
1. Run: python visualize.py
2. Select POI folder (e.g., POI_1) containing date subfolders
3. Choose analysis type (point or polygon)
4. Select variables to plot
5. Generate time-series and export CSV

REQUIREMENTS:
-------------
- tkinter (usually comes with Python)
- matplotlib
- pandas
- numpy
- gdal (osgeo)

Install: pip install matplotlib pandas numpy gdal

AUTHOR: GitHub Copilot
DATE: January 2026
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import pandas as pd
from osgeo import gdal, ogr, osr
import json

gdal.UseExceptions()


class SEBALVisualizer:
    def __init__(self, root):
        self.root = root
        self.root.title("SEBAL Time-Series Visualizer")
        self.root.geometry("1200x800")
        
        # Data storage
        self.poi_folder = None
        self.available_dates = []
        self.selected_variables = []
        self.geometry_type = tk.StringVar(value="point")
        self.aggregation_method = tk.StringVar(value="mean")
        self.point_coords = {"lon": tk.StringVar(), "lat": tk.StringVar()}
        self.polygon_coords = []
        self.timeseries_data = None
        
        # Variable mapping (filename pattern -> display name)
        self.variable_map = {
            "ETact": "Actual ET (mm/day)",
            "ET_24": "Daily ET (mm/day)",
            "ETP_24": "Potential ET (mm/day)",
            "Biomass_prod": "Biomass Production (kg/ha/day)",
            "Biomass_wp": "Water Productivity Biomass (kg/m³)",
            "Biomass_deficit": "Biomass Deficit (kg/ha/day)",
            "Theta_top": "Top Soil Moisture (m³/m³)",
            "Theta_sub": "Root Zone Soil Moisture (m³/m³)",
            "SMC_top": "Top Soil Moisture Content (%)",
            "SMC_sub": "Root Zone Moisture Content (%)",
            "Depletion_factor_top": "Top Depletion Factor",
            "Depletion_factor_sub": "Root Depletion Factor",
            "Moisture_stress_top": "Top Moisture Stress",
            "Moisture_stress_sub": "Root Moisture Stress",
            "H_inst": "Sensible Heat Flux (W/m²)",
            "LE_inst": "Latent Heat Flux (W/m²)",
            "Rn_inst": "Net Radiation (W/m²)",
            "G_inst": "Soil Heat Flux (W/m²)",
            "Surface_temp": "Surface Temperature (K)",
            "NDVI": "NDVI",
            "Albedo": "Surface Albedo"
        }
        
        self.setup_gui()
    
    def setup_gui(self):
        """Setup the GUI layout"""
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(4, weight=1)
        
        # Section 1: Folder Selection
        ttk.Label(main_frame, text="1. Select POI Folder:", font=('Arial', 10, 'bold')).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))
        
        folder_frame = ttk.Frame(main_frame)
        folder_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 15))
        folder_frame.columnconfigure(1, weight=1)
        
        ttk.Button(folder_frame, text="Browse POI Folder", 
                  command=self.select_folder).grid(row=0, column=0, padx=(0, 10))
        self.folder_label = ttk.Label(folder_frame, text="No folder selected", 
                                     foreground="gray")
        self.folder_label.grid(row=0, column=1, sticky=tk.W)
        
        # Section 2: Geometry Type
        ttk.Label(main_frame, text="2. Select Analysis Type:", font=('Arial', 10, 'bold')).grid(
            row=2, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))
        
        geom_frame = ttk.Frame(main_frame)
        geom_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 15))
        
        ttk.Radiobutton(geom_frame, text="Point (Lon, Lat)", variable=self.geometry_type,
                       value="point", command=self.update_geometry_ui).grid(row=0, column=0, sticky=tk.W)
        ttk.Radiobutton(geom_frame, text="Polygon (GeoJSON/Shapefile)", variable=self.geometry_type,
                       value="polygon", command=self.update_geometry_ui).grid(row=0, column=1, sticky=tk.W)
        
        # Point input
        self.point_frame = ttk.LabelFrame(geom_frame, text="Point Coordinates", padding="10")
        self.point_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        
        ttk.Label(self.point_frame, text="Longitude:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(self.point_frame, textvariable=self.point_coords["lon"], width=15).grid(
            row=0, column=1, padx=(5, 20))
        
        ttk.Label(self.point_frame, text="Latitude:").grid(row=0, column=2, sticky=tk.W)
        ttk.Entry(self.point_frame, textvariable=self.point_coords["lat"], width=15).grid(
            row=0, column=3, padx=5)
        
        # Polygon input
        self.polygon_frame = ttk.LabelFrame(geom_frame, text="Polygon File", padding="10")
        self.polygon_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        self.polygon_frame.grid_remove()  # Hidden initially
        
        ttk.Button(self.polygon_frame, text="Load Polygon (GeoJSON/SHP)", 
                  command=self.load_polygon).grid(row=0, column=0, padx=(0, 10))
        self.polygon_label = ttk.Label(self.polygon_frame, text="No polygon loaded", 
                                      foreground="gray")
        self.polygon_label.grid(row=0, column=1, sticky=tk.W)
        
        # Aggregation method for polygons
        agg_frame = ttk.Frame(self.polygon_frame)
        agg_frame.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(10, 0))
        ttk.Label(agg_frame, text="Aggregation:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        ttk.Radiobutton(agg_frame, text="Mean", variable=self.aggregation_method,
                       value="mean").grid(row=0, column=1, padx=5)
        ttk.Radiobutton(agg_frame, text="Sum", variable=self.aggregation_method,
                       value="sum").grid(row=0, column=2, padx=5)
        ttk.Radiobutton(agg_frame, text="Median", variable=self.aggregation_method,
                       value="median").grid(row=0, column=3, padx=5)
        
        # Section 3: Variable Selection
        var_label = ttk.Label(main_frame, text="3. Select Variables to Plot:", 
                             font=('Arial', 10, 'bold'))
        var_label.grid(row=4, column=0, sticky=(tk.W, tk.N), pady=(0, 5))
        
        # Variable listbox with scrollbar
        var_frame = ttk.Frame(main_frame)
        var_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 15))
        var_frame.columnconfigure(0, weight=1)
        var_frame.rowconfigure(0, weight=1)
        
        scrollbar = ttk.Scrollbar(var_frame, orient=tk.VERTICAL)
        self.var_listbox = tk.Listbox(var_frame, selectmode=tk.MULTIPLE, 
                                      yscrollcommand=scrollbar.set, height=10)
        scrollbar.config(command=self.var_listbox.yview)
        
        self.var_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # Populate variable list
        for var_name in self.variable_map.values():
            self.var_listbox.insert(tk.END, var_name)
        
        # Select defaults
        default_vars = ["Actual ET (mm/day)", "Potential ET (mm/day)", 
                       "Biomass Production (kg/ha/day)", "Top Soil Moisture (m³/m³)"]
        for i, var in enumerate(self.variable_map.values()):
            if var in default_vars:
                self.var_listbox.selection_set(i)
        
        # Section 4: Action Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=6, column=0, columnspan=2, pady=(0, 15))
        
        ttk.Button(button_frame, text="📊 Generate Time-Series", 
                  command=self.generate_timeseries, style='Accent.TButton').grid(
            row=0, column=0, padx=5)
        ttk.Button(button_frame, text="💾 Export to CSV", 
                  command=self.export_csv).grid(row=0, column=1, padx=5)
        ttk.Button(button_frame, text="🗺️ Preview Raster", 
                  command=self.preview_raster).grid(row=0, column=2, padx=5)
        ttk.Button(button_frame, text="🔄 Refresh", 
                  command=self.refresh).grid(row=0, column=3, padx=5)
        
        # Section 5: Status
        self.status_label = ttk.Label(main_frame, text="Ready", foreground="green")
        self.status_label.grid(row=7, column=0, columnspan=2, sticky=tk.W)
    
    def update_geometry_ui(self):
        """Show/hide geometry input based on selection"""
        if self.geometry_type.get() == "point":
            self.point_frame.grid()
            self.polygon_frame.grid_remove()
        else:
            self.point_frame.grid_remove()
            self.polygon_frame.grid()
    
    def select_folder(self):
        """Select POI folder containing date subfolders"""
        folder = filedialog.askdirectory(title="Select POI Folder (e.g., POI_1)")
        if folder:
            self.poi_folder = folder
            self.folder_label.config(text=folder, foreground="black")
            self.scan_dates()
    
    def scan_dates(self):
        """Scan for available date folders"""
        if not self.poi_folder:
            return
        
        self.available_dates = []
        try:
            for item in sorted(os.listdir(self.poi_folder)):
                item_path = os.path.join(self.poi_folder, item)
                if os.path.isdir(item_path) and item.startswith('2'):
                    # Check if output folder exists
                    output_folder = os.path.join(item_path, 'output')
                    if os.path.exists(output_folder):
                        # Parse date from folder name (YYYY_MM_DD_L8 or YYYY_MM_DD_L9)
                        parts = item.split('_')
                        if len(parts) >= 4:
                            date_str = f"{parts[0]}-{parts[1]}-{parts[2]}"
                            satellite = parts[3]
                            self.available_dates.append({
                                'folder': item,
                                'date': date_str,
                                'satellite': satellite,
                                'output_path': output_folder
                            })
            
            self.status_label.config(
                text=f"Found {len(self.available_dates)} processed dates", 
                foreground="green")
        except Exception as e:
            messagebox.showerror("Error", f"Error scanning dates: {str(e)}")
    
    def load_polygon(self):
        """Load polygon from GeoJSON or Shapefile"""
        file_path = filedialog.askopenfilename(
            title="Select Polygon File",
            filetypes=[("GeoJSON", "*.geojson *.json"), ("Shapefile", "*.shp"), 
                      ("All files", "*.*")]
        )
        
        if file_path:
            try:
                # Open with OGR
                datasource = ogr.Open(file_path)
                if datasource is None:
                    raise Exception("Could not open file")
                
                layer = datasource.GetLayer(0)
                feature = layer.GetNextFeature()
                
                if feature is None:
                    raise Exception("No features in file")
                
                geometry = feature.GetGeometryRef()
                
                # Store geometry
                self.polygon_coords = geometry
                self.polygon_label.config(
                    text=f"{os.path.basename(file_path)} ({geometry.GetGeometryName()})",
                    foreground="black"
                )
                
                datasource = None
            except Exception as e:
                messagebox.showerror("Error", f"Error loading polygon: {str(e)}")
    
    def extract_point_value(self, raster_path, lon, lat):
        """Extract value at point from raster with coordinate transformation"""
        try:
            ds = gdal.Open(raster_path)
            if ds is None:
                return None
            
            # Get raster projection
            raster_srs = osr.SpatialReference()
            raster_srs.ImportFromWkt(ds.GetProjection())
            
            # Create lat/lon coordinate system (EPSG:4326)
            latlon_srs = osr.SpatialReference()
            latlon_srs.ImportFromEPSG(4326)
            
            # Create coordinate transformation
            transform = osr.CoordinateTransformation(latlon_srs, raster_srs)
            
            # Transform lon/lat to raster coordinate system
            x, y, _ = transform.TransformPoint(lat, lon)  # Note: TransformPoint takes (lat, lon)
            
            # Get geotransform
            gt = ds.GetGeoTransform()
            
            # Convert transformed coordinates to pixel coordinates
            px = int((x - gt[0]) / gt[1])
            py = int((y - gt[3]) / gt[5])
            
            # Check bounds
            if px < 0 or py < 0 or px >= ds.RasterXSize or py >= ds.RasterYSize:
                ds = None
                return None
            
            # Read value
            band = ds.GetRasterBand(1)
            value = band.ReadAsArray(px, py, 1, 1)[0, 0]
            
            ds = None
            
            # Check for nodata
            if value < -9000:
                return None
            
            return float(value)
        except Exception as e:
            print(f"Error extracting point value: {e}")
            return None
    
    def extract_polygon_stats(self, raster_path, geometry, method="mean"):
        """Extract statistics from raster within polygon with coordinate transformation"""
        try:
            ds = gdal.Open(raster_path)
            if ds is None:
                return None
            
            # Get raster projection
            raster_srs = osr.SpatialReference()
            raster_srs.ImportFromWkt(ds.GetProjection())
            
            # Get geometry projection (assume EPSG:4326 if not set)
            geom_srs = geometry.GetSpatialReference()
            if geom_srs is None:
                geom_srs = osr.SpatialReference()
                geom_srs.ImportFromEPSG(4326)
            
            # Transform geometry to raster coordinate system if needed
            if not geom_srs.IsSame(raster_srs):
                transform = osr.CoordinateTransformation(geom_srs, raster_srs)
                geometry = geometry.Clone()
                geometry.Transform(transform)
            
            # Create memory raster for mask
            mem_driver = gdal.GetDriverByName('MEM')
            mem_ds = mem_driver.Create('', ds.RasterXSize, ds.RasterYSize, 1, gdal.GDT_Byte)
            mem_ds.SetGeoTransform(ds.GetGeoTransform())
            mem_ds.SetProjection(ds.GetProjection())
            
            # Create temporary layer for rasterization
            mem_layer_driver = ogr.GetDriverByName('Memory')
            mem_layer_ds = mem_layer_driver.CreateDataSource('')
            mem_layer = mem_layer_ds.CreateLayer('poly', raster_srs, ogr.wkbPolygon)
            
            # Add geometry to layer
            feature_defn = mem_layer.GetLayerDefn()
            feature = ogr.Feature(feature_defn)
            feature.SetGeometry(geometry)
            mem_layer.CreateFeature(feature)
            
            # Rasterize polygon
            gdal.RasterizeLayer(mem_ds, [1], mem_layer, burn_values=[1])
            
            # Read data
            mask = mem_ds.GetRasterBand(1).ReadAsArray()
            data = ds.GetRasterBand(1).ReadAsArray()
            
            # Mask data
            masked_data = np.ma.masked_where(mask == 0, data)
            masked_data = np.ma.masked_less(masked_data, -9000)  # Remove nodata
            
            ds = None
            mem_ds = None
            
            # Calculate statistic
            if masked_data.count() == 0:
                return None
            
            if method == "mean":
                return float(masked_data.mean())
            elif method == "sum":
                return float(masked_data.sum())
            elif method == "median":
                return float(np.ma.median(masked_data))
            
        except Exception as e:
            print(f"Error extracting polygon stats: {e}")
            return None
    
    def generate_timeseries(self):
        """Generate time-series plots"""
        # Validate inputs
        if not self.poi_folder or not self.available_dates:
            messagebox.showwarning("Warning", "Please select a POI folder first")
            return
        
        # Get selected variables
        selected_indices = self.var_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("Warning", "Please select at least one variable")
            return
        
        selected_vars = [list(self.variable_map.keys())[i] for i in selected_indices]
        
        # Validate geometry
        if self.geometry_type.get() == "point":
            try:
                lon = float(self.point_coords["lon"].get())
                lat = float(self.point_coords["lat"].get())
            except:
                messagebox.showwarning("Warning", "Please enter valid longitude and latitude")
                return
        else:
            if self.polygon_coords is None or not hasattr(self.polygon_coords, 'ExportToWkt'):
                messagebox.showwarning("Warning", "Please load a polygon file")
                return
        
        # Extract data
        self.status_label.config(text="Extracting time-series data...", foreground="orange")
        self.root.update()
        
        timeseries_data = {var: [] for var in selected_vars}
        dates = []
        
        for date_info in self.available_dates:
            output_folder = date_info['output_path']
            date_str = date_info['date']
            dates.append(datetime.strptime(date_str, '%Y-%m-%d'))
            
            for var in selected_vars:
                # Find raster file (search in subfolders too)
                raster_file = None
                
                # Search in all subfolders
                for root, dirs, files in os.walk(output_folder):
                    for file in files:
                        if file.endswith('.tif') and var in file:
                            raster_file = os.path.join(root, file)
                            break
                    if raster_file:
                        break
                
                if raster_file:
                    if self.geometry_type.get() == "point":
                        value = self.extract_point_value(raster_file, lon, lat)
                    else:
                        value = self.extract_polygon_stats(
                            raster_file, self.polygon_coords, 
                            self.aggregation_method.get())
                    
                    timeseries_data[var].append(value if value is not None else np.nan)
                else:
                    timeseries_data[var].append(np.nan)
        
        # Store data
        self.timeseries_data = pd.DataFrame(timeseries_data, index=dates)
        
        # Create plot
        self.plot_timeseries()
        
        self.status_label.config(text="Time-series generated successfully!", foreground="green")
    
    def plot_timeseries(self):
        """Plot time-series data"""
        if self.timeseries_data is None:
            return
        
        # Create new window for plot
        plot_window = tk.Toplevel(self.root)
        plot_window.title("SEBAL Time-Series")
        plot_window.geometry("1400x800")
        
        # Create figure with subplots
        n_vars = len(self.timeseries_data.columns)
        n_cols = min(2, n_vars)
        n_rows = (n_vars + n_cols - 1) // n_cols
        
        fig = Figure(figsize=(14, 4 * n_rows))
        
        for i, var in enumerate(self.timeseries_data.columns):
            ax = fig.add_subplot(n_rows, n_cols, i + 1)
            
            # Plot data
            data = self.timeseries_data[var].dropna()
            if len(data) > 0:
                ax.plot(data.index, data.values, marker='o', linestyle='-', linewidth=2, 
                       markersize=6, label=self.variable_map[var])
                ax.set_xlabel('Date', fontsize=10)
                ax.set_ylabel(self.variable_map[var], fontsize=10)
                ax.set_title(self.variable_map[var], fontsize=12, fontweight='bold')
                ax.grid(True, alpha=0.3)
                
                # Format x-axis dates
                import matplotlib.dates as mdates
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
                ax.xaxis.set_major_locator(mdates.AutoDateLocator())
                
                # Rotate and align date labels
                plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
                
                # Ensure all dates are visible
                fig.autofmt_xdate()
            else:
                ax.text(0.5, 0.5, 'No data available', ha='center', va='center', 
                       transform=ax.transAxes)
        
        fig.tight_layout()
        
        # Embed in tkinter
        canvas = FigureCanvasTkAgg(fig, master=plot_window)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Add toolbar
        from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk
        toolbar = NavigationToolbar2Tk(canvas, plot_window)
        toolbar.update()
    
    def export_csv(self):
        """Export time-series data to CSV"""
        if self.timeseries_data is None:
            messagebox.showwarning("Warning", "Please generate time-series first")
            return
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if file_path:
            try:
                # Rename columns to display names
                df_export = self.timeseries_data.copy()
                df_export.columns = [self.variable_map[col] for col in df_export.columns]
                df_export.index.name = 'Date'
                df_export.to_csv(file_path)
                messagebox.showinfo("Success", f"Data exported to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Error exporting CSV: {str(e)}")
    
    def preview_raster(self):
        """Preview a raster from selected date"""
        if not self.available_dates:
            messagebox.showwarning("Warning", "No dates available")
            return
        
        # Create preview window
        preview_window = tk.Toplevel(self.root)
        preview_window.title("Raster Preview")
        preview_window.geometry("900x700")
        
        # Date selection
        frame = ttk.Frame(preview_window, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="Select Date:").grid(row=0, column=0, sticky=tk.W, padx=5)
        date_var = tk.StringVar()
        date_combo = ttk.Combobox(frame, textvariable=date_var, width=30, state='readonly')
        date_combo['values'] = [f"{d['date']} ({d['satellite']})" for d in self.available_dates]
        date_combo.grid(row=0, column=1, padx=5)
        date_combo.current(0)
        
        ttk.Label(frame, text="Select Variable:").grid(row=0, column=2, sticky=tk.W, padx=5)
        var_var = tk.StringVar()
        var_combo = ttk.Combobox(frame, textvariable=var_var, width=30, state='readonly')
        var_combo['values'] = list(self.variable_map.values())
        var_combo.grid(row=0, column=3, padx=5)
        var_combo.current(0)
        
        # Canvas for raster
        canvas_frame = ttk.Frame(frame)
        canvas_frame.grid(row=1, column=0, columnspan=4, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)
        
        def show_raster():
            selected_idx = date_combo.current()
            selected_var_name = var_combo.get()
            var_key = [k for k, v in self.variable_map.items() if v == selected_var_name][0]
            
            output_folder = self.available_dates[selected_idx]['output_path']
            
            # Find raster (search in subfolders)
            raster_file = None
            for root, dirs, files in os.walk(output_folder):
                for file in files:
                    if file.endswith('.tif') and var_key in file:
                        raster_file = os.path.join(root, file)
                        break
                if raster_file:
                    break
            
            if not raster_file:
                messagebox.showwarning("Warning", f"Raster not found for {selected_var_name}")
                return
            
            # Read and plot
            ds = gdal.Open(raster_file)
            data = ds.GetRasterBand(1).ReadAsArray()
            data = np.ma.masked_less(data, -9000)
            ds = None
            
            # Clear previous plot
            for widget in canvas_frame.winfo_children():
                widget.destroy()
            
            # Create plot
            fig = Figure(figsize=(9, 7))
            ax = fig.add_subplot(111)
            im = ax.imshow(data, cmap='RdYlGn', interpolation='nearest')
            ax.set_title(f"{selected_var_name}\n{self.available_dates[selected_idx]['date']}", 
                        fontsize=12, fontweight='bold')
            fig.colorbar(im, ax=ax, label=selected_var_name)
            
            canvas = FigureCanvasTkAgg(fig, master=canvas_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        ttk.Button(frame, text="Show Raster", command=show_raster).grid(
            row=0, column=4, padx=5)
        
        # Show initial raster
        show_raster()
    
    def refresh(self):
        """Refresh the application"""
        self.timeseries_data = None
        self.available_dates = []
        if self.poi_folder:
            self.scan_dates()
        self.status_label.config(text="Refreshed", foreground="green")


def main():
    root = tk.Tk()
    app = SEBALVisualizer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
