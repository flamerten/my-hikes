const map = L.map('map');
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
}).addTo(map);

const allLatLngs = [];
ROUTES.features.forEach(feature => {
  const latlngs = feature.geometry.coordinates.map(([lon, lat]) => [lat, lon]);
  allLatLngs.push(...latlngs);
  L.polyline(latlngs, { color: '#e04', weight: 3, opacity: 0.8 }).addTo(map);
});
if (allLatLngs.length) map.fitBounds(allLatLngs, { padding: [20, 20] });

PINS.forEach(pin => {
  const marker = pin.thumb_url
    ? L.marker([pin.lat, pin.lon], {
        icon: L.divIcon({
          html: `<img src="${pin.thumb_url}" style="width:44px;height:44px;object-fit:cover;border:2px solid #fff;border-radius:3px">`,
          iconSize: [44, 44],
          className: '',
        }),
      })
    : L.circleMarker([pin.lat, pin.lon], { radius: 5, color: '#e04' });
  marker.bindPopup(pin.filename).addTo(map);
});

new Chart(document.getElementById('elevation-chart'), {
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
