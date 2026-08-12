const contentDiv = document.getElementById('app-content');
const navBtns = document.querySelectorAll('.nav-btn');

const formatPrice = (val) => {
    return val >= 10000 ? (val/1000).toFixed(1) + 'k' : val.toLocaleString('id-ID');
};

const formatVol = (val) => {
    return val >= 1000000 ? (val/1000000).toFixed(1) + 'M' : val.toLocaleString('id-ID');
};

const renderHarga = (data) => {
    if (!data || data.length === 0) return '<div class="empty-state">Tidak ada data harga saham hari ini.</div>';
    
    let html = `
    <div class="data-table">
        <div class="table-header">
            <div>KODE</div>
            <div>HARGA</div>
            <div>%CHG</div>
            <div style="text-align: right;">VOL</div>
        </div>
    `;
    data.forEach(item => {
        const isPos = item.chg_pct > 0;
        const isNeg = item.chg_pct < 0;
        const badgeClass = isPos ? 'badge-green' : (isNeg ? 'badge-red' : 'badge-gray');
        const sign = isPos ? '+' : '';
        
        html += `
        <div class="table-row">
            <div class="ticker-code">${item.kode}</div>
            <div class="price-val">${formatPrice(item.harga)}</div>
            <div><span class="badge ${badgeClass}">${sign}${item.chg_pct}%</span></div>
            <div style="text-align: right; color: var(--text-muted);">${formatVol(item.volume)}</div>
        </div>`;
    });
    html += '</div>';
    return html;
};

const renderBroker = (data) => {
    if (!data || data.length === 0) return '<div class="empty-state">Tidak ada data broker summary hari ini.</div>';
    
    let html = `
    <div class="data-table">
        <div class="table-header table-header-broker">
            <div>BROKER</div>
            <div>NET VOL</div>
            <div style="text-align: right;">NET VALUE</div>
        </div>
    `;
    data.forEach(item => {
        const isAccum = item.net_val > 0;
        const colorClass = isAccum ? 'var(--green)' : 'var(--red)';
        const valStr = (item.net_val / 1000000000).toFixed(1) + 'B';
        const sign = isAccum ? '+' : '';
        
        html += `
        <div class="table-row table-row-broker">
            <div class="ticker-code" style="color: ${colorClass};">${item.broker}</div>
            <div class="price-val">${formatPrice(item.net_vol)}</div>
            <div style="text-align: right; font-weight: 700; color: ${colorClass};">${sign}${valStr}</div>
        </div>`;
    });
    html += '</div>';
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
                contentDiv.innerHTML = renderHarga(result.data);
            } else if (tab === 'broker') {
                contentDiv.innerHTML = renderBroker(result.data);
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
