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
    def get_available_variables(dataset_id: str) -> List[Dict[str, str]]:
        """Get available variables for a dataset"""
        try:
            info = ee.data.getInfo(dataset_id)
            if not info or 'bands' not in info:
                return []

            return [{
                'id': band['id'],
                'name': band.get('name', band['id']),
                'description': band.get('description', ''),
                'units': band.get('units', '')
            } for band in info['bands']]

        except Exception as e:
            print(f"Error getting variables: {e}")
            return []

    @staticmethod
    def get_dataset_temporal_info(dataset_id: str) -> Dict[str, Any]:
        """Get temporal information for a dataset"""
        try:
            collection = ee.ImageCollection(dataset_id)
            dates = collection.aggregate_array('system:time_start').getInfo()

            if not dates:
                return {}

            start_date = datetime.fromtimestamp(min(dates) / 1000)
            end_date = datetime.fromtimestamp(max(dates) / 1000)

            return {
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': end_date.strftime('%Y-%m-%d'),
                'temporal_resolution': collection.first().get('temporal_resolution').getInfo()
            }

        except Exception as e:
            print(f"Error getting temporal info: {e}")
            return {}

    @staticmethod
    def search_datasets(query: str = None, tags: Optional[List[str]] = None) -> List[Dict]:
        """
        Search for datasets in Earth Engine catalog using the database
        Only search by ID (fuzzy match) and tags
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

            # 转换为字典列表
            results = []
            for dataset in datasets:
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

            return results

        except Exception as e:
            print(f"Error searching datasets: {e}")
            return []

    @staticmethod
    def get_dataset_info(dataset_id: str) -> Optional[Dict]:
        """Get detailed information about a specific dataset"""
        try:
            info = ee.data.getInfo(dataset_id)
            if not info:
                return None

            return {
                'id': dataset_id,
                'title': info.get('title', dataset_id),
                'description': info.get('description', ''),
                'provider': info.get('provider', ''),
                'temporal_resolution': info.get('cadence', ''),
                'spatial_resolution': info.get('resolution', ''),
                'tags': info.get('tags', []),
                'bands': [
                    {
                        'name': band['id'],
                        'description': band.get('description', ''),
                        'units': band.get('units', ''),
                        'data_type': band.get('data_type', '')
                    }
                    for band in info.get('bands', [])
                ],
                'documentation_url': f'https://developers.google.com/earth-engine/datasets/catalog/{dataset_id.replace("/", "_")}'
            }

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
