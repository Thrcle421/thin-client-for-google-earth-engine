import ee
from django.shortcuts import render, redirect
from django.http import JsonResponse
import geojson
import datetime
import json
from django.views.decorators.http import require_http_methods
from .services import GEEService
from django.core.paginator import Paginator
from functools import wraps
from django.views.decorators.csrf import ensure_csrf_cookie
from .models import DatasetTag, DatasetMetadata


@ensure_csrf_cookie
def auth_view(request):
    """Earth Engine authentication page"""
    if GEEService.initialize():
        return redirect('dataset_catalog')
    return render(request, 'geedownloader/auth.html')


def require_ee_auth(view_func):
    """Decorator to check Earth Engine authentication status

    Redirects to auth page if not authenticated
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not GEEService.initialize():
            return redirect('auth')
        return view_func(request, *args, **kwargs)
    return wrapper


@ensure_csrf_cookie
def start_auth(request):
    """Start Earth Engine authentication process"""
    if request.method == 'POST':
        return JsonResponse(GEEService.start_authentication())
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})


def auth_modal_view(request):
    """Render the authentication modal template"""
    return render(request, 'geedownloader/auth_modal.html')


def dataset_catalog(request):
    """Dataset catalog view with improved search and filtering"""
    return render(request, 'geedownloader/catalog.html')


@require_http_methods(["GET"])
def search_datasets(request):
    """Enhanced dataset search endpoint with pagination and sorting"""
    query = request.GET.get('query', '')
    tags = request.GET.getlist('tags', None)
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 10))

    try:
        result = GEEService.search_datasets(query, tags, page, per_page)

        return JsonResponse(result)

    except Exception as e:
        return JsonResponse({
            'error': str(e),
            'message': 'Error occurred while searching datasets'
        }, status=500)


@require_http_methods(["GET"])
def dataset_detail(request, dataset_id):
    print("dataset_id1", dataset_id)
    """Enhanced dataset detail view"""
    dataset_info = GEEService.get_dataset_info(dataset_id)
    print("dataset_info", dataset_info)

    if not dataset_info:
        return JsonResponse({'error': 'Dataset not found'}, status=404)

    return render(request, 'geedownloader/dataset_detail.html', {
        'metadata': dataset_info
    })


@require_http_methods(["POST"])
def validate_dates(request):
    """Endpoint to validate selected date range"""
    try:
        data = json.loads(request.body)
        dataset_id = data.get('dataset_id')
        start_date = data.get('start_date')
        end_date = data.get('end_date')

        if not all([dataset_id, start_date, end_date]):
            return JsonResponse({
                'error': 'Missing required parameters'
            }, status=400)

        is_valid = GEEService.validate_date_range(
            dataset_id, start_date, end_date)
        return JsonResponse({'valid': is_valid})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_ee_auth
def download_prism(request):
    """Download PRISM dataset with specified parameters"""
    if request.method == 'POST':
        try:
            data = request.POST.dict()
            result = GEEService.start_download_task(
                **{
                    'dataset_id': data.get('dataset_id', 'OREGONSTATE/PRISM/AN81d'),
                    'start_date': data.get('start_date'),
                    'end_date': data.get('end_date'),
                    'variable': data.get('variable'),
                    'region': data.get('region'),
                    'export_format': data.get('format', 'GeoTIFF'),
                    'scale': int(data.get('scale', 1000))
                }
            )

            if result.get('error'):
                return JsonResponse({'error': result['error']}, status=400)

            return JsonResponse({
                'status': 'success',
                'message': 'Download task started. Check your Google Drive folder for results.',
                'task_id': result.get('task_id')
            })

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})


@require_http_methods(["GET"])
@require_ee_auth
def get_task_status(request, task_id):
    """Get the status of a download task"""
    print(f"\n\n==== Getting status for task ID: {task_id} ====")

    # Get project ID from request
    project_id = request.GET.get('project_id')
    if project_id:
        print(f"Using project ID from request: {project_id}")
    else:
        # Try to get from session
        project_id = request.session.get('ee_project_id')
        if project_id:
            print(f"Using project ID from session: {project_id}")
        else:
            # Default to the one we know works
            project_id = "ee-thrcle421"
            print(f"Using default project ID: {project_id}")

    # Re-initialize Earth Engine with the correct project ID
    try:
        ee.Initialize(project=project_id)
        print(f"Re-initialized Earth Engine with project ID: {project_id}")
    except Exception as e:
        print(
            f"Error initializing Earth Engine with project {project_id}: {e}")

    # Try directly with Earth Engine API
    try:
        # Get raw task list from Earth Engine
        tasks_list = ee.data.getTaskList()
        print(f"Total tasks from EE API: {len(tasks_list)}")

        # Debug for first task in list
        if tasks_list:
            print(f"First task type: {type(tasks_list[0])}")
            print(f"First task: {tasks_list[0]}")

        # Direct search without using service
        matching_task = None
        for task in tasks_list:
            try:
                # Try different ways to match the task ID
                if isinstance(task, dict) and 'id' in task and task['id'] == task_id:
                    matching_task = task
                    break
                elif isinstance(task, dict) and 'id' in task and str(task['id']) == str(task_id):
                    matching_task = task
                    break
            except Exception as e:
                print(f"Error comparing task: {e}")
                continue

        if matching_task:
            print(f"Found matching task directly: {matching_task}")
            # Construct a safe response
            try:
                state = matching_task.get('state', 'UNKNOWN') if isinstance(
                    matching_task, dict) else 'UNKNOWN'
                progress = matching_task.get('progress', 0) if isinstance(
                    matching_task, dict) else 0
                error_msg = matching_task.get('error_message', None) if isinstance(
                    matching_task, dict) else None

                response_data = {
                    'status': state,
                    'progress': progress,
                    'error': error_msg
                }
                print(f"Direct response data: {response_data}")
                return JsonResponse(response_data)
            except Exception as direct_e:
                print(f"Error building direct response: {direct_e}")
                # Continue to service method
    except Exception as ee_error:
        print(f"Direct EE API error: {ee_error}")
        # Continue to service method

    # Fallback to service method with explicit project ID
    try:
        result = GEEService.get_task_status(task_id, project_name=project_id)
        print(f"Service result: {result}")

        # Ensure result is a dictionary
        if not isinstance(result, dict):
            print(f"Result is not a dict: {type(result)}")
            result = {'status': 'FAILED', 'error': 'Invalid result format'}

        # Ensure result has status field
        if 'status' not in result and 'error' in result:
            result['status'] = 'FAILED'
        elif 'status' not in result:
            result['status'] = 'UNKNOWN'

        print(f"Final result: {result}")
        return JsonResponse(result)
    except Exception as e:
        import traceback
        print(f"Error in get_task_status: {e}")
        traceback.print_exc()
        return JsonResponse({
            'status': 'FAILED',
            'error': f"Server error: {str(e)}"
        })


@require_http_methods(["GET"])
def get_dataset_variables(request):
    """Get available variables for a dataset"""
    dataset_id = request.GET.get('dataset_id')
    if not dataset_id:
        return JsonResponse({'error': 'Missing dataset_id parameter'}, status=400)

    try:
        variables = GEEService.get_available_variables(dataset_id)
        return JsonResponse({'variables': variables})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
def get_dataset_temporal_info(request):
    """Get temporal information for a dataset"""
    dataset_id = request.GET.get('dataset_id')
    print("dataset_id2", dataset_id)
    if not dataset_id:
        return JsonResponse({'error': 'Missing dataset_id parameter'}, status=400)

    try:
        # Get project ID from request or session
        project_id = request.GET.get(
            'project_id') or request.session.get('ee_project_id')

        # If project ID is provided, try to initialize Earth Engine
        if project_id:
            try:
                ee.Initialize(project=project_id)
                print(
                    f"Initialized Earth Engine with project: {project_id} for temporal info")
            except Exception as e:
                print(f"Error initializing Earth Engine: {e}")

        # Call Earth Engine to get temporal information
        info = GEEService.get_dataset_temporal_info(dataset_id, project_id)
        return JsonResponse(info)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


def select_project(request):
    """Handle project selection"""
    if request.method == 'POST':
        project_id = request.POST.get('project_id')
        if project_id:
            request.session['ee_project_id'] = project_id
            return redirect('dataset_catalog')
    return redirect('login')


@require_http_methods(["POST"])
def download_dataset(request):
    """Dataset download endpoint with improved error handling and validation"""
    if not GEEService.initialize():
        return JsonResponse({
            'error': 'Authentication required',
            'auth_required': True
        }, status=401)

    try:
        data = json.loads(request.body)

        required_fields = ['dataset_id', 'variable',
                           'start_date', 'end_date', 'region', 'project_name']
        missing_fields = [
            field for field in required_fields if not data.get(field)]
        if missing_fields:
            return JsonResponse({
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }, status=400)

        # Re-initialize Earth Engine with the provided project ID
        try:
            ee.Initialize(project=data['project_name'])
            print(
                f"Re-initialized Earth Engine with project: {data['project_name']}")
        except Exception as e:
            print(f"Error re-initializing Earth Engine: {e}")

        if not GEEService.validate_date_range(
            data['dataset_id'],
            data['start_date'],
            data['end_date']
        ):
            return JsonResponse({
                'error': 'Selected date range is not available for this dataset'
            }, status=400)

        # Validate variable availability
        variables_result = GEEService.get_available_variables(
            data['dataset_id'])
        # Check if variables exist in the result and properly access the variables
        if 'variables' in variables_result and isinstance(variables_result['variables'], list):
            variables = variables_result['variables']
            if not any(v.get('id') == data['variable'] for v in variables):
                return JsonResponse({
                    'error': 'Selected variable is not available for this dataset'
                }, status=400)
        else:
            # If variables structure is different, skip validation to avoid errors
            print(
                f"Warning: Unexpected variables structure: {variables_result}")

        # Validate region format
        try:
            region = data['region']
            if isinstance(region, str):
                try:
                    region_obj = json.loads(region)
                    if not region_obj or not isinstance(region_obj, dict) or not region_obj.get('features'):
                        raise ValueError(
                            'Invalid region format: missing features or invalid structure')
                except json.JSONDecodeError:
                    raise ValueError(
                        'Invalid region format: not a valid JSON string')
            else:
                raise ValueError('Region must be a GeoJSON string')
        except (ValueError, AttributeError) as e:
            return JsonResponse({
                'error': f'Invalid region format: {str(e)}'
            }, status=400)

        # Start download task
        result = GEEService.start_download_task(
            dataset_id=data['dataset_id'],
            start_date=data['start_date'],
            end_date=data['end_date'],
            variable=data['variable'],
            region=region,
            export_format=data.get('format', 'GeoTIFF'),
            scale=int(data.get('scale', 1000)),
            folder_name=data.get('folder_name', 'GEE-Downloads'),
            project_name=data['project_name']  # Pass project ID
        )

        if result.get('error'):
            return JsonResponse({
                'error': result['error']
            }, status=400)

        return JsonResponse({
            'status': 'success',
            'message': 'Download task started. Check your Google Drive folder for results.',
            'task_id': result['task_id']
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': str(e),
            'message': 'Error occurred while starting download task'
        }, status=500)


def check_auth_status(request):
    """Check Earth Engine authentication status"""
    return JsonResponse(GEEService.check_auth_status(request))


def get_tags(request):
    """Get all available tags from database"""
    search_term = request.GET.get('term', '')
    tags = DatasetTag.objects.filter(
        name__icontains=search_term).values('name')
    return JsonResponse(list(tags), safe=False)


@require_http_methods(["POST"])
def download_local(request):
    """Handle local downloads by generating a direct download URL"""
    if not GEEService.initialize():
        return JsonResponse({
            'error': 'Authentication required',
            'auth_required': True
        }, status=401)

    try:
        data = json.loads(request.body)

        # Validate required parameters
        required_fields = ['dataset_id', 'variable',
                           'start_date', 'end_date', 'region', 'project_name']
        missing_fields = [
            field for field in required_fields if not data.get(field)]
        if missing_fields:
            return JsonResponse({
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }, status=400)

        # Re-initialize Earth Engine with the provided project ID
        try:
            ee.Initialize(project=data['project_name'])
            print(
                f"Re-initialized Earth Engine with project: {data['project_name']}")
        except Exception as e:
            print(f"Error re-initializing Earth Engine: {e}")

        # Validate region format
        try:
            # region should be a GeoJSON string, but let's verify
            region = data['region']
            if isinstance(region, str):
                try:
                    region_obj = json.loads(region)
                    if not region_obj or not isinstance(region_obj, dict) or not region_obj.get('features'):
                        raise ValueError(
                            'Invalid region format: missing features or invalid structure')
                except json.JSONDecodeError:
                    raise ValueError(
                        'Invalid region format: not a valid JSON string')
            else:
                raise ValueError('Region must be a GeoJSON string')
        except (ValueError, AttributeError) as e:
            return JsonResponse({
                'error': f'Invalid region format: {str(e)}'
            }, status=400)

        # Get download URL
        result = GEEService.get_download_url(
            dataset_id=data['dataset_id'],
            start_date=data['start_date'],
            end_date=data['end_date'],
            variable=data['variable'],
            region=region,
            export_format=data.get('format', 'GeoTIFF'),
            scale=int(data.get('scale', 1000)),
            folder_name=data.get('folder_name', 'GEE-Downloads'),
            project_name=data['project_name']  # Pass project ID
        )

        if 'error' in result:
            return JsonResponse({
                'error': result['error']
            }, status=400)

        return JsonResponse(result)

    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': str(e),
            'message': 'Error occurred while generating download URL'
        }, status=500)


@require_http_methods(["GET"])
def get_dataset_api_variables(request, dataset_id):
    """API endpoint to get dataset variables including description and tags"""
    if not dataset_id:
        return JsonResponse({'error': 'Missing dataset_id parameter'}, status=400)

    try:
        # Get project ID from request or session
        project_id = request.GET.get(
            'project_id') or request.session.get('ee_project_id')

        # If project ID is provided, try to initialize Earth Engine
        if project_id:
            try:
                ee.Initialize(project=project_id)
                print(f"Initialized Earth Engine with project: {project_id}")
            except Exception as e:
                print(f"Error initializing Earth Engine: {e}")

        result = GEEService.get_available_variables(dataset_id, project_id)
        return JsonResponse(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
def reinitialize_ee(request):
    """Reinitialize Earth Engine Authentication"""
    try:
        # Try to get project_id from request body
        try:
            data = json.loads(request.body)
            project_id = data.get('project_id')
        except json.JSONDecodeError:
            # Try to get from form data
            project_id = request.POST.get('project_id')

        # If project_id not provided, try to get from session
        if not project_id:
            project_id = request.session.get('ee_project_id')

        if not project_id:
            return JsonResponse({
                'success': False,
                'message': 'Missing project_id parameter'
            }, status=400)

        # Save project_id to session
        request.session['ee_project_id'] = project_id

        # Reinitialize Earth Engine
        ee.Authenticate()
        ee.Initialize(project=project_id)

        # Test connection
        test = ee.Number(1).add(2).getInfo()
        if test == 3:
            return JsonResponse({
                'success': True,
                'message': 'Earth Engine authentication successful',
                'project_id': project_id
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Earth Engine authentication test failed'
            }, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': f'Failed to reinitialize Earth Engine: {str(e)}'
        }, status=500)


@require_http_methods(["POST"])
@require_ee_auth
def ee_download_to_drive(request):
    """API endpoint for downloading Earth Engine data directly to Google Drive using the download_ee_to_drive utility"""
    try:
        data = json.loads(request.body)

        # Required parameters
        required_fields = ['start_date', 'end_date']
        missing_fields = [
            field for field in required_fields if not data.get(field)]
        if missing_fields:
            return JsonResponse({
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }, status=400)

        # Optional parameters with defaults
        collection_name = data.get('collection_name', "ECMWF/ERA5/DAILY")
        band_name = data.get('band_name', "minimum_2m_air_temperature")
        folder_name = data.get('folder_name', "EE_exports")
        file_prefix = data.get('file_prefix', "data")
        convert_kelvin = data.get('convert_kelvin', False)
        project_name = data.get('project_name')

        # Process region
        region = None
        if data.get('region'):
            try:
                region_geom = data.get('region')
                if isinstance(region_geom, str):
                    region_geom = json.loads(region_geom)

                if 'features' in region_geom:
                    region = ee.Geometry(
                        region_geom['features'][0]['geometry'])
                else:
                    region = ee.Geometry(region_geom)
            except Exception as e:
                return JsonResponse({
                    'error': f'Invalid region format: {str(e)}'
                }, status=400)

        # Process scale
        scale = None
        if data.get('scale'):
            try:
                scale = int(data.get('scale'))
            except (ValueError, TypeError):
                return JsonResponse({
                    'error': 'Scale must be a number'
                }, status=400)

        # Import the download function
        from .ee_download import download_ee_to_drive

        # Execute the download
        task_ids = download_ee_to_drive(
            start_date=data.get('start_date'),
            end_date=data.get('end_date'),
            collection_name=collection_name,
            band_name=band_name,
            folder_name=folder_name,
            file_prefix=file_prefix,
            region=region,
            scale=scale,
            convert_kelvin=convert_kelvin,
            project_name=project_name
        )

        return JsonResponse({
            'success': True,
            'message': f'Download tasks started. Check your Google Drive folder "{folder_name}".',
            'task_ids': task_ids,
            'folder_name': folder_name
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': str(e),
            'message': 'Error occurred while starting download tasks'
        }, status=500)
