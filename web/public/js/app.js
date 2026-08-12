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
    if (!data || data.length === 0) return '<div class="empty-state">Belum ada tarikan data OHLC 30 hari terakhir.</div>';
    
    const labels = data.map(d => d.date);
    const totals = data.map(d => d.total);
    
    // Warn if any day drops below typical threshold (e.g., 900 tickers)
    // Adjust colors dynamically based on completeness
    const bgColors = totals.map(t => t >= 800 ? 'rgba(52, 211, 153, 0.7)' : 'rgba(248, 113, 113, 0.7)');
    const borderColors = totals.map(t => t >= 800 ? 'rgba(52, 211, 153, 1)' : 'rgba(248, 113, 113, 1)');
    
    const html = `
    <div class="chart-container">
        <h3 class="chart-title">📈 Monitor Data OHLC (30 Hari)</h3>
        <p style="text-align: center; color: var(--text-muted); font-size: 12px; margin-top: -10px; margin-bottom: 20px;">Jumlah Ticker Terunduh per Hari</p>
        <canvas id="hargaChart" height="300"></canvas>
    </div>
    `;
    
    setTimeout(() => {
        const ctx = document.getElementById('hargaChart').getContext('2d');
        if (currentChart) currentChart.destroy();
        
        currentChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Total Ticker',
                    data: totals,
                    backgroundColor: bgColors,
                    borderColor: borderColors,
                    borderWidth: 1,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.raw} Ticker`
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { color: '#94A3B8' },
                        grid: { color: 'rgba(255,255,255,0.05)' }
                    },
                    x: {
                        ticks: { color: '#F8FAFC', font: { size: 10 } },
                        grid: { display: false }
                    }
                }
            }
        });
    }, 50);

    return html;
};

const renderBrokerChart = (data) => {
    if (!data || data.length === 0) return '<div class="empty-state">Belum ada tarikan data Broksum 30 hari terakhir.</div>';
    
    const labels = data.map(d => d.date);
    const totals = data.map(d => d.total);
    
    const bgColors = totals.map(t => t >= 800 ? 'rgba(56, 189, 248, 0.7)' : 'rgba(248, 113, 113, 0.7)');
    const borderColors = totals.map(t => t >= 800 ? 'rgba(56, 189, 248, 1)' : 'rgba(248, 113, 113, 1)');
    
    const html = `
    <div class="chart-container">
        <h3 class="chart-title">🏢 Monitor Data Broksum (30 Hari)</h3>
        <p style="text-align: center; color: var(--text-muted); font-size: 12px; margin-top: -10px; margin-bottom: 20px;">Jumlah Ticker Terunduh per Hari</p>
        <canvas id="brokerChart" height="300"></canvas>
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
                    label: 'Total Ticker',
                    data: totals,
                    backgroundColor: bgColors,
                    borderColor: borderColors,
                    borderWidth: 1,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.raw} Ticker`
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { color: '#94A3B8' },
                        grid: { color: 'rgba(255,255,255,0.05)' }
                    },
                    x: {
                        ticks: { color: '#F8FAFC', font: { size: 10 } },
                        grid: { display: false }
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
