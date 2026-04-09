import PhotoSwipe from 'https://cdn.jsdelivr.net/npm/photoswipe@5.4.4/dist/photoswipe.esm.min.js';

// ---------------------------------------------------------------------------
// Map
// ---------------------------------------------------------------------------

const map = L.map('map');
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
}).addTo(map);

// ---------------------------------------------------------------------------
// Route polylines — clickable, highlight on select
// ---------------------------------------------------------------------------

const STYLE_DEFAULT  = { color: '#e04', weight: 3, opacity: 0.8 };
const STYLE_SELECTED = { color: '#e04', weight: 5, opacity: 1.0 };
const STYLE_DIM      = { color: '#aaa', weight: 2, opacity: 0.4 };

// keyed by slug: { poly: L.Polyline, props: object }
const polylines = {};
const allLatLngs = [];

ROUTES.features.forEach(feature => {
  const props   = feature.properties;
  const latlngs = feature.geometry.coordinates.map(([lon, lat]) => [lat, lon]);
  allLatLngs.push(...latlngs);

  const poly = L.polyline(latlngs, { ...STYLE_DEFAULT }).addTo(map);
  poly.bindTooltip(props.name, { sticky: true });
  polylines[props.slug] = { poly, props };

  poly.on('click', e => {
    L.DomEvent.stopPropagation(e);
    selectRoute(props.slug);
  });
});

if (allLatLngs.length) map.fitBounds(allLatLngs, { padding: [20, 20] });

// ---------------------------------------------------------------------------
// Photo markers — clustered, open PhotoSwipe lightbox on click
// ---------------------------------------------------------------------------

const pswpItems = [];
const photoCluster = L.markerClusterGroup();

PINS.forEach(pin => {
  const marker = L.circleMarker([pin.lat, pin.lon], {
    radius: 6,
    color: '#fff',
    fillColor: '#e04',
    fillOpacity: 0.9,
    weight: 1.5,
  });

  if (pin.thumb_url) {
    const idx = pswpItems.length;
    pswpItems.push({
      src: pin.thumb_url,
      width: pin.thumb_width ?? 800,
      height: pin.thumb_height ?? 600,
      alt: pin.filename,
    });
    marker.on('click', () => openLightbox(idx));
  } else {
    marker.bindPopup(pin.filename);
  }

  photoCluster.addLayer(marker);
});

map.addLayer(photoCluster);

function openLightbox(index) {
  const pswp = new PhotoSwipe({ dataSource: pswpItems, index });
  pswp.init();
}

// ---------------------------------------------------------------------------
// Elevation chart
// ---------------------------------------------------------------------------

const elevationChart = new Chart(document.getElementById('elevation-chart'), {
  type: 'line',
  data: {
    labels: ELEVATION.map(p => (p.d / 1000).toFixed(2) + ' km'),
    datasets: [{
      data: ELEVATION.map(p => p.ele),
      fill: true,
      borderColor: '#e04',
      backgroundColor: 'rgba(220,0,68,0.1)',
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.3,
    }],
  },
  options: {
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { maxTicksLimit: 8 } },
      y: { title: { display: true, text: 'Elevation (m)' } },
    },
  },
});

// ---------------------------------------------------------------------------
// Route selection
// ---------------------------------------------------------------------------

let selectedSlug = null;

function selectRoute(slug) {
  selectedSlug = slug;
  const { props } = polylines[slug];

  Object.entries(polylines).forEach(([s, { poly }]) => {
    poly.setStyle(s === slug ? STYLE_SELECTED : STYLE_DIM);
    if (s === slug) poly.bringToFront();
  });

  document.getElementById('route-panel').style.display = '';
  document.getElementById('route-panel-name').textContent = props.name;
  document.getElementById('route-panel-stats').innerHTML = `
    <li><strong>${(props.distance_m / 1000).toFixed(1)} km</strong> distance</li>
    <li><strong>${Math.round(props.ele_gain_m)} m</strong> gain</li>
    <li><strong>${Math.round(props.ele_loss_m)} m</strong> loss</li>
    <li><strong>${Math.round(props.max_ele_m)} m</strong> max elevation</li>
    <li><strong>${props.avg_pace_min_km.toFixed(1)} min/km</strong> avg pace</li>
  `;

  const profile = ROUTE_ELEVATION[slug] ?? [];
  elevationChart.data.labels = profile.map(p => (p.d / 1000).toFixed(2) + ' km');
  elevationChart.data.datasets[0].data = profile.map(p => p.ele);
  elevationChart.update();
}

function resetRoutes() {
  selectedSlug = null;
  Object.values(polylines).forEach(({ poly }) => poly.setStyle(STYLE_DEFAULT));
  document.getElementById('route-panel').style.display = 'none';

  elevationChart.data.labels = ELEVATION.map(p => (p.d / 1000).toFixed(2) + ' km');
  elevationChart.data.datasets[0].data = ELEVATION.map(p => p.ele);
  elevationChart.update();
}

document.getElementById('route-panel-reset').addEventListener('click', resetRoutes);
// clicking the map background (not a polyline) resets selection
map.on('click', () => { if (selectedSlug) resetRoutes(); });
