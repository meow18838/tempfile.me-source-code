from flask import Flask, request, redirect, url_for, send_from_directory, render_template, jsonify
from werkzeug.utils import secure_filename
import os
import uuid
import mimetypes
from PIL import Image
import cv2
import numpy as np
import hashlib
import time
from collections import defaultdict
import random

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['PREVIEW_FOLDER'] = 'previews'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024 * 1024  # 5GB

# Token storage: IP -> {filename: (token, timestamp)}
tokens = defaultdict(dict)

for folder in [app.config['UPLOAD_FOLDER'], app.config['PREVIEW_FOLDER']]:
    if not os.path.exists(folder):
        os.makedirs(folder)

def generate_image_preview(filename):
    img_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    preview_path = os.path.join(app.config['PREVIEW_FOLDER'], f"preview_{filename}")
    
    with Image.open(img_path) as img:
        img.thumbnail((200, 200))
        img.save(preview_path)
    
    return preview_path

def generate_video_preview(filename):
    video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    preview_path = os.path.join(app.config['PREVIEW_FOLDER'], f"preview_{filename}.jpg")
    
    cap = cv2.VideoCapture(video_path)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    frames = []
    for i in range(4):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_count * i / 4))
        ret, frame = cap.read()
        if ret:
            frame = cv2.resize(frame, (100, 100))
            frames.append(frame)
    
    cap.release()
    
    if len(frames) == 4:
        preview = np.vstack((np.hstack((frames[0], frames[1])), np.hstack((frames[2], frames[3]))))
        cv2.imwrite(preview_path, preview)
        return preview_path
    
    return None

def generate_token(filename, ip):
    token = str(random.randint(0,9999))
    tokens[ip][filename] = (token, time.time())
    return token

def validate_token(filename, token, ip):
    if ip in tokens and filename in tokens[ip]:
        stored_token, timestamp = tokens[ip][filename]
        if stored_token == token and time.time() - timestamp < 24 * 3600:
            return True
    return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/report')
def report():
    return render_template('report.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    files = request.files.getlist('files')
    links = []

    for file in files:
        if file.filename == '':
            continue
        if file:
            filename = secure_filename(file.filename)
            unique_filename = str(random.randint(0,9999)) + "_" + filename
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(file_path)
            links.append(url_for('file_info', filename=unique_filename, _external=True))
    
    return jsonify({'links': links})

@app.route('/file/<filename>')
def uploaded_file(filename):
    token = request.args.get('token')
    ip = request.remote_addr
    
    if not validate_token(filename, token, ip):
        return redirect(url_for('file_info', filename=filename).replace('http://', 'https://'))
    
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/f/<filename>')
@app.route('/file_info/<filename>', endpoint="old_file_url")
def file_info(filename):
    ip = request.remote_addr
    token = generate_token(filename, ip)
    file_url = url_for('uploaded_file', filename=filename, token=token, _external=True).replace('http://', 'https://')
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    mime_type, _ = mimetypes.guess_type(file_path)
  
    preview_url = None
    if mime_type:
        if mime_type.startswith('image'):
            preview_path = generate_image_preview(filename)
            preview_url = url_for('preview_file', filename=os.path.basename(preview_path), _external=True).replace('http://', 'https://')
        elif mime_type.startswith('video'):
            preview_path = generate_video_preview(filename)
            if preview_path:
                preview_url = url_for('preview_file', filename=os.path.basename(preview_path), _external=True).replace('http://', 'https://')
    
    return render_template('file_info.html', filename=filename, file_url=file_url, preview_url=preview_url)

@app.route('/preview/<filename>')
def preview_file(filename):
    return send_from_directory(app.config['PREVIEW_FOLDER'], filename)