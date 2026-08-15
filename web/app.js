const NUM_SENSORS = 4;
const MAX_POINTS = 40;

const charts = [];

function makeChart(ctx, label) {
  return new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        label: label,
        data: [],
        borderColor: 'rgba(33,150,243,1)',
        borderWidth: 1,
        pointRadius: 0,
      }]
    },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { display: false },
        y: { display: true }
      },
      plugins: { legend: { display: false } }
    }
  });
}

function createGrid() {
  const container = document.getElementById('charts');
  for (let i = 0; i < NUM_SENSORS; i++) {
    const card = document.createElement('div');
    card.className = 'chart-card';
    const title = document.createElement('div');
    title.className = 'chart-title';
    title.textContent = `Sensor ${i}`;
    const canvas = document.createElement('canvas');
    card.appendChild(title);
    card.appendChild(canvas);
    container.appendChild(card);
    charts[i] = makeChart(canvas.getContext('2d'), `S${i}`);
  }
}

function pushSample(sensorId, ts, value) {
  const chart = charts[sensorId];
  if (!chart) return;
  const ds = chart.data.datasets[0];
  ds.data.push({ x: ts, y: value });
  if (ds.data.length > MAX_POINTS) ds.data.shift();
  // update labels to match point count (not used visually)
  chart.data.labels = ds.data.map((d) => '');
  chart.update('none');
}

function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const url = `${proto}://${location.hostname}:8765`;
  const ws = new WebSocket(url);
  ws.onopen = () => console.log('Connected to simulator');
  ws.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data);
      if (msg.type === 'batch' && Array.isArray(msg.samples)) {
        msg.samples.forEach(s => pushSample(s.sensor_id, new Date(s.ts), s.value));
      }
      if (msg.type === 'maintenance' && Array.isArray(msg.samples)) {
        // update maintenance chart
        msg.samples.forEach(s => pushMaintenanceSample(s.sensor_id, new Date(s.ts), s.value));
      }
    } catch (err) {
      console.error('parse error', err);
    }
  };
  ws.onclose = () => {
    console.log('Disconnected — retrying in 1s');
    setTimeout(connect, 1000);
  };
}

// Logged values polling
let pollTimer = null;
function startPolling(interval) {
  stopPolling();
  pollTimer = setInterval(async () => {
    try {
      const res = await fetch('/api/recent?limit=10');
      const data = await res.json();
      const tbody = document.querySelector('#logged-table tbody');
      tbody.innerHTML = '';
      data.forEach(row => {
        const tr = document.createElement('tr');
        const tdts = document.createElement('td'); tdts.textContent = row.ts;
        const tdv = document.createElement('td'); tdv.textContent = (row.values || []).join(', ');
        tr.appendChild(tdts); tr.appendChild(tdv);
        tbody.appendChild(tr);
      });
    } catch (e) { console.error('poll error', e); }
  }, interval * 1000);
}

function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

// Maintenance chart
const maintenanceCtx = document.getElementById('maintenance-canvas').getContext('2d');
const maintenanceChart = new Chart(maintenanceCtx, {
  type: 'line', data: { labels: [], datasets: [{ label: 'Maintenance', data: [], borderColor: 'red', pointRadius: 0 }] },
  options: { animation: false, responsive: true, maintainAspectRatio: false, scales: { x: { display: false } } }
});

function pushMaintenanceSample(sensorId, ts, value) {
  // show sensor id + value as a single series for now
  maintenanceChart.data.datasets[0].data.push({ x: ts, y: value });
  if (maintenanceChart.data.datasets[0].data.length > 100) maintenanceChart.data.datasets[0].data.shift();
  maintenanceChart.update('none');
}

// Wire UI controls
document.addEventListener('DOMContentLoaded', () => {
  createGrid();
  connect();

  document.getElementById('start-poll').onclick = () => {
    const val = parseFloat(document.getElementById('poll-interval').value) || 1;
    startPolling(val);
  };
  document.getElementById('stop-poll').onclick = () => stopPolling();
  document.getElementById('reset-db').onclick = async () => {
    if (!confirm('Reset the database?')) return;
    const res = await fetch('/api/reset-db', { method: 'POST' });
    const j = await res.json();
    alert(JSON.stringify(j));
  };
  document.getElementById('apply-config').onclick = async () => {
    const sensors = document.getElementById('maintenance-sensors').value;
    const interval = parseFloat(document.getElementById('maintenance-interval').value) || 0.5;
    const body = { maintenance_sensors: sensors, maintenance_interval: interval };
    const res = await fetch('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const j = await res.json();
    alert('Config applied: ' + JSON.stringify(j));
  };
});
