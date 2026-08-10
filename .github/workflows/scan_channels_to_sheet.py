import gspread
from oauth2client.service_account import ServiceAccountCredentials
import yt_dlp
import os
import time
import requests
import json

# =============================================
# === LẤY ID 2 BẢNG TỪ BIẾN MÔI TRƯỜNG ===
# =============================================
SHEET_SOURCE_ID = os.environ['SHEET_SOURCE']
SHEET_VIDEO_ID = os.environ['SHEET_VIDEO']

# =============================================
# === ⚙️ CẤU HÌNH DOUYIN-TIKTOK-DOWNLOAD-API ===
# =============================================
# Nếu dùng bản công khai thử nghiệm: "https://api.douyin.wtf"
# Nếu tự triển khai API riêng: đổi thành link API của bạn
DOUYIN_API_BASE = "https://api.douyin.wtf"

# Số video tối đa lấy mỗi kênh Douyin
DOUYIN_MAX_VIDEOS = 30

# Số video tối đa lấy mỗi kênh (các nền tảng khác dùng yt-dlp)
MAX_VIDEOS_PER_CHANNEL = 30

# =============================================
# === KẾT NỐI GOOGLE SHEETS ===
# =============================================
scope = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
creds = ServiceAccountCredentials.from_json_keyfile_name(
    'credentials.json', scope)
client = gspread.authorize(creds)

sheet_source = client.open_by_key(SHEET_SOURCE_ID).sheet1
sheet_video = client.open_by_key(SHEET_VIDEO_ID).sheet1

print("✅ Kết nối thành công 2 bảng Google Sheets")

# Lấy danh sách link đã có để tránh trùng
existing_links = set()
all_videos = sheet_video.get_all_values()
for row in all_videos[1:]:
    if len(row) > 1 and row[1].strip():
        existing_links.add(row[1].strip())
print(f"📊 Đã có {len(existing_links)} video trong Sheet 2")

# =============================================
# === HÀM XỬ LÝ DOUYIN BẰNG API ===
# =============================================
def get_douyin_videos(channel_url):
    videos = []
    try:
        api_url = f"{DOUYIN_API_BASE}/api/user_info_videos"
        params = {
            "url": channel_url,
            "limit": DOUYIN_MAX_VIDEOS
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        print(f" 📡 Gọi API: {api_url}")
        response = requests.get(api_url, params=params, headers=headers, timeout=30)

        if response.status_code != 200:
            print(f" ❌ API trả lỗi: HTTP {response.status_code}")
            return videos

        data = response.json()
        video_list = []

        # Thử các cấu trúc phản hồi phổ biến
        if "data" in data:
            if "videos" in data["data"]:
                video_list = data["data"]["videos"]
            elif isinstance(data["data"], list):
                video_list = data["data"]
        elif "videos" in data:
            video_list = data["videos"]

        print(f" 📥 API trả về {len(video_list)} video")

        for idx, v in enumerate(video_list):
            try:
                video_url = ""
                title = ""
                upload_date = ""

                # Lấy link video
                if "video_url" in v:
                    video_url = v["video_url"]
                elif "share_url" in v:
                    video_url = v["share_url"]
                elif "aweme_id" in v:
                    video_url = f"https://www.douyin.com/video/{v['aweme_id']}"

                # Lấy tiêu đề
                if "title" in v:
                    title = v["title"]
                elif "desc" in v:
                    title = v["desc"]

                # Lấy ngày đăng
                if "create_time" in v and v["create_time"]:
                    try:
                        ts = int(v["create_time"])
                        upload_date = time.strftime("%Y-%m-%d", time.localtime(ts))
                    except:
                        pass
                elif "upload_date" in v:
                    upload_date = v["upload_date"]

                if video_url:
                    videos.append({
                        "url": video_url,
                        "title": title,
                        "upload_date": upload_date
                    })
            except Exception as e:
                print(f" ⚠️ Lỗi phân tích video {idx}: {str(e)[:60]}")
                continue

    except Exception as e:
        print(f" ❌ Lỗi gọi Douyin API: {str(e)[:100]}")

    return videos

# =============================================
# === HÀM XỬ LÝ CÁC NỀN TẢNG KHÁC BẰNG YT-DLP ===
# =============================================
def get_videos_ytdlp(channel_url):
    videos = []
    try:
        ydl_opts = {
            'quiet': True,
            'extract_flat': True,
            'playlistend': MAX_VIDEOS_PER_CHANNEL,
            'ignoreerrors': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
            if info and 'entries' in info:
                for entry in info['entries']:
                    if not entry:
                        continue
                    video_url = entry.get('url', '') or entry.get('webpage_url', '')
                    title = entry.get('title', '')
                    upload_date = entry.get('upload_date', '')
                    if upload_date and len(upload_date) == 8:
                        upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
                    if video_url:
                        videos.append({
                            "url": video_url,
                            "title": title,
                            "upload_date": upload_date
                        })
    except Exception as e:
        print(f" ❌ Lỗi yt-dlp: {str(e)[:100]}")

    return videos

# =============================================
# === VÒNG LẶP CHÍNH — ĐỌC TỪNG HÀNG SHEET 1 ===
# =============================================
channels = sheet_source.get_all_values()
print(f"\n📋 Đọc {len(channels)-1} kênh từ Sheet 1")

total_new = 0

for row_idx, channel in enumerate(channels[1:], start=2):
    if len(channel) < 3:
        continue

    platform = channel[0].strip()
    channel_url = channel[1].strip()
    status = channel[2].strip()

    # Bỏ qua nếu chưa có link hoặc đã quét rồi
    if not channel_url or status != "Chưa quét":
        continue

    print(f"\n{'='*60}")
    print(f"🔍 Hàng {row_idx} | Nền tảng: {platform}")
    print(f" Link: {channel_url[:70]}...")

    # Tự động chọn công cụ
    if platform.lower() == "douyin":
        print(f" 🎯 Sử dụng: Douyin-TikTok-Download-API")
        videos = get_douyin_videos(channel_url)
    else:
        print(f" 🎯 Sử dụng: yt-dlp")
        videos = get_videos_ytdlp(channel_url)

    # Chuẩn bị dữ liệu ghi vào Sheet 2
    new_rows = []
    for v in videos:
        if v["url"] not in existing_links:
            new_row = [
                platform,          # A: Nguồn kênh
                v["url"],           # B: Link video gốc
                v["title"],         # C: Tiêu đề
                v["upload_date"],   # D: Ngày đăng
                "Chờ duyệt",        # E: Trạng thái
                "", "", "", "", "", ""  # F→K: Để trống
            ]
            new_rows.append(new_row)
            existing_links.add(v["url"])

    # Ghi vào Sheet 2
    if new_rows:
        try:
            sheet_video.append_rows(new_rows)
            total_new += len(new_rows)
            print(f" ✅ Thêm {len(new_rows)} video mới vào Sheet 2")
        except Exception as e:
            print(f" ❌ Lỗi ghi Sheet 2: {str(e)[:80]}")
            sheet_source.update_cell(row_idx, 3, f"Lỗi: {str(e)[:40]}")
            continue
    else:
        print(f" ℹ️ Không có video mới")

    # Đánh dấu đã quét xong
    sheet_source.update_cell(row_idx, 3, "Đã quét")
    print(f" ✅ Đánh dấu kênh = Đã quét")

    time.sleep(3)  # Nghỉ giữa các kênh

print(f"\n{'='*60}")
print(f"🎉 HOÀN THÀNH! Tổng cộng thêm {total_new} video mới")
print(f"{'='*60}")
