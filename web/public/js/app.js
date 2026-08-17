const API_BASE = '/api';
const appContent = document.getElementById('app-content');
let currentTab = 'dashboard';
let dashboardDataCache = null;

// Clock updates
setInterval(() => {
    const now = new Date();
    const clockEl = document.getElementById('live-clock');
    if (clockEl) {
        clockEl.innerText = now.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });
    }
}, 1000);

// Initialize Navigation
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        const targetBtn = e.currentTarget;
        targetBtn.classList.add('active');
        currentTab = targetBtn.dataset.tab;
        renderView();
    });
});

async function fetchDashboardData() {
    try {
        appContent.innerHTML = `<div class="loading-state"><div class="spinner"></div><p>Fetching metrics...</p></div>`;
        const res = await fetch(`${API_BASE}/stock?action=health`);
        const json = await res.json();
        if(json.status === 'success') {
            dashboardDataCache = json.data;
            renderView();
        } else {
            showError("Gagal mengambil data: " + (json.error || "Unknown"));
        }
    } catch(e) {
        // Fallback ke Dummy Data jika API lokal mati (Preview Mode)
        console.warn("API Error, falling back to dummy data for UI Preview...");
        dashboardDataCache = {
            saham: { total: 923, last_update: "2026-08-15" },
            pipeline: {
                date: "2026-08-15",
                ohlcv_scraped: 915,
                target_harvester: 450,
                broksum_synced: 300
            },
            history: [
                { date: "2026-08-15", ohlcv_scraped: 915, target_harvester: 450, broksum_synced: 300 },
                { date: "2026-08-14", ohlcv_scraped: 915, target_harvester: 460, broksum_synced: 460 },
                { date: "2026-08-13", ohlcv_scraped: 915, target_harvester: 455, broksum_synced: 455 },
                { date: "2026-08-12", ohlcv_scraped: 100, target_harvester: 50, broksum_synced: 0 },
                { date: "2026-08-11", ohlcv_scraped: 914, target_harvester: 452, broksum_synced: 450 },
                { date: "2026-08-10", ohlcv_scraped: 914, target_harvester: 440, broksum_synced: 440 },
                { date: "2026-08-09", ohlcv_scraped: 913, target_harvester: 430, broksum_synced: 430 }
            ],
            errors: [
                { bot_name: "harvester", level: "WARNING", message: "Timeout parsing broker summary BBCA", time: "2026-08-15 14:32" },
                { bot_name: "harvester", level: "ERROR", message: "Database connection lost (retry 1)", time: "2026-08-14 02:11" }
            ]
        };
        renderView();
    }
}

function renderView() {
    if(currentTab === 'dashboard') {
        renderDashboard();
    } else if(currentTab === 'upload') {
        renderUploadForm();
    }
}

function calculateHealth(total, master) {
    if(master === 0) return { pct: 0, status: "Tunggu Master Data", color: "yellow" };
    const pct = Math.round((total / master) * 100);
    if(pct >= 95) return { pct, status: "Normal / Sehat", color: "green" };
    if(pct >= 50) return { pct, status: "Sedang Sinkronisasi", color: "yellow" };
    return { pct, status: "Ada Kendala Tarik Data", color: "red" };
}

function renderDashboard() {
    if(!dashboardDataCache) return fetchDashboardData();

    const data = dashboardDataCache;
    const master = data.saham;
    const pipe = data.pipeline || { date: "N/A", ohlcv_scraped: 0, target_harvester: 0, broksum_synced: 0 };
    
    // Hitung persentase untuk indikator
    const ohlcvPct = master.total > 0 ? Math.round((pipe.ohlcv_scraped / master.total) * 100) : 0;
    const broksumPct = pipe.target_harvester > 0 ? Math.round((pipe.broksum_synced / pipe.target_harvester) * 100) : 0;

    // Tentukan status Broksum (in-progress animasi pulse atau success)
    const broksumStepClass = broksumPct >= 99 ? "success" : (pipe.target_harvester > 0 ? "in-progress" : "info");
    const broksumIcon = broksumPct >= 99 ? "✓" : "3";
    const ohlcvIcon = ohlcvPct >= 95 ? "✓" : "1";

    // Calendar UI Generation
    let historyHtml = generateCalendarHtml(data.history);

    let errorsHtml = '';
    if(data.errors.length === 0) {
        errorsHtml = `<div style="text-align: center; color: var(--accent-emerald); padding: 1rem 0;">Normal 🟢 (No errors in 48h)</div>`;
    } else {
        data.errors.forEach(e => {
            const color = e.level === 'CRITICAL' || e.level === 'ERROR' ? 'var(--accent-rose)' : 'var(--accent-yellow)';
            errorsHtml += `
            <div style="margin-bottom: 12px; padding: 10px; background: rgba(0,0,0,0.3); border-left: 3px solid ${color}; border-radius: 4px;">
                <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 4px;">[${e.bot_name}] ${e.time}</div>
                <div style="font-size: 0.85rem; color: var(--text-main);">${e.message}</div>
            </div>`;
        });
    }

    appContent.innerHTML = `
        <div class="dashboard-grid">
            <!-- Master Data -->
            <div class="glass-card">
                <div class="card-header">
                    <div class="card-title">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"></path><path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"></path></svg>
                        Total Master Emiten
                    </div>
                </div>
                <div class="card-value">${master.total}</div>
                <div class="card-subtitle">Last Synced: ${master.last_update}</div>
            </div>

            <!-- Pipeline Tracker (Menggantikan 2 Card Sebelumnya) -->
            <div class="glass-card" style="grid-column: 1 / -1;">
                <div class="card-header">
                    <div class="card-title">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
                        Sync Pipeline Monitor
                    </div>
                    <span class="status-badge badge-info">Market: ${pipe.date}</span>
                </div>
                
                <div class="pipeline-stepper">
                    <!-- Step 1: OHLCV -->
                    <div class="step success">
                        <div class="step-icon">${ohlcvIcon}</div>
                        <div class="step-content">
                            <h4>Harga Harian (OHLCV)</h4>
                            <p>${pipe.ohlcv_scraped} / ${master.total} Emiten (${ohlcvPct}% Tersimpan)</p>
                        </div>
                    </div>
                    
                    <!-- Step 2: Target Harvester -->
                    <div class="step info">
                        <div class="step-icon">2</div>
                        <div class="step-content">
                            <h4>Filter Emiten Aktif (Volume > 0)</h4>
                            <p>${pipe.target_harvester} Emiten masuk ke dalam antrean Harvester.</p>
                        </div>
                    </div>

                    <!-- Step 3: Broksum -->
                    <div class="step ${broksumStepClass}">
                        <div class="step-icon">${broksumIcon}</div>
                        <div class="step-content">
                            <h4>Scraping Broker Summary</h4>
                            <p>${pipe.broksum_synced} / ${pipe.target_harvester} Emiten (${broksumPct}% Selesai)</p>
                            ${broksumPct < 99 && pipe.target_harvester > 0 ? 
                                `<div class="progress-container" style="margin-top: 8px; height: 4px;">
                                    <div class="progress-bar bg-yellow" style="width: ${broksumPct}%"></div>
                                 </div>` : ''}
                        </div>
                    </div>
                </div>
            </div>

            <!-- Month Calendar Heatmap Card -->
            <div class="glass-card" style="grid-column: 1 / -1;">
                <div class="card-header" style="margin-bottom: 15px;">
                    <div class="card-title">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
                        <span id="calendar-month-title">Calendar Sync History</span>
                    </div>
                </div>
                <div class="calendar-header">
                    <div>Mon</div><div>Tue</div><div>Wed</div><div>Thu</div><div>Fri</div><div>Sat</div><div>Sun</div>
                </div>
                <div id="calendar-grid" class="calendar-grid">
                    ${historyHtml}
                </div>
            </div>

            <!-- System Logs -->
            <div class="glass-card" style="grid-column: 1 / -1;">
                <div class="card-title">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg>
                    Recent Bot Issues (48h)
                </div>
                ${errorsHtml}
            </div>
        </div>
    `;
}

function renderUploadForm() {
    appContent.innerHTML = `
        <div class="upload-container glass-card" style="margin-top: 10px;">
            <h2 style="margin-bottom: 8px">Update Master Data</h2>
            <p class="text-muted" style="margin-bottom: 24px; font-size: 0.9rem">Upload file format .xlsx dari web IDX (Daftar Saham) untuk memperbarui data emiten.</p>
            
            <form id="uploadForm">
                <div class="dropzone" id="dropzone">
                    <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
                    <h3 id="fileNameDisplay">Drag & Drop Excel di sini</h3>
                    <p>Atau klik untuk pilih file .xlsx</p>
                    <input type="file" name="file" id="fileInput" accept=".xlsx" style="display: none;" required>
                </div>
                <button type="submit" id="btnUpload" class="btn-primary">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 16 12 12 8 16"></polyline><line x1="12" y1="12" x2="12" y2="21"></line><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"></path><polyline points="16 16 12 12 8 16"></polyline></svg>
                    Upload & Proses
                </button>
            </form>
            <div id="uploadStatus" style="margin-top: 16px; font-size: 0.9rem; text-align: center;"></div>
        </div>
    `;

    // Dropzone logic
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('fileInput');
    const fileNameDisplay = document.getElementById('fileNameDisplay');

    dropzone.addEventListener('click', () => fileInput.click());
    
    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });
    
    dropzone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
    });
    
    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            fileInput.files = e.dataTransfer.files;
            fileNameDisplay.innerText = e.dataTransfer.files[0].name;
        }
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length) {
            fileNameDisplay.innerText = fileInput.files[0].name;
        }
    });

    // Upload Submit logic
    document.getElementById('uploadForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!fileInput.files.length) return;
        
        const btnUpload = document.getElementById('btnUpload');
        const statusEl = document.getElementById('uploadStatus');
        
        btnUpload.disabled = true;
        btnUpload.innerHTML = 'Mengunggah...';
        statusEl.innerHTML = '';

        const formData = new FormData();
        formData.append('file', fileInput.files[0]);

        try {
            const res = await fetch(`${API_BASE}/upload`, {
                method: 'POST',
                body: formData
            });
            const result = await res.json();
            
            if (res.ok && result.status === "success") {
                statusEl.innerHTML = `<span class="text-green">${result.message}</span>`;
                // Clear cache so it fetches new master count
                dashboardDataCache = null; 
            } else {
                statusEl.innerHTML = `<span class="text-red">Gagal: ${result.error || result.message}</span>`;
            }
        } catch (err) {
            statusEl.innerHTML = `<span class="text-red">Error jaringan: ${err.message}</span>`;
        } finally {
            btnUpload.disabled = false;
            btnUpload.innerHTML = 'Upload & Proses';
        }
    });
}

function showError(msg) {
    appContent.innerHTML = `<div class="glass-card" style="border-left: 4px solid var(--accent-rose)"><h3 class="text-red">System Error</h3><p>${msg}</p></div>`;
}

function generateCalendarHtml(historyData) {
    let html = '';
    const today = new Date();
    const currentYear = today.getFullYear();
    const currentMonth = today.getMonth(); // 0-11
    const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
    
    // Update judul bulan di next render tick
    setTimeout(() => {
        const titleEl = document.getElementById('calendar-month-title');
        if(titleEl) titleEl.innerText = `${monthNames[currentMonth]} ${currentYear} Sync`;
    }, 10);

    const historyMap = {};
    if (historyData) {
        historyData.forEach(item => {
            historyMap[item.date] = item;
        });
    }

    const firstDayDate = new Date(currentYear, currentMonth, 1);
    let firstDayIndex = firstDayDate.getDay() - 1;
    if (firstDayIndex === -1) firstDayIndex = 6;
    
    const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();

    for (let i = 0; i < firstDayIndex; i++) {
        html += `<div class="cal-box cal-box-empty"></div>`;
    }

    for (let day = 1; day <= daysInMonth; day++) {
        const monthStr = String(currentMonth + 1).padStart(2, '0');
        const dayStr = String(day).padStart(2, '0');
        const dateStr = `${currentYear}-${monthStr}-${dayStr}`;

        const hist = historyMap[dateStr];
        let boxClass = 'cal-box-empty';
        let contentHtml = `<div class="cal-stats" style="margin-top: 10px;">-</div>`;

        if (hist) {
            // Status determination
            if (hist.broksum_synced >= hist.target_harvester && hist.broksum_synced > 0) {
                boxClass = 'cal-box-green';
            } else if (hist.ohlcv_scraped > 0) {
                boxClass = 'cal-box-red';
            }

            contentHtml = `
                <div class="cal-stats">
                    <span>Harga: <strong>${hist.ohlcv_scraped}</strong></span>
                    <span>Broksum: <strong>${hist.broksum_synced}</strong></span>
                </div>
            `;
        }

        // Highlight today
        const isToday = (day === today.getDate()) ? 'border: 1px solid var(--accent-emerald);' : '';

        html += `
            <div class="cal-box ${boxClass}" style="${isToday}">
                <div class="cal-date">${day}</div>
                ${contentHtml}
            </div>
        `;
    }
    return html;
}

// Start
fetchDashboardData();
