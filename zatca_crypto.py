import base64
import hashlib
from lxml import etree
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, Prehashed
from cryptography.hazmat.primitives import hashes

def get_invoice_hash(xml_string: str) -> str:
    """
    Applies C14N canonicalization to the XML invoice after stripping dynamic signing
    elements, computes its SHA-256 hash, and returns the result in Base64.
    
    This matches ZATCA Phase 2 hashing requirements by stripping:
    - ext:UBLExtensions
    - cac:Signature
    - cac:AdditionalDocumentReference (where cbc:ID is 'QR')
    """
    parser = etree.XMLParser(remove_blank_text=True, resolve_entities=False)
    root = etree.fromstring(xml_string.encode('utf-8'), parser)
    
    namespaces = {
        'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
        'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
        'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'
    }
    
    # 1. Strip signature nodes modified/added during signing
    for elem in root.xpath('//ext:UBLExtensions', namespaces=namespaces):
        elem.getparent().remove(elem)
        
    for elem in root.xpath('//cac:Signature', namespaces=namespaces):
        elem.getparent().remove(elem)
        
    for elem in root.xpath('//cac:AdditionalDocumentReference[cbc:ID="QR"]', namespaces=namespaces):
        elem.getparent().remove(elem)
        
    # 2. Canonicalize XML (C14N 1.0)
    canonicalized_xml = etree.tostring(root, method="c14n", exclusive=False, with_comments=False)
    
    # 3. Compute SHA-256 hash
    sha256_hash = hashlib.sha256(canonicalized_xml).digest()
    return base64.b64encode(sha256_hash).decode('utf-8')

def generate_ecdsa_keys():
    """
    Generates a private and public key pair using ECDSA with the secp256k1 curve
    as mandated by ZATCA standards.
    
    Returns:
        private_key: The ec.EllipticCurvePrivateKey object.
        public_key: The ec.EllipticCurvePublicKey object.
    """
    private_key = ec.generate_private_key(ec.SECP256K1())
    public_key = private_key.public_key()
    return private_key, public_key

def sign_invoice(invoice_hash_b64: str, private_key) -> str:
    """
    Signs the Base64-encoded invoice hash using the ECDSA private key.
    Converts the standard DER signature to raw 64-byte format (IEEE P1363 - concatenated 32-byte R and S)
    required by ZATCA, and returns the result encoded in Base64.
    """
    # Decode Base64 hash to bytes
    invoice_hash_bytes = base64.b64decode(invoice_hash_b64)
    
    # Sign using ECDSA with secp256k1
    der_signature = private_key.sign(
        invoice_hash_bytes,
        ec.ECDSA(Prehashed(hashes.SHA256()))
    )
    
    # Convert DER (ASN.1) signature format to raw 64-byte format (R || S)
    r, s = decode_dss_signature(der_signature)
    r_bytes = r.to_bytes(32, byteorder='big')
    s_bytes = s.to_bytes(32, byteorder='big')
    raw_signature = r_bytes + s_bytes
    
    # Return Base64 of raw signature
    return base64.b64encode(raw_signature).decode('utf-8')
