import gspread
from oauth2client.service_account import ServiceAccountCredentials
import yt_dlp
import os
import time

# === Lấy ID 2 bảng từ biến môi trường ===
SHEET_SOURCE_ID = os.environ['SHEET_SOURCE']
SHEET_VIDEO_ID = os.environ['SHEET_VIDEO']

# === Kết nối Google Sheets ===
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

# === ⚙️ CÁC THÔNG SỐ CÓ THỂ TINH CHỈNH ===
MAX_VIDEOS_PER_CHANNEL = 30  # Số video tối đa lấy mỗi kênh
DELAY_BETWEEN_CHANNELS = 2   # Nghỉ bao nhiêu giây giữa các kênh

# === Lấy danh sách link video đã có trong Sheet 2 để tránh trùng ===
existing_links = set()
all_videos = sheet_video.get_all_values()
for row in all_videos[1:]:
    if len(row) > 1 and row[1].strip():
        existing_links.add(row[1].strip())
print(f"📊 Đã có {len(existing_links)} video trong Sheet 2")

# === Đọc Sheet 1 — từng hàng một ===
channels = sheet_source.get_all_values()
print(f"📋 Đọc {len(channels)-1} kênh từ Sheet 1")

total_new = 0

for row_idx, channel in enumerate(channels[1:], start=2):
    if len(channel) < 3:
        continue

    platform = channel[0].strip()
    channel_url = channel[1].strip()
    status = channel[2].strip()

    # Bỏ qua nếu không có link hoặc đã quét rồi
    if not channel_url or status != "Chưa quét":
        continue

    print(f"\n🔍 Đang quét kênh hàng {row_idx}: {platform}")
    print(f" Link: {channel_url[:60]}...")

    try:
        # === Cấu hình yt-dlp ===
        ydl_opts = {
            'quiet': True,
            'extract_flat': True,
            'playlistend': MAX_VIDEOS_PER_CHANNEL,
            'ignoreerrors': True,
            'no_warnings': True,
        }

        new_rows = []
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)

            if info and 'entries' in info:
                for entry in info['entries']:
                    if not entry:
                        continue

                    video_url = entry.get('url', '') or entry.get('webpage_url', '')
                    if not video_url or video_url in existing_links:
                        continue

                    title = entry.get('title', '')
                    upload_date = entry.get('upload_date', '')

                    # Định dạng lại ngày: YYYYMMDD → YYYY-MM-DD
                    if upload_date and len(upload_date) == 8:
                        upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"

                    # Tạo hàng mới cho Sheet 2 — đủ 11 cột A→K
                    new_row = [
                        platform,          # A: KÊNH NGUỒN
                        video_url,         # B: LINK VIDEO GỐC
                        title,             # C: TIÊU ĐỀ GỐC
                        upload_date,       # D: NGÀY ĐĂNG
                        "Chờ duyệt",       # E: TRẠNG THÁI
                        "",                # F: LINK VIDEO ĐÃ SỬA
                        "",                # G: LINK VIDEO HOÀN CHỈNH
                        "",                # H: TIÊU ĐỀ VIỆT
                        "",                # I: MÔ TẢ + HASHTAG
                        "",                # J: NỀN TẢNG ĐÍCH
                        ""                 # K: LINK ĐÃ ĐĂNG
                    ]
                    new_rows.append(new_row)
                    existing_links.add(video_url)

        # Ghi tất cả video mới vào Sheet 2
        if new_rows:
            sheet_video.append_rows(new_rows)
            total_new += len(new_rows)
            print(f" ✅ Thêm {len(new_rows)} video mới vào Sheet 2")
        else:
            print(f" ℹ️ Không có video mới")

        # Cập nhật trạng thái Sheet 1 = Đã quét
        sheet_source.update_cell(row_idx, 3, "Đã quét")
        print(f" ✅ Đánh dấu kênh này = Đã quét")

        time.sleep(DELAY_BETWEEN_CHANNELS)  # Nghỉ giữa các kênh

    except Exception as e:
        error_msg = str(e)[:50]
        print(f" ❌ Lỗi: {error_msg}")
        sheet_source.update_cell(row_idx, 3, f"Lỗi: {error_msg}")
        continue

print(f"\n🎉 HOÀN THÀNH! Tổng cộng thêm {total_new} video mới")
