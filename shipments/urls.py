from django.urls import path

from . import views

app_name = 'shipments'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('shipments/', views.shipment_list, name='shipment_list'),
    path('shipments/<str:tracking_number>/', views.shipment_detail, name='shipment_detail'),
    path('live/', views.live_tracking, name='live_tracking'),
    path('api/telemetry/latest/', views.telemetry_latest, name='telemetry_latest'),
]
