import gspread
from oauth2client.service_account import ServiceAccountCredentials
import google.generativeai as genai
import os
import time
import re

# =============================================
# === LẤY CẤU HÌNH TỪ BIẾN MÔI TRƯỜNG ===
# =============================================
SHEET_VIDEO_ID = os.environ['SHEET_VIDEO_ID']
GEMINI_KEY = os.environ['GEMINI_API_KEY']

# =============================================
# === ⚙️ CÁC THAM SỐ CÓ THỂ TINH CHỈNH ===
# =============================================
SHEET_NAME = "Sheet1"
MAX_PER_RUN = 10          # Số bài viết tối đa mỗi lần chạy
SLEEP_BETWEEN = 3         # Nghỉ giữa các lần gọi API (giây)

# ✅ PROMPT — QUAN TRỌNG NHẤT, TÙY CHỈNH THEO KÊNH CỦA BẠN
PROMPT_TEMPLATE = """Bạn là chuyên gia viết nội dung mạng xã hội TIẾNG VIỆT.
Dựa vào thông tin video sau, viết nội dung đăng bài cho TikTok / YouTube Shorts / Reels.

THÔNG TIN VIDEO:
- Tiêu đề gốc (tiếng Trung): {title_zh}
- Nguồn kênh: {source}
- Thể loại dự đoán: {category}

YÊU CẦU:
1. TIÊU ĐỀ VIỆT: Viết 1 tiêu đề ngắn gọn, hấp dẫn, gây tò mò, phù hợp video ngắn.
   - Dưới 100 ký tự
   - Dùng từ thu hút: "bạn có biết", "kinh ngạc", "khó tin", "mẹo hay", "thật bất ngờ"...
   - Kết thúc bằng ? hoặc ! để tăng tương tác

2. MÔ TẢ CHI TIẾT: Viết 3-5 dòng mô tả nội dung.
   - Ngôn ngữ tự nhiên, gần gũi người Việt
   - Kêu gọi tương tác: "bạn nghĩ sao?", "đã thử chưa?", "like & follow để xem thêm"

3. HASHTAG: Đề xuất 8-12 hashtag liên quan.
   - Kết hợp hashtag chung + chuyên đề
   - Ví dụ: #xuhuong #review #meohay #kinhnghiem

ĐỊNH DẠNG TRẢ LỜI (PHẢI ĐÚNG ĐỊNH DẠNG NÀY):
===TIEU_DE===
[nội dung tiêu đề]
===MO_TA===
[nội dung mô tả]
===HASHTAG===
#hashtag1 #hashtag2 #hashtag3

CHỈ TRẢ VỀ NỘI DUNG THEO ĐỊNH DẠNG, KHÔNG GIẢI THÍCH GÌ THÊM."""

# Danh sách thể loại để AI tự nhận diện
CATEGORIES = [
    "Ẩm thực / Nấu ăn",
    "Review công nghệ",
    "Hài hước / Tiếu lâm",
    "Khoa học / Kiến thức",
    "Đời sống / Tâm sự",
    "Du lịch / Khám phá",
    "Làm đẹp / Thời trang",
    "Giáo dục / Học tập",
    "Thể thao",
    "Nhạc / Điện ảnh",
    "Trải nghiệm / Sống ảo",
    "Khác"
]

# =============================================
# === KẾT NỐI DỊCH VỤ ===
# =============================================
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

scope = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
gs_client = gspread.authorize(creds)
sheet = gs_client.open_by_key(SHEET_VIDEO_ID).worksheet(SHEET_NAME)

print(f"✅ Đã kết nối Sheet 2")
print(f"📊 Đang tìm video: trạng thái = 'Đã lồng tiếng' & chưa có nội dung...")

# =============================================
# === HÀM XỬ LÝ ===
# =============================================
def parse_ai_response(response_text):
    """Phân tích kết quả AI trả về"""
    result = {"title_vi": "", "description": "", "hashtags": ""}
    try:
        if "===TIEU_DE===" in response_text:
            parts = response_text.split("===TIEU_DE===")[1].split("===MO_TA===")
            result["title_vi"] = parts[0].strip()
            if len(parts) > 1:
                parts2 = parts[1].split("===HASHTAG===")
                result["description"] = parts2[0].strip()
                if len(parts2) > 1:
                    result["hashtags"] = parts2[1].strip()
    except:
        pass
    return result


def generate_content(title_zh, source):
    """Gọi AI viết nội dung hoàn chỉnh"""
    # Bước 1: Đoán thể loại
    cat_prompt = f"""Dựa vào tiêu đề tiếng Trung, chọn 1 thể loại phù hợp nhất trong danh sách:
{CATEGORIES}

Tiêu đề: {title_zh}

CHỈ VIẾT TÊN THỂ LOẠI, KHÔNG THÊM GÌ KHÁC."""
    try:
        cat_resp = model.generate_content(cat_prompt)
        category = cat_resp.text.strip()
    except:
        category = "Khác"

    # Bước 2: Viết nội dung chính
    prompt = PROMPT_TEMPLATE.format(
        title_zh=title_zh,
        source=source,
        category=category
    )
    resp = model.generate_content(prompt)
    return parse_ai_response(resp.text), category

# =============================================
# === VÒNG LẶP CHÍNH ===
# =============================================
rows = sheet.get_all_values()
processed = 0
print(f"\n📋 Đọc {len(rows)-1} hàng từ Sheet 2")
print("="*60)

for i, row in enumerate(rows[1:], start=2):
    if processed >= MAX_PER_RUN:
        break

    # Kiểm tra điều kiện:
    # Cột E (5) = "Đã lồng tiếng"
    # Cột H (8) = rỗng → chưa viết nội dung
    if len(row) < 5 or row[4].strip() != "Đã lồng tiếng":
        continue
    if len(row) > 7 and row[7].strip():
        continue  # Đã có tiêu đề Việt rồi → bỏ qua

    title_zh = row[2].strip() if len(row) > 2 else "Không có tiêu đề"
    source = row[0].strip() if len(row) > 0 else "Không xác định"

    print(f"\n✍️ Hàng {i}: {title_zh[:60]}...")
    print(f" Nguồn: {source}")

    try:
        content, category = generate_content(title_zh, source)

        if content["title_vi"]:
            print(f" 🎯 Thể loại: {category}")
            print(f" 📌 Tiêu đề: {content['title_vi'][:60]}...")
            print(f" #️⃣ Hashtag: {content['hashtags'][:50]}...")

            # Ghi vào Sheet:
            sheet.update_cell(i, 8, content["title_vi"])          # Cột H = Tiêu đề Việt
            full_desc = f"{content['description']}\n\n{content['hashtags']}"
            sheet.update_cell(i, 9, full_desc)                    # Cột I = Mô tả + Hashtag
            sheet.update_cell(i, 5, "Đã có nội dung")             # Cột E = Cập nhật trạng thái

            print(f" ✅ Đã ghi xong! Trạng thái → Đã có nội dung")
            processed += 1
            time.sleep(SLEEP_BETWEEN)
        else:
            print(f" ⚠️ AI trả về không hợp lệ, bỏ qua")

    except Exception as e:
        print(f" ❌ Lỗi hàng {i}: {str(e)[:100]}")
        continue

print(f"\n{'='*60}")
print(f"🏁 KẾT THÚC! Đã viết nội dung cho {processed}/{MAX_PER_RUN} video")

if processed == 0:
    print("\n💡 Không tìm thấy video cần xử lý!")
    print("💡 Đảm bảo Cơ chế 3 đã chạy xong → trạng thái = 'Đã lồng tiếng'")
    print("💡 Và Cột H (Tiêu đề Việt) còn trống")
