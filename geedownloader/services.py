import ee
import geojson
from typing import Dict, List, Optional, Any
from datetime import datetime
import subprocess
import json
import os
from pathlib import Path
from django.http import HttpRequest
from .models import DatasetMetadata, DatasetBand
import requests
from django.db.models import Q


class GEEService:
    """Provides methods for interacting with Google Earth Engine API"""

    _project_id = None

    @classmethod
    def set_project_id(cls, project_id: str):
        """Set the project ID for future operations"""
        cls._project_id = project_id

    @staticmethod
    def initialize() -> bool:
        """Initialize Earth Engine and check authentication status"""
        try:
            ee.Authenticate()
            ee.Initialize()
            return True
        except Exception as e:
            print(f"Error initializing Earth Engine: {e}")
            return False

    @staticmethod
    def start_authentication() -> Dict[str, Any]:
        """Start the Earth Engine authentication process

        Returns:
            Dict containing status and message of the authentication process
        """
        try:
            # Get user's home directory
            home_dir = str(Path.home())
            credentials_path = os.path.join(
                home_dir, '.config', 'earthengine', 'credentials')

            # Remove existing credentials if any
            if os.path.exists(credentials_path):
                os.remove(credentials_path)

            # Run authentication command
            cmd = ['earthengine', 'authenticate']
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"Authentication command failed: {result.stderr}")
                return {
                    'status': 'error',
                    'message': result.stderr or 'Failed to start authentication process'
                }

            return {
                'status': 'success',
                'message': 'Authentication process started. Please check your terminal to complete the process.'
            }

        except Exception as e:
            print(f"Authentication error: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }

    @staticmethod
    def check_auth_status(request: HttpRequest) -> Dict[str, Any]:
        """Check Earth Engine authentication status"""
        try:
            try:
                data = json.loads(request.body)
                project_id = data.get('project_id')
            except json.JSONDecodeError:
                project_id = None

            if not project_id:
                return {
                    'authenticated': False,
                    'status': 'error',
                    'message': 'Please enter your GEE Project ID'
                }

            try:
                ee.Initialize(project=project_id)
                GEEService.set_project_id(project_id)

                test = ee.Number(1).add(2)
                result = test.getInfo()

                if result == 3:
                    print("Authentication successful!")
                    return {
                        'authenticated': True,
                        'status': 'success'
                    }
                else:
                    return {
                        'authenticated': False,
                        'status': 'error',
                        'message': 'API test failed. Please try authenticating again.'
                    }

            except ee.EEException as e:
                error_msg = str(e).lower()
                if "not registered" in error_msg:
                    return {
                        'authenticated': False,
                        'status': 'error',
                        'message': 'Please complete your registration at https://signup.earthengine.google.com/'
                    }
                elif "not authorized" in error_msg:
                    return {
                        'authenticated': False,
                        'status': 'error',
                        'message': 'Please authenticate at https://code.earthengine.google.com first.'
                    }
                else:
                    print(f"API call error: {e}")
                    return {
                        'authenticated': False,
                        'status': 'error',
                        'message': f'Authentication failed: {str(e)}'
                    }

        except Exception as e:
            print(f"Authentication check failed: {str(e)}")
            return {
                'authenticated': False,
                'status': 'error',
                'message': f'Authentication check failed: {str(e)}'
            }

    @staticmethod
    def start_download_task(
        dataset_id: str,
        start_date: str,
        end_date: str,
        variable: str,
        region: str,
        export_format: str = 'GeoTIFF',
        scale: int = 1000,
        folder_name: str = 'GEE-Downloads',
        project_name: str = None
    ) -> Dict[str, Any]:
        """
        Start a download task to export dataset to Google Drive

        Parameters:
        -----------
        dataset_id : str
            Earth Engine dataset ID (collection or image)
        start_date : str
            Start date in format 'YYYY-MM-DD'
        end_date : str
            End date in format 'YYYY-MM-DD'
        variable : str
            Band/variable name to export
        region : str
            GeoJSON string representing the export region
        export_format : str
            Export format (e.g., 'GeoTIFF', 'TFRecord')
        scale : int
            Resolution in meters
        folder_name : str
            Name of the folder in Google Drive where files will be saved
        project_name : str
            Google Earth Engine project ID

        Returns:
        --------
        Dict with task information or error message
        """
        try:
            print(
                f"\n=== Starting download task for {dataset_id} with project {project_name} ===")

            # Ensure Earth Engine is initialized with the correct project ID
            if project_name:
                try:
                    ee.Initialize(project=project_name)
                    print(
                        f"Re-initialized Earth Engine with project ID: {project_name}")

                    # Test the project access with a simple operation
                    try:
                        test = ee.Number(1).add(2).getInfo()
                        if test != 3:
                            return {'error': f"Failed to initialize Earth Engine with project ID: {project_name}. Test operation failed."}
                    except ee.ee_exception.EEException as test_error:
                        error_msg = str(test_error)
                        if "Permission denied" in error_msg or "not found" in error_msg or "does not have required permission" in error_msg:
                            return {'error': f"Permission error: Caller does not have required permission to use project {project_name}. Please check your project ID."}
                        else:
                            print(f"Test operation error: {test_error}")
                except Exception as e:
                    print(
                        f"Error initializing Earth Engine with project {project_name}: {e}")
                    error_msg = str(e)
                    if "Permission denied" in error_msg or "not found" in error_msg or "does not have required permission" in error_msg:
                        return {'error': f"Permission error: Caller does not have required permission to use project {project_name}. Please check your project ID."}
                    # Continue execution as it might already be initialized

            # Parse the region
            try:
                if isinstance(region, str):
                    try:
                        region_geom = geojson.loads(region)
                    except Exception as e:
                        print(f"Error parsing region as JSON: {e}")
                        return {'error': f"Invalid region format: {str(e)}"}
                else:
                    region_geom = region

                # Verify the region structure
                if not region_geom or not isinstance(region_geom, dict) or not region_geom.get('features'):
                    print("Region missing features or invalid structure")
                    return {'error': "Invalid region format: missing features or invalid structure"}

                # Create EE geometry from the first feature's geometry
                ee_geometry = ee.Geometry(
                    region_geom['features'][0]['geometry'])
                print(f"Region geometry parsed successfully")
            except Exception as e:
                print(f"Error parsing region geometry: {e}")
                return {'error': f"Invalid region format: {str(e)}"}

            # Check dataset access before proceeding
            access_check = GEEService.check_dataset_access(
                dataset_id, project_name)
            if not access_check['success']:
                error_msg = access_check.get('message', access_check['error'])
                print(f"Access error: {error_msg}")
                return {'error': error_msg}

            # Validate date range
            if not GEEService.validate_date_range(dataset_id, start_date, end_date):
                print(
                    f"Date range validation failed for {start_date} to {end_date}")
                return {'error': 'Selected date range is not available for this dataset'}

            # Create a list of dates for time series if needed
            single_date = start_date == end_date

            # Determine if this is an image or image collection
            is_collection = False
            try:
                dataset_type = access_check['info'].get('type', '')
                is_collection = dataset_type == 'IMAGE_COLLECTION'
                print(f"Dataset type: {dataset_type}")
            except Exception as e:
                print(f"Error determining dataset type: {e}")

            # Try first as image, then as collection if that fails
            image = None
            try:
                if not is_collection:
                    # For single image datasets
                    print(f"Processing as single image: {dataset_id}")
                    image = ee.Image(dataset_id).select(variable)
                else:
                    # For image collections
                    print(
                        f"Processing as image collection from {start_date} to {end_date}")
                    collection = ee.ImageCollection(dataset_id)
                    filtered_data = collection.filterDate(
                        start_date, end_date).select(variable)

                    # Get collection size
                    collection_size = filtered_data.size().getInfo()
                    print(f"Found {collection_size} images in date range")

                    if collection_size == 0:
                        date_info = GEEService.get_dataset_temporal_info(
                            dataset_id, project_name)
                        available_range = ""
                        if date_info.get('start_date') and date_info.get('end_date'):
                            available_range = f" Data is available from {date_info.get('start_date')} to {date_info.get('end_date')}."

                        return {
                            'error': f'No data available for the selected date range ({start_date} to {end_date}).{available_range} Please try a different date range.'
                        }

                    # Compute mean image (or use more appropriate reducer if needed)
                    image = filtered_data.mean()
            except Exception as e:
                print(f"Error processing dataset: {e}")
                return {'error': f"Failed to process dataset: {str(e)}"}

            # Format the output name
            try:
                if isinstance(dataset_id, str) and '/' in dataset_id:
                    filename_base = dataset_id.split('/')[-1]
                else:
                    filename_base = str(dataset_id).replace('/', '_')

                date_suffix = start_date
                if start_date != end_date:
                    date_suffix = f"{start_date}_to_{end_date}"

                output_name = f"{filename_base}_{variable}_{date_suffix}"
                print(f"Output filename: {output_name}")
            except Exception as e:
                print(f"Error formatting output name: {e}")
                output_name = f"earthengine_export_{variable}"

            # Create and start the export task
            try:
                print(
                    f"Starting export to folder '{folder_name}' with format '{export_format}'")
                task = ee.batch.Export.image.toDrive(
                    image=image,
                    description=output_name,
                    folder=folder_name,
                    region=ee_geometry,
                    scale=scale,
                    crs='EPSG:4326',
                    fileFormat=export_format,
                    maxPixels=1e13
                )

                task.start()

                # Ensure task.id is a string
                task_id = str(task.id) if hasattr(task, 'id') else "unknown"
                print(f"Successfully started export task with ID: {task_id}")

                # Return task information with the folder name included
                return {
                    'task_id': task_id,
                    'status': 'STARTED',
                    'description': output_name,
                    'folder': folder_name,
                    'filename': f"{output_name}.{export_format.lower()}"
                }
            except Exception as e:
                print(f"Error creating or starting export task: {e}")
                return {'error': f'Failed to start export task: {str(e)}'}

        except Exception as e:
            print(f"Error in start_download_task: {e}")
            import traceback
            traceback.print_exc()
            return {'error': str(e)}

    @staticmethod
    def get_task_status(task_id: str, project_name: str = None) -> Dict[str, Any]:
        """
        Get the status of a download task

        Parameters:
        -----------
        task_id : str
            The Earth Engine task ID to check
        project_name : str, optional
            The Earth Engine project ID to use

        Returns:
        --------
        Dict containing status information:
            - status: Task state (e.g., READY, RUNNING, COMPLETED, FAILED)
            - progress: Percentage completion (0-100)
            - error: Error message if task failed
        """
        try:
            print(f"Getting status for task ID: {task_id}")

            # Ensure Earth Engine is initialized with the correct project ID
            if project_name:
                try:
                    ee.Initialize(project=project_name)
                    print(
                        f"Re-initialized Earth Engine with project ID: {project_name} for task status")
                except Exception as e:
                    print(
                        f"Error initializing Earth Engine with project {project_name}: {e}")
                    # Continue execution as it might already be initialized with default project

            # Explicitly reinitialize with "ee-thrcle421" if no project provided
            # This is a fallback to ensure we're using the known working project
            elif not project_name:
                try:
                    ee.Initialize(project="ee-thrcle421")
                    print(
                        "Re-initialized Earth Engine with default project ID: ee-thrcle421")
                except Exception as e:
                    print(
                        f"Error initializing Earth Engine with default project: {e}")

            # Get the task list from Earth Engine
            tasks = ee.data.getTaskList()
            print(f"Total tasks: {len(tasks)}")

            # Print task structure for debugging
            if tasks and len(tasks) > 0:
                print(f"First task type: {type(tasks[0])}")
                print(
                    f"First task keys: {tasks[0].keys() if isinstance(tasks[0], dict) else 'Not a dict'}")
                print(f"First task: {tasks[0]}")

            # Make sure task_id is a string
            if not isinstance(task_id, str):
                task_id = str(task_id)

            # Find the matching task
            task = None
            for t in tasks:
                try:
                    if isinstance(t, dict) and 'id' in t and str(t['id']) == task_id:
                        task = t
                        break
                except Exception as e:
                    print(f"Error comparing task: {e}")
                    continue

            # Handle case where task is not found
            if not task:
                print(f"Task with ID {task_id} not found")
                return {
                    'status': 'FAILED',
                    'progress': 0,
                    'error': 'Task not found or may have expired'
                }

            print(f"Found task: {task}")

            # Extract state and progress with fallbacks for safety
            state = 'UNKNOWN'
            progress = 0
            error_msg = None

            if isinstance(task, dict):
                state = task.get('state', 'UNKNOWN')

                # Calculate progress based on state
                if state == 'COMPLETED':
                    progress = 100
                elif state == 'FAILED' or state == 'CANCELLED':
                    progress = 0
                else:
                    # For READY, RUNNING, etc. states
                    progress = task.get('progress', 0)
                    if progress is None:
                        progress = 0
                    elif isinstance(progress, float):
                        # Convert from fraction to percentage
                        progress = int(progress * 100)

                # Get error message if available
                error_msg = task.get('error_message', None)

            # Build result dictionary
            result = {
                'status': state,
                'progress': progress,
                'error': error_msg
            }
            print(f"Returning result: {result}")
            return result

        except Exception as e:
            print(f"Error getting task status: {e}")
            import traceback
            traceback.print_exc()
            return {
                'status': 'FAILED',
                'progress': 0,
                'error': f"Error checking task status: {str(e)}"
            }

    @staticmethod
    def get_available_variables(dataset_id: str, project_name: str = None) -> Dict:
        """Get available variables for a dataset"""
        try:
            print(
                f"\n=== Getting variables for dataset: {dataset_id} with project {project_name} ===")

            # Ensure Earth Engine is initialized with the correct project ID
            if project_name:
                try:
                    ee.Initialize(project=project_name)
                    print(
                        f"Re-initialized Earth Engine with project ID: {project_name} for getting variables")
                except Exception as e:
                    print(
                        f"Error initializing Earth Engine with project {project_name}: {e}")
                    # Continue execution as it might already be initialized

            access_check = GEEService.check_dataset_access(
                dataset_id, project_name)
            if not access_check['success']:
                error_message = access_check.get(
                    'message', access_check['error'])
                print(f"Access error: {error_message}")
                return {
                    'variables': [{
                        'id': 'default',
                        'name': 'Default Band',
                        'description': f'Error accessing dataset: {error_message}'
                    }],
                    'description': f'Error: {error_message}',
                    'tags': [],
                    'title': dataset_id,
                    'error': error_message
                }

            basic_info = access_check['info']
            print(f"Basic info type: {type(basic_info)}")

            description = basic_info.get('description', '')
            if not description and 'properties' in basic_info:
                description = basic_info['properties'].get('description', '')

            title = basic_info.get('title', '')
            if not title and 'properties' in basic_info:
                title = basic_info['properties'].get('title', '')

            tags = []
            if 'keywords' in basic_info:
                tags.extend(basic_info['keywords'])
            if 'properties' in basic_info and 'keywords' in basic_info['properties']:
                tags.extend(basic_info['properties']['keywords'])
            tags = list(set(tags))

            bands_info = basic_info.get('bands', [])
            print(f"\nOriginal bands_info from basic_info: {bands_info}")

            if not bands_info and basic_info.get('type') == 'IMAGE_COLLECTION':
                print("\nTrying to get bands from first image of collection...")
                try:
                    first_image = ee.ImageCollection(dataset_id).first()
                    first_image_info = first_image.getInfo()
                    bands_info = first_image_info.get('bands', [])
                    print(f"Bands info from first image: {bands_info}")
                except Exception as e:
                    print(f"Error getting bands from first image: {e}")

            if not isinstance(bands_info, list):
                print(
                    f"\nWarning: bands_info is not a list, it's a {type(bands_info)}")
                bands_info = []

            if not bands_info:
                print(f"\nNo bands found for {dataset_id}, returning default")
                bands_info = [{
                    'id': 'default',
                    'name': 'Default Band',
                    'description': 'Default band for this dataset'
                }]

            print(f"\nFinal bands_info: {bands_info}")
            result = {
                'variables': bands_info,
                'description': description,
                'tags': tags,
                'title': title
            }
            print(f"\nFinal response: {result}")
            return result

        except ee.ee_exception.EEException as e:
            error_msg = str(e)
            print(f"Earth Engine API error: {error_msg}")
            if "permission" in error_msg.lower():
                return {
                    'variables': [{
                        'id': 'default',
                        'name': 'Default Band',
                        'description': f'Permission error: {error_msg}'
                    }],
                    'description': f'Permission error: You do not have access to this dataset.',
                    'tags': [],
                    'title': dataset_id,
                    'error': error_msg
                }
            else:
                return {
                    'variables': [{
                        'id': 'default',
                        'name': 'Default Band',
                        'description': f'Earth Engine error: {error_msg}'
                    }],
                    'description': f'Error: {error_msg}',
                    'tags': [],
                    'title': dataset_id,
                    'error': error_msg
                }

        except Exception as e:
            import traceback
            print(f"Error getting variables: {e}")
            print(traceback.format_exc())
            return {
                'variables': [{
                    'id': 'default',
                    'name': 'Default Band',
                    'description': 'Error occurred while fetching band information: ' + str(e)
                }],
                'description': '',
                'tags': [],
                'title': ''
            }

    @staticmethod
    def get_dataset_temporal_info(dataset_id: str, project_name: str = None) -> Dict:
        """Get temporal information for a dataset"""
        try:
            print(
                f"\n=== Getting temporal info for dataset: {dataset_id} with project {project_name} ===")

            # Ensure Earth Engine is initialized with the correct project ID
            if project_name:
                try:
                    ee.Initialize(project=project_name)
                    print(
                        f"Re-initialized Earth Engine with project ID: {project_name} for temporal info")
                except Exception as e:
                    print(
                        f"Error initializing Earth Engine with project {project_name}: {e}")
                    # Continue execution as it might already be initialized

            try:
                image = ee.Image(dataset_id)
                date = image.get('system:time_start').getInfo()
                if date:
                    date_str = datetime.fromtimestamp(
                        date / 1000).strftime('%Y-%m-%d')
                    return {
                        'start_date': date_str,
                        'end_date': date_str
                    }
            except Exception as e:
                print(f"Not a single image or error: {e}")

            try:
                dataset = ee.ImageCollection(dataset_id)
                dates = dataset.aggregate_array('system:time_start').getInfo()

                if dates and len(dates) > 0:
                    start_date = datetime.fromtimestamp(
                        min(dates) / 1000).strftime('%Y-%m-%d')
                    end_date = datetime.fromtimestamp(
                        max(dates) / 1000).strftime('%Y-%m-%d')

                    return {
                        'start_date': start_date,
                        'end_date': end_date
                    }
            except Exception as e:
                print(f"Not an image collection or error: {e}")

            return {
                'start_date': None,
                'end_date': None
            }
        except Exception as e:
            print(f"Error getting temporal info: {e}")
            import traceback
            traceback.print_exc()
            return {
                'start_date': None,
                'end_date': None,
                'error': str(e)
            }

    @staticmethod
    def search_datasets(query: str = None, tags: Optional[List[str]] = None,
                        page: int = 1, per_page: int = 10) -> Dict[str, Any]:
        """
        Search for datasets in Earth Engine catalog using the database
        Only search by ID (fuzzy match) and tags with pagination support
        """
        try:
            datasets = DatasetMetadata.objects.all()

            if query:
                datasets = datasets.filter(id__icontains=query)

            if tags:
                for tag in tags:
                    datasets = datasets.filter(tags__name__icontains=tag)

            total_count = datasets.count()

            start = (page - 1) * per_page
            end = start + per_page

            paginated_datasets = datasets[start:end]

            results = []
            for dataset in paginated_datasets:
                results.append({
                    'id': dataset.id,
                    'title': dataset.title,
                    'description': dataset.description,
                    'provider': dataset.provider,
                    'temporal_resolution': dataset.temporal_resolution,
                    'spatial_resolution': dataset.spatial_resolution,
                    'start_date': dataset.start_date.strftime('%Y-%m-%d') if dataset.start_date else '',
                    'end_date': dataset.end_date.strftime('%Y-%m-%d') if dataset.end_date else '',
                    'tags': [tag.name for tag in dataset.tags.all()],
                    'thumbnail_url': dataset.thumbnail_url,
                    'documentation_url': dataset.documentation_url,
                    'asset_url': dataset.asset_url
                })

            total_pages = (total_count + per_page - 1) // per_page

            return {
                'datasets': results,
                'total_count': total_count,
                'total_pages': total_pages,
                'current_page': page
            }

        except Exception as e:
            print(f"Error searching datasets: {e}")
            return {
                'datasets': [],
                'total_count': 0,
                'total_pages': 0,
                'current_page': page
            }

    @staticmethod
    def get_dataset_info(dataset_id: str) -> Optional[Dict]:
        """Get detailed information about a specific dataset"""
        try:
            basic_info = ee.data.getInfo(dataset_id)
            if not basic_info:
                print(f"Could not get basic info for dataset: {dataset_id}")
                return None

            dataset_type = basic_info.get('type', '')
            print(f"Dataset type: {dataset_type}")

            info = {
                'id': dataset_id,
                'type': dataset_type,
                'properties': basic_info.get('properties', {}),
                'description': basic_info.get('description', '')
            }

            if not info['description'] and 'properties' in basic_info and 'description' in basic_info['properties']:
                info['description'] = basic_info['properties'].get(
                    'description', '')

            info['title'] = basic_info.get('title', dataset_id)
            if not info['title'] and 'properties' in basic_info and 'title' in basic_info['properties']:
                info['title'] = basic_info['properties'].get(
                    'title', dataset_id)

            if 'bands' in basic_info:
                info['bands'] = basic_info['bands']
            else:
                info['bands'] = []

            if dataset_type == 'IMAGE':
                try:
                    image = ee.Image(dataset_id)

                    if not info['bands']:
                        bands_info = []
                        band_names = image.bandNames().getInfo()
                        for band_name in band_names:
                            bands_info.append({
                                'id': band_name,
                                'data_type': image.select(band_name).dataType().getInfo()
                            })
                        info['bands'] = bands_info

                    system_time = image.get('system:time_start').getInfo()
                    if system_time:
                        info['start_time'] = datetime.fromtimestamp(
                            system_time / 1000).strftime('%Y-%m-%d')
                        info['end_time'] = info['start_time']

                    info['geometry'] = image.geometry().bounds().getInfo()

                except Exception as e:
                    print(f"Error getting additional info for image: {e}")

            elif dataset_type == 'IMAGE_COLLECTION':
                try:
                    collection = ee.ImageCollection(dataset_id)
                    first_image = collection.first()

                    if not info['bands']:
                        bands_info = []
                        if first_image:
                            first_image_info = first_image.getInfo()
                            if 'bands' in first_image_info:
                                info['bands'] = first_image_info['bands']
                            else:
                                band_names = first_image.bandNames().getInfo()
                                for band_name in band_names:
                                    bands_info.append({
                                        'id': band_name,
                                        'data_type': first_image.select(band_name).dataType().getInfo()
                                    })
                                info['bands'] = bands_info

                    info['size'] = collection.size().getInfo()

                    time_range = collection.reduceColumns(
                        reducer=ee.Reducer.minMax(),
                        selectors=['system:time_start']
                    ).getInfo()

                    if 'min' in time_range and 'max' in time_range:
                        info['start_time'] = datetime.fromtimestamp(
                            time_range['min'] / 1000).strftime('%Y-%m-%d')
                        info['end_time'] = datetime.fromtimestamp(
                            time_range['max'] / 1000).strftime('%Y-%m-%d')

                    if first_image:
                        info['geometry'] = first_image.geometry().bounds().getInfo()

                except Exception as e:
                    print(
                        f"Error getting additional info for image collection: {e}")

            # In your get_dataset_info method, add this as a fallback
            if 'geometry' not in info:
                try:
                    # Try to get basic geometry from dataset providers or documentation
                    if 'properties' in basic_info and 'providers' in basic_info['properties'] and len(basic_info['properties']['providers']) > 0:
                        provider = basic_info['properties']['providers'][0]
                        if 'extent' in provider:
                            extent = provider['extent']
                            # Create a simple bounding box from the extent
                            if 'spatial' in extent and 'coordinates' in extent['spatial']:
                                coords = extent['spatial']['coordinates']
                                info['geometry'] = {
                                    'type': 'Polygon',
                                    'coordinates': [coords]
                                }

                    # If we still don't have geometry, create a default world bounding box
                    if 'geometry' not in info:
                        print(
                            f"Creating default world geometry for {dataset_id}")
                        # Simple world bounding box [-180, -90, 180, 90]
                        info['geometry'] = {
                            'type': 'Polygon',
                            'coordinates': [[
                                [-180, -90], [180, -90], [180,
                                                          90], [-180, 90], [-180, -90]
                            ]]
                        }
                except Exception as e:
                    print(f"Error creating fallback geometry: {e}")
                    # Create a simple world bounding box as last resort
                    info['geometry'] = {
                        'type': 'Polygon',
                        'coordinates': [[
                            [-180, -90], [180, -90], [180,
                                                      90], [-180, 90], [-180, -90]
                        ]]
                    }

            print(f"Final dataset info: {info}")
            return info

        except Exception as e:
            print(f"Error in get_dataset_info: {e}")
            return None

    @staticmethod
    def validate_date_range(dataset_id: str, start_date: str, end_date: str) -> bool:
        """Validate if the selected date range is available for the dataset"""
        try:
            basic_info = ee.data.getInfo(dataset_id)
            if basic_info and basic_info.get('type') == 'IMAGE':
                print("Dataset is a single image, date range validation not needed")
                return True

            try:
                dataset = ee.ImageCollection(dataset_id)
                dates = dataset.aggregate_array('system:time_start').getInfo()

                if not dates or len(dates) == 0:
                    print(
                        "No dates found in dataset, assuming date validation is not applicable")
                    return True

                dataset_start = datetime.fromtimestamp(min(dates) / 1000)
                dataset_end = datetime.fromtimestamp(max(dates) / 1000)

                selected_start = datetime.strptime(start_date, '%Y-%m-%d')
                selected_end = datetime.strptime(end_date, '%Y-%m-%d')

                print(f"Dataset date range: {dataset_start} to {dataset_end}")
                print(
                    f"Selected date range: {selected_start} to {selected_end}")

                is_valid = dataset_start <= selected_end and selected_start <= dataset_end
                print(f"Date range validation result: {is_valid}")
                return is_valid
            except Exception as e:
                print(f"Error checking date range for ImageCollection: {e}")
                try:
                    image = ee.Image(dataset_id)
                    print("Dataset loaded as Image, date range validation not needed")
                    return True
                except Exception as img_error:
                    print(f"Also failed to load as Image: {img_error}")
                    return True

        except Exception as e:
            print(f"Error validating date range: {e}")
            return True

    @staticmethod
    def get_download_url(
        dataset_id: str,
        start_date: str,
        end_date: str,
        variable: str,
        region: str,
        export_format: str = 'GeoTIFF',
        scale: int = 1000,
        folder_name: str = 'GEE-Downloads',
        project_name: str = None
    ) -> Dict[str, Any]:
        """Generate a URL for direct download of the selected dataset"""
        try:
            print(
                f"\n=== Getting download URL for {dataset_id} with project {project_name} ===")

            # Ensure Earth Engine is initialized with the correct project ID
            if project_name:
                try:
                    ee.Initialize(project=project_name)
                    print(
                        f"Re-initialized Earth Engine with project ID: {project_name}")
                except Exception as e:
                    print(
                        f"Error initializing Earth Engine with project {project_name}: {e}")
                    # Continue execution as it might already be initialized

            # Prepare image directly without checking dataset access first
            try:
                # Try as image first
                image = None
                try:
                    image = ee.Image(dataset_id).select(variable)
                    dataset_type = 'IMAGE'
                except Exception:
                    # Try as image collection
                    dataset = ee.ImageCollection(dataset_id)
                    filtered_data = dataset.filterDate(
                        start_date, end_date).select(variable)

                    # Check if there's data
                    collection_size = filtered_data.size().getInfo()
                    if collection_size == 0:
                        return {'error': 'No data available for the selected parameters'}

                    # Get the mean image
                    image = filtered_data.mean()
                    dataset_type = 'IMAGE_COLLECTION'

                # Process the region
                try:
                    # If region is already a JSON string
                    if isinstance(region, str):
                        region_geom = geojson.loads(region)
                    else:
                        region_geom = region

                    ee_geometry = ee.Geometry(
                        region_geom['features'][0]['geometry'])
                except Exception as e:
                    print(f"Error processing region: {e}")
                    return {'error': f'Invalid region format: {str(e)}'}

                # Create filename
                if isinstance(dataset_id, str) and '/' in dataset_id:
                    filename_base = dataset_id.split('/')[-1]
                else:
                    filename_base = str(dataset_id).replace('/', '_')

                output_name = f'{filename_base}_{variable}_{start_date}_{end_date}'

                # Try to get download URL with reduced max pixels
                url = image.getDownloadURL({
                    'name': output_name,
                    'region': ee_geometry,
                    'scale': scale,
                    'crs': 'EPSG:4326',
                    'format': export_format.lower(),
                    'maxPixels': 1e7  # Reduce this value to improve chances of success
                })

                return {
                    'success': True,
                    'url': url,
                    'filename': f'{output_name}.{export_format.lower()}',
                    'folder': folder_name
                }

            except Exception as e:
                error_msg = str(e)
                print(f"Error in direct access approach: {error_msg}")

                # If it's a permission error, return specific error
                if "permission" in error_msg.lower():
                    return {
                        'error': f'Permission error: You may not have access to download this dataset. Try using the Earth Engine Code Editor directly. Error: {error_msg}'
                    }
                else:
                    return {'error': f'Failed to process or download dataset: {error_msg}'}

        except Exception as e:
            print(f"Error in get_download_url: {e}")
            return {'error': str(e)}

    @staticmethod
    def check_dataset_access(dataset_id: str, project_name: str = None) -> Dict[str, Any]:
        """Check if the user has permission to access the specified dataset"""
        try:
            # Ensure Earth Engine is initialized with the correct project ID
            if project_name:
                try:
                    ee.Initialize(project=project_name)
                    print(
                        f"Re-initialized Earth Engine with project ID: {project_name} for dataset access check")
                except Exception as e:
                    print(
                        f"Error initializing Earth Engine with project {project_name}: {e}")
                    error_msg = str(e)
                    if "Permission denied" in error_msg or "not found" in error_msg or "does not have required permission" in error_msg:
                        return {
                            'success': False,
                            'error': 'Project ID error',
                            'error_type': 'permission',
                            'message': f'Permission error: Caller does not have required permission to use project {project_name}. Please check that you are using the correct project ID.'
                        }
                    # Continue execution as it might already be initialized

            # Try different approaches to access the dataset
            # First attempt: Try to load as an Image
            try:
                image = ee.Image(dataset_id)
                # Just attempt to get any property to verify access
                _ = image.bandNames().getInfo()
                return {'success': True, 'info': {'type': 'IMAGE'}}
            except Exception as img_error:
                print(f"Not an image or error: {img_error}")

            # Second attempt: Try to load as an ImageCollection
            try:
                collection = ee.ImageCollection(dataset_id)
                # Just attempt to get size to verify access
                _ = collection.size().getInfo()
                return {'success': True, 'info': {'type': 'IMAGE_COLLECTION'}}
            except Exception as coll_error:
                print(f"Not an image collection or error: {coll_error}")

            # If both approaches fail, try the original method
            basic_info = ee.data.getInfo(dataset_id)
            if basic_info:
                return {'success': True, 'info': basic_info}
            else:
                return {'success': False, 'error': 'Dataset not found or not accessible'}

        except ee.ee_exception.EEException as e:
            error_msg = str(e)
            print(f"Error accessing dataset {dataset_id}: {error_msg}")

            # Check if it's a permission error
            if "does not have required permission" in error_msg or "permission denied" in error_msg:
                return {
                    'success': False,
                    'error': 'Permission denied',
                    'error_type': 'permission',
                    'message': f'Permission error: Caller does not have required permission to use this dataset. Error: {error_msg}'
                }
            else:
                return {
                    'success': False,
                    'error': 'Unknown error',
                    'error_type': 'unknown',
                    'message': f'Error accessing dataset: {error_msg}'
                }
        except Exception as e:
            print(f"General error checking dataset access: {e}")
            return {
                'success': False,
                'error': 'Error checking dataset access',
                'message': str(e)
            }
