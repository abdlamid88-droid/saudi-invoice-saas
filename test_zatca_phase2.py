import unittest
import base64
import hashlib
from lxml import etree
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed

# Import the module under test
from zatca_phase2 import generate_tlv_qr_code, hash_and_sign_invoice

class TestZatcaPhase2(unittest.TestCase):
    
    def setUp(self):
        # Generate a private key using secp256k1 for testing
        self.private_key = ec.generate_private_key(ec.SECP256K1())
        self.private_key_pem = self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')
        
        # Create a mock UBL 2.1 invoice XML
        self.mock_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
         xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2">
    <ext:UBLExtensions>
        <ext:UBLExtension>
            <ext:ExtensionContent>
                <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
                    <ds:SignatureValue>MockSignatureValue</ds:SignatureValue>
                </ds:Signature>
            </ext:ExtensionContent>
        </ext:UBLExtension>
    </ext:UBLExtensions>
    <cbc:ID>INV-12345</cbc:ID>
    <cbc:IssueDate>2026-06-16</cbc:IssueDate>
    <cac:Signature>
        <cbc:ID>urn:oasis:names:specification:ubl:signature:Invoice</cbc:ID>
    </cac:Signature>
    <cac:AdditionalDocumentReference>
        <cbc:ID>QR</cbc:ID>
        <cbc:UUID>some-uuid</cbc:UUID>
    </cac:AdditionalDocumentReference>
    <cac:AdditionalDocumentReference>
        <cbc:ID>ICV</cbc:ID>
        <cbc:UUID>another-uuid</cbc:UUID>
    </cac:AdditionalDocumentReference>
    <cac:AccountingSupplierParty>
        <cac:Party>
            <cac:PartyName>
                <cbc:Name>Supplier Ltd</cbc:Name>
            </cac:PartyName>
        </cac:Party>
    </cac:AccountingSupplierParty>
</Invoice>
"""

    def test_generate_tlv_qr_code_basic(self):
        # Phase 1 basic fields
        tags = {
            1: "Seller Name",
            2: "123456789012345",
            3: "2026-06-16T15:09:14Z",
            4: "115.00",
            5: "15.00"
        }
        
        qr_code = generate_tlv_qr_code(tags)
        
        # Verify it's a valid Base64 string
        decoded_bytes = base64.b64decode(qr_code)
        
        # Let's inspect the TLV structure
        # First tag should be 1
        self.assertEqual(decoded_bytes[0], 1)
        # Next byte should be length of "Seller Name" (11)
        self.assertEqual(decoded_bytes[1], 11)
        # Value should be "Seller Name"
        self.assertEqual(decoded_bytes[2:13].decode('utf-8'), "Seller Name")
        
        # Check tag 2
        offset = 13
        self.assertEqual(decoded_bytes[offset], 2)
        self.assertEqual(decoded_bytes[offset + 1], 15)
        self.assertEqual(decoded_bytes[offset + 2:offset + 17].decode('utf-8'), "123456789012345")

    def test_generate_tlv_qr_code_invalid_tag(self):
        with self.assertRaises(ValueError):
            generate_tlv_qr_code({10: "Invalid Tag"})
            
    def test_generate_tlv_qr_code_value_too_long(self):
        with self.assertRaises(ValueError):
            generate_tlv_qr_code({1: "a" * 256})

    def test_hash_and_sign_invoice(self):
        # Compute hash and signature
        invoice_hash, signature_b64, public_key_der = hash_and_sign_invoice(
            self.mock_xml, 
            self.private_key_pem
        )
        
        # 1. Verify the invoice hash is Base64 of SHA-256
        # Let's calculate the expected stripped XML manually to compare
        parser = etree.XMLParser(remove_blank_text=True)
        root = etree.fromstring(self.mock_xml, parser)
        
        namespaces = {
            'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'
        }
        
        # Strip elements
        for elem in root.xpath('//ext:UBLExtensions', namespaces=namespaces):
            elem.getparent().remove(elem)
        for elem in root.xpath('//cac:Signature', namespaces=namespaces):
            elem.getparent().remove(elem)
        for elem in root.xpath('//cac:AdditionalDocumentReference[cbc:ID="QR"]', namespaces=namespaces):
            elem.getparent().remove(elem)
            
        expected_canon = etree.tostring(root, method="c14n", exclusive=False, with_comments=False)
        expected_hash = hashlib.sha256(expected_canon).digest()
        expected_hash_b64 = base64.b64encode(expected_hash).decode('utf-8')
        
        self.assertEqual(invoice_hash, expected_hash_b64)
        
        # 2. Verify signature format (Base64 of raw 64 bytes)
        raw_sig = base64.b64decode(signature_b64)
        self.assertEqual(len(raw_sig), 64)
        
        # 3. Verify public key loads correctly
        pub_key = serialization.load_der_public_key(public_key_der)
        self.assertIsInstance(pub_key, ec.EllipticCurvePublicKey)
        self.assertIsInstance(pub_key.curve, ec.SECP256K1)
        
        # 4. Verify signature validates against the hash
        # To verify raw (r, s) signature, we convert it back to DER signature format
        r = int.from_bytes(raw_sig[:32], byteorder='big')
        s = int.from_bytes(raw_sig[32:], byteorder='big')
        
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
        der_signature = encode_dss_signature(r, s)
        
        # Verification should not raise an exception
        pub_key.verify(
            der_signature,
            expected_hash,
            ec.ECDSA(Prehashed(hashes.SHA256()))
        )

if __name__ == '__main__':
    unittest.main()
