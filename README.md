# Earth Engine Dataset Downloader

A Django-based web application for searching, exploring, and downloading Google Earth Engine datasets.

## Features

- Search and browse Earth Engine datasets catalog
- Filter datasets by tags and keywords
- Visualize dataset details including bands, coverage area, and temporal range
- Download data to Google Drive or directly to your device
- Draw and specify regions of interest on interactive maps
- Real-time task status monitoring for large downloads
- Download time series data to Google Drive with custom folder names

## Getting Started

### Prerequisites

- Python 3.8+
- Google Earth Engine account
- Django 4.2+

### Installation

1. Clone the repository

```bash
git clone <repository-url>
cd earthenginedemo
```

2. Install dependencies

```bash
pip install -r requirements.txt
```

3. Run migrations

```bash
python manage.py migrate
```

4. Start the development server

```bash
python manage.py runserver
```

5. Access the application at http://localhost:8000

### Authentication

1. Before using the application, you need to complete Google Earth Engine authentication
2. Click on "Authenticate" button on the main page
3. Follow the instructions to authenticate with your GEE account
4. Enter your Project ID when prompted

## Usage

### Searching Datasets

1. Use the search bar to find datasets by ID or description
2. Filter results using tags on the sidebar
3. Click on a dataset to view details and download options

### Downloading Data

1. Select a dataset from search results
2. Choose the variable/band you want to download
3. Set the date range (if applicable)
4. Draw a region of interest on the map
5. Set export parameters:
   - Scale (meters)
   - Export format (GeoTIFF, TFRecord)
   - Google Drive folder name (where files will be saved)
   - Download method (Google Drive or Direct Download)
6. Click "Start Download" to begin the process
7. For Google Drive exports, monitor task status on the page
8. For direct downloads, the file will start downloading when ready

### Using the download_ee_to_drive Function

You can also use the utility function directly in your code:

```python
from geedownloader.ee_download import download_ee_to_drive

# Example usage:
download_ee_to_drive(
    start_date='1990-01-01',
    end_date='1990-01-03',
    collection_name="ECMWF/ERA5/DAILY",
    band_name="minimum_2m_air_temperature",
    folder_name="tmin_1990",
    file_prefix="tmin",
    convert_kelvin=True,
    project_name="your-gee-project-id"  # Optional: Specify your GEE project ID
)
```

#### Parameters

| Parameter       | Description                                            | Default                 |
|-----------------|--------------------------------------------------------|-------------------------|
| start_date      | Start date (YYYY-MM-DD)                                | Required                |
| end_date        | End date (YYYY-MM-DD)                                  | Required                |
| collection_name | Earth Engine collection ID                             | "ECMWF/ERA5/DAILY"      |
| band_name       | Name of the band to export                             | "minimum_2m_air_temperature" |
| folder_name     | Name of the Google Drive folder for exports            | "EE_exports"            |
| file_prefix     | Prefix for the exported filenames                      | "data"                  |
| region          | Region of interest (ee.Geometry)                       | Global bounds           |
| scale           | Resolution in meters                                   | Native resolution       |
| convert_kelvin  | Whether to convert temperatures from Kelvin to Celsius | False                   |
| project_name    | Google Earth Engine project ID                         | None                    |

## Parameters

### Download Options

| Parameter   | Description                                     | Default       |
| ----------- | ----------------------------------------------- | ------------- |
| Variable    | The dataset band/variable to download           | Required      |
| Start Date  | Beginning of temporal range                     | Required      |
| End Date    | End of temporal range                           | Required      |
| Scale       | Resolution in meters                            | 1000          |
| Format      | Export format (GeoTIFF, TFRecord)               | GeoTIFF       |
| Folder Name | Google Drive folder where exports will be saved | GEE-Downloads |
| Region      | Area of interest drawn on map                   | Required      |

## Development

### Project Structure

- `geedownloader/` - Main application
  - `templates/` - HTML templates
  - `static/` - CSS, JS, and other static files
  - `services.py` - Earth Engine API integration
  - `views.py` - Django views and endpoints
  - `models.py` - Data models
  - `ee_download.py` - Earth Engine direct download utilities

### API Endpoints

- `/search/` - Search datasets
- `/dataset/<id>/` - Get dataset details
- `/download/` - Start Google Drive export
- `/download-local/` - Direct download (smaller files)
- `/task-status/<task_id>/` - Check export task status

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Google Earth Engine for providing access to petabytes of geospatial data
- The Django community for the excellent web framework
- All contributors to this project
