import base64
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from lxml import etree
from cryptography import x509
from cryptography.x509.oid import NameOID, ObjectIdentifier
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature, Prehashed

# Import our Phase 2 helpers
from zatca_phase2 import generate_tlv_qr_code, hash_and_sign_invoice

# Minimal compliant ZATCA UBL 2.1 XML template
XML_INVOICE_TEMPLATE = b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
         xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2">
    <ext:UBLExtensions>
        <ext:UBLExtension>
            <ext:ExtensionURI>urn:oasis:names:specification:ubl:dsig:enveloped:xades</ext:ExtensionURI>
            <ext:ExtensionContent>
                <!-- Signature metadata will go here -->
                <sig:UBLDocumentSignatures xmlns:sig="urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2">
                    <sac:SignatureInformation xmlns:sac="urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2">
                        <cbc:ID>urn:oasis:names:specification:ubl:signature:1</cbc:ID>
                        <sdoc:ReferencedSignatureID xmlns:sdoc="urn:oasis:names:specification:ubl:schema:xsd:SignatureBasicComponents-2">urn:oasis:names:specification:ubl:signature:Invoice</sdoc:ReferencedSignatureID>
                    </sac:SignatureInformation>
                </sig:UBLDocumentSignatures>
            </ext:ExtensionContent>
        </ext:UBLExtension>
    </ext:UBLExtensions>
    <cbc:ProfileID>reporting:1.0</cbc:ProfileID>
    <cbc:ID>INV-2026-0001</cbc:ID>
    <cbc:UUID>95e8f498-5c4d-4e2b-98f6-17b5c8f85fca</cbc:UUID>
    <cbc:IssueDate>2026-06-16</cbc:IssueDate>
    <cbc:IssueTime>17:20:00</cbc:IssueTime>
    <cbc:InvoiceTypeCode name="0211000">388</cbc:InvoiceTypeCode>
    <cbc:DocumentCurrencyCode>SAR</cbc:DocumentCurrencyCode>
    <cbc:TaxCurrencyCode>SAR</cbc:TaxCurrencyCode>
    <cac:AdditionalDocumentReference>
        <cbc:ID>ICV</cbc:ID>
        <cbc:UUID>1</cbc:UUID>
    </cac:AdditionalDocumentReference>
    <cac:AdditionalDocumentReference>
        <cbc:ID>PIH</cbc:ID>
        <cbc:Attachment>
            <cbc:EmbeddedDocumentBinaryObject mimeCode="text/plain">NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ==</cbc:EmbeddedDocumentBinaryObject>
        </cbc:Attachment>
    </cac:AdditionalDocumentReference>
    <cac:AdditionalDocumentReference>
        <cbc:ID>QR</cbc:ID>
        <cbc:Attachment>
            <cbc:EmbeddedDocumentBinaryObject mimeCode="text/plain">WILL_BE_REPLACED_WITH_BASE64_QR_CODE</cbc:EmbeddedDocumentBinaryObject>
        </cbc:Attachment>
    </cac:AdditionalDocumentReference>
    <cac:Signature>
        <cbc:ID>urn:oasis:names:specification:ubl:signature:Invoice</cbc:ID>
        <cbc:SignatureMethod>urn:oasis:names:specification:ubl:dsig:enveloped:xades</cbc:SignatureMethod>
    </cac:Signature>
    <cac:AccountingSupplierParty>
        <cac:Party>
            <cac:PartyIdentification>
                <cbc:ID schemeID="CRN">1010000000</cbc:ID>
            </cac:PartyIdentification>
            <cac:PartyName>
                <cbc:Name>Dummy Developer Enterprise</cbc:Name>
            </cac:PartyName>
            <cac:PostalAddress>
                <cbc:StreetName>King Fahd Road</cbc:StreetName>
                <cbc:BuildingNumber>1234</cbc:BuildingNumber>
                <cbc:CitySubdivisionName>Al Olaya</cbc:CitySubdivisionName>
                <cbc:CityName>Riyadh</cbc:CityName>
                <cbc:PostalZone>12211</cbc:PostalZone>
                <cac:Country>
                    <cbc:IdentificationCode>SA</cbc:IdentificationCode>
                </cac:Country>
            </cac:PostalAddress>
            <cac:PartyTaxScheme>
                <cbc:CompanyID>399999999900003</cbc:CompanyID>
                <cac:TaxScheme>
                    <cbc:ID>VAT</cbc:ID>
                </cac:TaxScheme>
            </cac:PartyTaxScheme>
        </cac:Party>
    </cac:AccountingSupplierParty>
    <cac:AccountingCustomerParty>
        <cac:Party>
            <cac:PartyTaxScheme>
                <cac:TaxScheme>
                    <cbc:ID>VAT</cbc:ID>
                </cac:TaxScheme>
            </cac:PartyTaxScheme>
        </cac:Party>
    </cac:AccountingCustomerParty>
    <cac:TaxTotal>
        <cbc:TaxAmount currencyID="SAR">15.00</cbc:TaxAmount>
        <cac:TaxSubtotal>
            <cbc:TaxableAmount currencyID="SAR">100.00</cbc:TaxableAmount>
            <cbc:TaxAmount currencyID="SAR">15.00</cbc:TaxAmount>
            <cac:TaxCategory>
                <cbc:ID>S</cbc:ID>
                <cbc:Percent>15.00</cbc:Percent>
                <cac:TaxScheme>
                    <cbc:ID>VAT</cbc:ID>
                </cac:TaxScheme>
            </cac:TaxCategory>
        </cac:TaxSubtotal>
    </cac:TaxTotal>
    <cac:LegalMonetaryTotal>
        <cbc:LineExtensionAmount currencyID="SAR">100.00</cbc:LineExtensionAmount>
        <cbc:TaxExclusiveAmount currencyID="SAR">100.00</cbc:TaxExclusiveAmount>
        <cbc:TaxInclusiveAmount currencyID="SAR">115.00</cbc:TaxInclusiveAmount>
        <cbc:AllowanceTotalAmount currencyID="SAR">0.00</cbc:AllowanceTotalAmount>
        <cbc:PayableAmount currencyID="SAR">115.00</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
    <cac:InvoiceLine>
        <cbc:ID>1</cbc:ID>
        <cbc:InvoicedQuantity unitCode="PCE">1.000000</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="SAR">100.00</cbc:LineExtensionAmount>
        <cac:Item>
            <cbc:Name>Dummy Sandbox Product</cbc:Name>
            <cac:ClassifiedTaxCategory>
                <cbc:ID>S</cbc:ID>
                <cbc:Percent>15.00</cbc:Percent>
                <cac:TaxScheme>
                    <cbc:ID>VAT</cbc:ID>
                </cac:TaxScheme>
            </cac:ClassifiedTaxCategory>
        </cac:Item>
        <cac:Price>
            <cbc:PriceAmount currencyID="SAR">100.00</cbc:PriceAmount>
        </cac:Price>
    </cac:InvoiceLine>
</Invoice>
"""

def generate_dummy_developer_certificate(private_key: ec.EllipticCurvePrivateKey) -> bytes:
    """
    Generates a dummy self-signed developer certificate simulating ZATCA's CSID certificate.
    """
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "SA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Dummy Developer Enterprise"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Riyadh Branch"),
        x509.NameAttribute(NameOID.COMMON_NAME, "TST-886431145-399999999900003")
    ])
    
    template_name = "TSTZATCA-Code-Signing"
    template_bytes = bytes([0x13, len(template_name)]) + template_name.encode('ascii')
    
    # Subject Alternative Name containing directoryName with ZATCA OIDs
    san_dn = x509.Name([
        x509.NameAttribute(ObjectIdentifier("2.5.4.4"), "1-TST|2-TST|3-95e8f498-5c4d-4e2b-98f6-17b5c8f85fca"),
        x509.NameAttribute(ObjectIdentifier("0.9.2342.19200300.100.1.1"), "399999999900003"),
        x509.NameAttribute(ObjectIdentifier("2.5.4.12"), "1100"),
        x509.NameAttribute(ObjectIdentifier("2.5.4.26"), "Riyadh"),
        x509.NameAttribute(ObjectIdentifier("2.5.4.15"), "IT Services")
    ])
    
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.now(timezone.utc) - timedelta(days=1)
    ).not_valid_after(
        datetime.now(timezone.utc) + timedelta(days=365)
    ).add_extension(
        x509.UnrecognizedExtension(
            ObjectIdentifier("1.3.6.1.4.1.311.20.2"),
            template_bytes
        ),
        critical=False
    ).add_extension(
        x509.SubjectAlternativeName([
            x509.DirectoryName(san_dn)
        ]),
        critical=False
    ).sign(private_key, hashes.SHA256())
    
    return cert.public_bytes(serialization.Encoding.DER)

def embed_signature_and_qr(xml_content: bytes, signature_b64: str, cert_der: bytes, qr_code_b64: str) -> bytes:
    """
    Parses the invoice XML and embeds the digital signature, certificate, and QR code.
    """
    parser = etree.XMLParser(remove_blank_text=False)
    root = etree.fromstring(xml_content, parser)
    
    namespaces = {
        'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
        'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
        'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
        'sig': 'urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2',
        'sac': 'urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2'
    }
    
    # 1. Embed QR code
    qr_node = root.xpath('//cac:AdditionalDocumentReference[cbc:ID="QR"]/cbc:Attachment/cbc:EmbeddedDocumentBinaryObject', namespaces=namespaces)
    if qr_node:
        qr_node[0].text = qr_code_b64
        
    # 2. Re-create ExtensionContent signature blocks to simulate XAdES embedding
    # We find the UBLExtension content
    ext_content_node = root.xpath('//ext:UBLExtension/ext:ExtensionContent', namespaces=namespaces)
    if ext_content_node:
        # Create a basic ds:Signature block
        ds_ns = "http://www.w3.org/2000/09/xmldsig#"
        etree.register_namespace('ds', ds_ns)
        
        signature_el = etree.Element(f"{{{ds_ns}}}Signature", Id="signature")
        
        # ds:SignatureValue
        sig_val = etree.SubElement(signature_el, f"{{{ds_ns}}}SignatureValue")
        sig_val.text = signature_b64
        
        # ds:KeyInfo with ds:X509Data and ds:X509Certificate
        key_info = etree.SubElement(signature_el, f"{{{ds_ns}}}KeyInfo")
        x509_data = etree.SubElement(key_info, f"{{{ds_ns}}}X509Data")
        x509_cert = etree.SubElement(x509_data, f"{{{ds_ns}}}X509Certificate")
        x509_cert.text = base64.b64encode(cert_der).decode('utf-8')
        
        # Find UBLDocumentSignatures node and append the ds:Signature
        doc_sigs = ext_content_node[0].xpath('//sig:UBLDocumentSignatures/sac:SignatureInformation', namespaces=namespaces)
        if doc_sigs:
            doc_sigs[0].append(signature_el)
            
    return etree.tostring(root, xml_declaration=True, encoding='utf-8', pretty_print=True)

def validate_invoice_locally(xml_content: bytes) -> bool:
    """
    Parses the final signed UBL XML, extracts the QR code, decodes and verifies it 
    offline using the embedded signature and public key.
    """
    print("\n=== STARTING LOCAL CRYPTOGRAPHIC VALIDATION ===")
    
    parser = etree.XMLParser(remove_blank_text=False)
    root = etree.fromstring(xml_content, parser)
    
    namespaces = {
        'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
        'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
        'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'
    }
    
    # 1. Extract QR code
    qr_node = root.xpath('//cac:AdditionalDocumentReference[cbc:ID="QR"]/cbc:Attachment/cbc:EmbeddedDocumentBinaryObject', namespaces=namespaces)
    if not qr_node or not qr_node[0].text:
        print("[FAIL] QR Code not found in XML.")
        return False
        
    qr_code_b64 = qr_node[0].text.strip()
    print(f"[OK] Extracted QR code (Base64 length: {len(qr_code_b64)} characters).")
    
    # 2. Parse TLV tags
    try:
        decoded_qr = base64.b64decode(qr_code_b64)
    except Exception as e:
        print(f"[FAIL] Failed to base64-decode QR code: {e}")
        return False
        
    tags = {}
    index = 0
    try:
        while index < len(decoded_qr):
            tag_id = decoded_qr[index]
            length = decoded_qr[index + 1]
            value = decoded_qr[index + 2 : index + 2 + length]
            tags[tag_id] = value
            index += 2 + length
    except Exception as e:
        print(f"[FAIL] Failed to parse TLV structured bytes: {e}")
        return False
        
    print("[OK] Parsed TLV tags from QR code successfully:")
    print(f"  - Tag 1 (Seller Name): {tags.get(1, b'').decode('utf-8')}")
    print(f"  - Tag 2 (VAT Number):  {tags.get(2, b'').decode('utf-8')}")
    print(f"  - Tag 3 (Timestamp):   {tags.get(3, b'').decode('utf-8')}")
    print(f"  - Tag 4 (Total Amount): {tags.get(4, b'').decode('utf-8')}")
    print(f"  - Tag 5 (VAT Amount):   {tags.get(5, b'').decode('utf-8')}")
    print(f"  - Tag 6 (Invoice Hash): {tags.get(6, b'').decode('utf-8')}")
    print(f"  - Tag 7 (Signature):   {tags.get(7, b'').decode('utf-8')[:30]}... (Base64)")
    print(f"  - Tag 8 (Public Key):  {len(tags.get(8, b''))} bytes")
    print(f"  - Tag 9 (Cert Sign):   {len(tags.get(9, b''))} bytes")
    
    # 3. Cryptographically verify signature on the hash
    print("\nVerifying signature on the hash...")
    
    public_key_der = tags.get(8)
    if not public_key_der:
        print("[FAIL] Public key (Tag 8) not present in QR code.")
        return False
        
    try:
        public_key = serialization.load_der_public_key(public_key_der)
    except Exception as e:
        print(f"[FAIL] Failed to load public key: {e}")
        return False
        
    invoice_hash_b64 = tags.get(6).decode('utf-8')
    invoice_hash_bytes = base64.b64decode(invoice_hash_b64)
    
    signature_b64 = tags.get(7).decode('utf-8')
    raw_signature = base64.b64decode(signature_b64)
    
    if len(raw_signature) != 64:
        print(f"[FAIL] Raw signature length is not 64 bytes (got {len(raw_signature)}).")
        return False
        
    # Convert raw 64-byte signature to DER
    r = int.from_bytes(raw_signature[:32], byteorder='big')
    s = int.from_bytes(raw_signature[32:], byteorder='big')
    der_signature = encode_dss_signature(r, s)
    
    try:
        public_key.verify(
            der_signature,
            invoice_hash_bytes,
            ec.ECDSA(Prehashed(hashes.SHA256()))
        )
        print("[PASS] ECDSA Signature matches the Invoice Hash (Tag 6) using the Public Key (Tag 8)!")
    except Exception as e:
        print(f"[FAIL] ECDSA Cryptographic signature verification failed: {e}")
        return False
        
    return True

def main():
    print("=== ZATCA PHASE 2 LOCAL PLAYGROUND (OFFLINE TESTING) ===\n")
    
    # Step 1: Generate a local key pair (secp256k1)
    print("1. Generating secp256k1 private key...")
    private_key = ec.generate_private_key(ec.SECP256K1())
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')
    
    # Step 2: Generate a dummy developer certificate
    print("2. Generating dummy self-signed developer certificate...")
    cert_der = generate_dummy_developer_certificate(private_key)
    print(f"Generated certificate (DER size: {len(cert_der)} bytes)")
    
    # Step 3: Hash and sign the mock XML invoice
    print("\n3. Stripping and hashing the XML invoice...")
    invoice_hash_b64, signature_b64, public_key_der = hash_and_sign_invoice(
        XML_INVOICE_TEMPLATE, 
        private_key_pem
    )
    print(f"Invoice Hash (Base64): {invoice_hash_b64}")
    print(f"ECDSA Signature (Base64): {signature_b64}")
    
    # Step 4: Construct ZATCA Phase 2 TLV QR Code
    print("\n4. Generating TLV structured QR code...")
    # Tag 9 is the Certificate signature (or a mock signature of the CSID)
    mock_cert_signature = b"mock-cert-signature-value"
    
    tags = {
        1: "Dummy Developer Enterprise",
        2: "399999999900003",
        3: "2026-06-16T17:20:00Z",
        4: "115.00",
        5: "15.00",
        6: invoice_hash_b64,
        7: signature_b64,
        8: public_key_der,
        9: mock_cert_signature
    }
    
    qr_code_b64 = generate_tlv_qr_code(tags)
    print(f"Final Base64 QR Code: {qr_code_b64}")
    
    # Step 5: Embed signature, certificate, and QR code in the invoice
    print("\n5. Embedding signature and QR code into UBL XML invoice...")
    signed_xml = embed_signature_and_qr(XML_INVOICE_TEMPLATE, signature_b64, cert_der, qr_code_b64)
    
    # Save signed XML
    output_xml_path = "certificates/signed_invoice_playground.xml"
    os.makedirs("certificates", exist_ok=True)
    with open(output_xml_path, "wb") as f:
        f.write(signed_xml)
    print(f"Saved signed XML invoice to: {output_xml_path}")
    
    # Step 6: Validate locally
    validate_invoice_locally(signed_xml)

if __name__ == "__main__":
    main()
