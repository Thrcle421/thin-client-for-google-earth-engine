from django.core.management.base import BaseCommand
import requests
from geedownloader.models import DatasetMetadata, DatasetBand, DatasetTag
from datetime import datetime
import json


class Command(BaseCommand):
    help = 'Load GEE dataset catalog from GitHub repository into database'

    def handle(self, *args, **options):
        # 从 GitHub 获取数据目录
        catalog_url = "https://raw.githubusercontent.com/samapriya/Earth-Engine-Datasets-List/master/gee_catalog.json"
        self.stdout.write(f"Fetching catalog from {catalog_url}...")

        try:
            response = requests.get(catalog_url)
            response.raise_for_status()
            catalog_data = response.json()
        except Exception as e:
            self.stderr.write(self.style.ERROR(
                f'Failed to fetch catalog: {str(e)}'))
            return

        # 首先处理所有标签
        all_tags = set()
        for dataset in catalog_data:
            tags = dataset.get('tags', '').split(',')
            all_tags.update(tag.strip() for tag in tags if tag.strip())

        # 创建或获取所有标签
        tag_objects = {}
        for tag_name in all_tags:
            tag_obj, _ = DatasetTag.objects.get_or_create(name=tag_name)
            tag_objects[tag_name] = tag_obj

        self.stdout.write(f"Processed {len(tag_objects)} unique tags")

        # 计数器
        created_count = 0
        updated_count = 0
        error_count = 0

        # 处理每个数据集
        total_datasets = len(catalog_data)
        self.stdout.write(f"Processing {total_datasets} datasets...")

        for dataset in catalog_data:
            try:
                dataset_id = dataset.get('id')
                if not dataset_id:
                    continue

                # 转换日期格式
                start_date = None
                end_date = None
                if dataset.get('start_date'):
                    try:
                        start_date = datetime.strptime(
                            dataset['start_date'], '%Y-%m-%d').date()
                    except ValueError:
                        pass
                if dataset.get('end_date'):
                    try:
                        end_date = datetime.strptime(
                            dataset['end_date'], '%Y-%m-%d').date()
                    except ValueError:
                        pass

                # 创建或更新数据集记录
                dataset_obj, created = DatasetMetadata.objects.update_or_create(
                    id=dataset_id,
                    defaults={
                        'title': dataset.get('title', ''),
                        'description': dataset.get('description', ''),
                        'provider': dataset.get('provider', ''),

                        # 时间相关
                        'start_date': start_date,
                        'end_date': end_date,
                        'temporal_resolution': dataset.get('temporal_resolution', ''),
                        'update_frequency': dataset.get('update_frequency', ''),

                        # 空间相关
                        'spatial_resolution': dataset.get('spatial_resolution', ''),
                        'spatial_coverage': dataset.get('spatial_coverage', ''),
                        'coordinate_system': dataset.get('coordinate_system', ''),

                        # 数据访问
                        'asset_url': dataset.get('asset_url', ''),
                        'thumbnail_url': dataset.get('thumbnail_url', ''),
                        'visualization_url': dataset.get('visualization_url', ''),
                        'sample_url': dataset.get('sample_url', ''),

                        # 元数据
                        'citation': dataset.get('citation', ''),
                        'license': dataset.get('license', ''),
                        'terms_of_use_url': dataset.get('terms_of_use', ''),
                        'documentation_url': dataset.get('documentation_url', ''),

                        # 技术信息
                        'scale': dataset.get('scale', ''),
                        'data_type': dataset.get('data_type', ''),
                        'period': dataset.get('period', ''),

                        # 额外信息
                        'keywords': dataset.get('keywords', ''),
                        'family_name': dataset.get('family_name', ''),
                        'doi': dataset.get('doi', '')
                    }
                )

                # 处理标签
                dataset_tags = []
                for tag in dataset.get('tags', '').split(','):
                    tag = tag.strip()
                    if tag and tag in tag_objects:
                        dataset_tags.append(tag_objects[tag])

                # 更新数据集的标签
                dataset_obj.tags.set(dataset_tags)

                # 处理波段信息（如果有）
                if dataset.get('bands'):
                    for band_info in dataset['bands']:
                        band_name = band_info.get('id')
                        if band_name:
                            DatasetBand.objects.update_or_create(
                                dataset=dataset_obj,
                                name=band_name,
                                defaults={
                                    'description': band_info.get('description', ''),
                                    'units': band_info.get('units', ''),
                                    'data_type': band_info.get('data_type', '')
                                }
                            )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

            except Exception as e:
                error_count += 1
                self.stderr.write(
                    self.style.ERROR(f'Error processing dataset {dataset.get("id")}: {str(e)}'))

        # 输出统计信息
        self.stdout.write(self.style.SUCCESS(
            f'\nCatalog update completed:'
            f'\n- Created: {created_count}'
            f'\n- Updated: {updated_count}'
            f'\n- Errors: {error_count}'
            f'\n- Total processed: {total_datasets}'
            f'\n- Total tags: {len(tag_objects)}'
        ))
