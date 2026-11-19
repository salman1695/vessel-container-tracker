// File 2: frontend/map.js (Dedicated Map & Sea Route Module)

let map = null;
let mapLayerGroup = null;
let standardTileLayer = null;
let satelliteTileLayer = null;
let isSatelliteMode = false;

function initMap() {
  if (map) return;
  map = L.map('map').setView([20, 85], 3);

  standardTileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 18
  });

  satelliteTileLayer = L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    {
      attribution: '&copy; Esri World Imagery',
      maxZoom: 18
    }
  );

  standardTileLayer.addTo(map);

  // Free OpenSeaMap Nautical Overlay (Sea lanes, ports, buoys)
  L.tileLayer('https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenSeaMap'
  }).addTo(map);

  mapLayerGroup = L.layerGroup().addTo(map);
}

function toggleMapLayer() {
  initMap();
  const btn = document.getElementById('mapLayerToggleBtn');
  if (!isSatelliteMode) {
    map.removeLayer(standardTileLayer);
    satelliteTileLayer.addTo(map);
    isSatelliteMode = true;
    if (btn) btn.textContent = '🗺️ Standard Map';
  } else {
    map.removeLayer(satelliteTileLayer);
    standardTileLayer.addTo(map);
    isSatelliteMode = false;
    if (btn) btn.textContent = '🛰️ Satellite View';
  }
}

function renderSeaMap({ seaRoutePath, coords, vesselName, vesselImo, originPort, destPort, formatDateFn }) {
  initMap();
  setTimeout(() => {
    map.invalidateSize();
    mapLayerGroup.clearLayers();
    const bounds = [];

    const pathPoints = (seaRoutePath || []).map(p => [p.lat, p.lng]);
    if (pathPoints.length > 0) {
      L.polyline(pathPoints, {
        color: '#0284c7',
        weight: 3.5,
        dashArray: '7, 7',
        opacity: 0.95
      }).addTo(mapLayerGroup);

      pathPoints.forEach(pt => bounds.push(pt));

      // Origin Port Marker (POL)
      L.circleMarker(pathPoints[0], {
        radius: 8,
        color: '#ffffff',
        weight: 2,
        fillColor: '#10b981',
        fillOpacity: 1
      })
        .bindPopup(`<b>Origin (POL):</b> ${originPort || 'Start'}`)
        .addTo(mapLayerGroup);

      // Destination Port Marker (POD)
      L.circleMarker(pathPoints[pathPoints.length - 1], {
        radius: 8,
        color: '#ffffff',
        weight: 2,
        fillColor: '#f43f5e',
        fillOpacity: 1
      })
        .bindPopup(`<b>Destination (POD):</b> ${destPort || 'End'}`)
        .addTo(mapLayerGroup);
    }

    // Live AIS Vessel Marker
    if (coords && coords.lat && coords.lng) {
      const shipIcon = L.divIcon({
        className: 'ship-pulse',
        iconSize: [20, 20],
        iconAnchor: [10, 10]
      });

      const marker = L.marker([coords.lat, coords.lng], { icon: shipIcon })
        .bindPopup(
          `<div class="text-xs">
            <b>🚢 ${vesselName || 'Vessel'}</b><br>
            IMO: ${vesselImo || '-'}<br>
            AIS Ping: ${formatDateFn(coords.updatedAt)}
          </div>`
        )
        .addTo(mapLayerGroup);

      marker.openPopup();
      bounds.push([coords.lat, coords.lng]);
    }

    if (bounds.length > 0) {
      map.fitBounds(bounds, { padding: [45, 45] });
    }
  }, 150);
}