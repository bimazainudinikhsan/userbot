# bmcodexbot/utils_faktur.py
import os
import math
from datetime import datetime, timedelta

# Import ReportLab
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.pdfgen import canvas

def format_currency(amount):
    try:
        val = int(amount) if amount % 1 == 0 else amount
        return f"Rp {val:,.0f}".replace(',', '.') + ",00"
    except:
        return str(amount)

def generate_faktur(user_id, nama_klien, email_klien, no_hp, deskripsi, subtotal, catatan, payment_details, do_rounddown=False, use_ppn=False, rounddown_limit=1000, output_folder='.'):
    """
    Generate Faktur menggunakan ReportLab (Platypus Engine).
    """
    
    # --- 1. SETUP FILE & FOLDER ---
    if not os.path.exists(output_folder) and output_folder != '.':
        os.makedirs(output_folder)

    now = datetime.now()
    tgl_str = now.strftime("%d%m%Y")
    ts = int(now.timestamp())
    nomor_faktur = f"{tgl_str}{user_id}-{ts}"
    filename = f"Faktur_{nomor_faktur}.pdf"
    full_path = os.path.join(output_folder, filename)

    doc = SimpleDocTemplate(
        full_path,
        pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    style_normal = styles['Normal']
    style_right = ParagraphStyle('Right', parent=styles['Normal'], alignment=2)
    style_center_bold = ParagraphStyle('CenterBold', parent=styles['Normal'], alignment=1, fontName='Helvetica-Bold', fontSize=9)

    # --- 2. HEADER ---
    logo_path = 'logo_invoice.png' if os.path.exists('logo_invoice.png') else None
    tanggal_faktur = now.strftime("%d/%m/%Y")
    jatuh_tempo = (now + timedelta(days=30)).strftime("%d/%m/%Y")
    
    header_data = [
        [
            RLImage(logo_path, width=25*mm, height=25*mm) if logo_path else "", 
            Paragraph(f"<b>JASA CLEAR VIRUS</b><br/><br/>Faktur: {nomor_faktur}<br/>Tgl: {tanggal_faktur}<br/>Jatuh Tempo: {jatuh_tempo}", style_right)
        ]
    ]
    
    t_header = Table(header_data, colWidths=[85*mm, 85*mm])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
    ]))
    elements.append(t_header)
    elements.append(Spacer(1, 10*mm))

    # --- 3. INFO KLIEN ---
    client_info = f"""
    <b>DITAGIHKAN KEPADA:</b><br/>
    {nama_klien}<br/>
    {email_klien}<br/>
    {no_hp}
    """
    elements.append(Paragraph(client_info, style_normal))
    elements.append(Spacer(1, 10*mm))

    # --- 4. TABEL ITEM ---
    ppn = subtotal * 0.05 if use_ppn else 0
    total_pre = subtotal + ppn
    
    if do_rounddown:
        grand_total = math.floor(total_pre / rounddown_limit) * rounddown_limit
    else:
        grand_total = total_pre

    subtotal_str = format_currency(subtotal)
    
    table_data = [['Deskripsi', 'Qty', 'Harga Unit', 'Total']]
    table_data.append([
        Paragraph(deskripsi, style_normal),
        '1',
        subtotal_str,
        subtotal_str
    ])
    
    col_widths = [90*mm, 20*mm, 30*mm, 30*mm]
    t_items = Table(table_data, colWidths=col_widths)
    
    t_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]
    t_items.setStyle(TableStyle(t_style))
    elements.append(t_items)
    
    # --- 5. TOTAL & PPN ---
    total_data = []
    total_data.append(['', '', 'Subtotal', subtotal_str])
    
    if use_ppn:
        total_data.append(['', '', 'PPN (5%)', format_currency(ppn)])
        
    if do_rounddown and (total_pre != grand_total):
        diff = grand_total - total_pre
        total_data.append(['', '', f'(Pembulatan)', format_currency(diff)])
        
    total_data.append(['', '', 'TOTAL BAYAR', format_currency(grand_total)])
    
    t_total = Table(total_data, colWidths=col_widths)
    t_total.setStyle(TableStyle([
        ('ALIGN', (-2, 0), (-1, -1), 'RIGHT'),
        ('LINEABOVE', (-2, -1), (-1, -1), 1, colors.black),
        ('FONTNAME', (-2, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    elements.append(t_total)
    elements.append(Spacer(1, 10*mm))

    # --- 6. FOOTER INFO (Bank & Catatan & QRIS) ---
    
    qris_path = None
    if os.path.exists('qris.jpg'): qris_path = 'qris.jpg'
    elif os.path.exists('qris.png'): qris_path = 'qris.png'
    
    # Siapkan konten Bank & Catatan (Kiri)
    notes_content = f"""
    <b>Rincian Pembayaran:</b><br/>
    {payment_details}<br/><br/>
    <b>Catatan:</b><br/>
    {catatan}
    """
    
    # Siapkan konten QRIS + Teks (Kanan)
    # Kita pakai list flowables untuk cell kanan ini
    right_content = []
    if qris_path:
        right_content.append(RLImage(qris_path, width=35*mm, height=35*mm))
        right_content.append(Spacer(1, 2*mm))
    
    # TAMBAHAN TEKS DI BAWAH QRIS
    right_content.append(Paragraph("<b>SCAN PEMBAYARAN<br/>QRIS DISINI</b>", style_center_bold))

    # Buat Tabel Footer (2 Kolom)
    footer_table_data = [
        [Paragraph(notes_content, style_normal), right_content]
    ]
    
    t_footer = Table(footer_table_data, colWidths=[110*mm, 60*mm])
    t_footer.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (1,0), (1,0), 'CENTER'), # Kolom kanan rata tengah (untuk QRIS)
    ]))
    elements.append(t_footer)

    # --- 7. STATIC FOOTER (Copyright) ---
    def add_static_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica-Bold', 10)
        canvas.drawCentredString(A4[0]/2, 30*mm, "CLEAR VIRUS")
        
        canvas.setFont('Helvetica', 9)
        canvas.drawCentredString(A4[0]/2, 25*mm, "Kota Semarang")
        canvas.drawCentredString(A4[0]/2, 20*mm, "clearv1rusbybm@gmail.com | 0812-3189-8181")
        canvas.drawCentredString(A4[0]/2, 15*mm, "www.clearvirusbybm.com")
        
        canvas.setFont('Helvetica-Oblique', 8)
        canvas.drawCentredString(A4[0]/2, 8*mm, "Generated by Clear Virus Bot")
        canvas.restoreState()

    # --- BUILD PDF ---
    try:
        doc.build(elements, onFirstPage=add_static_footer, onLaterPages=add_static_footer)
    except Exception as e:
        print(f"Gagal build PDF ReportLab: {e}")
        raise e

    return full_path