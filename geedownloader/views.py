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
from .models import DatasetTag


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

def dataset_catalog(request):
    """Dataset catalog view with improved search and filtering"""
    return render(request, 'geedownloader/catalog.html')


@require_http_methods(["GET"])
def search_datasets(request):
    """Enhanced dataset search endpoint with pagination and sorting"""
    query = request.GET.get('query', '').lower()
    tags = request.GET.getlist('tags', None)
    page = int(request.GET.get('page', 1))
    sort = request.GET.get('sort', 'relevance')
    per_page = int(request.GET.get('per_page', 10))

    if not GEEService.initialize():
        return JsonResponse({
            'error': 'Earth Engine authentication required',
            'auth_required': True
        }, status=401)

    try:
        # 获取数据集列表
        datasets = GEEService.search_datasets(query, tags)

        # 应用排序
        if sort != 'relevance':  # relevance是默认排序，由搜索结果决定
            if sort == 'title':
                datasets.sort(key=lambda x: x['title'].lower())
            elif sort == 'provider':
                datasets.sort(key=lambda x: (x['provider'] or '').lower())
            elif sort == 'updated':
                datasets.sort(key=lambda x: x.get(
                    'updated_at', ''), reverse=True)

        # 应用分页
        paginator = Paginator(datasets, per_page)
        page_obj = paginator.get_page(page)

        return JsonResponse({
            'datasets': list(page_obj),
            'total_pages': paginator.num_pages,
            'current_page': page,
            'total_count': paginator.count
        })

    except Exception as e:
        return JsonResponse({
            'error': str(e),
            'message': 'Error occurred while searching datasets'
        }, status=500)


@require_http_methods(["GET"])
def dataset_detail(request, dataset_id):
    """Enhanced dataset detail view"""
    if not GEEService.initialize():
        return render(request, 'geedownloader/auth_modal.html')

    dataset_info = GEEService.get_dataset_info(dataset_id)
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
    result = GEEService.get_task_status(task_id)
    return JsonResponse(result, status=400 if result.get('error') else 200)


@require_http_methods(["GET"])
@require_ee_auth
def get_dataset_variables(request, dataset_id):
    """Get available variables for a dataset"""
    variables = GEEService.get_available_variables(dataset_id)
    return JsonResponse({'variables': variables})


@require_http_methods(["GET"])
@require_ee_auth
def get_dataset_temporal_info(request, dataset_id):
    """Get temporal information for a dataset"""
    info = GEEService.get_dataset_temporal_info(dataset_id)
    return JsonResponse(info)


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

        # Validate required parameters
        required_fields = ['dataset_id', 'variable',
                           'start_date', 'end_date', 'region']
        missing_fields = [
            field for field in required_fields if not data.get(field)]
        if missing_fields:
            return JsonResponse({
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }, status=400)

        # Validate date range
        if not GEEService.validate_date_range(
            data['dataset_id'],
            data['start_date'],
            data['end_date']
        ):
            return JsonResponse({
                'error': 'Selected date range is not available for this dataset'
            }, status=400)

        # Validate variable availability
        variables = GEEService.get_available_variables(data['dataset_id'])
        if not any(v['id'] == data['variable'] for v in variables):
            return JsonResponse({
                'error': 'Selected variable is not available for this dataset'
            }, status=400)

        # Validate region format
        try:
            region = json.loads(data['region'])
            if not region.get('features'):
                raise ValueError('Invalid region format')
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({
                'error': 'Invalid region format'
            }, status=400)

        # Start download task
        result = GEEService.start_download_task(
            dataset_id=data['dataset_id'],
            start_date=data['start_date'],
            end_date=data['end_date'],
            variable=data['variable'],
            region=data['region'],
            export_format=data.get('format', 'GeoTIFF'),
            scale=int(data.get('scale', 1000))
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
    tags = DatasetTag.objects.filter(name__icontains=search_term).values('name')
    return JsonResponse(list(tags), safe=False)
