from flask import Flask, request, render_template, send_file, redirect, url_for
import subprocess
import os
import tempfile
import re
import shutil
import webbrowser
import time

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024 * 1024  # 10GB limit

MKVTOOLNIX_PATH = os.path.join(os.path.dirname(__file__), 'mkvtoolnix')

def get_subtitle_tracks(mkv_path):
    """Get list of subtitle track IDs and info"""
    cmd = [os.path.join(MKVTOOLNIX_PATH, 'mkvinfo.exe'), mkv_path]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    if result.returncode != 0:
        return []
    
    tracks = []
    lines = result.stdout.split('\n')
    current_track = None
    for line in lines:
        if '|  + Track number:' in line:
            if current_track:
                tracks.append(current_track)
            current_track = {}
            # Extract track number
            track_num = line.split('Track number:')[1].split()[0]
            current_track['number'] = int(track_num)
            current_track['id'] = int(line.split('(track ID for mkvmerge & mkvextract:')[1].split(')')[0])
        elif current_track is not None:
            if '|  + Track type: subtitles' in line:
                current_track['type'] = 'subtitles'
            elif '|  + Codec ID:' in line:
                current_track['codec'] = line.split('Codec ID:')[1].strip()
            elif '|  + Language' in line:
                current_track['language'] = line.split('Language')[1].strip().split(':')[1].strip() if ':' in line else 'und'
            elif '|  + Name:' in line:
                current_track['name'] = line.split('Name:')[1].strip()
    
    if current_track and current_track.get('type') == 'subtitles':
        tracks.append(current_track)
    
    return tracks

def extract_subtitle(mkv_path, track_id, output_path):
    """Extract subtitle track"""
    cmd = [os.path.join(MKVTOOLNIX_PATH, 'mkvextract.exe'), 'tracks', mkv_path, f'{track_id}:{output_path}']
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0

def convert_ass_to_srt(ass_content):
    """Convert ASS content to SRT string"""
    lines = ass_content.split('\n')
    srt_lines = []
    seq = 1
    for line in lines:
        if line.startswith('Dialogue:'):
            parts = line.split(',', 9)
            if len(parts) < 10:
                continue
            start = parts[1]
            end = parts[2]
            text = parts[9]
            # Remove ASS tags
            text = re.sub(r'\{[^}]*\}', '', text)
            # Convert time
            def convert_time(t):
                try:
                    h, m, s = t.split(':')
                    s, ms = s.split('.')
                    ms = ms.ljust(3, '0')[:3]
                    return f"{int(h):02d}:{m}:{s},{ms}"
                except:
                    return "00:00:00,000"
            start_srt = convert_time(start)
            end_srt = convert_time(end)
            srt_lines.append(f"{seq}")
            srt_lines.append(f"{start_srt} --> {end_srt}")
            srt_lines.append(text)
            srt_lines.append("")
            seq += 1
    return '\n'.join(srt_lines)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    
    if not file.filename.lower().endswith('.mkv'):
        return "Please upload an MKV file"
    
    with tempfile.TemporaryDirectory() as temp_dir:
        mkv_path = os.path.join(temp_dir, 'input.mkv')
        file.save(mkv_path)
        
        tracks = get_subtitle_tracks(mkv_path)
        if not tracks:
            return "No subtitle tracks found in the MKV file"
        
        extracted_files = []
        for track in tracks:
            track_id = track['id']
            codec = track['codec']
            lang = track.get('language', 'und')
            name = track.get('name', f'Track_{track_id}')
            
            if codec == 'S_TEXT/ASS':
                ass_path = os.path.join(temp_dir, f'{name}_{lang}.ass')
                if extract_subtitle(mkv_path, track_id, ass_path):
                    # Convert to SRT
                    with open(ass_path, 'r', encoding='utf-8') as f:
                        ass_content = f.read()
                    srt_content = convert_ass_to_srt(ass_content)
                    srt_path = os.path.join(temp_dir, f'{name}_{lang}.srt')
                    with open(srt_path, 'w', encoding='utf-8') as f:
                        f.write(srt_content)
                    extracted_files.append((f'{name}_{lang}.ass', ass_path))
                    extracted_files.append((f'{name}_{lang}.srt', srt_path))
            elif codec == 'S_TEXT/UTF8':
                srt_path = os.path.join(temp_dir, f'{name}_{lang}.srt')
                if extract_subtitle(mkv_path, track_id, srt_path):
                    extracted_files.append((f'{name}_{lang}.srt', srt_path))
            # Add more codecs if needed
        
        if not extracted_files:
            return "Failed to extract subtitles"
        
        # For simplicity, since we can't return files directly, we'll copy to a static folder or something
        # But for local, perhaps return HTML with download links
        # Since Flask can serve files, but for multiple, return a page with links
        
        # Copy files to a temp location that can be served
        static_temp = os.path.join(app.root_path, 'static', 'temp')
        os.makedirs(static_temp, exist_ok=True)
        
        download_links = []
        for filename, filepath in extracted_files:
            dest = os.path.join(static_temp, filename)
            shutil.copy(filepath, dest)
            download_links.append(filename)
        
        return render_template('results.html', files=download_links)

@app.route('/download/<filename>')
def download(filename):
    return send_file(os.path.join(app.root_path, 'static', 'temp', filename), as_attachment=True)

if __name__ == '__main__':
    # Open browser after a short delay
    def open_browser():
        time.sleep(1)
        webbrowser.open('http://127.0.0.1:5000/')
    
    import threading
    threading.Thread(target=open_browser).start()
    app.run(debug=False, host='127.0.0.1', port=5000)