import os
import json
import asyncio
import qrcode
import base64
import arabic_reshaper
from bidi.algorithm import get_display
from fpdf import FPDF
from io import BytesIO
import streamlit as st
import google.generativeai as genai
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

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
        padding: 1.25rem;
        backdrop-filter: blur(8px);
        margin: 1rem 0;
        color: #f1f5f9;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
    }
    
    /* Align Streamlit Chat Input */
    .stChatInputContainer {
        border-radius: 30px !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        background: rgba(255, 255, 255, 0.05) !important;
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
def save_zatca_invoice(amount: float, company: str) -> str:
    """
    Saves a ZATCA invoice to the registry, computes taxes, and generates a base64 QR code.

    Args:
        amount: The total invoice amount (inclusive of VAT).
        company: Name of the customer/buyer company.
    """
    tenant_id = st.session_state.get("tenant_id")
    if not tenant_id:
        return json.dumps({
            "status": "error",
            "message": "خطأ أمني: لم يتم العثور على معرّف مستأجر (Tenant ID) صالح في الجلسة. يرجى تسجيل الدخول أولاً."
        })
        
    try:
        # Crucial security constraint: inject tenant_id programmatically in the background from session state
        result = call_mcp_tool("save_zatca_invoice", {
            "amount": amount,
            "company": company,
            "tenant_id": tenant_id
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
def generate_invoice_pdf(supplier_name: str, vat_number: str, total_amount: float, tax_amount: float, date_str: str, qr_code_bytes: bytes, invoice_id: str = "N/A", buyer_company: str = "N/A") -> bytes:
    try:
        pdf = FPDF()
        pdf.add_page()
        
        # Load Amiri Font (absolute path to avoid issues)
        font_path = os.path.expanduser("~/Documents/agent_workspace/Amiri-Regular.ttf")
        if not os.path.exists(font_path):
            font_path = "Amiri-Regular.ttf"
            
        pdf.add_font("Amiri", "", font_path)
        pdf.set_font("Amiri", size=11)
        
        # Helper for Arabic reshaping and RTL
        def ar(txt):
            if not txt:
                return ""
            return get_display(arabic_reshaper.reshape(str(txt)))
            
        # Draw elegant double border
        pdf.rect(5, 5, 200, 287, 'D')
        pdf.rect(6, 6, 198, 285, 'D')
        
        # Header (Simplified Tax Invoice)
        pdf.set_font("Amiri", size=18)
        pdf.cell(w=0, h=12, text=ar("فاتورة ضريبية مبسطة"), new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.set_font("Amiri", size=10)
        pdf.cell(w=0, h=8, text=ar("SIMPLIFIED TAX INVOICE"), new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(5)
        
        # Line separator
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
        
        # Invoice Metadata block
        pdf.set_font("Amiri", size=11)
        pdf.cell(w=0, h=8, text=f"{invoice_id} : {ar('رقم الفاتورة')}", new_x="LMARGIN", new_y="NEXT", align="R")
        pdf.cell(w=0, h=8, text=f"{date_str} : {ar('تاريخ الإصدار')}", new_x="LMARGIN", new_y="NEXT", align="R")
        pdf.ln(3)
        
        # Supplier & Buyer Info
        pdf.cell(w=0, h=8, text=f"{ar(supplier_name)} : {ar('اسم المورد')}", new_x="LMARGIN", new_y="NEXT", align="R")
        pdf.cell(w=0, h=8, text=f"{vat_number} : {ar('الرقم الضريبي للمورد')}", new_x="LMARGIN", new_y="NEXT", align="R")
        pdf.cell(w=0, h=8, text=f"{ar(buyer_company)} : {ar('اسم العميل/الشركة')}", new_x="LMARGIN", new_y="NEXT", align="R")
        pdf.ln(5)
        
        # Line separator
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
        
        # Financial Details Table
        subtotal = total_amount - tax_amount
        
        # Table headers / Rows (Description on the right, Value on the left)
        # Row 1: Subtotal
        pdf.cell(w=90, h=8, text=f"{subtotal:.2f} SAR", align="L")
        pdf.cell(w=90, h=8, text=ar("المبلغ الخاضع للضريبة (غير شامل الضريبة)"), align="R", new_x="LMARGIN", new_y="NEXT")
        
        # Row 2: Tax (15%)
        pdf.cell(w=90, h=8, text=f"{tax_amount:.2f} SAR", align="L")
        pdf.cell(w=90, h=8, text=ar("ضريبة القيمة المضافة (15%)"), align="R", new_x="LMARGIN", new_y="NEXT")
        
        # Row 3: Total (inclusive)
        pdf.set_font("Amiri", size=13)
        pdf.cell(w=90, h=10, text=f"{total_amount:.2f} SAR", align="L")
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
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if "invoice" in msg:
                inv = msg["invoice"]
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
                        
                        # Generate and offer the PDF for download
                        try:
                            pdf_bytes = generate_invoice_pdf(
                                supplier_name=st.session_state.get("tenant_id", "مورد تجريبي"),
                                vat_number=st.session_state.get("vat_number", "399999999900003"),
                                total_amount=inv["amount"],
                                tax_amount=inv["tax"],
                                date_str=inv["timestamp"],
                                qr_code_bytes=qr_bytes,
                                invoice_id=inv["invoice_id"],
                                buyer_company=inv["buyer_company"]
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
                            st.error(f"❌ خطأ أثناء توليد ملف PDF: {pdf_err}")
                elif inv.get("status") == "error":
                    st.error(f"❌ خطأ: {inv['message']}")

    # Chat Input
    if user_input := st.chat_input("اكتب طلبك هنا (مثال: أصدر فاتورة بقيمة 230 ريال لشركة التقنية الحديثة)..."):
        # Display user message
        st.chat_message("user").markdown(user_input)
        st.session_state.messages.append({"role": "user", "content": user_input})
        
        chat = st.session_state.chat
        
        with st.spinner("جاري معالجة الطلب..."):
            try:
                response = chat.send_message(user_input)
                
                # Check if Gemini issued a tool call
                invoice_data = None
                if response.candidates and response.candidates[0].content.parts:
                    part = response.candidates[0].content.parts[0]
                    if part.function_call:
                        function_call = part.function_call
                        name = function_call.name
                        args = function_call.args
                        
                        if name == "save_zatca_invoice":
                            # Execute the tool
                            result_str = save_zatca_invoice(amount=args["amount"], company=args["company"])
                            invoice_data = json.loads(result_str)
                            
                            # Send the tool output back to Gemini to get the final textual explanation
                            response = chat.send_message(
                                genai.types.Part.from_function_response(
                                    name=name,
                                    response={"result": result_str}
                                )
                            )
                
                # Save assistant response safely
                try:
                    assistant_response = response.text if response.text else "تمت معالجة الطلب."
                except ValueError:
                    assistant_response = "تم تسجيل الفاتورة بنجاح في النظام."
                st.chat_message("assistant").markdown(assistant_response)
                
                message_entry = {"role": "assistant", "content": assistant_response}
                if invoice_data:
                    message_entry["invoice"] = invoice_data
                    
                    # Force a redraw of the page to render the success banner and QR image correctly
                    st.session_state.messages.append(message_entry)
                    st.rerun()
                else:
                    st.session_state.messages.append(message_entry)
                    
            except Exception as e:
                st.error(f"حدث خطأ أثناء معالجة الطلب: {e}")
