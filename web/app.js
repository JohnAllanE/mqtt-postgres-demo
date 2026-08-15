const NUM_SENSORS = 4;
const MAX_POINTS = 40;
const API_BASE = `${location.protocol}//${location.hostname}:8080`;

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
  // clear any stray text nodes or previous content
  container.innerHTML = '';
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

// Logged values polling + charts
const LOG_MAX_POINTS = 50;
let pollTimer = null;
let loggedChart6 = null;
let loggedChart4 = null;

function makeMultiSensorChart(ctx, sensorCount, title) {
  const datasets = [];
  for (let i = 0; i < sensorCount; i++) {
    const hue = Math.round((i / Math.max(1, sensorCount)) * 360);
    datasets.push({ label: `s${i}`, data: [], borderColor: `hsl(${hue} 70% 40%)`, pointRadius: 0 });
  }
  return new Chart(ctx, {
    type: 'line',
    data: { labels: [], datasets },
    options: { animation: false, responsive: true, maintainAspectRatio: false, scales: { x: { display: false } } }
  });
}

function startPolling(interval) {
  stopPolling();
  pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/recent?limit=60`);
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
      // update logged charts
      if (loggedChart6 || loggedChart4) {
        updateLoggedCharts(data || []);
      }
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
  // create logged charts
  const ctx6 = document.getElementById('logged-6-canvas').getContext('2d');
  const ctx4 = document.getElementById('logged-4-canvas').getContext('2d');
  loggedChart6 = makeMultiSensorChart(ctx6, 6, 'group-6');
  loggedChart4 = makeMultiSensorChart(ctx4, 4, 'group-4');

  document.getElementById('start-poll').onclick = () => {
    const val = parseFloat(document.getElementById('poll-interval').value) || 1;
    startPolling(val);
  };
  document.getElementById('stop-poll').onclick = () => stopPolling();
  document.getElementById('reset-db').onclick = async () => {
    if (!confirm('Reset the database?')) return;
    const res = await fetch(`${API_BASE}/api/reset-db`, { method: 'POST' });
    const j = await res.json();
    alert(JSON.stringify(j));
  };
  document.getElementById('apply-config').onclick = async () => {
    const sensors = document.getElementById('maintenance-sensors').value;
    const interval = parseFloat(document.getElementById('maintenance-interval').value) || 0.5;
    const body = { maintenance_sensors: sensors, maintenance_interval: interval };
    const res = await fetch(`${API_BASE}/api/config`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const j = await res.json();
    alert('Config applied: ' + JSON.stringify(j));
  };

  // start polling by default so logged charts populate automatically
  startPolling(parseFloat(document.getElementById('poll-interval').value) || 1);
});


function updateLoggedCharts(rows) {
  // rows are newest-first; make chronological
  const chron = (rows || []).slice().reverse();
  const rows6 = chron.filter(r => Array.isArray(r.values) && r.values.length === 6);
  const rows4 = chron.filter(r => Array.isArray(r.values) && r.values.length === 4);

  if (loggedChart6) {
    // build datasets for each sensor
    for (let i = 0; i < 6; i++) {
      const dataPoints = rows6.map(r => ({ x: new Date(r.ts), y: r.values[i] }));
      loggedChart6.data.datasets[i].data = dataPoints.slice(-LOG_MAX_POINTS);
    }
    loggedChart6.update('none');
  }

  if (loggedChart4) {
    for (let i = 0; i < 4; i++) {
      const dataPoints = rows4.map(r => ({ x: new Date(r.ts), y: r.values[i] }));
      loggedChart4.data.datasets[i].data = dataPoints.slice(-LOG_MAX_POINTS);
    }
    loggedChart4.update('none');
  }
}
