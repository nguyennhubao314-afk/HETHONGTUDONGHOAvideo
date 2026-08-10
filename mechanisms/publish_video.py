import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import time
import requests
import gdown
import json

# =============================================
# === CẤU HÌNH ===
# =============================================
SHEET_VIDEO_ID = os.environ['SHEET_VIDEO_ID']
YOUTUBE_REFRESH = os.environ.get('YOUTUBE_REFRESH', '')
TIKTOK_TOKEN = os.environ.get('TIKTOK_TOKEN', '')
FB_TOKEN = os.environ.get('FB_TOKEN', '')

MAX_PUBLISH = 2          # Số video đăng mỗi lần chạy
SLEEP_BETWEEN = 120      # Nghỉ giữa các video (giây)
DEFAULT_PRIVACY = 'public'  # Trạng thái: public / private / unlisted
YOUTUBE_CATEGORY = '22'     # 22=Người dùng & Blog, 24=Giải trí

# =============================================
# === KẾT NỐI GOOGLE SHEETS ===
# =============================================
scope = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
gs_client = gspread.authorize(creds)
sheet = gs_client.open_by_key(SHEET_VIDEO_ID).sheet1
print("✅ Đã kết nối Google Sheets")

# =============================================
# === TẢI VIDEO TỪ GOOGLE DRIVE ===
# =============================================
def download_video_from_drive(drive_link, save_path):
    try:
        if "/file/d/" in drive_link:
            file_id = drive_link.split("/file/d/")[1].split("/")[0]
            url = f"https://drive.google.com/uc?id={file_id}"
            gdown.download(url, save_path, quiet=False)
            return os.path.exists(save_path)
    except Exception as e:
        print(f" ❌ Lỗi tải video: {str(e)[:80]}")
    return False

# =============================================
# === ĐĂNG LÊN YOUTUBE ===
# =============================================
def upload_to_youtube(video_path, title, description):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    try:
        with open('youtube_client.json', 'r', encoding='utf-8') as f:
            client_info = json.load(f)['installed']

        creds = Credentials(
            None,
            refresh_token=YOUTUBE_REFRESH,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=client_info['client_id'],
            client_secret=client_info['client_secret']
        )
        youtube = build('youtube', 'v3', credentials=creds)

        tags = [t.strip('#') for t in description.split() if t.startswith('#')][:15]
        body = {
            'snippet': {
                'title': title[:100],
                'description': description[:5000],
                'tags': tags,
                'categoryId': YOUTUBE_CATEGORY
            },
            'status': {
                'privacyStatus': DEFAULT_PRIVACY,
                'selfDeclaredMadeForKids': False
            }
        }
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        res = youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
        return f"https://www.youtube.com/watch?v={res['id']}"
    except Exception as e:
        print(f" ❌ Lỗi đăng YouTube: {str(e)[:120]}")
        return None

# =============================================
# === VÒNG LẶP CHÍNH ===
# =============================================
print(f"\n🚀 BẮT ĐẦU KIỂM TRA & ĐĂNG BÀI")
print(f"📊 Tối đa {MAX_PUBLISH} video/lần chạy")
print("="*60)

rows = sheet.get_all_values()
published = 0

for i, row in enumerate(rows[1:], start=2):
    if published >= MAX_PUBLISH:
        break

    # Kiểm tra điều kiện: Cột E=Đã có nội dung, Cột J có nền tảng, Cột K trống
    if len(row) < 5 or row[4].strip() != "Đã có nội dung":
        continue
    platform = row[9].strip().lower() if len(row) > 9 else ""
    link_da_dang = row[10].strip() if len(row) > 10 else ""
    if not platform or link_da_dang:
        continue

    # Lấy dữ liệu từ các cột
    video_link = row[6].strip() if len(row) > 6 else ""   # Cột G
    title_vi = row[7].strip() if len(row) > 7 else "Video hay"  # Cột H
    desc_full = row[8].strip() if len(row) > 8 else ""           # Cột I
    if not video_link:
        continue

    print(f"\n📹 Hàng {i}: {title_vi[:50]}...")
    print(f" Nền tảng: {platform}")

    try:
        # Tải video về máy chủ
        local_video = f"/tmp/video_{i}.mp4"
        print(f" ⬇️ Đang tải video từ Drive...")
        if not download_video_from_drive(video_link, local_video):
            print(f" ❌ Tải thất bại, bỏ qua hàng này")
            continue
        file_size = os.path.getsize(local_video) / (1024*1024)
        print(f" ✅ Đã tải xong: {file_size:.1f} MB")

        # Đăng lên nền tảng
        post_link = None
        if 'youtube' in platform:
            print(f" 🎥 Đang đăng lên YouTube...")
            post_link = upload_to_youtube(local_video, title_vi, desc_full)
        else:
            print(f" ⚠️ Nền tảng '{platform}' chưa hỗ trợ")

        # Cập nhật lại Google Sheets
        if post_link:
            print(f" ✅ Đăng thành công! Link: {post_link}")
            sheet.update_cell(i, 11, post_link)   # Cột K = link đã đăng
            sheet.update_cell(i, 5, "Đã đăng")    # Cột E = trạng thái
            published += 1
            print(f" 📝 Đã cập nhật lại Google Sheets")
            if published < MAX_PUBLISH:
                print(f" ⏳ Nghỉ {SLEEP_BETWEEN}s trước video tiếp theo...")
                time.sleep(SLEEP_BETWEEN)
        else:
            print(f" ❌ Đăng thất bại")

        # Xóa file tạm
        if os.path.exists(local_video):
            os.remove(local_video)

    except Exception as e:
        print(f" ❌ LỖI: {str(e)[:100]}")
        continue

# Kết thúc
print(f"\n{'='*60}")
print(f"🏁 KẾT THÚC! Đã đăng {published}/{MAX_PUBLISH} video")
if published == 0:
    print("💡 Không tìm thấy video nào cần đăng")
    print("💡 Kiểm tra: Trạng thái (Cột E) = 'Đã có nội dung' + Cột J ghi 'youtube' + Cột K để trống")
