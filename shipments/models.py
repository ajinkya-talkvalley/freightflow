"""
Models for FreightFlow shipments app. Mirrors Schema Spec §1 exactly.

Critical: Telemetry.tracking_number is denormalized CharField (NOT a
ForeignKey to Shipment) for write throughput on high-frequency GPS pings.
"""
from django.db import models


# Canonical Southern California cities (Schema Spec §3.4)
CANONICAL_CITIES = (
    'Riverside',
    'San Bernardino',
    'Ontario',
    'Long Beach',
    'Los Angeles',
    'Anaheim',
    'Irvine',
    'Fontana',
    'Pomona',
    'Corona',
)
CITY_CHOICES = [(c, c) for c in CANONICAL_CITIES]


# Shipment status values (Schema Spec §3.5)
class ShipmentStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    PICKED_UP = 'PICKED_UP', 'Picked up'
    IN_TRANSIT = 'IN_TRANSIT', 'In transit'
    OUT_FOR_DELIVERY = 'OUT_FOR_DELIVERY', 'Out for delivery'
    DELIVERED = 'DELIVERED', 'Delivered'
    DELAYED = 'DELAYED', 'Delayed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class Route(models.Model):
    route_code = models.CharField(max_length=10, unique=True, db_index=True)
    origin_city = models.CharField(max_length=100, choices=CITY_CHOICES)
    destination_city = models.CharField(max_length=100, choices=CITY_CHOICES)
    distance_km = models.DecimalField(max_digits=6, decimal_places=2)
    typical_duration_hours = models.DecimalField(max_digits=4, decimal_places=2)

    class Meta:
        ordering = ['route_code']

    def __str__(self):
        return f'{self.route_code} ({self.origin_city} → {self.destination_city})'


class Driver(models.Model):
    employee_id = models.CharField(max_length=10, unique=True, db_index=True)
    full_name = models.CharField(max_length=200)
    license_number = models.CharField(max_length=20)
    phone = models.CharField(max_length=20)
    hire_date = models.DateField()

    class Meta:
        ordering = ['employee_id']

    def __str__(self):
        return f'{self.employee_id} {self.full_name}'


class Shipment(models.Model):
    tracking_number = models.CharField(max_length=15, unique=True, db_index=True)
    status = models.CharField(max_length=20, choices=ShipmentStatus.choices, db_index=True)
    origin_city = models.CharField(max_length=100, choices=CITY_CHOICES)
    destination_city = models.CharField(max_length=100, choices=CITY_CHOICES)
    weight_kg = models.DecimalField(max_digits=8, decimal_places=2)
    pieces = models.IntegerField()
    shipment_date = models.DateField()
    estimated_delivery = models.DateField()
    actual_delivery = models.DateField(null=True, blank=True)
    is_delayed = models.BooleanField(default=False)
    customer_email = models.EmailField()
    driver = models.ForeignKey(
        Driver, on_delete=models.SET_NULL, null=True, blank=True, related_name='shipments'
    )
    route = models.ForeignKey(
        Route, on_delete=models.SET_NULL, null=True, blank=True, related_name='shipments'
    )
    carrier_tracking_number = models.CharField(max_length=30, null=True, blank=True)
    # S3 key or filename — NOT an ImageField (Schema Spec §1.3).
    proof_of_delivery = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        ordering = ['-shipment_date', 'tracking_number']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['shipment_date']),
        ]

    def __str__(self):
        return f'{self.tracking_number} ({self.status})'


class Telemetry(models.Model):
    truck_id = models.CharField(max_length=10, db_index=True)
    # Denormalized — NOT a ForeignKey. See Schema Spec §1.4.
    tracking_number = models.CharField(max_length=15, db_index=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)
    timestamp = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['truck_id', '-timestamp']),
        ]

    def __str__(self):
        return f'{self.truck_id}@{self.timestamp:%Y-%m-%d %H:%M:%S}'
