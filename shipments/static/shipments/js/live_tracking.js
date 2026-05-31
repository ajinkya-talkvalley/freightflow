// Live truck tracking — polls /api/telemetry/latest/ every 3 seconds and
// repositions one Leaflet marker per truck_id. Response shape per
// Schema Spec §6.6: {"trucks": [{truck_id, tracking_number, lat, lng, timestamp}, ...]}

(function () {
    // Southern California — encompasses the 10 canonical cities
    const SOCAL_CENTER = [33.95, -117.65];
    const map = L.map('map').setView(SOCAL_CENTER, 9);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '© OpenStreetMap contributors',
    }).addTo(map);

    const markers = {};  // truck_id -> L.Marker

    async function refresh() {
        try {
            const res = await fetch('/api/telemetry/latest/', {headers: {'Accept': 'application/json'}});
            if (!res.ok) return;
            const data = await res.json();
            const seen = new Set();
            (data.trucks || []).forEach(t => {
                seen.add(t.truck_id);
                const latlng = [t.lat, t.lng];
                if (markers[t.truck_id]) {
                    markers[t.truck_id].setLatLng(latlng);
                } else {
                    markers[t.truck_id] = L.marker(latlng).addTo(map);
                }
                markers[t.truck_id].bindPopup(
                    `<strong>${t.truck_id}</strong><br>Shipment: ${t.tracking_number}<br>${t.timestamp}`
                );
            });
            // Remove markers for trucks no longer reported
            Object.keys(markers).forEach(id => {
                if (!seen.has(id)) {
                    map.removeLayer(markers[id]);
                    delete markers[id];
                }
            });
        } catch (err) {
            console.error('telemetry refresh failed', err);
        }
    }

    refresh();
    setInterval(refresh, 3000);
})();
