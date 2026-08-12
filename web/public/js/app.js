const contentDiv = document.getElementById('app-content');
const navBtns = document.querySelectorAll('.nav-btn');

const formatPrice = (val) => {
    return val >= 10000 ? (val/1000).toFixed(1) + 'k' : val.toLocaleString('id-ID');
};

const formatVol = (val) => {
    return val >= 1000000 ? (val/1000000).toFixed(1) + 'M' : val.toLocaleString('id-ID');
};

let currentChart = null;

const renderHargaChart = (data) => {
    if (!data || data.length === 0) return '<div class="empty-state">Tidak ada data harga saham hari ini.</div>';
    
    // Sort by volume descending and take top 10
    const topVol = [...data].sort((a, b) => b.volume - a.volume).slice(0, 10);
    
    const labels = topVol.map(d => d.kode);
    const volumes = topVol.map(d => d.volume);
    
    const html = `
    <div class="chart-container">
        <h3 class="chart-title">🔥 Top 10 Volume Terbesar</h3>
        <canvas id="hargaChart" height="300"></canvas>
    </div>
    `;
    
    // We must return the HTML first so it gets injected into the DOM
    // Then we initialize the chart in a timeout
    setTimeout(() => {
        const ctx = document.getElementById('hargaChart').getContext('2d');
        if (currentChart) currentChart.destroy();
        
        currentChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Volume',
                    data: volumes,
                    backgroundColor: 'rgba(56, 189, 248, 0.7)',
                    borderColor: 'rgba(56, 189, 248, 1)',
                    borderWidth: 1,
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => formatVol(ctx.raw)
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { color: '#94A3B8', callback: (val) => formatVol(val) },
                        grid: { color: 'rgba(255,255,255,0.05)' }
                    },
                    x: {
                        ticks: { color: '#F8FAFC', font: { weight: 'bold' } },
                        grid: { display: false }
                    }
                }
            }
        });
    }, 50);

    return html;
};

const renderBrokerChart = (data) => {
    if (!data || data.length === 0) return '<div class="empty-state">Tidak ada data broker summary hari ini.</div>';
    
    // Top 10 Net Buy/Sell
    const topBrokers = [...data].slice(0, 12);
    
    const labels = topBrokers.map(d => d.broker);
    const netVals = topBrokers.map(d => d.net_val);
    const bgColors = netVals.map(v => v > 0 ? 'rgba(52, 211, 153, 0.7)' : 'rgba(248, 113, 113, 0.7)');
    const borderColors = netVals.map(v => v > 0 ? 'rgba(52, 211, 153, 1)' : 'rgba(248, 113, 113, 1)');
    
    const html = `
    <div class="chart-container">
        <h3 class="chart-title">🏢 Top Broker Akumulasi vs Distribusi</h3>
        <canvas id="brokerChart" height="350"></canvas>
    </div>
    `;
    
    setTimeout(() => {
        const ctx = document.getElementById('brokerChart').getContext('2d');
        if (currentChart) currentChart.destroy();
        
        currentChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Net Value (Rp)',
                    data: netVals,
                    backgroundColor: bgColors,
                    borderColor: borderColors,
                    borderWidth: 1,
                    borderRadius: 6
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                const valStr = (Math.abs(ctx.raw) / 1000000000).toFixed(1) + ' B';
                                return ctx.raw > 0 ? '+ ' + valStr : '- ' + valStr;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(255,255,255,0.05)' },
                        ticks: {
                            color: '#94A3B8',
                            callback: (val) => (val / 1000000000).toFixed(0) + 'B'
                        }
                    },
                    y: {
                        grid: { display: false },
                        ticks: { color: '#F8FAFC', font: { weight: 'bold' } }
                    }
                }
            }
        });
    }, 50);
    
    return html;
};

const renderUpload = () => {
    return `
    <div class="upload-glass">
        <h2>Update Master Saham</h2>
        <p style="color: var(--text-muted); font-size: 14px; margin-bottom: 24px;">Upload daftar saham terbaru dari situs Bursa Efek Indonesia (.xlsx)</p>
        
        <input type="file" id="excelFile" accept=".xlsx" />
        
        <button id="uploadBtn" class="btn-primary">
            Sync Database
        </button>
        
        <div id="uploadStatus" style="margin-top: 24px; font-weight: 500; font-size: 14px;"></div>
    </div>
    `;
};

const setupUploadEvent = () => {
    const uploadBtn = document.getElementById('uploadBtn');
    const fileInput = document.getElementById('excelFile');
    const statusDiv = document.getElementById('uploadStatus');

    if (!uploadBtn) return;

    uploadBtn.addEventListener('click', async () => {
        if (!fileInput.files || fileInput.files.length === 0) {
            statusDiv.innerHTML = '<span class="text-red">Pilih file terlebih dahulu!</span>';
            return;
        }

        const file = fileInput.files[0];
        statusDiv.innerHTML = 'Uploading dan memproses... ⏳';
        uploadBtn.disabled = true;

        try {
            const response = await fetch(`/api/upload?filename=${encodeURIComponent(file.name)}`, {
                method: 'POST',
                body: file,
                headers: {
                    'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                }
            });

            const result = await response.json();
            if (response.ok) {
                statusDiv.innerHTML = `<span class="text-green">✅ ${result.message} (${result.data.total_active} baris).</span>`;
            } else {
                statusDiv.innerHTML = `<span class="text-red">❌ Error: ${result.error}</span>`;
            }
        } catch (e) {
            statusDiv.innerHTML = `<span class="text-red">❌ Request failed: ${e.message}</span>`;
        } finally {
            uploadBtn.disabled = false;
        }
    });
};

const loadData = async (tab) => {
    contentDiv.innerHTML = `
      <div class="loading-state">
        <div class="spinner"></div>
        <p>Fetching market data...</p>
      </div>`;
    
    if (tab === 'upload') {
        contentDiv.innerHTML = renderUpload();
        setupUploadEvent();
        return;
    }

    try {
        const response = await fetch(`/api/stock?action=${tab}`);
        const result = await response.json();
        
        if (result.status === 'success') {
            if (tab === 'harga') {
                contentDiv.innerHTML = renderHargaChart(result.data);
            } else if (tab === 'broker') {
                contentDiv.innerHTML = renderBrokerChart(result.data);
            }
        } else {
            contentDiv.innerHTML = `<div class="error">Error: ${result.error || 'Terjadi kesalahan'}</div>`;
        }
    } catch (e) {
        contentDiv.innerHTML = `<div class="error">Gagal terhubung ke API (Offline)</div>`;
    }
};

navBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        navBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        loadData(btn.dataset.tab);
    });
});

// Init
loadData('harga');
