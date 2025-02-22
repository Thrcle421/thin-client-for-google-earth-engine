from django.db import models

class DatasetMetadata(models.Model):
    """Dataset metadata model to store information about Earth Engine datasets"""
    id = models.CharField(max_length=255, primary_key=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    provider = models.CharField(max_length=255, blank=True)
    tags = models.ManyToManyField('DatasetTag', related_name='datasets', blank=True)
    
    # 时间相关字段
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    temporal_resolution = models.CharField(max_length=100, blank=True)
    update_frequency = models.CharField(max_length=100, blank=True)
    
    # 空间相关字段
    spatial_resolution = models.CharField(max_length=100, blank=True)
    spatial_coverage = models.CharField(max_length=255, blank=True)
    coordinate_system = models.CharField(max_length=100, blank=True)
    
    # 数据访问相关
    asset_url = models.URLField(blank=True)
    thumbnail_url = models.URLField(blank=True)
    visualization_url = models.URLField(blank=True)
    sample_url = models.URLField(blank=True)
    
    # 元数据
    citation = models.TextField(blank=True)
    license = models.CharField(max_length=255, blank=True)
    terms_of_use_url = models.URLField(blank=True)
    documentation_url = models.URLField(blank=True)
    
    # 技术信息
    scale = models.CharField(max_length=100, blank=True)
    data_type = models.CharField(max_length=100, blank=True)
    period = models.CharField(max_length=100, blank=True)
    
    # 额外信息
    keywords = models.TextField(blank=True)
    family_name = models.CharField(max_length=255, blank=True)
    doi = models.CharField(max_length=255, blank=True)
    
    # 系统字段
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['title']

    def __str__(self):
        return f"{self.title} ({self.id})"

class DatasetBand(models.Model):
    """Model to store information about dataset bands/variables"""
    dataset = models.ForeignKey(DatasetMetadata, on_delete=models.CASCADE, related_name='bands')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    units = models.CharField(max_length=100, blank=True)
    data_type = models.CharField(max_length=50, blank=True)
    min_value = models.FloatField(null=True, blank=True)
    max_value = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['name']
        unique_together = ['dataset', 'name']

    def __str__(self):
        return f"{self.name} ({self.dataset.id})"

class DatasetTag(models.Model):
    """Model to store dataset tags"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name 