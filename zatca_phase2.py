import base64
import hashlib
from typing import Dict, Union, Tuple
from lxml import etree
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, Prehashed
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes

def generate_tlv_qr_code(tags: Dict[int, Union[str, bytes]]) -> str:
    """
    Generates a ZATCA-compliant Base64 encoded QR code from a dictionary of TLV tags.
    
    In ZATCA Phase 2:
    - Tags 1-7 represent UTF-8 encoded text/values.
    - Tags 8-9 represent raw binary data (DER public key and Certificate Signature).
    
    Args:
        tags (Dict[int, Union[str, bytes]]): A dictionary mapping tag IDs (1-9) to their values.
        
    Returns:
        str: The final Base64 encoded TLV structured QR code string.
        
    Raises:
        ValueError: If a tag ID is out of range (not 1-9) or if a tag's value length in bytes exceeds 255.
    """
    tlv_bytes = bytearray()
    
    for tag_id in sorted(tags.keys()):
        if not (1 <= tag_id <= 9):
            raise ValueError(f"Invalid tag ID: {tag_id}. Tags must be between 1 and 9.")
            
        value = tags[tag_id]
        
        # Determine value bytes and encode appropriately
        if isinstance(value, bytes):
            value_bytes = value
        elif isinstance(value, str):
            value_bytes = value.encode('utf-8')
        else:
            value_bytes = str(value).encode('utf-8')
            
        length = len(value_bytes)
        if length > 255:
            raise ValueError(f"Value for tag {tag_id} exceeds maximum allowed length of 255 bytes (got {length} bytes).")
            
        tlv_bytes.append(tag_id)
        tlv_bytes.append(length)
        tlv_bytes.extend(value_bytes)
        
    return base64.b64encode(tlv_bytes).decode('utf-8')

def hash_and_sign_invoice(xml_content: bytes, private_key_pem: str) -> Tuple[str, str, bytes]:
    """
    Calculates the SHA-256 hash of an XML UBL 2.1 invoice (pre-signing state) 
    and signs it using ECDSA with the secp256k1 curve.
    
    The function performs the following steps:
    1. Removes elements that are modified or added during the signing process:
       - <ext:UBLExtensions>
       - <cac:Signature>
       - <cac:AdditionalDocumentReference> where <cbc:ID> is "QR"
    2. Canonicalizes the XML using C14N 1.0 (equivalent to 1.1 for standard UBL structures).
    3. Calculates the SHA-256 hash of the canonicalized XML and encodes it in Base64.
    4. Signs the SHA-256 hash using the provided private key (secp256k1 curve).
    5. Converts the DER signature to the raw 64-byte format (IEEE P1363) required by ZATCA
       and encodes it in Base64.
    6. Extracts the public key in DER format.
    
    Args:
        xml_content (bytes): The raw XML bytes of the UBL 2.1 invoice.
        private_key_pem (str): The PEM-encoded ECDSA private key (using the secp256k1 curve).
        
    Returns:
        Tuple[str, str, bytes]: A tuple containing:
            - invoice_hash_b64 (str): Base64 encoded SHA-256 hash of the canonicalized XML.
            - signature_b64 (str): Base64 encoded raw 64-byte ECDSA signature (IEEE P1363).
            - public_key_der (bytes): Raw DER-encoded public key bytes (useful for Tag 8 of the QR code).
            
    Raises:
        TypeError: If the private key is not an Elliptic Curve private key.
        ValueError: If the private key does not use the secp256k1 curve.
    """
    # 1. Parse XML and strip elements
    parser = etree.XMLParser(remove_blank_text=True, resolve_entities=False)
    try:
        root = etree.fromstring(xml_content, parser)
    except etree.XMLSyntaxError as e:
        raise ValueError(f"Failed to parse XML: {e}")
        
    namespaces = {
        'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
        'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
        'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'
    }
    
    # Remove ext:UBLExtensions
    for elem in root.xpath('//ext:UBLExtensions', namespaces=namespaces):
        elem.getparent().remove(elem)
        
    # Remove cac:Signature
    for elem in root.xpath('//cac:Signature', namespaces=namespaces):
        elem.getparent().remove(elem)
        
    # Remove cac:AdditionalDocumentReference where cbc:ID is "QR"
    for elem in root.xpath('//cac:AdditionalDocumentReference[cbc:ID="QR"]', namespaces=namespaces):
        elem.getparent().remove(elem)
        
    # 2. Canonicalize XML (using C14N standard)
    canonicalized_xml = etree.tostring(root, method="c14n", exclusive=False, with_comments=False)
    
    # 3. Calculate SHA-256 hash
    sha256_hash = hashlib.sha256(canonicalized_xml).digest()
    invoice_hash_b64 = base64.b64encode(sha256_hash).decode('utf-8')
    
    # 4. Load private key
    try:
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode('utf-8'),
            password=None
        )
    except Exception as e:
        raise ValueError(f"Failed to load private key: {e}")
        
    if not isinstance(private_key, ec.EllipticCurvePrivateKey):
        raise TypeError("The provided key is not an Elliptic Curve Private Key.")
        
    # Verify it uses secp256k1 curve
    if not isinstance(private_key.curve, ec.SECP256K1):
        raise ValueError("The private key must use the secp256k1 curve.")
        
    # 5. Sign the SHA-256 hash
    der_signature = private_key.sign(
        sha256_hash,
        ec.ECDSA(Prehashed(hashes.SHA256()))
    )
    
    # 6. Convert DER signature to raw 64-byte format (IEEE P1363)
    r, s = decode_dss_signature(der_signature)
    r_bytes = r.to_bytes(32, byteorder='big')
    s_bytes = s.to_bytes(32, byteorder='big')
    raw_signature = r_bytes + s_bytes
    signature_b64 = base64.b64encode(raw_signature).decode('utf-8')
    
    # 7. Extract DER public key bytes
    public_key = private_key.public_key()
    public_key_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    return invoice_hash_b64, signature_b64, public_key_der
