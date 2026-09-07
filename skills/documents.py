from typing import Dict, Any, Optional
from docgen.invoice_template import generate_pdf_invoice
from docgen.deck_builder import generate_analysis_pptx

def generate_invoice_pdf(bill_id: str) -> Dict[str, Any]:
    """
    Generate a formatted PDF invoice for a given bill ID.
    Returns status and file path of the generated PDF document.
    """
    try:
        pdf_path = generate_pdf_invoice(bill_id)
        return {
            "status": "success",
            "message": f"PDF Invoice for Bill '{bill_id}' generated successfully.",
            "file_path": pdf_path,
            "bill_id": bill_id
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to generate PDF invoice: {str(e)}"
        }

def generate_analysis_deck(period: str = "Today", shop_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Generate a PowerPoint (.pptx) executive sales analysis presentation deck.
    Returns status and file path of the generated PPTX document.
    """
    try:
        pptx_path = generate_analysis_pptx(period, shop_name=shop_name)
        return {
            "status": "success",
            "message": f"PowerPoint Analysis Deck generated successfully for period '{period}'.",
            "file_path": pptx_path,
            "period": period
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to generate analysis deck: {str(e)}"
        }
