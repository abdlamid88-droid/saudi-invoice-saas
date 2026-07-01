import os
import json
import asyncio
import qrcode
import base64
import datetime
import arabic_reshaper
from bidi.algorithm import get_display
from fpdf import FPDF
from io import BytesIO
import streamlit as st
import google.generativeai as genai
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import requests

from zatca_mcp_server import save_zatca_invoice


# Page configuration
st.set_page_config(
    page_title="ZATCA Chatbot UI",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Arabic CSS styling (Dark Theme / Glassmorphism / Cairo Font)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"], .stText, .stMarkdown, .stButton {
        font-family: 'Cairo', sans-serif !important;
        direction: rtl;
        text-align: right;
    }
    
    /* Main Background Gradient */
    .stApp {
        background: linear-gradient(135deg, #090d16 0%, #15102a 100%) !important;
        color: #f1f5f9;
    }
    
    /* Title Styling */
    .main-title {
        font-size: 2.8rem;
        font-weight: 700;
        background: linear-gradient(90deg, #38bdf8, #818cf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
        text-align: center;
        text-shadow: 0 0 30px rgba(56, 189, 248, 0.2);
    }
    .subtitle {
        font-size: 1.1rem;
        color: #94a3b8;
        text-align: center;
        margin-bottom: 2rem;
    }

    /* Glassmorphism Card for Invoices */
    .invoice-card {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 1.5rem;
        backdrop-filter: blur(10px);
        margin: 1.5rem 0;
        color: #f1f5f9;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
    }
    
    /* Align Streamlit Chat Input */
    .stChatInputContainer {
        border-radius: 30px !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        background: rgba(255, 255, 255, 0.05) !important;
    }

    /* Input Labels */
    label {
        color: #e2e8f0 !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        margin-bottom: 0.5rem !important;
    }

    /* Styling Streamlit Forms */
    div[data-testid="stForm"] {
        background: rgba(255, 255, 255, 0.02) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 16px !important;
        padding: 2rem !important;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3) !important;
        backdrop-filter: blur(8px);
    }

    /* Button Styling overrides */
    button[kind="secondaryFormSubmit"], button[kind="primary"] {
        background: linear-gradient(90deg, #6366f1 0%, #4f46e5 100%) !important;
        color: white !important;
        border: none !important;
        font-weight: 600 !important;
        border-radius: 30px !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 15px rgba(99, 102, 241, 0.3) !important;
        padding: 0.5rem 2rem !important;
    }
    button[kind="secondaryFormSubmit"]:hover, button[kind="primary"]:hover {
        background: linear-gradient(90deg, #4f46e5 0%, #4338ca 100%) !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5) !important;
    }

    /* Custom classes for spacing and headers */
    .section-header {
        font-size: 1.5rem;
        font-weight: 600;
        color: #818cf8;
        margin-top: 2rem;
        margin-bottom: 1rem;
        border-bottom: 2px solid rgba(129, 140, 248, 0.2);
        padding-bottom: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# Helper function to invoke the local MCP server over stdio
def call_mcp_tool(tool_name: str, arguments: dict) -> str:
    """
    Connects to the local zatca_mcp_server.py via stdio,
    executes the requested tool, and returns the string output.
    """
    async def _call():
        # Dynamic resolution of the MCP server script path
        server_script = os.path.expanduser("~/Documents/agent_workspace/zatca_mcp_server.py")
        if not os.path.exists(server_script):
            server_script = os.path.join(os.getcwd(), "zatca_mcp_server.py")
            if not os.path.exists(server_script):
                server_script = "zatca_mcp_server.py"
                
        # Create a clean copy of the environment and remove PORT to prevent
        # FastMCP from defaulting to SSE and attempting to start Uvicorn on Streamlit's port.
        env = os.environ.copy()
        if "PORT" in env:
            del env["PORT"]
            
        server_params = StdioServerParameters(
            command="python3",
            args=[server_script],
            env=env
        )
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                response = await session.call_tool(tool_name, arguments)
                if not response.content:
                    raise ValueError("No response content received from MCP server.")
                return response.content[0].text

    return asyncio.run(_call())

# Local wrapper for the ZATCA tool to pass to Gemini
def save_zatca_invoice(amount: float, company: str, tax = None) -> str:
    """
    Saves a ZATCA invoice to the registry, computes taxes, and generates a base64 QR code.

    Args:
        amount: The total invoice amount (inclusive of VAT).
        company: Name of the customer/buyer company.
        tax: Optional tax amount. If not provided, it will be calculated as 15% of the total amount.
    """
    tenant_id = st.session_state.get("tenant_id")
    if not tenant_id:
        return json.dumps({
            "status": "error",
            "message": "خطأ أمني: لم يتم العثور على معرّف مستأجر (Tenant ID) صالح في الجلسة. يرجى تسجيل الدخول أولاً."
        })
        
    if tax is None:
        tax = round((amount * 0.15) / 1.15, 2)
        
    try:
        # Crucial security constraint: inject tenant_id programmatically in the background from session state
        result = call_mcp_tool("save_zatca_invoice", {
            "amount": amount,
            "company": company,
            "tenant_id": tenant_id,
            "tax": str(tax)
        })
        return result
    except Exception as e:
        # Handle connection or execution errors gracefully and report to model
        error_info = {
            "status": "error",
            "message": f"فشل الاتصال بخادم ZATCA MCP: {str(e)}"
        }
        return json.dumps(error_info)

# Decode QR code base64 or generate a new QR code image if it is a TLV data string
def get_qr_image_bytes(qr_data_b64: str) -> bytes:
    try:
        decoded = base64.b64decode(qr_data_b64.strip())
        # Check if the bytes start with PNG or JPEG signatures
        if decoded.startswith(b'\x89PNG') or decoded.startswith(b'\xff\xd8'):
            return decoded
    except Exception:
        pass

    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data_b64)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return b""


# Function to generate ZATCA-compliant PDF invoice with Arabic support (RTL)
def generate_invoice_pdf(supplier_name: str, vat_number: str, total_amount: float, tax_amount: float, date_str: str, qr_code_bytes: bytes, invoice_id: str = "N/A", buyer_company: str = "N/A", invoice_type: str = "388", linked_invoice_id: str = None, instruction_note: str = None) -> bytes:
    try:
        pdf = FPDF()
        pdf.add_page()
        
        # Load a font that supports Arabic and Unicode (Amiri-Regular.ttf or system fallback)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        font_candidates = [
            os.path.join(current_dir, "Amiri-Regular.ttf"),
            "Amiri-Regular.ttf",
            "/app/Amiri-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ]
        
        font_name = "Amiri"
        font_path = None
        for path in font_candidates:
            if os.path.exists(path):
                font_path = path
                break
                
        if font_path:
            pdf.add_font(font_name, "", font_path)
        else:
            raise FileNotFoundError("Arabic font 'Amiri' (Amiri-Regular.ttf) was not found in the search paths.")
            
        pdf.set_font(font_name, size=11)
        
        # Helper for Arabic reshaping and RTL
        def ar(txt):
            if not txt:
                return ""
            return get_display(arabic_reshaper.reshape(str(txt)))
            
        # Draw elegant double border
        pdf.rect(5, 5, 200, 287, 'D')
        pdf.rect(6, 6, 198, 285, 'D')
        
        # Determine title and subtitle based on invoice_type
        if invoice_type == '381':
            title_ar = "إشعار دائن مبسط"
            subtitle_en = "SIMPLIFIED CREDIT NOTE"
        elif invoice_type == '383':
            title_ar = "إشعار مدين مبسط"
            subtitle_en = "SIMPLIFIED DEBIT NOTE"
        else:
            title_ar = "فاتورة ضريبية مبسطة"
            subtitle_en = "SIMPLIFIED TAX INVOICE"
            
        # Header (Simplified Tax Invoice / Credit Note / Debit Note)
        pdf.set_font(font_name, size=18)
        pdf.cell(w=0, h=12, text=ar(title_ar), new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.set_font(font_name, size=10)
        pdf.cell(w=0, h=8, text=ar(subtitle_en), new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(5)
        
        # Line separator
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
        
        # Invoice Metadata block
        pdf.set_font(font_name, size=11)
        pdf.cell(w=0, h=8, text=ar(f"رقم الفاتورة: {invoice_id}"), new_x="LMARGIN", new_y="NEXT", align="R")
        pdf.cell(w=0, h=8, text=ar(f"تاريخ الإصدار: {date_str}"), new_x="LMARGIN", new_y="NEXT", align="R")
        pdf.ln(3)
        
        # Programmatically inject extra text rows for Credit and Debit Notes right below metadata
        if invoice_type in ['381', '383']:
            pdf.cell(w=0, h=8, text=ar(f"رقم الفاتورة الأصلية المرتبطة: {linked_invoice_id or 'N/A'}"), new_x="LMARGIN", new_y="NEXT", align="R")
            pdf.cell(w=0, h=8, text=ar(f"سبب الإشعار/التعديل: {instruction_note or 'غير محدد'}"), new_x="LMARGIN", new_y="NEXT", align="R")
            pdf.ln(3)
        
        # Supplier & Buyer Info
        pdf.cell(w=0, h=8, text=ar(f"اسم المورد: {supplier_name}"), new_x="LMARGIN", new_y="NEXT", align="R")
        pdf.cell(w=0, h=8, text=ar(f"الرقم الضريبي للمورد: {vat_number}"), new_x="LMARGIN", new_y="NEXT", align="R")
        pdf.cell(w=0, h=8, text=ar(f"اسم العميل/الشركة: {buyer_company}"), new_x="LMARGIN", new_y="NEXT", align="R")
        pdf.ln(5)
        
        # Line separator
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
        
        # Financial Details Table
        subtotal = total_amount - tax_amount
        
        # Table headers / Rows (Description on the right, Value on the left)
        # Row 1: Subtotal
        pdf.cell(w=90, h=8, text=ar(f"{subtotal:.2f} SAR"), align="L")
        pdf.cell(w=90, h=8, text=ar("المبلغ الخاضع للضريبة (غير شامل الضريبة)"), align="R", new_x="LMARGIN", new_y="NEXT")
        
        # Row 2: Tax (15%)
        pdf.cell(w=90, h=8, text=ar(f"{tax_amount:.2f} SAR"), align="L")
        pdf.cell(w=90, h=8, text=ar("ضريبة القيمة المضافة (15%)"), align="R", new_x="LMARGIN", new_y="NEXT")
        
        # Row 3: Total (inclusive)
        pdf.set_font(font_name, size=13)
        pdf.cell(w=90, h=10, text=ar(f"{total_amount:.2f} SAR"), align="L")
        pdf.cell(w=90, h=10, text=ar("الإجمالي شامل ضريبة القيمة المضافة"), align="R", new_x="LMARGIN", new_y="NEXT")
        
        pdf.ln(5)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(10)
        
        # QR Code centered at the bottom
        if qr_code_bytes:
            from io import BytesIO
            qr_stream = BytesIO(qr_code_bytes)
            pdf.image(qr_stream, x=85, w=40, h=40)
            
        pdf_bytes = pdf.output()
        return bytes(pdf_bytes)
    except Exception as e:
        print(f"Error inside generate_invoice_pdf: {e}")
        return None


# Render header
st.markdown("<div class='main-title'>بوابة الفوترة الذكية ZATCA</div>", unsafe_allow_html=True)
st.markdown("<div class='subtitle'>نظام إصدار الفواتير الإلكترونية المتكامل مع خادم MCP وذكاء Google Gemini الاصطناعي</div>", unsafe_allow_html=True)

# Check login status
is_logged_in = "tenant_id" in st.session_state and st.session_state.tenant_id

# Sidebar Login / Connection Configuration
st.sidebar.title("⚙️ البوابة الأمنية (SaaS)")

if not is_logged_in:
    st.sidebar.subheader("🔒 تسجيل الدخول للمستأجر")
    vat_input = st.sidebar.text_input("الرقم الضريبي للمنشأة (TIN/VAT):", placeholder="مثال: 399999999900003")
    tenant_input = st.sidebar.text_input("معرّف المستأجر (Tenant ID):", placeholder="مثال: TENANT_001")
    
    if st.sidebar.button("تسجيل الدخول"):
        if not vat_input or not tenant_input:
            st.sidebar.error("❌ يرجى ملء جميع الحقول.")
        elif not vat_input.isdigit() or len(vat_input) != 15:
            st.sidebar.error("❌ يجب أن يكون الرقم الضريبي مكوناً من 15 رقماً.")
        else:
            st.session_state.tenant_id = tenant_input.strip()
            st.session_state.vat_number = vat_input.strip()
            st.sidebar.success("🔓 تم تسجيل الدخول بنجاح!")
            st.rerun()
else:
    st.sidebar.success("🔓 متصل بنجاح")
    st.sidebar.markdown(f"""
    **بيانات المنشأة النشطة:**
    * **الرقم الضريبي:** `{st.session_state.vat_number}`
    * **معرّف المستأجر:** `{st.session_state.tenant_id}`
    """)
    
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        api_key = st.sidebar.text_input("مفتاح API الخاص بـ Gemini:", type="password")
        
    st.sidebar.markdown("---")
    if st.sidebar.button("تسجيل الخروج"):
        del st.session_state.tenant_id
        del st.session_state.vat_number
        if "chat" in st.session_state:
            del st.session_state.chat
        if "messages" in st.session_state:
            st.session_state.messages = []
        st.rerun()

# Main logic
if not is_logged_in:
    st.markdown("""
    <div style='text-align: center; padding: 5rem 2rem; background: rgba(255,255,255,0.02); border-radius: 15px; border: 1px dashed rgba(255,255,255,0.1);'>
        <h2 style='color: #818cf8;'>🔒 نظام الفوترة الإلكتروني مؤمن بالكامل</h2>
        <p style='color: #94a3b8; font-size: 1.15rem; margin-top: 1rem;'>
            يرجى إدخال الرقم الضريبي للمنشأة (المكون من 15 رقماً) ومعرّف المستأجر الخاص بك في القائمة الجانبية للوصول إلى لوحة إصدار الفواتير.
        </p>
    </div>
    """, unsafe_allow_html=True)
elif not api_key:
    st.info("👋 مرحباً بك! يرجى إدخال مفتاح API لنموذج Gemini في القائمة الجانبية لبدء المحادثة وإصدار الفواتير.")
else:
    genai.configure(api_key=api_key)
    
    # Initialize chatbot and history
    if "chat" not in st.session_state:
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            tools=[save_zatca_invoice],
            system_instruction="أنت مساعد مالي ذكي وخبير لنظام الفوترة الإلكترونية ZATCA في المملكة العربية السعودية. يمكنك مساعدة المستخدمين في إصدار الفواتير وعرض تفاصيلها. تحدث دائماً باللغة العربية الفصحى بأسلوب مهني وواضح وسلس."
        )
        st.session_state.chat = model.start_chat()
        
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "invoice" in message:
                inv = message["invoice"]
                if inv.get("status") == "success":
                    st.success(f"✅ تم تسجيل الفاتورة بنجاح في النظام! رقم العملية: {inv['invoice_id']}")
                    
                    # Display invoice card using Streamlit columns & native components
                    col1, col2 = st.columns([1, 2])
                    with col1:
                        qr_bytes = get_qr_image_bytes(inv["qr_code"])
                        if qr_bytes:
                            st.image(qr_bytes, caption="رمز الاستجابة السريعة للفوترة (ZATCA QR Code)", width=200)
                    with col2:
                        st.info(f"""
                        📋 **بيانات الفاتورة الإلكترونية:**
                        * **رقم الفاتورة:** `{inv['invoice_id']}`
                        * **اسم العميل/الشركة:** `{inv['buyer_company']}`
                        * **المبلغ الإجمالي (شامل الضريبة):** `{inv['amount']:.2f} ريال سعودي`
                        * **ضريبة القيمة المضافة (15%):** `{inv['tax']:.2f} ريال سعودي`
                        * **توقيت الإصدار (UTC):** `{inv['timestamp']}`
                        * **معرّف المستأجر المظلي (خلفي):** `{inv['tenant_id']}`
                        """)

                        inv = message["invoice"]
                        try:
                            # 1. استيراد مكتبات الرسم
                            import qrcode
                            from io import BytesIO
                            
                            # 2. تحويل نص ZATCA إلى صورة QR حقيقية بصيغة PNG
                            qr_img = qrcode.make(inv["qr_code"])
                            img_buffer = BytesIO()
                            qr_img.save(img_buffer, format="PNG")
                            qr_png_bytes = img_buffer.getvalue() # هذه هي الصورة الحقيقية الآن

                            # 3. تمرير الصورة الحقيقية لدالة الـ PDF
                            pdf_bytes = generate_invoice_pdf(
                                supplier_name=st.session_state.get("tenant_id", "مورد تجريبي"),
                                vat_number=st.session_state.get("vat_number", "399999999900003"),
                                total_amount=inv["amount"],
                                tax_amount=inv["tax"],
                                date_str=inv["timestamp"],
                                qr_code_bytes=qr_png_bytes,  # <--- السر هنا
                                invoice_id=inv["invoice_id"],
                                buyer_company=inv["buyer_company"],
                                invoice_type=inv.get("invoice_type", "388"),
                                linked_invoice_id=inv.get("linked_invoice_id", None),
                                instruction_note=inv.get("instruction_note", None)
                            )
                            
                            if pdf_bytes:
                                st.download_button(
                                    label="📄 تحميل الفاتورة كملف PDF",
                                    data=pdf_bytes,
                                    file_name=f"invoice_{inv['invoice_id']}.pdf",
                                    mime="application/pdf",
                                    key=f"dl_{inv['invoice_id']}"
                                )
                        except Exception as pdf_err:
                            st.error(f"⚠️ تعذر توليد ملف PDF بسبب: {pdf_err}")                        
                elif inv.get("status") == "error":
                    st.error(f"❌ خطأ: {inv['message']}")

    # Chat Input
    if user_input := st.chat_input("اكتب طلبك هنا..."):
        st.chat_message("user").markdown(user_input)
        st.session_state.messages.append({"role": "user", "content": user_input})
        chat = st.session_state.chat
        with st.spinner("جاري معالجة الطلب..."):
            try:
                response = chat.send_message(user_input)
                invoice_data = None
                fc_name = None
                fc_args = {}
                
                if response.candidates and len(response.candidates) > 0:
                    for part in response.candidates[0].content.parts:
                        fc = getattr(part, "function_call", None)
                        if fc:
                            fc_name = getattr(fc, "name", None)
                            if hasattr(fc, "args"):
                                fc_args = {k: v for k, v in fc.args.items()}
                            break
                            
                if fc_name == "save_zatca_invoice":
                    from zatca_mcp_server import save_zatca_invoice
                    import json
                    result_str = save_zatca_invoice(
                        amount=fc_args.get("amount", 0.0), 
                        company=fc_args.get("company", ""),
                        tenant_id=st.session_state.get("tenant_id", "TENANT_001")
                    )
                    invoice_data = json.loads(result_str)
                    response = chat.send_message({"function_response": {"name": fc_name, "response": {"result": result_str}}})
                
                try:
                    assistant_response = response.text if response.text else "تمت معالجة الطلب."
                except Exception:
                    assistant_response = "تم تسجيل الفاتورة بنجاح في النظام."
                    
                st.chat_message("assistant").markdown(assistant_response)
                message_entry = {"role": "assistant", "content": assistant_response}
                if invoice_data:
                    message_entry["invoice"] = invoice_data
                st.session_state.messages.append(message_entry)
                st.rerun()
            except Exception as e:
                st.error(f"حدث خطأ أثناء معالجة الطلب: {e}")

    # Direct Invoice Generation Form (Alternative to Chatbot)
    st.markdown("<div class='section-header'>📝 نموذج إصدار الفاتورة المباشر</div>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        buyer_company = st.text_input("اسم العميل / الشركة", value="شركة المعالي", key="direct_company")
    with col2:
        buyer_vat = st.text_input("الرقم الضريبي للمشتري (15 رقم)", value="300000000000003", key="direct_vat")
    with col3:
        amount = st.number_input("مبلغ الفاتورة (ريال)", min_value=1.0, value=400.0, step=10.0, key="direct_amount")
        
    doc_types = {
        "فاتورة قياسية (Standard Invoice)": "388",
        "إشعار دائن (Credit Note)": "381",
        "إشعار مدين (Debit Note)": "383"
    }
    selected_label = st.selectbox("نوع المستند / Document Type", options=list(doc_types.keys()), key="direct_doc_type")
    invoice_type = doc_types[selected_label]
    
    linked_invoice_id = None
    instruction_note = None
    if invoice_type in ["381", "383"]:
        c1, c2 = st.columns(2)
        with c1:
            linked_invoice_id = st.text_input("رقم الفاتورة المرتبطة / Linked Invoice ID", placeholder="مثال: INV-20260627-XYZ", key="direct_linked_id")
        with c2:
            instruction_note = st.text_input("سبب الإشعار / Note/Reason", placeholder="مثال: مرتجع مبيعات أو تعديل سعر", key="direct_instruction_note")
        
    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    submit_btn = st.button("إصدار وتشفير الفاتورة 🚀", type="primary")

    if submit_btn:
        if not buyer_company or not buyer_vat or not amount:
            st.error("❌ يرجى ملء جميع الحقول المطلوبة.")
        elif not buyer_vat.isdigit() or len(buyer_vat) != 15:
            st.error("❌ يجب أن يكون الرقم الضريبي للمشتري مكوناً من 15 رقماً.")
        else:
            with st.spinner("جاري الاتصال بالمحرك التشفيري..."):
                api_base_url = os.getenv('API_URL', 'http://localhost:8000').rstrip('/')
                api_url = f"{api_base_url}/api/v1/invoices/issue"
                
                calculated_tax = round((amount * 0.15) / 1.15, 2)
                payload = {
                    "buyer_company": buyer_company,
                    "buyer_vat": buyer_vat,
                    "amount": amount,
                    "supplier_name": "Muntda Corporation",
                    "vat_number": "311111111111113",
                    "tax": str(calculated_tax),
                    "invoice_type": invoice_type,
                    "instruction_note": instruction_note,
                    "linked_invoice_id": linked_invoice_id
                }
                
                try:
                    response = requests.post(api_url, json=payload, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        
                        if data.get("status") == "success":
                            st.success(f"✅ تمت أتمتة الفاتورة وتشفيرها بنجاح! رقم العملية: {data.get('invoice_id')}")
                            
                            st.info(f"""
                            🔐 **التفاصيل التشفيرية (ZATCA Phase II):**
                            * **حالة الفاتورة:** `{data.get('zatca_status')}`
                            * **تجزئة الفاتورة السابقة (PIH):** `{data.get('pih_used')}`
                            * **تجزئة الفاتورة الحالية (Hash):** `{data.get('new_invoice_hash')}`
                            """)
                            
                            # Save fields to session state for rerun persistence
                            st.session_state['current_invoice_type'] = invoice_type
                            st.session_state['current_linked_invoice_id'] = linked_invoice_id
                            st.session_state['current_instruction_note'] = instruction_note
                            
                            # Generate PDF and save to session state
                            try:
                                qr_code_b64 = data.get("qr_code_base64", "")
                                qr_png_bytes = get_qr_image_bytes(qr_code_b64)
                                
                                pdf_bytes = generate_invoice_pdf(
                                    supplier_name="Muntda Corporation",
                                    vat_number="311111111111113",
                                    total_amount=amount,
                                    tax_amount=calculated_tax,
                                    date_str=datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                                    qr_code_bytes=qr_png_bytes,
                                    invoice_id=data.get("invoice_id", "N/A"),
                                    buyer_company=buyer_company,
                                    invoice_type=st.session_state['current_invoice_type'],
                                    linked_invoice_id=st.session_state['current_linked_invoice_id'],
                                    instruction_note=st.session_state['current_instruction_note']
                                )
                                if pdf_bytes:
                                    st.session_state['download_pdf_data'] = pdf_bytes
                                    st.session_state['download_pdf_name'] = f"invoice_{data.get('invoice_id')}.pdf"
                            except Exception as pdf_err:
                                st.warning(f"⚠️ تم التشفير بنجاح، ولكن تعذر توليد ملف PDF: {pdf_err}")
                            
                            # Fetch XML
                            xml_url = data.get("xml_download_url")
                            if xml_url:
                                full_xml_url = f"{api_base_url}{xml_url}"
                                try:
                                    xml_response = requests.get(full_xml_url, timeout=10)
                                    if xml_response.status_code == 200:
                                        st.session_state['download_xml_data'] = xml_response.content
                                        st.session_state['download_xml_name'] = f"{data.get('invoice_id')}.xml"
                                    else:
                                        st.warning("⚠️ تم التشفير بنجاح، ولكن تعذر جلب ملف الـ XML للتحميل.")
                                except Exception as e:
                                    st.error(f"❌ خطأ أثناء محاولة جلب الـ XML: {e}")
                        else:
                            st.warning("⚠️ استجاب المحرك ولكن بحالة غير متوقعة:")
                            st.json(data)
                    else:
                        st.error(f"❌ خطأ من الخادم (الكود {response.status_code}): {response.text}")
                except Exception as e:
                    st.error(f"❌ حدث خطأ أثناء الاتصال بالمحرك التشفيري: {e}")

    # Show download button outside form
    if 'download_xml_data' in st.session_state:
        st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
        col_xml, col_pdf = st.columns(2)
        with col_xml:
            st.download_button(
                label="📄 تحميل ملف الفاتورة (XML المعتمد للهيئة)",
                data=st.session_state['download_xml_data'],
                file_name=st.session_state['download_xml_name'],
                mime="application/xml",
                type="primary",
                use_container_width=True
            )
        if 'download_pdf_data' in st.session_state:
            with col_pdf:
                st.download_button(
                    label="📄 تحميل الفاتورة كملف PDF",
                    data=st.session_state['download_pdf_data'],
                    file_name=st.session_state['download_pdf_name'],
                    mime="application/pdf",
                    type="primary",
                    key="direct_pdf_download",
                    use_container_width=True
                )
