const NUM_SENSORS = 10;
// display window in milliseconds (e.g. 2000 = last 2 seconds)
const DISPLAY_WINDOW_MS = 2000;
const MAX_POINTS = 200; // safety cap

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
  const t = (ts instanceof Date) ? ts.getTime() : Number(ts);
  ds.data.push({ x: t, y: value });

  const cutoff = Date.now() - DISPLAY_WINDOW_MS;
  // trim to keep only recent points and also respect MAX_POINTS as a hard cap
  const filtered = ds.data.filter(d => d.x >= cutoff);
  if (filtered.length > MAX_POINTS) {
    // keep the most recent MAX_POINTS
    ds.data = filtered.slice(-MAX_POINTS);
  } else {
    ds.data = filtered;
  }

  // update labels to match point count (not used visually)
  chart.data.labels = ds.data.map(() => '');
  // update x axis viewport (optional)
  if (!chart.options.scales) chart.options.scales = {};
  if (!chart.options.scales.x) chart.options.scales.x = {};
  chart.options.scales.x.min = cutoff;
  chart.options.scales.x.max = Date.now();

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
    } catch (err) {
      console.error('parse error', err);
    }
  };
  ws.onclose = () => {
    console.log('Disconnected — retrying in 1s');
    setTimeout(connect, 1000);
  };
}

createGrid();
connect();
