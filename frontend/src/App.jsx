import { useState } from 'react'
import './App.css'
import InvoiceGenerator from './InvoiceGenerator' // استيراد المكون الجديد

function App() {
  return (
    <>
      <section id="center">
        <h1>نظام الفوترة الإلكترونية</h1>
        <p>متوافق مع متطلبات هيئة الزكاة والضريبة والجمارك</p>
        
        {/* استدعاء مكون الفاتورة هنا */}
        <InvoiceGenerator />
      </section>

      <section id="next-steps">
        <div id="docs">
          <h2>حالة النظام</h2>
          <p>جاهز للإصدار والاعتماد</p>
        </div>
      </section>
    </>
  )
}

export default App
