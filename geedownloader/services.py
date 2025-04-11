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
    def get_available_variables(dataset_id: str) -> Dict:
        """Get available variables for a dataset"""
        try:
            print(f"\n=== Getting variables for dataset: {dataset_id} ===")

            # 获取数据集的基本信息
            basic_info = ee.data.getInfo(dataset_id)
            print(f"Basic info type: {type(basic_info)}")

            if not basic_info:
                print("Error: Could not get basic info from ee.data.getInfo()")
                return {
                    'variables': [],
                    'description': '',
                    'tags': [],
                    'title': dataset_id
                }

            # 获取描述信息
            description = basic_info.get('description', '')
            if not description and 'properties' in basic_info:
                description = basic_info['properties'].get('description', '')

            # 获取标题
            title = basic_info.get('title', '')
            if not title and 'properties' in basic_info:
                title = basic_info['properties'].get('title', '')

            # 获取标签
            tags = []
            if 'keywords' in basic_info:
                tags.extend(basic_info['keywords'])
            if 'properties' in basic_info and 'keywords' in basic_info['properties']:
                tags.extend(basic_info['properties']['keywords'])
            tags = list(set(tags))  # 去重

            # 获取波段信息
            bands_info = basic_info.get('bands', [])
            print(f"\nOriginal bands_info from basic_info: {bands_info}")

            if not bands_info and basic_info.get('type') == 'IMAGE_COLLECTION':
                # 对于影像集合，尝试从第一个影像获取波段信息
                print("\nTrying to get bands from first image of collection...")
                first_image = ee.ImageCollection(dataset_id).first()
                first_image_info = first_image.getInfo()
                bands_info = first_image_info.get('bands', [])
                print(f"Bands info from first image: {bands_info}")

            # 确保bands_info是一个列表
            if not isinstance(bands_info, list):
                print(
                    f"\nWarning: bands_info is not a list, it's a {type(bands_info)}")
                bands_info = []

            # 如果没有获取到任何波段信息，返回默认波段
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
            # 获取数据集基本信息
            basic_info = ee.data.getInfo(dataset_id)
            if not basic_info:
                print(f"Could not get basic info for dataset: {dataset_id}")
                return None

            dataset_type = basic_info.get('type', '')
            print(f"Dataset type: {dataset_type}")

            # 基本信息结构，直接使用API返回的信息
            info = {
                'id': dataset_id,
                'type': dataset_type,
                'properties': basic_info.get('properties', {}),
                'description': basic_info.get('description', '')
            }

            # 如果properties中有description，且主description为空，则使用properties中的
            if not info['description'] and 'properties' in basic_info and 'description' in basic_info['properties']:
                info['description'] = basic_info['properties'].get(
                    'description', '')

            # 设置标题，优先使用API返回的title
            info['title'] = basic_info.get('title', dataset_id)
            if not info['title'] and 'properties' in basic_info and 'title' in basic_info['properties']:
                info['title'] = basic_info['properties'].get(
                    'title', dataset_id)

            # 为了兼容现有前端，添加bands字段
            if 'bands' in basic_info:
                info['bands'] = basic_info['bands']
            else:
                info['bands'] = []

            # 根据类型获取额外的信息
            if dataset_type == 'IMAGE':
                try:
                    image = ee.Image(dataset_id)

                    # 如果原始信息中没有bands，获取bands信息
                    if not info['bands']:
                        bands_info = []
                        band_names = image.bandNames().getInfo()
                        for band_name in band_names:
                            bands_info.append({
                                'id': band_name,
                                'data_type': image.select(band_name).dataType().getInfo()
                            })
                        info['bands'] = bands_info

                    # 获取时间信息
                    system_time = image.get('system:time_start').getInfo()
                    if system_time:
                        info['start_time'] = datetime.fromtimestamp(
                            system_time / 1000).strftime('%Y-%m-%d')
                        info['end_time'] = info['start_time']

                    # 获取空间范围
                    info['geometry'] = image.geometry().bounds().getInfo()

                except Exception as e:
                    print(f"Error getting additional info for image: {e}")

            elif dataset_type == 'IMAGE_COLLECTION':
                try:
                    collection = ee.ImageCollection(dataset_id)
                    first_image = collection.first()

                    # 如果原始信息中没有bands，从第一个影像获取bands信息
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

                    # 获取集合大小
                    info['size'] = collection.size().getInfo()

                    # 获取时间范围
                    time_range = collection.reduceColumns(
                        reducer=ee.Reducer.minMax(),
                        selectors=['system:time_start']
                    ).getInfo()

                    if 'min' in time_range and 'max' in time_range:
                        info['start_time'] = datetime.fromtimestamp(
                            time_range['min'] / 1000).strftime('%Y-%m-%d')
                        info['end_time'] = datetime.fromtimestamp(
                            time_range['max'] / 1000).strftime('%Y-%m-%d')

                    # 获取空间范围
                    if first_image:
                        info['geometry'] = first_image.geometry().bounds().getInfo()

                except Exception as e:
                    print(
                        f"Error getting additional info for image collection: {e}")

            print(f"Final dataset info: {info}")
            return info

        except Exception as e:
            print(f"Error in get_dataset_info: {e}")
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
