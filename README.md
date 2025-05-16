# Google Earth Engine Thin Client

A Django web application for browsing, searching, and downloading data from Google Earth Engine.

## Prerequisites

- Python 3.8+
- Google Earth Engine account with authentication
- Google Cloud Project with Earth Engine API enabled

## Installation

1. Clone the repository:

```bash
git clone git@github.com:Thrcle421/thin-client-for-google-earth-engine.git
cd earthenginedemo
```

2. Create a virtual environment:

There are several ways to create a Python virtual environment depending on your operating system and preferences:

### Using venv (built-in Python module)

```bash
# Create the virtual environment
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On macOS and Linux:
source venv/bin/activate
```

### Using conda (if you have Anaconda or Miniconda installed)

```bash
# Create the virtual environment
conda create -n earthengine-env python=3.12.4

# Activate the virtual environment
# On Windows, macOS, and Linux:
conda activate earthengine-env
```

### Using virtualenv (requires installation)

```bash
# Install virtualenv if not already installed
pip install virtualenv

# Create the virtual environment
virtualenv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On macOS and Linux:
source venv/bin/activate
```

To deactivate the virtual environment when you're done, simply run:

```bash
deactivate  # For venv and virtualenv
# OR
conda deactivate  # For conda environments
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Set up the database and load data:

```bash
# Step 1: Create database migrations
python manage.py makemigrations

# Step 2: Apply migrations to the database
python manage.py migrate

# Step 3: Load Earth Engine dataset catalog
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

## Running the Application

Start the development server:

```bash
python manage.py runserver
```
