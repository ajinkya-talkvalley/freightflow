from django.contrib import admin

from .models import Driver, Route, Shipment, Telemetry


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ('route_code', 'origin_city', 'destination_city', 'distance_km', 'typical_duration_hours')
    list_filter = ('origin_city', 'destination_city')
    search_fields = ('route_code', 'origin_city', 'destination_city')
    ordering = ('route_code',)


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ('employee_id', 'full_name', 'license_number', 'phone', 'hire_date')
    list_filter = ('hire_date',)
    search_fields = ('employee_id', 'full_name', 'license_number', 'phone')
    ordering = ('employee_id',)


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = (
        'tracking_number', 'status', 'origin_city', 'destination_city',
        'shipment_date', 'estimated_delivery', 'actual_delivery', 'is_delayed',
    )
    list_filter = ('status', 'origin_city', 'destination_city', 'is_delayed')
    search_fields = ('tracking_number', 'customer_email', 'carrier_tracking_number')
    autocomplete_fields = ('driver', 'route')
    date_hierarchy = 'shipment_date'
    ordering = ('-shipment_date',)


@admin.register(Telemetry)
class TelemetryAdmin(admin.ModelAdmin):
    list_display = ('truck_id', 'tracking_number', 'lat', 'lng', 'timestamp')
    list_filter = ('truck_id',)
    search_fields = ('truck_id', 'tracking_number')
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)
