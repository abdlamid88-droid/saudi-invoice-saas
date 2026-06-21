import os
import re
import json
import uuid
import base64
import argparse
import requests
from cryptography import x509
from cryptography.x509.oid import NameOID, ObjectIdentifier
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

def get_asn1_template_bytes(environment_type: str) -> bytes:
    """
    Returns the DER ASN.1 PrintableString bytes for the certificateTemplateName extension.
    """
    if environment_type == 'NonProduction':
        template = 'TSTZATCA-Code-Signing'
    elif environment_type == 'Simulation':
        template = 'PREZATCA-Code-Signing'
    elif environment_type == 'Production':
        template = 'ZATCA-Code-Signing'
    else:
        raise ValueError("Invalid environment type. Choose from: NonProduction, Simulation, Production.")
    
    # PrintableString tag is 0x13 (19)
    return bytes([0x13, len(template)]) + template.encode('ascii')

def generate_key_and_csr(config: dict, environment_type: str) -> tuple[str, str, str]:
    """
    Generates a secp256k1 EC private key and ZATCA-compliant CSR.
    
    Returns:
        tuple: (private_key_pem_clean, csr_base64, private_key_pem_full)
    """
    # 1. Generate private key (secp256k1 curve)
    private_key = ec.generate_private_key(ec.SECP256K1())
    
    # 2. Build Subject DN
    subject_dn = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, config.get("country", "SA")),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, config.get("ou", "")),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, config.get("organization", "")),
        x509.NameAttribute(NameOID.COMMON_NAME, config.get("common_name", ""))
    ])
    
    # 3. Create CSR Builder
    builder = x509.CertificateSigningRequestBuilder().subject_name(subject_dn)
    
    # 4. Add custom certificate template OID (1.3.6.1.4.1.311.20.2)
    template_bytes = get_asn1_template_bytes(environment_type)
    builder = builder.add_extension(
        x509.UnrecognizedExtension(
            ObjectIdentifier("1.3.6.1.4.1.311.20.2"),
            template_bytes
        ),
        critical=False
    )
    
    # 5. Add ZATCA specific attributes to SAN (directoryName)
    san_dn = x509.Name([
        x509.NameAttribute(ObjectIdentifier("2.5.4.4"), config.get("serial_number", "")),
        x509.NameAttribute(ObjectIdentifier("0.9.2342.19200300.100.1.1"), config.get("vat_number", "")),
        x509.NameAttribute(ObjectIdentifier("2.5.4.12"), config.get("invoice_type", "1100")),
        x509.NameAttribute(ObjectIdentifier("2.5.4.26"), config.get("location", "")),
        x509.NameAttribute(ObjectIdentifier("2.5.4.15"), config.get("business_category", ""))
    ])
    
    builder = builder.add_extension(
        x509.SubjectAlternativeName([
            x509.DirectoryName(san_dn)
        ]),
        critical=False
    )
    
    # 6. Sign CSR
    csr = builder.sign(private_key, hashes.SHA256())
    
    # 7. Serialize private key and CSR to PEM
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )
    csr_pem = csr.public_bytes(serialization.Encoding.PEM)
    
    # 8. Format key and CSR as expected by ZATCA
    private_key_pem_str = private_key_pem.decode('utf-8')
    private_key_clean = re.sub(
        r'-----BEGIN .* PRIVATE KEY-----|-----END .* PRIVATE KEY-----|\s', '', 
        private_key_pem_str
    )
    
    csr_base64 = base64.b64encode(csr_pem).decode('utf-8')
    
    return private_key_clean, csr_base64, private_key_pem_str

def request_compliance_csid(csr_base64: str, otp: str, environment_type: str) -> dict:
    """
    Submits the CSR and OTP to the ZATCA Compliance CSID API.
    """
    # Determine API path based on environment type
    if environment_type == 'NonProduction':
        api_path = 'developer-portal'
    elif environment_type == 'Simulation':
        api_path = 'simulation'
    elif environment_type == 'Production':
        api_path = 'core'
    else:
        raise ValueError("Invalid environment type.")
        
    url = f"https://gw-fatoora.zatca.gov.sa/e-invoicing/{api_path}/compliance"
    
    headers = {
        'accept': 'application/json',
        'accept-language': 'en',
        'OTP': otp,
        'Accept-Version': 'V2',
        'Content-Type': 'application/json',
    }
    
    payload = json.dumps({'csr': csr_base64})
    
    print(f"Sending CSR to ZATCA Compliance CSID API ({url})...")
    response = requests.post(url, headers=headers, data=payload)
    
    if response.status_code != 200:
        raise Exception(f"ZATCA API Error: {response.status_code} - {response.text}")
        
    return response.json()

def main():
    parser = argparse.ArgumentParser(description="ZATCA Phase 2 E-Invoicing Onboarding (CSR & OTP Authentication)")
    parser.add_argument("--env", choices=["NonProduction", "Simulation", "Production"], default="NonProduction",
                        help="ZATCA environment type (default: NonProduction / Sandbox)")
    parser.add_argument("--otp", help="One-Time Password (OTP) from ZATCA Fatoora Portal")
    parser.add_argument("--vat", default="399999999900003", help="15-digit VAT / Tax Registration Number")
    parser.add_argument("--company", default="Maximum Speed Tech Supply LTD", help="Legal Company Name")
    parser.add_argument("--ou", default="Riyadh Branch", help="Organizational Unit / Branch Name")
    parser.add_argument("--location", default="RRRD2929", help="Registered Location Address")
    parser.add_argument("--industry", default="Supply activities", help="Industry/Business Category")
    parser.add_argument("--common-name", help="Common Name / EGS Device Name")
    parser.add_argument("--serial", help="Serial Number (Device Serial Number / UUID)")
    
    args = parser.parse_args()
    
    print("\n=== ZATCA PHASE 2 ONBOARDING SCRIPT ===\n")
    
    # 1. Prompt for OTP if not supplied
    otp = args.otp
    if not otp:
        print("Tip: You can get an OTP by logging into the ZATCA Fatoora portal.")
        otp = input("Please enter the ZATCA OTP: ").strip()
        if not otp:
            print("Error: OTP is required for onboarding.")
            return

    # Generate custom IDs if not supplied
    guid_string = str(uuid.uuid4()).upper()
    common_name = args.common_name or f"TST-{args.vat[:9]}-{args.vat}"
    serial_number = args.serial or f"1-TST|2-TST|3-{guid_string}"
    
    csr_config = {
        "country": "SA",
        "ou": args.ou,
        "organization": args.company,
        "common_name": common_name,
        "serial_number": serial_number,
        "vat_number": args.vat,
        "invoice_type": "1100", # Default code for Standard and Simplified invoices
        "location": args.location,
        "business_category": args.industry
    }
    
    print("Configuration Parameters:")
    print(json.dumps(csr_config, indent=4))
    
    # 2. Generate Private Key and CSR
    print("\nGenerating secp256k1 key and CSR...")
    private_key_clean, csr_base64, private_key_pem_full = generate_key_and_csr(csr_config, args.env)
    
    print("Key & CSR generated successfully.")
    
    # 3. Call ZATCA API with OTP
    try:
        response_data = request_compliance_csid(csr_base64, otp, args.env)
    except Exception as e:
        print(f"\nFailed to request Compliance CSID: {e}")
        return
        
    print("\nCompliance CSID requested successfully!")
    
    # 4. Save results to local files
    os.makedirs("certificates", exist_ok=True)
    
    # Save Private Key PEM
    private_key_file = "certificates/PrivateKey.pem"
    with open(private_key_file, "w") as f:
        f.write(private_key_pem_full)
    print(f"Saved private key to: {private_key_file}")
    
    # Save CSR PEM (for reference)
    csr_pem_file = "certificates/taxpayer.csr"
    # Decoded from Base64 to save as regular PEM file
    csr_pem_bytes = base64.b64decode(csr_base64)
    with open(csr_pem_file, "wb") as f:
        f.write(csr_pem_bytes)
    print(f"Saved CSR file to: {csr_pem_file}")
    
    # Save full certificate metadata details
    cert_info = {
        "environmentType": args.env,
        "csr_config": csr_config,
        "csr": csr_base64,
        "privateKey": private_key_clean,
        "OTP": otp,
        "ccsid_requestID": response_data.get("requestID"),
        "ccsid_binarySecurityToken": response_data.get("binarySecurityToken"),
        "ccsid_secret": response_data.get("secret"),
    }
    
    metadata_file = "certificates/certificateInfo.json"
    with open(metadata_file, "w") as f:
        json.dump(cert_info, f, indent=4)
    print(f"Saved onboarding credentials to: {metadata_file}")
    
    print("\nOnboarding completed successfully! You can now run compliance invoice submissions.")

if __name__ == "__main__":
    main()
