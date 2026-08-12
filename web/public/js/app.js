document.addEventListener("DOMContentLoaded", () => {
  fetchStockData();
});

async function fetchStockData() {
  const content = document.getElementById('app-content');
  try {
    // Memanggil API internal Vercel Serverless
    const response = await fetch('/api/stock?action=hmb');
    const result = await response.json();
    
    if (result.status === 'success') {
      renderData(result.data, content);
    } else {
      content.innerHTML = `<div style="color:red">Error: ${result.error}</div>`;
    }
  } catch (error) {
    content.innerHTML = `<div style="color:red">Gagal terhubung ke API (Offline)</div>`;
  }
}

function renderData(data, container) {
  if (!data || data.length === 0) {
    container.innerHTML = '<div>Tidak ada data saham harian.</div>';
    return;
  }
  
  container.innerHTML = '';
  data.forEach(item => {
    const card = document.createElement('div');
    card.className = 'stock-card';
    const isRisk = item.pct_diff < 0;
    const diffColor = isRisk ? 'red' : 'green';
    
    card.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <div class="stock-ticker" style="font-size: 1.2rem; font-weight: bold;">${item.kode || 'UNKNOWN'}</div>
        <div style="font-size: 0.9rem; color: #888;">Top: ${item.brokers}</div>
      </div>
      <div style="display:flex; justify-content:space-between; margin-top: 8px;">
        <div>
          <div style="font-size:0.8rem; color:#aaa;">Harga</div>
          <div class="stock-price" style="font-weight: bold;">Rp ${item.harga ? item.harga.toLocaleString('id-ID') : '-'}</div>
        </div>
        <div>
          <div style="font-size:0.8rem; color:#aaa;">HMB</div>
          <div class="stock-price" style="font-weight: bold;">Rp ${item.hmb ? item.hmb.toLocaleString('id-ID') : '-'}</div>
        </div>
        <div style="text-align: right;">
          <div style="font-size:0.8rem; color:#aaa;">Risk/Reward</div>
          <div style="color: ${diffColor}; font-weight: bold;">${item.pct_diff > 0 ? '+' : ''}${item.pct_diff}%</div>
        </div>
      </div>
    `;
    container.appendChild(card);
  });
}
