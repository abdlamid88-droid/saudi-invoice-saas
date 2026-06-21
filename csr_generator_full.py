# csr_generator.py
from cryptography import x509
from cryptography.x509.oid import NameOID, ObjectIdentifier
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
import base64
import os
import re

class Csr_Generator:
    def __init__(self, config, environment_type):
        self.config = config
        self.environment_type = environment_type
        self.asn_template = self.get_asn_template()

    def get_asn_template(self):
        if self.environment_type == 'NonProduction':
            return '..TSTZATCA-Code-Signing'
        elif self.environment_type == 'Simulation':
            return '..PREZATCA-Code-Signing'
        elif self.environment_type == 'Production':
            return '..ZATCA-Code-Signing'
        else:
            raise ValueError("Invalid environment type specified.")

    def generate_private_key(self):
        return ec.generate_private_key(ec.SECP256K1(), default_backend())

    def generate_csr(self):
        private_key = self.generate_private_key()
        
        # Build the CSR
        csr_builder = x509.CertificateSigningRequestBuilder()
        csr_builder = csr_builder.subject_name(x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, self.config.get('csr.country.name', 'SA')),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, self.config.get('csr.organization.unit.name', '')),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, self.config.get('csr.organization.name', '')),
            x509.NameAttribute(NameOID.COMMON_NAME, self.config.get('csr.common.name', ''))
        ]))
        
        # Add ASN.1 extension
        #template_bytes = bytes([0x13, len(self.asn_template)]) + self.asn_template.encode('ascii')
        csr_builder = csr_builder.add_extension(
            x509.UnrecognizedExtension(
                ObjectIdentifier("1.3.6.1.4.1.311.20.2"), 
                #template_bytes
                self.asn_template.encode()
            ),
            critical=False
        )
        
        # Add SAN extension
        csr_builder = csr_builder.add_extension(
            x509.SubjectAlternativeName([
                x509.DirectoryName(x509.Name([
                    x509.NameAttribute(ObjectIdentifier("2.5.4.4"), self.config.get('csr.serial.number', '')),
                    x509.NameAttribute(ObjectIdentifier("0.9.2342.19200300.100.1.1"), self.config.get('csr.organization.identifier', '')),
                    x509.NameAttribute(ObjectIdentifier("2.5.4.12"), self.config.get('csr.invoice.type', '')),
                    x509.NameAttribute(ObjectIdentifier("2.5.4.26"), self.config.get('csr.location.address', '')),
                    x509.NameAttribute(ObjectIdentifier("2.5.4.15"), self.config.get('csr.industry.business.category', ''))
                ]))
            ]),
            critical=False
        )

        # Sign the CSR with the private key
        csr = csr_builder.sign(private_key, hashes.SHA256(), default_backend())

        # Serialize private key and CSR
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )
        csr_pem = csr.public_bytes(serialization.Encoding.PEM)

        # Strip header/footer from private key
        private_key_content = re.sub(
            r'-----BEGIN .* PRIVATE KEY-----|-----END .* PRIVATE KEY-----|\n', '', 
            private_key_pem.decode('utf-8')
        )

        # Encode CSR in Base64
        csr_base64 = base64.b64encode(csr_pem).decode('utf-8')

        return private_key_content, csr_base64

    def save_to_files(self, private_key_pem, csr_pem):
        os.makedirs("certificates", exist_ok=True)
        private_key_file = 'certificates/PrivateKey.pem'
        csr_file = 'certificates/taxpayer.csr'
        
        with open(private_key_file, "wb") as key_file:
            key_file.write(private_key_pem)
        
        with open(csr_file, "wb") as csr_file:
            csr_file.write(csr_pem)
        
        print(f"\nPrivate key and CSR have been saved to {private_key_file} and {csr_file}, respectively.")
