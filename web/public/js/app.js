const contentDiv = document.getElementById('app-content');
const navBtns = document.querySelectorAll('.nav-btn');

const formatPrice = (val) => {
    return val >= 10000 ? (val/1000).toFixed(1) + 'k' : val.toLocaleString('id-ID');
};

const formatVol = (val) => {
    return val >= 1000000 ? (val/1000000).toFixed(1) + 'M' : val.toLocaleString('id-ID');
};

const renderHarga = (data) => {
    if (!data || data.length === 0) return '<div class="empty">Tidak ada data harga saham.</div>';
    
    let html = `
    <div class="data-table">
        <div class="table-header">
            <div>KODE</div>
            <div>HARGA</div>
            <div>%CHG</div>
            <div>VOL</div>
        </div>
    `;
    data.forEach(item => {
        const colorClass = item.chg_pct > 0 ? 'text-green' : (item.chg_pct < 0 ? 'text-red' : 'text-gray');
        const sign = item.chg_pct > 0 ? '+' : '';
        html += `
        <div class="table-row">
            <div><strong>${item.kode}</strong></div>
            <div>${formatPrice(item.harga)}</div>
            <div class="${colorClass}">${sign}${item.chg_pct}%</div>
            <div>${formatVol(item.volume)}</div>
        </div>`;
    });
    html += '</div>';
    return html;
};

const renderBroker = (data) => {
    if (!data || data.length === 0) return '<div class="empty">Tidak ada data broker summary.</div>';
    
    let html = `
    <div class="data-table">
        <div class="table-header">
            <div>BRK</div>
            <div>NET VOL</div>
            <div>NET VAL</div>
        </div>
    `;
    data.forEach(item => {
        const isAccum = item.net_val > 0;
        const colorClass = isAccum ? 'text-green' : 'text-red';
        const valStr = (item.net_val / 1000000000).toFixed(1) + ' B';
        html += `
        <div class="table-row">
            <div><strong>${item.broker}</strong></div>
            <div>${formatPrice(item.net_vol)}</div>
            <div class="${colorClass}">${valStr}</div>
        </div>`;
    });
    html += '</div>';
    return html;
};

const renderUpload = () => {
    return `
    <div class="upload-container" style="padding: 20px; text-align: center;">
        <h2>Upload Data IDX</h2>
        <p style="color: #888; font-size: 0.9em; margin-bottom: 20px;">Pilih file .xlsx dari IDX untuk bulk replace database.</p>
        <input type="file" id="excelFile" accept=".xlsx" style="margin-bottom: 20px; color: white;" />
        <br/>
        <button id="uploadBtn" style="padding: 10px 20px; background: #3b82f6; color: white; border: none; border-radius: 8px; font-weight: bold;">Mulai Upload</button>
        <div id="uploadStatus" style="margin-top: 20px; font-weight: bold;"></div>
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
    contentDiv.innerHTML = '<div class="loading">Loading data...</div>';
    
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
