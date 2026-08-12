const sensorIdInput = document.getElementById('sensorId');
const loadButton = document.getElementById('loadBtn');
const statusEl = document.getElementById('status');

let chart;

function ensureChart() {
  if (chart) {
    return chart;
  }

  const ctx = document.getElementById('sensorChart');
  chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: 'condenser_temp_f', data: [], borderWidth: 2 },
        { label: 'evaporator_temp_f', data: [], borderWidth: 2 },
        { label: 'high_side_psi', data: [], borderWidth: 2 },
        { label: 'low_side_psi', data: [], borderWidth: 2 },
      ],
    },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { ticks: { maxTicksLimit: 8 } },
      },
    },
  });

  return chart;
}

async function loadReadings() {
  const sensorId = sensorIdInput.value.trim() || 'ac-1';
  statusEl.textContent = 'Loading...';

  try {
    const response = await fetch(`/api/v1/readings?sensor_id=${encodeURIComponent(sensorId)}&limit=200`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const payload = await response.json();
    const rows = payload.rows || [];

    const labels = rows.map((r) => new Date(r.sample_ts).toLocaleTimeString());
    const c = ensureChart();

    c.data.labels = labels;
    for (let i = 0; i < 4; i += 1) {
      c.data.datasets[i].data = rows.map((r) => (Array.isArray(r.values) ? r.values[i] : null));
    }
    c.update();

    statusEl.textContent = `Loaded ${rows.length} rows for ${sensorId}`;
  } catch (err) {
    statusEl.textContent = `Load failed: ${err.message}`;
  }
}

loadButton.addEventListener('click', loadReadings);
loadReadings();
setInterval(loadReadings, 4000);
