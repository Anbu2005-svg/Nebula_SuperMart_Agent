import os
import re
from typing import Dict, Any
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from skills.billing import preview_bill

def generate_pdf_invoice(bill_id: str, output_dir: str = "generated_docs") -> str:
    """Generates a professional ReportLab PDF invoice for a given bill_id."""
    clean_bill_id = re.sub(r'[^a-zA-Z0-9_-]', '', bill_id)
    bill_data = preview_bill(clean_bill_id)
    if bill_data.get("status") == "error":
        raise ValueError(bill_data.get("message", "Bill not found"))
        
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, f"invoice_{clean_bill_id}.pdf")
    
    doc = SimpleDocTemplate(
        file_path,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1A365D')
    )
    
    subtitle_style = ParagraphStyle(
        'SubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#4A5568')
    )
    
    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        textColor=colors.white,
        alignment=1 # Center
    )
    
    cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=11,
        textColor=colors.HexColor('#2D3748')
    )
    
    right_cell_style = ParagraphStyle(
        'RightTableCell',
        parent=cell_style,
        alignment=2 # Right
    )

    bold_right_cell_style = ParagraphStyle(
        'BoldRightTableCell',
        parent=cell_style,
        fontName='Helvetica-Bold',
        alignment=2
    )

    story = []

    # Shop Header
    shop_name = os.getenv("SHOP_NAME", "Nebula SuperMart")
    shop_address = os.getenv("SHOP_ADDRESS", "123 Main Street, Chennai, TN - 600001")
    shop_gstin = os.getenv("SHOP_GSTIN", "33AABCU9603R1ZM")

    story.append(Paragraph(f"<b>{shop_name}</b>", title_style))
    story.append(Paragraph(f"{shop_address} | GSTIN: {shop_gstin}", subtitle_style))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#2B6CB0'), spaceAfter=15))

    # Bill Info Table
    info_data = [
        [
            Paragraph(f"<b>Tax Invoice</b>", ParagraphStyle('H2', fontName='Helvetica-Bold', fontSize=14, textColor=colors.HexColor('#2B6CB0'))),
            Paragraph(f"<b>Bill ID:</b> {bill_data['bill_id']}", right_cell_style)
        ],
        [
            Paragraph(f"<b>Customer:</b> {bill_data['customer_name']}", cell_style),
            Paragraph(f"<b>Status:</b> {bill_data['bill_status'].upper()}", right_cell_style)
        ]
    ]
    info_table = Table(info_data, colWidths=[270, 270])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 15))

    # Line Items Table
    headers = [
        Paragraph("<b>S.No</b>", table_header_style),
        Paragraph("<b>Product Name</b>", table_header_style),
        Paragraph("<b>HSN</b>", table_header_style),
        Paragraph("<b>Qty</b>", table_header_style),
        Paragraph("<b>Rate</b>", table_header_style),
        Paragraph("<b>GST%</b>", table_header_style),
        Paragraph("<b>CGST</b>", table_header_style),
        Paragraph("<b>SGST</b>", table_header_style),
        Paragraph("<b>Total (₹)</b>", table_header_style)
    ]
    
    table_rows = [headers]
    for idx, item in enumerate(bill_data['items'], 1):
        table_rows.append([
            Paragraph(str(idx), cell_style),
            Paragraph(item['name'], cell_style),
            Paragraph(item.get('hsn_code') or "-", cell_style),
            Paragraph(f"{item['qty']} {item['unit']}", cell_style),
            Paragraph(f"₹{item['unit_price']:.2f}", right_cell_style),
            Paragraph(f"{item['gst_slab']}%", right_cell_style),
            Paragraph(f"₹{item['cgst']:.2f}", right_cell_style),
            Paragraph(f"₹{item['sgst']:.2f}", right_cell_style),
            Paragraph(f"₹{item['line_total']:.2f}", right_cell_style)
        ])

    items_table = Table(table_rows, colWidths=[28, 155, 42, 52, 42, 38, 45, 45, 53])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2B6CB0')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F7FAFC')]),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 15))

    # Summary Breakdown Table
    summary = bill_data['summary']
    summary_data = [
        [Paragraph("Subtotal:", cell_style), Paragraph(f"₹{summary['subtotal']:.2f}", right_cell_style)],
        [Paragraph("Total CGST:", cell_style), Paragraph(f"₹{summary['cgst']:.2f}", right_cell_style)],
        [Paragraph("Total SGST:", cell_style), Paragraph(f"₹{summary['sgst']:.2f}", right_cell_style)],
        [Paragraph("Total Tax (GST):", cell_style), Paragraph(f"₹{summary['total_gst']:.2f}", right_cell_style)],
        [Paragraph("<b>Grand Total:</b>", ParagraphStyle('GT', parent=cell_style, fontName='Helvetica-Bold', fontSize=11)), 
         Paragraph(f"<b>₹{summary['grand_total']:.2f}</b>", ParagraphStyle('GTR', parent=right_cell_style, fontName='Helvetica-Bold', fontSize=11, textColor=colors.HexColor('#2B6CB0')))]
    ]

    summary_table = Table(summary_data, colWidths=[120, 100])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0')),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#EDF2F7')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))

    wrapper_table = Table([[Paragraph("", cell_style), summary_table]], colWidths=[320, 220])
    wrapper_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
    story.append(wrapper_table)

    story.append(Spacer(1, 30))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#CBD5E0'), spaceAfter=10))
    story.append(Paragraph("Thank you for shopping with us! Please come again.", ParagraphStyle('Footer', parent=styles['Normal'], alignment=1, fontSize=9, textColor=colors.HexColor('#718096'))))

    doc.build(story)
    return file_path
