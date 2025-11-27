from flask import Flask, request, render_template, send_file, redirect, url_for
import subprocess
import os
import tempfile
import re
import shutil
import webbrowser
import time
import sys
from translate import Translator

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024 * 1024  # 10GB limit

# Get the correct base path for bundled or development environments
if getattr(sys, 'frozen', False):
    # Running as bundled exe
    base_path = sys._MEIPASS
else:
    # Running from source
    base_path = os.path.dirname(__file__)

MKVTOOLNIX_PATH = os.path.join(base_path, 'mkvtoolnix')
FFMPEG_PATH = os.path.join(base_path, 'ffmpeg')

# Language mapping for translation
LANG_MAP = {
    'English': 'en',
    'French': 'fr',
    'Spanish': 'es',
    'German': 'de',
    'Italian': 'it',
    'Portuguese': 'pt',
    'Russian': 'ru',
    'Japanese': 'ja',
    'Korean': 'ko',
    'Chinese': 'zh',
    'Arabic': 'ar',
    'Hindi': 'hi',
    'Dutch': 'nl',
    'Polish': 'pl',
    'Turkish': 'tr',
    'Vietnamese': 'vi',
    'Czech': 'cs',
    'Greek': 'el',
    'Hebrew': 'he',
    'Persian': 'fa',
    'Ukrainian': 'uk',
    'Romanian': 'ro',
    'Indonesian': 'id'
}

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

def get_audio_tracks(mkv_path):
    """Get list of audio track IDs and info"""
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
            track_num = line.split('Track number:')[1].split()[0]
            current_track['number'] = int(track_num)
            current_track['id'] = int(line.split('(track ID for mkvmerge & mkvextract:')[1].split(')')[0])
        elif current_track is not None:
            if '|  + Track type: audio' in line:
                current_track['type'] = 'audio'
            elif '|  + Codec ID:' in line:
                current_track['codec'] = line.split('Codec ID:')[1].strip()
            elif '|  + Language' in line:
                current_track['language'] = line.split('Language')[1].strip().split(':')[1].strip() if ':' in line else 'und'
            elif '|  + Name:' in line:
                current_track['name'] = line.split('Name:')[1].strip()
    
    if current_track and current_track.get('type') == 'audio':
        tracks.append(current_track)
    
    return tracks

def convert_video(mkv_path, output_path, resolution=None, format='mp4'):
    """Convert video to specified format and resolution"""
    cmd = [os.path.join(FFMPEG_PATH, 'ffmpeg.exe'), '-i', mkv_path]
    if resolution and resolution != 'original':
        if resolution == '480p':
            scale = '854:480'
        elif resolution == '720p':
            scale = '1280:720'
        elif resolution == '1080p':
            scale = '1920:1080'
        else:
            scale = None
        if scale:
            cmd.extend(['-vf', f'scale={scale}'])
    cmd.extend(['-c:v', 'libx264', '-c:a', 'copy', '-y', output_path])
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0

def extract_subtitle(mkv_path, track_id, output_path):
    """Extract subtitle track using mkvextract"""
    cmd = [os.path.join(MKVTOOLNIX_PATH, 'mkvextract.exe'), 'tracks', mkv_path, f'{track_id}:{output_path}']
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0

def extract_audio(mkv_path, track_id, output_path):
    """Extract audio track using mkvextract and convert to MP3"""
    # First extract the raw audio
    temp_audio = output_path.replace('.mp3', '_temp.wav')
    cmd_extract = [os.path.join(MKVTOOLNIX_PATH, 'mkvextract.exe'), 'tracks', mkv_path, f'{track_id}:{temp_audio}']
    result_extract = subprocess.run(cmd_extract, capture_output=True)
    if result_extract.returncode != 0:
        return False
    
    # Convert to MP3 using ffmpeg
    cmd_convert = [os.path.join(FFMPEG_PATH, 'ffmpeg.exe'), '-i', temp_audio, '-acodec', 'libmp3lame', '-y', output_path]
    result_convert = subprocess.run(cmd_convert, capture_output=True)
    
    # Clean up temp file
    if os.path.exists(temp_audio):
        os.remove(temp_audio)
    
    return result_convert.returncode == 0

def translate_text(text, target_lang):
    """Translate text using free translation service"""
    if not text.strip():
        return text
    
    # Map language name to code
    lang_code = LANG_MAP.get(target_lang, 'en')
    
    try:
        translator = Translator(to_lang=lang_code)
        translation = translator.translate(text)
        return translation
    except Exception as e:
        error_msg = str(e).upper()
        if "PLEASE SELECT TWO DISTINCT LANGUAGES" in error_msg:
            # Text is already in target language, return as-is
            return text
        return f"Translation failed: {str(e)}"

def translate_srt(srt_content, target_lang):
    """Translate SRT subtitle content"""
    lines = srt_content.split('\n')
    translated_lines = []
    for line in lines:
        if line.strip() and not line.isdigit() and '-->' not in line:
            # This is likely subtitle text
            translated = translate_text(line, target_lang)
            translated_lines.append(translated)
        else:
            translated_lines.append(line)
    return '\n'.join(translated_lines)

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
    try:
        if 'file' not in request.files:
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            return redirect(request.url)
        
        if not file.filename.lower().endswith('.mkv'):
            return "Please upload an MKV file"
        
        extract_subtitles_checked = 'extract_subtitles' in request.form
        extract_audio_checked = 'extract_audio' in request.form
        convert_video_checked = 'convert_video' in request.form
        output_format = request.form.get('output_format', 'mp4')
        resolution = request.form.get('resolution', 'original')
        translate_subtitles_checked = 'translate_subtitles' in request.form
        target_lang = request.form.get('target_lang', 'English')
        
        with tempfile.TemporaryDirectory() as temp_dir:
            mkv_path = os.path.join(temp_dir, 'input.mkv')
            file.save(mkv_path)
            
            extracted_files = []
            
            # Debug: Check what operations are requested
            debug_info = []
            debug_info.append(f"File: {file.filename}")
            debug_info.append(f"Extract subtitles: {extract_subtitles_checked}")
            debug_info.append(f"Extract audio: {extract_audio_checked}")
            debug_info.append(f"Convert video: {convert_video_checked}")
            
            if extract_subtitles_checked:
                try:
                    tracks = get_subtitle_tracks(mkv_path)
                    debug_info.append(f"Found {len(tracks)} subtitle tracks")
                    for track in tracks:
                        debug_info.append(f"  Track {track['id']}: {track.get('codec', 'unknown')} - {track.get('language', 'und')}")
                    for track in tracks:
                        track_id = track['id']
                        codec = track['codec']
                        lang = track.get('language', 'und')
                        name = track.get('name', f'Track_{track_id}')
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
                                if translate_subtitles_checked:
                                    translated_srt = translate_srt(srt_content, target_lang)
                                    translated_srt_path = os.path.join(temp_dir, f'{name}_{lang}_{target_lang}.srt')
                                    with open(translated_srt_path, 'w', encoding='utf-8') as f:
                                        f.write(translated_srt)
                                    extracted_files.append((f'{name}_{lang}_{target_lang}.srt', translated_srt_path))
                        elif codec == 'S_TEXT/UTF8':
                            srt_path = os.path.join(temp_dir, f'{name}_{lang}.srt')
                            if extract_subtitle(mkv_path, track_id, srt_path):
                                with open(srt_path, 'r', encoding='utf-8') as f:
                                    srt_content = f.read()
                                extracted_files.append((f'{name}_{lang}.srt', srt_path))
                                if translate_subtitles_checked:
                                    translated_srt = translate_srt(srt_content, target_lang)
                                    translated_srt_path = os.path.join(temp_dir, f'{name}_{lang}_{target_lang}.srt')
                                    with open(translated_srt_path, 'w', encoding='utf-8') as f:
                                        f.write(translated_srt)
                                    extracted_files.append((f'{name}_{lang}_{target_lang}.srt', translated_srt_path))
                except Exception as e:
                    return f"Error extracting subtitles: {str(e)}"
            
            if extract_audio_checked:
                try:
                    audio_tracks = get_audio_tracks(mkv_path)
                    debug_info.append(f"Found {len(audio_tracks)} audio tracks")
                    for track in audio_tracks:
                        debug_info.append(f"  Track {track['id']}: {track.get('codec', 'unknown')} - {track.get('language', 'und')}")
                    for track in audio_tracks:
                        track_id = track['id']
                        lang = track.get('language', 'und')
                        name = track.get('name', f'Audio_{track_id}')
                        output_path = os.path.join(temp_dir, f'{name}_{lang}.mp3')  # Assume MP3
                        if extract_audio(mkv_path, track_id, output_path):
                            extracted_files.append((f'{name}_{lang}.mp3', output_path))
                except Exception as e:
                    return f"Error extracting audio: {str(e)}"
            
            if convert_video_checked:
                try:
                    base_name = os.path.splitext(file.filename)[0]
                    output_filename = f'{base_name}_converted.{output_format}'
                    output_path = os.path.join(temp_dir, output_filename)
                    if convert_video(mkv_path, output_path, resolution, output_format):
                        extracted_files.append((output_filename, output_path))
                except Exception as e:
                    return f"Error converting video: {str(e)}"
            
            if not extracted_files:
                debug_message = "No files were processed or extracted\n\nDebug info:\n" + "\n".join(debug_info)
                return debug_message
            
            # Copy files to static temp
            static_temp = os.path.join(app.root_path, 'static', 'temp')
            os.makedirs(static_temp, exist_ok=True)
            
            download_links = []
            for filename, filepath in extracted_files:
                dest = os.path.join(static_temp, filename)
                shutil.copy(filepath, dest)
                download_links.append(filename)
            
            return render_template('results.html', files=download_links)
    except Exception as e:
        return f"Internal server error: {str(e)}"

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