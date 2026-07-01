import datetime
import uuid
from typing import Dict, Union, Optional
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from lxml import etree

from zatca_orchestrator import generate_final_signed_invoice
from zatca_crypto import get_invoice_hash

app = FastAPI(
    title="ZATCA E-Invoicing Compliance API",
    description="API server for signing, hashing, and validating Saudi e-invoices according to ZATCA Phase 2 standards.",
    version="2.0.0"
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory database to store signed XML invoices for download
INVOICES_DB: Dict[str, str] = {}

class IssueInvoiceRequest(BaseModel):
    buyer_company: str
    buyer_vat: str
    amount: float
    supplier_name: str
    vat_number: str
    tax: Union[str, float]
    invoice_type: str = "388"
    instruction_note: Optional[str] = None
    linked_invoice_id: Optional[str] = None

@app.post("/api/v1/invoices/issue")
async def issue_invoice(request: IssueInvoiceRequest):
    try:
        # 1. Generate dynamic identifiers and timestamps
        invoice_id = f"INV-{datetime.datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        invoice_uuid = str(uuid.uuid4())
        issue_date = datetime.datetime.now().strftime('%Y-%m-%d')
        issue_time = datetime.datetime.now().strftime('%H:%M:%S')

        # 2. Use tax math from the request
        amount_val = float(request.amount)
        vat_val = float(request.tax)
        price_before_vat = round(amount_val - vat_val, 2)

        # Resolve Previous Invoice Hash (PIH)
        pih = 'NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ=='
        if request.invoice_type == '388':
            if INVOICES_DB:
                latest_invoice_id = list(INVOICES_DB.keys())[-1]
                latest_xml = INVOICES_DB[latest_invoice_id]
                pih = get_invoice_hash(latest_xml)
        elif request.invoice_type in ['381', '383']:
            if not request.linked_invoice_id or request.linked_invoice_id not in INVOICES_DB:
                raise HTTPException(status_code=400, detail="The original linked invoice was not found.")
            linked_xml = INVOICES_DB[request.linked_invoice_id]
            pih = get_invoice_hash(linked_xml)

        # 3. Build the invoice data structure
        invoice_data = {
            'invoice_id': invoice_id,
            'uuid': invoice_uuid,
            'issue_date': issue_date,
            'issue_time': issue_time,
            'icv': '1',
            'previous_hash': pih,
            'invoice_type_code': request.invoice_type,
            'instruction_note': request.instruction_note,
            'linked_invoice_id': request.linked_invoice_id,
            'supplier': {
                'crn': '1010000000',
                'name': request.supplier_name,
                'street_name': 'King Fahd Road',
                'building_number': '1234',
                'city_subdivision': 'Al Olaya',
                'city_name': 'Riyadh',
                'postal_zone': '12211',
                'country': 'SA',
                'vat_number': request.vat_number
            },
            'customer': {
                'name': request.buyer_company,
                'vat_number': request.buyer_vat
            },
            'items': [
                {
                    'name': 'Sandbox Cloud Integration Service',
                    'quantity': 1.0,
                    'price': price_before_vat,
                    'vat_percent': 15.0
                }
            ]
        }

        # 4. Generate the fully signed XML (incorporates tags 1-9)
        signed_xml = generate_final_signed_invoice(invoice_data)

        # 5. Extract hash of the invoice
        new_invoice_hash = get_invoice_hash(signed_xml)

        # 6. Extract generated QR code from the signed XML
        namespaces = {
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'
        }
        root = etree.fromstring(signed_xml.encode('utf-8'))
        qr_nodes = root.xpath('//cac:AdditionalDocumentReference[cbc:ID="QR"]/cac:Attachment/cbc:EmbeddedDocumentBinaryObject', namespaces=namespaces)
        qr_code = qr_nodes[0].text if qr_nodes else ""

        # 7. Store XML in database
        INVOICES_DB[invoice_id] = signed_xml

        return {
            "status": "success",
            "invoice_id": invoice_id,
            "zatca_status": "REPORTED",
            "pih_used": invoice_data['previous_hash'],
            "new_invoice_hash": new_invoice_hash,
            "qr_code_base64": qr_code,
            "xml_download_url": f"/api/v1/invoices/download/{invoice_id}"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to issue invoice: {str(e)}")

@app.get("/api/v1/invoices/download/{invoice_id}")
async def download_invoice(invoice_id: str):
    xml_content = INVOICES_DB.get(invoice_id)
    if not xml_content:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    # Return raw XML content
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename={invoice_id}.xml"
        }
    )

if __name__ == '__main__':
    uvicorn.run("zatca_api:app", host="0.0.0.0", port=8000, reload=True)
