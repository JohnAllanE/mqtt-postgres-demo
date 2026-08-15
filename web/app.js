const NUM_SENSORS = 10;
const MAX_POINTS = 200;

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
