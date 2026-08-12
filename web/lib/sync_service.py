import pandas as pd
import io
import re
from datetime import datetime, date
from sqlalchemy.orm import Session
from database import Saham

def _parse_idx_date(date_str) -> date | None:
    if pd.isna(date_str):
        return None
    if isinstance(date_str, datetime):
        return date_str.date()
    
    months_map = {
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'Mei': '05', 'Jun': '06',
        'Jul': '07', 'Agu': '08', 'Sep': '09', 'Okt': '10', 'Nov': '11', 'Des': '12'
    }
    try:
        parts = str(date_str).strip().split()
        if len(parts) == 3:
            day, month_id, year = parts
            month = months_map.get(month_id, '01')
            return datetime.strptime(f"{year}-{month}-{day.zfill(2)}", "%Y-%m-%d").date()
    except Exception:
        pass
    return None

def _clean_numeric(value) -> int:
    if pd.isna(value):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    clean_str = re.sub(r'[^\d]', '', str(value))
    return int(clean_str) if clean_str else 0

def _clean_string(value) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r'\s+', ' ', str(value)).strip()

def extract_date_from_filename(filename: str) -> date:
    """Ekstrak tanggal YYYYMMDD dari nama file Telegram."""
    match = re.search(r'\d{8}', filename)
    if match:
        date_str = match.group()
        return datetime.strptime(date_str, "%Y%m%d").date()
    return datetime.now().date()  # Fallback ke tanggal server hari ini

def process_saham_excel(db: Session, excel_bytes: bytes, filename: str) -> dict:
    """Eksekusi strategi Wipe & Replace secara atomik."""
    try:
        df = pd.read_excel(io.BytesIO(excel_bytes))
        
        required_columns = ['No', 'Kode', 'Nama Perusahaan', 'Tanggal Pencatatan', 'Saham', 'Papan Pencatatan']
        if not all(col in df.columns for col in required_columns):
            raise ValueError("Struktur kolom file Excel tidak valid. Pastikan format dari IDX.")

        # Ekstrak tanggal deterministik dari nama file
        update_date = extract_date_from_filename(filename)

        # 1. WIPE: Hapus semua data yang ada di tabel saat ini
        db.query(Saham).delete()

        # 2. PREPARE: Susun objek ORM dalam memori
        new_records = []
        for _, row in df.iterrows():
            kode = _clean_string(row['Kode'])
            if not kode:
                continue
                
            new_saham = Saham(
                no=_clean_numeric(row['No']),
                kode=kode,
                nama_perusahaan=_clean_string(row['Nama Perusahaan']),
                tanggal_pencatatan=_parse_idx_date(row['Tanggal Pencatatan']),
                saham=_clean_numeric(row['Saham']),
                papan_pencatatan=_clean_string(row['Papan Pencatatan']),
                tanggal_update=update_date
            )
            new_records.append(new_saham)

        # 3. BULK INSERT: Simpan seluruh list sekaligus (Jauh lebih cepat dari iterasi add)
        db.bulk_save_objects(new_records)
        
        # 4. COMMIT TRANSAKSI
        db.commit()

        return {
            'total_active': len(new_records),
            'tanggal_update': str(update_date)
        }

    except Exception as e:
        db.rollback()
        raise Exception(f"Kegagalan sinkronisasi data: {str(e)}")
