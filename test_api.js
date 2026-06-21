const crypto = require('crypto');

async function testZatcaAPI() {
    try {
        console.log("⏳ 1. Generating temporary secp256k1 private key...");
        // توليد مفتاح خاص وهمي وسليم لحظياً للاختبار
        const { privateKey } = crypto.generateKeyPairSync('ec', {
            namedCurve: 'secp256k1',
            privateKeyEncoding: { type: 'pkcs8', format: 'pem' }
        });

        const payload = {
            xmlString: "<Invoice xmlns=\"urn:oasis:names:specification:ubl:schema:xsd:Invoice-2\" xmlns:cbc=\"urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2\" xmlns:cac=\"urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2\" xmlns:ext=\"urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2\"><cbc:ID>INV-001</cbc:ID><cbc:IssueDate>2026-06-16</cbc:IssueDate></Invoice>",
            privateKeyPem: privateKey,
            supplierName: "Blind Invoice MVP",
            vatNumber: "311111111111113",
            timestamp: "2026-06-16T12:00:00Z",
            totalAmount: "115.00",
            vatAmount: "15.00"
        };

        console.log("🚀 2. Sending request to local Express server...");
        const response = await fetch('http://localhost:3000/invoice/sign', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        console.log("✅ API Response:\n", JSON.stringify(data, null, 2));
    } catch (error) {
        console.error("❌ Request Failed:", error.message);
    }
}

testZatcaAPI();
