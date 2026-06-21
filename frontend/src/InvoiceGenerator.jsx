import React, { useState, useEffect } from 'react';
import { QRCodeSVG } from 'qrcode.react';

const InvoiceGenerator = () => {
  // الحقول الديناميكية للنموذج
  const [supplierName, setSupplierName] = useState('Blind Invoice MVP');
  const [vatNumber, setVatNumber] = useState('311111111111113');
  const [amountBeforeVat, setAmountBeforeVat] = useState('');
  const [vatAmount, setVatAmount] = useState('0.00');
  const [totalAmount, setTotalAmount] = useState('0.00');

  // حالات السيرفر والأرشيف
  const [qrData, setQrData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [selectedQr, setSelectedQr] = useState(null);

  // تحديث الحسابات تلقائياً عند تغيير المبلغ الأساسي
  useEffect(() => {
    const baseAmount = parseFloat(amountBeforeVat) || 0;
    const vat = baseAmount * 0.15; // نسبة الضريبة 15%
    const total = baseAmount + vat;

    setVatAmount(vat.toFixed(2));
    setTotalAmount(total.toFixed(2));
  }, [amountBeforeVat]);

  // جلب الفواتير المؤرشفة من خادم الـ SQLite
  const fetchInvoices = async () => {
    try {
      const response = await fetch('http://localhost:5000/api/invoices');
      const data = await response.json();
      if (data.success) {
        setInvoices(data.data);
      }
    } catch (err) {
      console.error("خطأ أثناء تحديث الأرشيف:", err);
    }
  };

  useEffect(() => {
    fetchInvoices();
  }, []);

  // 🔥 دالة توليد الـ XML (UBL 2.1) ديناميكياً بناءً على مدخلات المستخدم
  const generateDynamicXML = (supplier, vatNo, time, total, vat) => {
    // تنسيق التاريخ والوقت المفصولين ليتوافقا مع الحقول القياسية لـ UBL
    const dateOnly = time.split('T')[0];
    const timeOnly = time.split('T')[1].substring(0, 8);

    return `<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" 
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" 
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:ProfileID>urn:fdc:zatca.gov.sa:invoice:2021</cbc:ProfileID>
    <cbc:ID>INV-${Date.now().toString().substring(8)}</cbc:ID>
    <cbc:UUID>${crypto.randomUUID ? crypto.randomUUID() : '123e4567-e89b-12d3-a456-426614174000'}</cbc:UUID>
    <cbc:IssueDate>${dateOnly}</cbc:IssueDate>
    <cbc:IssueTime>${timeOnly}</cbc:IssueTime>
    <cbc:InvoiceTypeCode name="0111000">388</cbc:InvoiceTypeCode>
    <cbc:DocumentCurrencyCode>SAR</cbc:DocumentCurrencyCode>
    <cbc:TaxCurrencyCode>SAR</cbc:TaxCurrencyCode>
    <cac:AccountingSupplierParty>
        <cac:Party>
            <cac:PartyName>
                <cbc:Name>${supplier}</cbc:Name>
            </cac:PartyName>
            <cac:PartyTaxScheme>
                <cbc:CompanyID>${vatNo}</cbc:CompanyID>
                <cac:TaxScheme>
                    <cbc:ID>VAT</cbc:ID>
                </cac:TaxScheme>
            </cac:PartyTaxScheme>
        </cac:Party>
    </cac:AccountingSupplierParty>
    <cac:LegalMonetaryTotal>
        <cbc:LineExtensionAmount currencyID="SAR">${parseFloat(total - vat).toFixed(2)}</cbc:LineExtensionAmount>
        <cbc:TaxExclusiveAmount currencyID="SAR">${parseFloat(total - vat).toFixed(2)}</cbc:TaxExclusiveAmount>
        <cbc:TaxInclusiveAmount currencyID="SAR">${total}</cbc:TaxInclusiveAmount>
        <cbc:AllowanceTotalAmount currencyID="SAR">0.00</cbc:AllowanceTotalAmount>
        <cbc:ChargeTotalAmount currencyID="SAR">0.00</cbc:ChargeTotalAmount>
        <cbc:PrepaidAmount currencyID="SAR">0.00</cbc:PrepaidAmount>
        <cbc:PayableAmount currencyID="SAR">${total}</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
</Invoice>`;
  };

  const handleGenerateInvoice = async (e) => {
    e.preventDefault();
    
    if (!amountBeforeVat || parseFloat(amountBeforeVat) <= 0) {
      setError("الرجاء إدخال مبلغ فاتورة صحيح");
      return;
    }

    setLoading(true);
    setError(null);

    const currentTime = new Date().toISOString();

    // 🔥 توليد ملف الـ XML الديناميكي الحقيقي بالقيم الحالية قبل الإرسال
    const dynamicXml = generateDynamicXML(supplierName, vatNumber, currentTime, totalAmount, vatAmount);

    const invoicePayload = {
      xmlString: dynamicXml, // إرسال الـ XML الحقيقي والمحدث
      privateKeyPem: "-----BEGIN EC PRIVATE KEY-----\nMHcCAQEEIL...\n-----END EC PRIVATE KEY-----", 
      supplierName: supplierName,
      vatNumber: vatNumber,
      timestamp: currentTime,
      totalAmount: totalAmount,
      vatAmount: vatAmount
    };

    try {
      const response = await fetch('http://localhost:5000/invoice/sign', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(invoicePayload),
      });

      const data = await response.json();

      if (data.success) {
        setQrData(data.qrCodeBase64);
        fetchInvoices(); // تحديث الجدول بالأسفل تلقائياً
      } else {
        setError(data.error || "حدث خطأ أثناء التشفير");
      }
    } catch (err) {
      setError("فشل الاتصال بالخادم. تأكد من تشغيل Express API.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '20px', maxWidth: '850px', margin: '0 auto', fontFamily: 'sans-serif', direction: 'rtl' }}>
      
      {/* قسم توليد الفواتير العلوي المحتوي على النموذج */}
      <div style={{ marginBottom: '40px', borderBottom: '1px solid #eee', paddingBottom: '30px' }}>
        <h2 style={{ textAlign: 'center' }}>نظام الفوترة الإلكترونية (ZATCA)</h2>
        
        <form onSubmit={handleGenerateInvoice} style={{ maxWidth: '500px', margin: '0 auto', textAlign: 'right', display: 'flex', flexDirection: 'column', gap: '15px' }}>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
            <label style={{ fontWeight: 'bold' }}>اسم المورد / الشركة:</label>
            <input 
              type="text" 
              value={supplierName} 
              onChange={(e) => setSupplierName(e.target.value)} 
              required
              style={{ padding: '8px', fontSize: '15px', borderRadius: '4px', border: '1px solid #ccc' }}
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
            <label style={{ fontWeight: 'bold' }}>الرقم الضريبي (15 رقم):</label>
            <input 
              type="text" 
              value={vatNumber} 
              onChange={(e) => setVatNumber(e.target.value)} 
              required
              maxLength={15}
              style={{ padding: '8px', fontSize: '15px', borderRadius: '4px', border: '1px solid #ccc' }}
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
            <label style={{ fontWeight: 'bold' }}>المبلغ الخاضع للضريبة (ر.س):</label>
            <input 
              type="number" 
              step="0.01"
              value={amountBeforeVat} 
              onChange={(e) => setAmountBeforeVat(e.target.value)} 
              required
              placeholder="0.00"
              style={{ padding: '8px', fontSize: '15px', borderRadius: '4px', border: '1px solid #ccc' }}
            />
          </div>

          {/* حقول الحساب التلقائي */}
          <div style={{ display: 'flex', gap: '20px' }}>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '5px' }}>
              <label style={{ color: '#555' }}>مبلغ الضريبة (15%):</label>
              <input 
                type="text" 
                value={vatAmount} 
                disabled 
                style={{ padding: '8px', fontSize: '15px', borderRadius: '4px', border: '1px solid #ddd', backgroundColor: '#e9ecef', fontWeight: 'bold' }}
              />
            </div>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '5px' }}>
              <label style={{ color: '#555' }}>الإجمالي شامل الضريبة:</label>
              <input 
                type="text" 
                value={totalAmount} 
                disabled 
                style={{ padding: '8px', fontSize: '15px', borderRadius: '4px', border: '1px solid #ddd', backgroundColor: '#e9ecef', fontWeight: 'bold', color: '#28a745' }}
              />
            </div>
          </div>

          <button 
            type="submit"
            disabled={loading}
            style={{ padding: '10px 20px', fontSize: '16px', cursor: 'pointer', marginTop: '10px', borderRadius: '4px', border: 'none', backgroundColor: '#007bff', color: '#fff', fontWeight: 'bold' }}
          >
            {loading ? 'جاري التشفير والاعتماد...' : 'إصدار الفاتورة واعتماد الـ QR'}
          </button>
        </form>

        {error && <p style={{ color: 'red', textAlign: 'center', marginTop: '15px' }}>{error}</p>}

        {qrData && (
          <div style={{ marginTop: '30px', textAlign: 'center' }}>
            <div style={{ padding: '20px', border: '1px solid #dee2e6', borderRadius: '8px', display: 'inline-block', backgroundColor: '#fff' }}>
              <h3 style={{ marginTop: 0 }}>الرمز الشريطي الحالي المعتمد</h3>
              <QRCodeSVG value={qrData} size={200} level={"M"} />
              <p style={{ fontSize: '12px', color: '#666', marginTop: '10px', wordBreak: 'break-all', maxWidth: '300px' }}>
                Base64: {qrData.substring(0, 40)}...
              </p>
            </div>
          </div>
        )}
      </div>

      {/* قسم الأرشيف الرقمي */}
      <div style={{ textAlign: 'right' }}>
        <h3 style={{ color: '#333', marginBottom: '20px' }}>📋 أرشيف الفواتير الرقمية المحفوظة (SQLite)</h3>
        
        <div style={{ display: 'flex', gap: '30px', flexWrap: 'wrap-reverse' }}>
          
          {/* جدول استعراض الفواتير */}
          <div style={{ flex: 2, minWidth: '350px' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', backgroundColor: '#fff', boxShadow: '0 2px 4px rgba(0,0,0,0.05)' }}>
              <thead>
                <tr style={{ backgroundColor: '#f8f9fa', borderBottom: '2px solid #dee2e6' }}>
                  <th style={{ padding: '12px', border: '1px solid #dee2e6', textAlign: 'right' }}>اسم المورد</th>
                  <th style={{ padding: '12px', border: '1px solid #dee2e6', textAlign: 'right' }}>الرقم الضريبي</th>
                  <th style={{ padding: '12px', border: '1px solid #dee2e6', textAlign: 'right' }}>التاريخ والوقت</th>
                  <th style={{ padding: '12px', border: '1px solid #dee2e6', textAlign: 'right' }}>الإجمالي (TTC)</th>
                  <th style={{ padding: '12px', border: '1px solid #dee2e6', textAlign: 'center' }}>العمليات</th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((inv) => (
                  <tr key={inv.id} style={{ borderBottom: '1px solid #dee2e6' }}>
                    <td style={{ padding: '12px', border: '1px solid #dee2e6' }}>{inv.supplierName}</td>
                    <td style={{ padding: '12px', border: '1px solid #dee2e6' }}>{inv.vatNumber}</td>
                    <td style={{ padding: '12px', border: '1px solid #dee2e6', fontSize: '13px', color: '#555' }}>
                      {new Date(inv.createdAt).toLocaleString('ar-EG')}
                    </td>
                    <td style={{ padding: '12px', border: '1px solid #dee2e6', fontWeight: 'bold', color: '#28a745' }}>
                      {inv.totalAmount} ر.س
                    </td>
                    <td style={{ padding: '12px', border: '1px solid #dee2e6', textAlign: 'center' }}>
                      <button 
                        onClick={() => setSelectedQr(inv.qrCodeBase64)}
                        style={{ backgroundColor: '#007bff', color: '#fff', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer', fontSize: '13px' }}
                      >
                        👁️ معاينة الـ QR
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* نافذة معاينة الـ QR من الأرشيف */}
          {selectedQr && (
            <div style={{ flex: 1, minWidth: '250px', border: '1px solid #dee2e6', padding: '20px', borderRadius: '8px', textAlign: 'center', backgroundColor: '#fdfdfd', alignSelf: 'flex-start' }}>
              <h4 style={{ margin: '0 0 15px 0', color: '#555' }}>🛡️ الرمز المسترجع من الأرشيف</h4>
              <div style={{ padding: '15px', backgroundColor: '#fff', display: 'inline-block', border: '1px solid #eee', borderRadius: '4px' }}>
                <QRCodeSVG value={selectedQr} size={160} level={"M"} />
              </div>
              <div style={{ marginTop: '15px' }}>
                <button 
                  onClick={() => setSelectedQr(null)}
                  style={{ backgroundColor: '#dc3545', color: '#fff', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer', fontSize: '13px' }}
                >
                  إغلاق المعاينة
                </button>
              </div>
            </div>
          )}

        </div>
      </div>

    </div>
  );
};

export default InvoiceGenerator;
