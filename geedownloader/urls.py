from django.urls import path
from . import views

urlpatterns = [
    # Authentication routes
    path('', views.auth_view, name='auth'),
    path('start-auth/', views.start_auth, name='start_auth'),
    path('check-auth-status/', views.check_auth_status, name='check_auth_status'),
    path('auth_modal/', views.auth_modal_view, name='auth_modal'),

    # Dataset routes
    path('catalog/', views.dataset_catalog, name='dataset_catalog'),
    path('search/', views.search_datasets, name='search_datasets'),
    path('dataset/variables/',
         views.get_dataset_variables, name='get_dataset_variables'),
    path('dataset/temporal-info/',
         views.get_dataset_temporal_info, name='get_dataset_temporal_info'),
    path('dataset/<path:dataset_id>/',
         views.dataset_detail, name='dataset_detail'),

    # Task routes
    path('validate-dates/', views.validate_dates, name='validate_dates'),
    path('download/', views.download_dataset, name='download_dataset'),
    path('download-local/', views.download_local, name='download_local'),
    path('task-status/<str:task_id>/',
         views.get_task_status, name='get_task_status'),

    # New API routes
    path('api/tags/', views.get_tags, name='get_tags'),
    path('api/dataset/<path:dataset_id>/variables/',
         views.get_dataset_api_variables, name='get_dataset_api_variables'),
]
