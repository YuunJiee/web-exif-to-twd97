import subprocess
import json
import os
import re
from openpyxl import Workbook
from pyproj import Transformer

transformer = Transformer.from_crs("EPSG:4326", "EPSG:3826", always_xy=True)

def convert_to_degrees(value):
    if isinstance(value, str):
        match = re.match(r"(\d+)[^\d]+(\d+)[^\d]+(\d+(?:\.\d+)?)", value)
        if match:
            d, m, s = map(float, match.groups())
            return d + m / 60 + s / 3600
    elif isinstance(value, (int, float)):
        return float(value)
    return None

def extract_exif(image_paths, exiftool_path, to_twd97=True):
    result = subprocess.run(
        [exiftool_path, "-j"] + image_paths,
        capture_output=True, text=True, encoding="utf-8"
    )
    if not result.stdout:
        raise RuntimeError("❌ 無法取得 EXIF 資料")

    data = json.loads(result.stdout)
    rows = []

    for item in data:
        fname = os.path.basename(item.get("SourceFile", ""))
        time = item.get("DateTimeOriginal", "")
        lat = convert_to_degrees(item.get("GPSLatitude", ""))
        lon = convert_to_degrees(item.get("GPSLongitude", ""))
        lat_ref = item.get("GPSLatitudeRef", "N")
        lon_ref = item.get("GPSLongitudeRef", "E")

        if lat_ref.upper() == "S": lat = -lat
        if lon_ref.upper() == "W": lon = -lon

        if lat and lon:
            if to_twd97:
                x, y = transformer.transform(lon, lat)
            else:
                x, y = lon, lat
            rows.append([fname, time, round(x, 5), round(y, 5)])
        else:
            rows.append([fname, time, "", ""])

    return rows

def save_to_excel(data_rows, output_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "EXIF結果"
    ws.append(["檔案名稱", "拍攝時間", "X", "Y"])
    for row in data_rows:
        ws.append(row)
    wb.save(output_path)
