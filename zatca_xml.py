import xml.etree.ElementTree as ET
from xml.dom import minidom

def generate_ubl_xml(invoice_data: dict) -> str:
    """
    Generates a UBL 2.1 compliant Simplified Tax Invoice (388) XML structure.
    
    Args:
        invoice_data (dict): Dictionary containing details for supplier, customer, items, etc.
        
    Returns:
        str: Prettified XML document string.
    """
    # 1. Register required namespaces
    ns = {
        'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
        'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
        'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2'
    }
    for prefix, uri in ns.items():
        ET.register_namespace(prefix, uri)

    # 2. Root element
    root = ET.Element('Invoice', {
        'xmlns': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
        'xmlns:cac': ns['cac'],
        'xmlns:cbc': ns['cbc'],
        'xmlns:ext': ns['ext']
    })

    # 3. UBLExtensions (Signature skeleton)
    exts = ET.SubElement(root, 'ext:UBLExtensions')
    ext = ET.SubElement(exts, 'ext:UBLExtension')
    uri = ET.SubElement(ext, 'ext:ExtensionURI')
    uri.text = 'urn:oasis:names:specification:ubl:dsig:enveloped:xades'
    content = ET.SubElement(ext, 'ext:ExtensionContent')
    
    sigs = ET.SubElement(content, 'sig:UBLDocumentSignatures', {
        'xmlns:sig': 'urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2'
    })
    sig_info = ET.SubElement(sigs, 'sac:SignatureInformation', {
        'xmlns:sac': 'urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2'
    })
    ET.SubElement(sig_info, 'cbc:ID').text = 'urn:oasis:names:specification:ubl:signature:1'
    ref_sig_id = ET.SubElement(sig_info, 'sdoc:ReferencedSignatureID', {
        'xmlns:sdoc': 'urn:oasis:names:specification:ubl:schema:xsd:SignatureBasicComponents-2'
    })
    ref_sig_id.text = 'urn:oasis:names:specification:ubl:signature:Invoice'

    # 4. Basic Invoice Metadata
    ET.SubElement(root, 'cbc:ProfileID').text = 'reporting:1.0'
    ET.SubElement(root, 'cbc:ID').text = invoice_data.get('invoice_id', 'INV-0001')
    ET.SubElement(root, 'cbc:UUID').text = invoice_data.get('uuid', '')
    ET.SubElement(root, 'cbc:IssueDate').text = invoice_data.get('issue_date', '')
    ET.SubElement(root, 'cbc:IssueTime').text = invoice_data.get('issue_time', '')
    
    type_code = ET.SubElement(root, 'cbc:InvoiceTypeCode', {
        'name': invoice_data.get('invoice_type_name', '0211000')
    })
    type_code.text = invoice_data.get('invoice_type_code', '388')
    
    ET.SubElement(root, 'cbc:DocumentCurrencyCode').text = 'SAR'
    ET.SubElement(root, 'cbc:TaxCurrencyCode').text = 'SAR'

    # 5. Additional Document References
    # ICV
    ref_icv = ET.SubElement(root, 'cac:AdditionalDocumentReference')
    ET.SubElement(ref_icv, 'cbc:ID').text = 'ICV'
    ET.SubElement(ref_icv, 'cbc:UUID').text = str(invoice_data.get('icv', '1'))

    # PIH
    ref_pih = ET.SubElement(root, 'cac:AdditionalDocumentReference')
    ET.SubElement(ref_pih, 'cbc:ID').text = 'PIH'
    att_pih = ET.SubElement(ref_pih, 'cac:Attachment')
    obj_pih = ET.SubElement(att_pih, 'cbc:EmbeddedDocumentBinaryObject', {'mimeCode': 'text/plain'})
    obj_pih.text = invoice_data.get('previous_hash', 'NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ==')

    # QR code placeholder
    ref_qr = ET.SubElement(root, 'cac:AdditionalDocumentReference')
    ET.SubElement(ref_qr, 'cbc:ID').text = 'QR'
    att_qr = ET.SubElement(ref_qr, 'cac:Attachment')
    obj_qr = ET.SubElement(att_qr, 'cbc:EmbeddedDocumentBinaryObject', {
        'mimeCode': 'text/plain',
        'id': 'qr_code_placeholder'
    })
    obj_qr.text = 'WILL_BE_REPLACED_WITH_BASE64_QR_CODE'

    # Signature Metadata
    signature = ET.SubElement(root, 'cac:Signature')
    ET.SubElement(signature, 'cbc:ID').text = 'urn:oasis:names:specification:ubl:signature:Invoice'
    ET.SubElement(signature, 'cbc:SignatureMethod').text = 'urn:oasis:names:specification:ubl:dsig:enveloped:xades'

    # 6. Supplier details (AccountingSupplierParty)
    supplier = invoice_data.get('supplier', {})
    sup_party = ET.SubElement(root, 'cac:AccountingSupplierParty')
    party = ET.SubElement(sup_party, 'cac:Party')
    
    if supplier.get('crn'):
        part_id = ET.SubElement(party, 'cac:PartyIdentification')
        crn = ET.SubElement(part_id, 'cbc:ID', {'schemeID': 'CRN'})
        crn.text = supplier['crn']
        
    part_name = ET.SubElement(party, 'cac:PartyName')
    ET.SubElement(part_name, 'cbc:Name').text = supplier.get('name', '')

    # Postal Address
    address = ET.SubElement(party, 'cac:PostalAddress')
    ET.SubElement(address, 'cbc:StreetName').text = supplier.get('street_name', '')
    ET.SubElement(address, 'cbc:BuildingNumber').text = supplier.get('building_number', '')
    ET.SubElement(address, 'cbc:CitySubdivisionName').text = supplier.get('city_subdivision', '')
    ET.SubElement(address, 'cbc:CityName').text = supplier.get('city_name', '')
    ET.SubElement(address, 'cbc:PostalZone').text = supplier.get('postal_zone', '')
    country = ET.SubElement(address, 'cac:Country')
    ET.SubElement(country, 'cbc:IdentificationCode').text = supplier.get('country', 'SA')

    # Tax Scheme
    tax_scheme = ET.SubElement(party, 'cac:PartyTaxScheme')
    ET.SubElement(tax_scheme, 'cbc:CompanyID').text = supplier.get('vat_number', '')
    scheme = ET.SubElement(tax_scheme, 'cac:TaxScheme')
    ET.SubElement(scheme, 'cbc:ID').text = 'VAT'

    # 7. Customer details (AccountingCustomerParty)
    cust_party = ET.SubElement(root, 'cac:AccountingCustomerParty')
    c_party = ET.SubElement(cust_party, 'cac:Party')
    
    customer = invoice_data.get('customer', {})
    if customer.get('name'):
        c_name = ET.SubElement(c_party, 'cac:PartyName')
        ET.SubElement(c_name, 'cbc:Name').text = customer['name']
        
    c_tax_scheme = ET.SubElement(c_party, 'cac:PartyTaxScheme')
    if customer.get('vat_number'):
        ET.SubElement(c_tax_scheme, 'cbc:CompanyID').text = customer['vat_number']
    c_scheme = ET.SubElement(c_tax_scheme, 'cac:TaxScheme')
    ET.SubElement(c_scheme, 'cbc:ID').text = 'VAT'

    # 8. Financial totals
    items = invoice_data.get('items', [])
    line_extension_total = sum(item['price'] * item['quantity'] for item in items)
    tax_percent = 15.00
    tax_total = sum((item['price'] * item['quantity']) * (item.get('vat_percent', tax_percent) / 100.0) for item in items)
    tax_inclusive_total = line_extension_total + tax_total

    # TaxTotal node
    tax_tot = ET.SubElement(root, 'cac:TaxTotal')
    ET.SubElement(tax_tot, 'cbc:TaxAmount', {'currencyID': 'SAR'}).text = f'{tax_total:.2f}'
    
    # Subtotal
    subtotal = ET.SubElement(tax_tot, 'cac:TaxSubtotal')
    ET.SubElement(subtotal, 'cbc:TaxableAmount', {'currencyID': 'SAR'}).text = f'{line_extension_total:.2f}'
    ET.SubElement(subtotal, 'cbc:TaxAmount', {'currencyID': 'SAR'}).text = f'{tax_total:.2f}'
    category = ET.SubElement(subtotal, 'cac:TaxCategory')
    ET.SubElement(category, 'cbc:ID').text = 'S'
    ET.SubElement(category, 'cbc:Percent').text = f'{tax_percent:.2f}'
    scheme_vat = ET.SubElement(category, 'cac:TaxScheme')
    ET.SubElement(scheme_vat, 'cbc:ID').text = 'VAT'

    # Monetary total
    monetary = ET.SubElement(root, 'cac:LegalMonetaryTotal')
    ET.SubElement(monetary, 'cbc:LineExtensionAmount', {'currencyID': 'SAR'}).text = f'{line_extension_total:.2f}'
    ET.SubElement(monetary, 'cbc:TaxExclusiveAmount', {'currencyID': 'SAR'}).text = f'{line_extension_total:.2f}'
    ET.SubElement(monetary, 'cbc:TaxInclusiveAmount', {'currencyID': 'SAR'}).text = f'{tax_inclusive_total:.2f}'
    ET.SubElement(monetary, 'cbc:AllowanceTotalAmount', {'currencyID': 'SAR'}).text = '0.00'
    ET.SubElement(monetary, 'cbc:PayableAmount', {'currencyID': 'SAR'}).text = f'{tax_inclusive_total:.2f}'

    # 9. Item lines
    for idx, item in enumerate(items, 1):
        line = ET.SubElement(root, 'cac:InvoiceLine')
        ET.SubElement(line, 'cbc:ID').text = str(idx)
        ET.SubElement(line, 'cbc:InvoicedQuantity', {'unitCode': 'PCE'}).text = f'{item.get("quantity", 1.0):.6f}'
        
        line_ext_amount = item['price'] * item['quantity']
        ET.SubElement(line, 'cbc:LineExtensionAmount', {'currencyID': 'SAR'}).text = f'{line_ext_amount:.2f}'
        
        # Item category
        item_node = ET.SubElement(line, 'cac:Item')
        ET.SubElement(item_node, 'cbc:Name').text = item['name']
        c_tax_cat = ET.SubElement(item_node, 'cac:ClassifiedTaxCategory')
        ET.SubElement(c_tax_cat, 'cbc:ID').text = 'S'
        ET.SubElement(c_tax_cat, 'cbc:Percent').text = f'{item.get("vat_percent", tax_percent):.2f}'
        item_scheme = ET.SubElement(c_tax_cat, 'cac:TaxScheme')
        ET.SubElement(item_scheme, 'cbc:ID').text = 'VAT'
        
        # Price
        price = ET.SubElement(line, 'cac:Price')
        ET.SubElement(price, 'cbc:PriceAmount', {'currencyID': 'SAR'}).text = f'{item["price"]:.2f}'

    # 10. Generate XML raw bytes and return parsed string
    xml_raw = ET.tostring(root, encoding='utf-8')
    parsed = minidom.parseString(xml_raw)
    return parsed.toprettyxml(indent='    ', encoding='utf-8').decode('utf-8')
