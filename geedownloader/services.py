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

    # 添加类变量来存储 project_id
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
                # 认证成功后保存 project_id
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
            # 验证日期范围
            if not GEEService.validate_date_range(dataset_id, start_date, end_date):
                return {
                    'error': 'Selected date range is not available for this dataset'
                }

            # 处理区域
            region_geom = geojson.loads(region)
            ee_geometry = ee.Geometry(region_geom['features'][0]['geometry'])

            # 获取数据集
            dataset = ee.ImageCollection(dataset_id)
            filtered_data = dataset.filterDate(
                start_date, end_date).select(variable)

            # 检查是否有数据
            if filtered_data.size().getInfo() == 0:
                return {'error': 'No data available for the selected parameters'}

            # 创建导出任务
            task = ee.batch.Export.image.toDrive(
                image=filtered_data.mean(),
                description=f'{dataset_id.split("/")[-1]}_{variable}_{start_date}_{end_date}',
                folder='GEE-Downloads',
                region=ee_geometry,
                scale=scale,
                crs='EPSG:4326',
                fileFormat=export_format,
                maxPixels=1e13
            )

            # 启动任务
            task.start()

            return {
                'task_id': task.id,
                'status': 'STARTED',
                'description': task.config['description']
            }

        except Exception as e:
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
    def get_available_variables(dataset_id: str) -> List[Dict]:
        """Get available variables for a dataset"""
        try:
            # 获取数据集信息
            info = ee.data.getInfo(dataset_id)
            print("info", info)
            if not info:
                return []

            # 提取波段信息
            variables = []

            # 检查是否有bands字段
            if 'bands' in info:
                for band in info['bands']:
                    variables.append({
                        'id': band.get('id', ''),
                        'name': band.get('id', ''),
                        'description': band.get('description', ''),
                        'units': band.get('units', '')
                    })
            # 如果没有bands字段，尝试从其他字段获取信息
            elif 'properties' in info and 'bands' in info['properties']:
                print("info['properties']['bands']",
                      info['properties']['bands'])
                # 有些数据集将bands信息存储在properties中
                for band in info['properties']['bands']:
                    variables.append({
                        'id': band.get('id', ''),
                        'name': band.get('id', ''),
                        'description': band.get('description', ''),
                        'units': band.get('units', '')
                    })
            elif 'type' in info and info['type'] == 'Image':
                # 如果是单个图像，尝试获取其波段信息
                try:
                    image = ee.Image(dataset_id)
                    band_names = image.bandNames().getInfo()
                    for band_name in band_names:
                        variables.append({
                            'id': band_name,
                            'name': band_name,
                            'description': '',
                            'units': ''
                        })
                except Exception as e:
                    print(f"Error getting band names: {e}")
            else:
                print(f"Asset {dataset_id} does not have bands information")
                # 如果无法获取波段信息，返回一个默认波段
                variables.append({
                    'id': 'default',
                    'name': 'Default Band',
                    'description': 'Default band for this dataset',
                    'units': ''
                })

            return variables
        except Exception as e:
            print(f"Error getting variables: {e}")
            # 发生错误时返回一个默认波段
            return [{
                'id': 'default',
                'name': 'Default Band',
                'description': 'Default band for this dataset',
                'units': ''
            }]

    @staticmethod
    def get_dataset_temporal_info(dataset_id: str) -> Dict:
        """Get temporal information for a dataset"""
        try:
            # 首先尝试作为单个图像处理
            try:
                image = ee.Image(dataset_id)
                date = image.get('system:time_start').getInfo()
                if date:
                    # 转换时间戳为日期字符串
                    date_str = datetime.fromtimestamp(
                        date / 1000).strftime('%Y-%m-%d')
                    return {
                        'start_date': date_str,
                        'end_date': date_str
                    }
            except Exception as e:
                print(f"Not a single image or error: {e}")

            # 如果不是单个图像，尝试作为图像集合处理
            try:
                dataset = ee.ImageCollection(dataset_id)
                dates = dataset.aggregate_array('system:time_start').getInfo()

                if dates and len(dates) > 0:
                    # 转换时间戳为日期字符串
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

            # 如果无法获取时间信息，返回空值
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
            # 获取数据集查询集
            datasets = DatasetMetadata.objects.all()

            # ID 模糊搜索
            if query:
                datasets = datasets.filter(id__icontains=query)

            # 标签过滤
            if tags:
                for tag in tags:
                    datasets = datasets.filter(tags__name__icontains=tag)

            # 计算总数
            total_count = datasets.count()

            # 计算分页
            start = (page - 1) * per_page
            end = start + per_page

            # 获取当前页的数据集
            paginated_datasets = datasets[start:end]

            # 转换为字典列表
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

            # 计算总页数
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
            info = ee.data.getInfo(dataset_id)
            if not info:
                return None

            # 构建基本的数据集信息（顶层字段）
            dataset_info = {
                'id': dataset_id,
                'name': info.get('name', ''),
                'type': info.get('type', ''),
                'start_time': info.get('startTime', ''),
                'end_time': info.get('endTime', ''),
                'update_time': info.get('updateTime', ''),
                'bands': [],
                'geometry': info.get('geometry', {}),
                'properties': {}  # 将存储所有properties内容
            }

            # 如果存在properties字段，将其所有内容复制到dataset_info['properties']
            if 'properties' in info and isinstance(info['properties'], dict):
                dataset_info['properties'] = info['properties']

                # 为了向后兼容，保留一些常用字段的直接引用
                dataset_info['title'] = info['properties'].get(
                    'title', dataset_id)
                dataset_info['description'] = info['properties'].get(
                    'description', '')
                dataset_info['provider'] = info['properties'].get(
                    'provider', '')
                dataset_info['keywords'] = info['properties'].get(
                    'keywords', [])
                # 其他常用字段...

            # 处理波段信息
            if 'bands' in info:
                for band in info['bands']:
                    band_info = {
                        'id': band.get('id', ''),
                        'data_type': band.get('dataType', {}).get('precision', ''),
                        'dimensions': band.get('grid', {}).get('dimensions', {}),
                        'crs': band.get('grid', {}).get('crsWkt', ''),
                        'transform': band.get('grid', {}).get('affineTransform', {}),
                        'pyramiding_policy': band.get('pyramidingPolicy', ''),
                        'range': band.get('dataType', {}).get('range', {})
                    }
                    dataset_info['bands'].append(band_info)

            return dataset_info

        except Exception as e:
            print(f"Error getting dataset info: {e}")
            return None

    @staticmethod
    def validate_date_range(dataset_id: str, start_date: str, end_date: str) -> bool:
        """Validate if the selected date range is available for the dataset"""
        try:
            dataset = ee.ImageCollection(dataset_id)
            dates = dataset.aggregate_array('system:time_start').getInfo()
            if not dates:
                return False

            dataset_start = datetime.fromtimestamp(min(dates) / 1000)
            dataset_end = datetime.fromtimestamp(max(dates) / 1000)

            selected_start = datetime.strptime(start_date, '%Y-%m-%d')
            selected_end = datetime.strptime(end_date, '%Y-%m-%d')

            return dataset_start <= selected_start <= dataset_end and dataset_start <= selected_end <= dataset_end

        except Exception as e:
            print(f"Error validating date range: {e}")
            return False
