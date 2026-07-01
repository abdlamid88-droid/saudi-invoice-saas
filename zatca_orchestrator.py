import base64
import os
import json
import hashlib
import re
from datetime import datetime, timezone, timedelta
from lxml import etree
from cryptography import x509
from cryptography.x509.oid import NameOID, ObjectIdentifier
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed, decode_dss_signature

from zatca_xml import generate_ubl_xml
from zatca_crypto import get_invoice_hash

def get_issuer_dn_string(cert_obj: x509.Certificate) -> str:
    """
    Extracts the issuer DN string from a cryptography certificate object,
    formatted with spaces after commas (e.g., CN=..., OU=..., O=..., C=...).
    """
    rfc_str = cert_obj.issuer.rfc4514_string()
    parts = re.split(r'(?<!\\),', rfc_str)
    parts_formatted = [part.strip() for part in parts]
    return ", ".join(parts_formatted)

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

def load_certificate_and_key() -> tuple[str, str]:
    """
    Loads the real ZATCA onboarding certificate and private key from the certificates directory.
    Falls back to generating dummy developer credentials if they do not exist.
    
    Returns:
        tuple: (cert_b64, private_key_pem)
    """
    cert_info_path = "certificates/certificateInfo.json"
    private_key_path = "certificates/PrivateKey.pem"
    
    cert_b64 = None
    private_key_pem = None
    
    if os.path.exists(cert_info_path):
        try:
            with open(cert_info_path, "r", encoding="utf-8") as f:
                cert_info = json.load(f)
                # First check production CSID, then compliance CSID
                cert_b64 = cert_info.get("pcsid_binarySecurityToken") or cert_info.get("ccsid_binarySecurityToken")
        except Exception as e:
            print(f"Warning: Failed to load certificate from {cert_info_path}: {e}")
            
    if os.path.exists(private_key_path):
        try:
            with open(private_key_path, "r", encoding="utf-8") as f:
                private_key_pem = f.read()
        except Exception as e:
            print(f"Warning: Failed to load private key from {private_key_path}: {e}")
            
    if not cert_b64 or not private_key_pem:
        print("Warning: Real onboarding certificate/key files not found. Generating dummy self-signed credentials...")
        # Generate private key (secp256k1)
        private_key = ec.generate_private_key(ec.SECP256K1())
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')
        
        cert_der = generate_dummy_developer_certificate(private_key)
        cert_b64 = base64.b64encode(cert_der).decode('utf-8')
        
    return cert_b64, private_key_pem

def generate_zatca_qr_v2(seller_name: str, vat_number: str, timestamp: str, invoice_total: float, vat_total: float, invoice_hash_b64: str, signature_b64: str, public_key_der: bytes, cert_signature: bytes) -> str:
    """
    Generates a ZATCA-compliant QR code encoded in TLV (Tag-Length-Value) as a Base64 string.
    Includes tags 1 to 9:
    1: Seller Name
    2: VAT Number
    3: Timestamp (ISO 8601)
    4: Invoice Total (inclusive of VAT)
    5: VAT Total
    6: XML Invoice Hash
    7: ECDSA Signature
    8: Public Key (DER)
    9: Certificate Signature
    """
    tags = {
        1: str(seller_name),
        2: str(vat_number),
        3: str(timestamp),
        4: f"{float(invoice_total):.2f}",
        5: f"{float(vat_total):.2f}",
        6: str(invoice_hash_b64),
        7: str(signature_b64),
        8: public_key_der,
        9: cert_signature
    }
    
    from zatca_phase2 import generate_tlv_qr_code
    return generate_tlv_qr_code(tags)

def generate_final_signed_invoice(invoice_data: dict) -> str:
    """
    Main orchestrator function that:
    1. Loads the real certificate and private key from `certificates/` (with fallback).
    2. Generates clean XML structure from template.
    3. Calculates invoice hash (pre-signing).
    4. Generates fully ZATCA-compliant XAdES-EPES signature elements:
       - xades:SignedProperties (including SigningTime, CertDigest, and IssuerSerial).
       - ds:SignedInfo containing references to the invoice and SignedProperties.
       - Signs ds:SignedInfo with the private key (ECDSA secp256k1) and creates ds:SignatureValue.
    5. Generates the 9-tag QR code (including Signature and Public Key).
    6. Injects the complete ds:Signature block and QR code into the XML.
    """
    # 1. Load Certificate and Private Key
    cert_b64, private_key_pem = load_certificate_and_key()
    
    # Parse certificate
    cert_der = base64.b64decode(cert_b64)
    cert_obj = x509.load_der_x509_certificate(cert_der)
    
    # Load private key
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode('utf-8'),
        password=None
    )
    
    # 2. Generate clean XML
    xml_string = generate_ubl_xml(invoice_data)
    
    # 3. Compute Invoice Hash
    invoice_hash = get_invoice_hash(xml_string)
    
    # 4. Generate Certificate Hash, Issuer DN, Serial Number
    cert_hash = hashlib.sha256(cert_der).digest()
    cert_hash_b64 = base64.b64encode(cert_hash).decode('utf-8')
    
    issuer_dn = get_issuer_dn_string(cert_obj)
    serial_number = str(cert_obj.serial_number)
    
    # Normalize Signing Time to match issue_date & issue_time
    signing_time = invoice_data['issue_date'] + 'T' + invoice_data['issue_time'] + 'Z'
    
    signed_properties_xml = f"""<xades:SignedProperties xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" xmlns:ds="http://www.w3.org/2000/09/xmldsig#" Id="xadesSignedProperties">
        <xades:SignedSignatureProperties>
            <xades:SigningTime>{signing_time}</xades:SigningTime>
            <xades:SigningCertificate>
                <xades:Cert>
                    <xades:CertDigest>
                        <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                        <ds:DigestValue>{cert_hash_b64}</ds:DigestValue>
                    </xades:CertDigest>
                    <xades:IssuerSerial>
                        <ds:X509IssuerName>{issuer_dn}</ds:X509IssuerName>
                        <ds:X509SerialNumber>{serial_number}</ds:X509SerialNumber>
                    </xades:IssuerSerial>
                </xades:Cert>
            </xades:SigningCertificate>
            <xades:SignaturePolicyIdentifier>
                <xades:SignaturePolicyId>
                    <xades:SigPolicyId>
                        <xades:Identifier>https://www.zatca.gov.sa/documents/signature-policy.pdf</xades:Identifier>
                    </xades:SigPolicyId>
                    <xades:SigPolicyHash>
                        <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                        <ds:DigestValue>rnCfcXlAk/cLYtR9ypOhtiz/TW7sTEj4meUcUlz7SoM=</ds:DigestValue>
                    </xades:SigPolicyHash>
                </xades:SignaturePolicyId>
            </xades:SignaturePolicyIdentifier>
        </xades:SignedSignatureProperties>
    </xades:SignedProperties>"""
    # Parse and canonicalize SignedProperties to compute its hash
    sp_root = etree.fromstring(signed_properties_xml.encode('utf-8'))
    sp_canonicalized = etree.tostring(sp_root, method="c14n", exclusive=False, with_comments=False)
    sp_hash_b64 = base64.b64encode(hashlib.sha256(sp_canonicalized).digest()).decode('utf-8')
    
    # 6. Generate SignedInfo XML and its canonicalized hash
    signed_info_xml = f"""<ds:SignedInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
        <ds:CanonicalizationMethod Algorithm="http://www.w3.org/2006/12/xml-c14n11"/>
        <ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256"/>
        <ds:Reference Id="invoiceSignedDataReference" URI="">
            <ds:Transforms>
                <ds:Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>
            </ds:Transforms>
            <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
            <ds:DigestValue>{invoice_hash}</ds:DigestValue>
        </ds:Reference>
        <ds:Reference Type="http://uri.etsi.org/01903#SignedProperties" URI="#xadesSignedProperties">
            <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
            <ds:DigestValue>{sp_hash_b64}</ds:DigestValue>
        </ds:Reference>
    </ds:SignedInfo>"""
    
    si_root = etree.fromstring(signed_info_xml.encode('utf-8'))
    si_canonicalized = etree.tostring(si_root, method="c14n", exclusive=False, with_comments=False)
    si_hash = hashlib.sha256(si_canonicalized).digest()
    
    # 7. Sign the SignedInfo hash using ECDSA and convert to raw 64-byte format
    der_signature = private_key.sign(
        si_hash,
        ec.ECDSA(Prehashed(hashes.SHA256()))
    )
    r, s = decode_dss_signature(der_signature)
    r_bytes = r.to_bytes(32, byteorder='big')
    s_bytes = s.to_bytes(32, byteorder='big')
    raw_signature = r_bytes + s_bytes
    signature_b64 = base64.b64encode(raw_signature).decode('utf-8')
    
    # 8. Generate ZATCA QR code (TLV Base64 with 9 tags)
    public_key = cert_obj.public_key()
    public_key_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    cert_signature = cert_obj.signature
    
    # Calculate totals
    items = invoice_data.get('items', [])
    line_extension_total = sum(item['price'] * item['quantity'] for item in items)
    tax_percent = 15.00
    tax_total = sum((item['price'] * item['quantity']) * (item.get('vat_percent', tax_percent) / 100.0) for item in items)
    tax_inclusive_total = line_extension_total + tax_total
    
    qr_code = generate_zatca_qr_v2(
        seller_name=invoice_data['supplier']['name'],
        vat_number=invoice_data['supplier']['vat_number'],
        timestamp=signing_time,
        invoice_total=tax_inclusive_total,
        vat_total=tax_total,
        invoice_hash_b64=invoice_hash,
        signature_b64=signature_b64,
        public_key_der=public_key_der,
        cert_signature=cert_signature
    )
    
    # 9. Assemble the final XML by injecting the ds:Signature
    parser = etree.XMLParser(remove_blank_text=False)
    root = etree.fromstring(xml_string.encode('utf-8'), parser)
    
    namespaces = {
        'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
        'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
        'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
        'sig': 'urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2',
        'sac': 'urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2',
        'xades': 'http://uri.etsi.org/01903/v1.3.2#',
        'ds': 'http://www.w3.org/2000/09/xmldsig#'
    }
    
    # Inject QR Code
    qr_nodes = root.xpath('//cac:AdditionalDocumentReference[cbc:ID="QR"]/cac:Attachment/cbc:EmbeddedDocumentBinaryObject', namespaces=namespaces)
    if qr_nodes:
        qr_nodes[0].text = qr_code
        
    # Construct complete ds:Signature block
    ds_ns = "http://www.w3.org/2000/09/xmldsig#"
    xades_ns = "http://uri.etsi.org/01903/v1.3.2#"
    etree.register_namespace('ds', ds_ns)
    etree.register_namespace('xades', xades_ns)
    
    signature_el = etree.Element(f"{{{ds_ns}}}Signature", Id="signature")
    
    # Append ds:SignedInfo
    signature_el.append(si_root)
    
    # Append ds:SignatureValue
    sig_val = etree.SubElement(signature_el, f"{{{ds_ns}}}SignatureValue")
    sig_val.text = signature_b64
    
    # Append ds:KeyInfo
    key_info = etree.SubElement(signature_el, f"{{{ds_ns}}}KeyInfo")
    x509_data = etree.SubElement(key_info, f"{{{ds_ns}}}X509Data")
    x509_cert = etree.SubElement(x509_data, f"{{{ds_ns}}}X509Certificate")
    x509_cert.text = cert_b64
    
    # Append ds:Object containing QualifyingProperties
    obj_el = etree.SubElement(signature_el, f"{{{ds_ns}}}Object")
    qual_prop = etree.Element(f"{{{xades_ns}}}QualifyingProperties", Target="#signature")
    qual_prop.append(sp_root)
    obj_el.append(qual_prop)
    
    # Inject into the XML skeleton
    ext_content_nodes = root.xpath('//ext:UBLExtension/ext:ExtensionContent', namespaces=namespaces)
    if ext_content_nodes:
        doc_sigs = ext_content_nodes[0].xpath('//sig:UBLDocumentSignatures/sac:SignatureInformation', namespaces=namespaces)
        if doc_sigs:
            doc_sigs[0].append(signature_el)
            
    final_xml = etree.tostring(root, xml_declaration=True, encoding='utf-8', pretty_print=True).decode('utf-8')
    
    # Fallback string replacement to guarantee placeholder replacement
    if 'WILL_BE_REPLACED_WITH_BASE64_QR_CODE' in final_xml:
        final_xml = final_xml.replace('WILL_BE_REPLACED_WITH_BASE64_QR_CODE', qr_code)
        
    return final_xml

if __name__ == '__main__':
    dummy_invoice = {
        'invoice_id': 'INV-2026-0001',
        'uuid': '95e8f498-5c4d-4e2b-98f6-17b5c8f85fca',
        'issue_date': '2026-06-18',
        'issue_time': '22:42:00',
        'icv': '1',
        'previous_hash': 'NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ==',
        'supplier': {
            'crn': '1010000000',
            'name': 'Dummy Developer Enterprise SA',
            'street_name': 'King Fahd Road',
            'building_number': '1234',
            'city_subdivision': 'Al Olaya',
            'city_name': 'Riyadh',
            'postal_zone': '12211',
            'country': 'SA',
            'vat_number': '399999999900003'
        },
        'customer': {
            'name': 'Saudi Tech Buyer LLC',
            'vat_number': '300000000000003'
        },
        'items': [
            {
                'name': 'Sandbox Cloud Integration Service',
                'quantity': 1.0,
                'price': 500.0,
                'vat_percent': 15.0
            }
        ]
    }
    
    print("Orchestrating invoice signing process...")
    signed_xml_output = generate_final_signed_invoice(dummy_invoice)
    
    output_filename = "final_cleared_invoice.xml"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(signed_xml_output)
        
    print(f"Success! Final signed XML invoice saved to: {output_filename}")
