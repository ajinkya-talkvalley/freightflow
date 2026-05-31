"""Views for the shipments app."""
from datetime import date

from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from .forms import ShipmentFilterForm
from .models import Shipment, ShipmentStatus, Telemetry


def dashboard(request):
    today = date.today()
    counts = {
        'total': Shipment.objects.count(),
        'in_transit': Shipment.objects.filter(status=ShipmentStatus.IN_TRANSIT).count(),
        'out_for_delivery': Shipment.objects.filter(status=ShipmentStatus.OUT_FOR_DELIVERY).count(),
        'delivered_today': Shipment.objects.filter(
            status=ShipmentStatus.DELIVERED, actual_delivery=today
        ).count(),
        'delayed': Shipment.objects.filter(status=ShipmentStatus.DELAYED).count(),
        'pending': Shipment.objects.filter(status=ShipmentStatus.PENDING).count(),
        'cancelled': Shipment.objects.filter(status=ShipmentStatus.CANCELLED).count(),
    }
    recent = Shipment.objects.select_related('driver', 'route').order_by('-shipment_date')[:10]
    return render(request, 'shipments/dashboard.html', {
        'counts': counts,
        'recent': recent,
    })


def shipment_list(request):
    form = ShipmentFilterForm(request.GET or None)
    qs = Shipment.objects.select_related('driver', 'route').all()
    if form.is_valid():
        q = form.cleaned_data.get('q')
        status = form.cleaned_data.get('status')
        if q:
            qs = qs.filter(tracking_number__icontains=q)  # portable case-insensitive
        if status:
            qs = qs.filter(status=status)
    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'shipments/shipment_list.html', {
        'form': form,
        'page': page,
    })


def shipment_detail(request, tracking_number):
    shipment = get_object_or_404(
        Shipment.objects.select_related('driver', 'route'),
        tracking_number=tracking_number,
    )
    return render(request, 'shipments/shipment_detail.html', {
        'shipment': shipment,
    })


def live_tracking(request):
    return render(request, 'shipments/live_tracking.html')


def telemetry_latest(request):
    """GET /api/telemetry/latest/ — JSON per Schema Spec §6.6.

    Returns the most recent telemetry row per truck_id. Portable across
    SQLite and PostgreSQL — no DISTINCT ON, no window functions.
    """
    truck_ids = list(Telemetry.objects.values_list('truck_id', flat=True).distinct())
    trucks = []
    for tid in truck_ids:
        row = Telemetry.objects.filter(truck_id=tid).order_by('-timestamp', '-id').first()
        if row is None:
            continue
        trucks.append({
            'truck_id': row.truck_id,
            'tracking_number': row.tracking_number,
            'lat': float(row.lat),
            'lng': float(row.lng),
            'timestamp': row.timestamp.strftime('%Y-%m-%dT%H:%M:%SZ'),
        })
    return JsonResponse({'trucks': trucks})
