# Earth Engine Data Explorer

A Django web application for browsing, searching, and downloading data from Google Earth Engine.

## Features

- Browse available datasets in Google Earth Engine
- Search datasets by name, tags, or providers
- View detailed metadata including bands, coverage area, and temporal information
- Download data directly or export to Google Drive
- Visualize dataset coverage on interactive maps

## Prerequisites

- Python 3.8+
- Google Earth Engine account with authentication
- Google Cloud Project with Earth Engine API enabled

## Installation

1. Clone the repository:

```bash
git clone https://github.com/yourusername/earthenginedemo.git
cd earthenginedemo
```

2. Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows, use: venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Set up the database:

```bash
python manage.py migrate
```

5. Load dataset catalog (optional, but recommended):

```bash
python manage.py load_gee_catalog
```

## Google Earth Engine Authentication

1. Install the Earth Engine CLI:

```bash
pip install earthengine-api
```

2. Authenticate with Earth Engine:

```bash
earthengine authenticate
```

3. Initialize Earth Engine with your project ID:

Visit https://code.earthengine.google.com/ and find your project ID in the settings.

## Configuration

Create a `.env` file in the project root:
