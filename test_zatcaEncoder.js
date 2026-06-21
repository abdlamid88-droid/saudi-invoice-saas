const assert = require('assert');
const crypto = require('crypto');
const { generateTlvQrCode, hashAndSignInvoice } = require('./zatcaEncoder');

// 1. Mock XML invoice matching the Python playground (canonicalized base case)
const mockXml = `<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
         xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2">
    <ext:UBLExtensions>
        <ext:UBLExtension>
            <ext:ExtensionURI>urn:oasis:names:specification:ubl:dsig:enveloped:xades</ext:ExtensionURI>
            <ext:ExtensionContent>
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
</Invoice>`;

async function runTests() {
  console.log("=== RUNNING NODE.JS ENCODER TESTS ===\n");

  // Generate private key (secp256k1)
  const { privateKey, publicKey } = crypto.generateKeyPairSync('ec', {
    namedCurve: 'secp256k1'
  });

  const privateKeyPem = privateKey.export({
    type: 'pkcs8',
    format: 'pem'
  });

  // Test 1: XML Hash and Sign
  console.log("Test 1: XML Hash and Sign...");
  const result = hashAndSignInvoice(mockXml, privateKeyPem);
  
  console.log(`- Generated Hash: ${result.invoiceHash}`);
  console.log(`- Generated Signature: ${result.signature.substring(0, 30)}...`);

  // Verify that the hash matches the standard expected hash from the Python playground
  const expectedHash = '6bTgVsju3MkzFAD2NyUqV69dz9YOq5FyJOI19Pj8eEQ=';
  assert.strictEqual(
    result.invoiceHash, 
    expectedHash, 
    `Hash mismatch! Expected: ${expectedHash}, got: ${result.invoiceHash}`
  );
  console.log("[PASS] XML Hash matches Python playground exactly!");

  // Verify the signature on the hash using public key
  const signatureBuffer = Buffer.from(result.signature, 'base64');
  const hashBuffer = Buffer.from(result.invoiceHash, 'base64');

  const verify = crypto.createVerify('SHA256');
  // Verify uses the canonicalized XML as data since crypto.sign automatically hashes the data
  // But wait, our hashAndSignInvoice function called sign.update(canonicalXml)
  // So to verify, we pass the canonicalized XML to verify.update()!
  const { stripXmlForHashing, c14nSerialize } = require('./zatcaEncoder');
  const canonicalXml = c14nSerialize(stripXmlForHashing(mockXml));
  verify.update(canonicalXml);

  const isVerified = verify.verify({
    key: publicKey,
    dsaEncoding: 'ieee-p1363'
  }, signatureBuffer);

  assert.ok(isVerified, "ECDSA Signature verification failed!");
  console.log("[PASS] ECDSA Signature verified successfully!");

  // Test 2: TLV QR Code Generation
  console.log("\nTest 2: TLV QR Code Generation...");
  const qrBase64 = generateTlvQrCode({
    1: "Dummy Developer Enterprise",
    2: "399999999900003",
    3: "2026-06-16T17:20:00Z",
    4: "115.00",
    5: "15.00",
    6: result.invoiceHash,
    7: result.signature,
    8: result.publicKeyDer,
    9: Buffer.from("mock-cert-signature-value")
  });

  console.log(`- Generated Base64 QR Code length: ${qrBase64.length}`);
  assert.ok(qrBase64.length > 100, "QR Code too short!");
  console.log("[PASS] TLV QR Code generated successfully!");

  console.log("\n=== ALL TESTS PASSED SUCCESSFULLY ===");
}

runTests().catch(err => {
  console.error(err);
  process.exit(1);
});
