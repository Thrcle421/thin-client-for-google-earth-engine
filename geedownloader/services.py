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
        scale: int = 1000
    ) -> Dict[str, Any]:
        """Start a download task for the specified dataset"""
        try:

            access_check = GEEService.check_dataset_access(dataset_id)
            if not access_check['success']:
                return {'error': access_check.get('message', access_check['error'])}

            basic_info = access_check['info']

            if not GEEService.validate_date_range(dataset_id, start_date, end_date):
                return {
                    'error': 'Selected date range is not available for this dataset'
                }

            try:
                region_geom = geojson.loads(region)
                ee_geometry = ee.Geometry(
                    region_geom['features'][0]['geometry'])
            except Exception as e:
                print(f"Error parsing region geometry: {e}")
                return {'error': f"Invalid region format: {str(e)}"}

            image = None
            dataset_type = basic_info.get('type', '')

            if dataset_type == 'IMAGE':
                try:
                    image = ee.Image(dataset_id).select(variable)
                except Exception as e:
                    print(f"Error selecting variable from image: {e}")
                    return {'error': f"Failed to select variable '{variable}' from image: {str(e)}"}
            else:
                try:
                    dataset = ee.ImageCollection(dataset_id)
                    filtered_data = dataset.filterDate(
                        start_date, end_date).select(variable)

                    collection_size = filtered_data.size().getInfo()
                    if collection_size == 0:
                        return {'error': 'No data available for the selected parameters'}

                    print(f"Found {collection_size} images matching criteria")

                    image = filtered_data.mean()
                except Exception as e:
                    print(f"Error processing image collection: {e}")
                    return {'error': f"Failed to process image collection: {str(e)}"}

            try:
                if isinstance(dataset_id, str) and '/' in dataset_id:
                    filename_base = dataset_id.split('/')[-1]
                else:
                    filename_base = str(dataset_id).replace('/', '_')

                output_name = f'{filename_base}_{variable}_{start_date}_{end_date}'
            except Exception as e:
                print(f"Error formatting output name: {e}")
                output_name = f'earthengine_export_{variable}'

            try:
                task = ee.batch.Export.image.toDrive(
                    image=image,
                    description=output_name,
                    folder='GEE-Downloads',
                    region=ee_geometry,
                    scale=scale,
                    crs='EPSG:4326',
                    fileFormat=export_format,
                    maxPixels=1e13
                )

                task.start()

                print(f"Successfully started export task with ID: {task.id}")

                return {
                    'task_id': task.id,
                    'status': 'STARTED',
                    'description': task.config['description']
                }
            except Exception as e:
                print(f"Error creating or starting export task: {e}")
                return {'error': f'Failed to start export task: {str(e)}'}

        except Exception as e:
            print(f"Error in start_download_task: {e}")
            return {'error': str(e)}

    @staticmethod
    def get_task_status(task_id: str) -> Dict[str, Any]:
        """Get the status of a download task"""
        try:
            tasks = ee.data.getTaskList()
            task = next((t for t in tasks if t['id'] == task_id), None)

            if not task:
                return {'error': 'Task not found'}

            return {
                'status': task['state'],
                'progress': task.get('progress', 0),
                'error': task.get('error_message', None)
            }

        except Exception as e:
            return {'error': str(e)}

    @staticmethod
    def get_available_variables(dataset_id: str) -> Dict:
        """Get available variables for a dataset"""
        try:
            print(f"\n=== Getting variables for dataset: {dataset_id} ===")

            access_check = GEEService.check_dataset_access(dataset_id)
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
    def get_dataset_temporal_info(dataset_id: str) -> Dict:
        """Get temporal information for a dataset"""
        try:
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
        scale: int = 1000
    ) -> Dict[str, Any]:
        """Generate a URL for direct download of the selected dataset"""
        try:
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
                region_geom = geojson.loads(region)
                ee_geometry = ee.Geometry(
                    region_geom['features'][0]['geometry'])

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
                    'filename': f'{output_name}.{export_format.lower()}'
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
    def check_dataset_access(dataset_id: str) -> Dict[str, Any]:
        """Check if the user has permission to access the specified dataset"""
        try:
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
                    'message': f'Caller does not have required permission to use this dataset. Error: {error_msg}'
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
