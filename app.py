from flask import Flask, request, render_template, send_file, redirect, url_for, session
import os
from werkzeug.utils import secure_filename
import zipfile
import tempfile
import shutil
import time
from exif_util import extract_exif, save_to_excel
from flask import jsonify

app = Flask(__name__)
app.secret_key = "supersecret"
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 自動清理舊資料夾
def clean_expired_temp_folders(root_folder, expire_seconds=1800):
    now = time.time()
    for folder in os.listdir(root_folder):
        full_path = os.path.join(root_folder, folder)
        if os.path.isdir(full_path):
            try:
                if now - os.path.getmtime(full_path) > expire_seconds:
                    shutil.rmtree(full_path, ignore_errors=True)
            except Exception:
                continue

@app.route("/", methods=["GET"])
def index():
    clean_expired_temp_folders(app.config['UPLOAD_FOLDER'])

    # 清空單次上傳暫存資料夾
    temp_folder = session.pop("temp_folder", None)
    if temp_folder and os.path.exists(temp_folder):
        shutil.rmtree(temp_folder, ignore_errors=True)

    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    uploaded_files = request.files.getlist("files")
    image_exts = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic"}
    extracted_images = []

    temp_folder = tempfile.mkdtemp(dir=app.config['UPLOAD_FOLDER'])
    session["temp_folder"] = temp_folder

    for file in uploaded_files:
        filename = secure_filename(file.filename)
        ext = os.path.splitext(filename)[1].lower()
        save_path = os.path.join(temp_folder, filename)
        file.save(save_path)

        if ext == ".zip":
            try:
                with zipfile.ZipFile(save_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_folder)
                    for root, _, files in os.walk(temp_folder):
                        for f in files:
                            f_ext = os.path.splitext(f)[1].lower()
                            if f_ext in image_exts:
                                extracted_images.append(os.path.join(root, f))
            except Exception as e:
                return f"❌ 解壓縮失敗: {e}", 400
        elif ext in image_exts:
            extracted_images.append(save_path)

    if not extracted_images:
        return "❌ 沒有找到任何有效的圖片檔案。", 400

    exiftool_path = "exiftool.exe"
    result_wgs84 = extract_exif(extracted_images, exiftool_path, to_twd97=False)
    result_twd97 = extract_exif(extracted_images, exiftool_path, to_twd97=True)

    # 累積資料
    session.setdefault("all_data_wgs84", []).extend(result_wgs84)
    session.setdefault("all_data_twd97", []).extend(result_twd97)

    # 上傳後立刻刪除圖片資料夾
    shutil.rmtree(temp_folder, ignore_errors=True)
    session.pop("temp_folder", None)

    return "OK"

@app.route("/map_preview", methods=["GET", "POST"])
def map_preview():
    if request.args.get("count_only") == "1":
        count = len(session.get("all_data_wgs84", []))
        return jsonify({"count": count})
    
    if request.method == "POST":
        crs = request.form.get("crs", "wgs84")
        data = session.get("all_data_wgs84" if crs == "wgs84" else "all_data_twd97", [])
        temp_folder = tempfile.mkdtemp(dir=app.config['UPLOAD_FOLDER'])
        output_path = os.path.join(temp_folder, "EXIF結果.xlsx")
        save_to_excel(data, output_path)
        return send_file(output_path, as_attachment=True)

    return render_template("map_preview.html",
                           count=len(session.get("all_data_wgs84", [])),
                           data_wgs84=session.get("all_data_wgs84", []),
                           data_twd97=session.get("all_data_twd97", []))

@app.route("/clear_all")
def clear_all():
    session.pop("all_data_wgs84", None)
    session.pop("all_data_twd97", None)
    temp_folder = session.pop("temp_folder", None)
    if temp_folder and os.path.exists(temp_folder):
        shutil.rmtree(temp_folder, ignore_errors=True)
    return redirect(url_for("index"))


@app.errorhandler(413)
def too_large(e):
    return render_template("index.html", error="❌ 上傳失敗：檔案總大小不能超過 100MB"), 413


if __name__ == "__main__":
    app.run(debug=True)

