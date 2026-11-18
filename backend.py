import os
import requests
from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import json
import math
import io
import time
import numpy as np
import traceback

# Imports
from astropy.coordinates import get_icrs_coordinates, SkyCoord
from astropy import units as u
from astropy.wcs import WCS
from PIL import Image
from reproject import reproject_interp

# --- Configuration ---
Image.MAX_IMAGE_PIXELS = None
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
# Only the static/ folder is web-accessible; source and config files are not.
app = Flask(__name__, static_folder=STATIC_DIR, static_url_path='')
CORS(app)

# Longest side of the skymap preview image. The preview is shown at a few
# hundred pixels, so rendering at full sensor resolution only wastes time.
SKYMAP_PREVIEW_MAX_PX = 1600

# API Constants & Key Loading (env var takes precedence over config.py)
ASTROMETRY_API_URL = 'http://nova.astrometry.net/api'
API_KEY = os.environ.get('ASTROMETRY_API_KEY')
if not API_KEY:
    try:
        from config import API_KEY
    except ImportError:
        API_KEY = None

# Global State for pre-loading the skymap
session_key = None
input_data = None
input_wcs = None

# --- Core Service Functions ---
def load_skymap_data():
    """Pre-loads the single skymap image and computes its WCS at server startup."""
    global input_data, input_wcs
    
    composite_map_path = os.environ.get('SKYMAP_PATH', os.path.join(BASE_DIR, 'composite_skymap_16k.png'))
    print(f"Attempting to pre-load skymap: {composite_map_path}")

    if not os.path.exists(composite_map_path):
        print(f"FATAL: Skymap file not found at '{composite_map_path}'. The skymap feature will not work.")
        return

    try:
        composite_image = Image.open(composite_map_path).convert('RGB')
        # Channels-first (3, H, W) so all channels reproject in one call
        input_data = np.moveaxis(np.asarray(composite_image), -1, 0)

        # WCS Definition for the single full-sky image
        w = WCS(naxis=2)
        w.wcs.crpix = [(composite_image.width + 1) / 2, (composite_image.height + 1) / 2]
        w.wcs.cdelt = np.array([-360. / composite_image.width, -180. / composite_image.height])
        w.wcs.crval = [0, 0]
        w.wcs.ctype = ["RA---CAR", "DEC--CAR"]
        input_wcs = w
        
        print("Skymap data pre-loaded successfully.")
    except Exception as e:
        print(f"CRITICAL ERROR during skymap pre-load: {e}")
        input_data = None
        input_wcs = None


def get_target_coords(data):
    """ICRS coordinates of the target, from custom RA/Dec or a name lookup.

    The previous version transformed ICRS -> AltAz -> ICRS, which returns the
    same coordinates and made the observer location have no effect. Exposure
    and framing only need the target's RA/Dec; location and time matter for
    altitude/visibility (the planner), not here.
    """
    if data.get('ra') is not None and data.get('dec') is not None:
        return SkyCoord(ra=float(data['ra'])*u.degree, dec=float(data['dec'])*u.degree)
    return get_icrs_coordinates(data['target_name'])


def build_sensor_wcs(coords, focal_length_mm, pixel_pitch_um, width_px, height_px, rotation_deg=0.0):
    """Gnomonic (TAN) WCS for a camera sensor, as numpy rows (row 0 = top).

    rotation_deg is the position angle of the image's "up" direction measured
    from north through east. At 0 the image is north-up, east-left.
    The TAN plate scale at the centre is exactly pixel_pitch / focal_length rad.
    """
    scale_deg = math.degrees((pixel_pitch_um / 1000.0) / focal_length_mm)
    th = math.radians(rotation_deg)
    w = WCS(naxis=2)
    w.wcs.crpix = [(width_px + 1) / 2, (height_px + 1) / 2]
    # Pixel axis 1 = column (right), axis 2 = row (down in the PNG).
    w.wcs.cd = scale_deg * np.array([[-math.cos(th), -math.sin(th)],
                                     [ math.sin(th), -math.cos(th)]])
    w.wcs.crval = [coords.ra.degree, coords.dec.degree]
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    return w

# --- Static File Routes ---
@app.route('/')
def serve_index():
    # Serve main HTML file; other static assets are served from static/ by Flask
    return send_from_directory(STATIC_DIR, 'index.html')


# --- API Endpoints ---
@app.route('/api/get_skymap_crop', methods=['POST'])
def get_skymap_crop():
    # Reproject a view of the sky using the pre-loaded single skymap
    if input_data is None or input_wcs is None:
        return jsonify({'error': 'Skymap data is not loaded on the server. Check server logs.'}), 500
        
    try:
        data = request.get_json()
        focal_length = data.get('focal_length')
        sensor_width_px = data.get('sensor_width_px')
        sensor_height_px = data.get('sensor_height_px')
        pixel_pitch = data.get('pixel_pitch')

        if not all([focal_length, sensor_width_px, sensor_height_px, pixel_pitch]):
            return jsonify({'error': 'Missing required camera parameters.'}), 400

        coords = get_target_coords(data)
        rotation_deg = float(data.get('rotation_deg') or 0.0)

        # Render a downscaled preview with the same field of view: shrinking the
        # sensor by `factor` and growing the pixel pitch by `factor` keeps the FOV.
        factor = max(1.0, max(sensor_width_px, sensor_height_px) / SKYMAP_PREVIEW_MAX_PX)
        out_w = max(1, round(sensor_width_px / factor))
        out_h = max(1, round(sensor_height_px / factor))
        output_wcs = build_sensor_wcs(coords, focal_length, pixel_pitch * factor, out_w, out_h, rotation_deg)

        print(f"Reprojecting {out_w}x{out_h} preview for RA {coords.ra.degree:.2f}, Dec {coords.dec.degree:.2f}...")
        t0 = time.perf_counter()
        # All three channels in one call: input is (3, H, W) with a 2D WCS.
        reprojected, _ = reproject_interp((input_data, input_wcs), output_wcs, shape_out=(out_h, out_w))
        reprojected_data = np.nan_to_num(np.moveaxis(reprojected, 0, -1)).clip(0, 255).astype(np.uint8)
        print(f"Reprojection complete in {time.perf_counter() - t0:.2f}s.")

        # Prepare and Send Response
        output_image = Image.fromarray(reprojected_data)
        img_io = io.BytesIO()
        output_image.save(img_io, 'PNG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/png')
        
    except Exception as e:
        print("--- AN ERROR OCCURRED DURING SKYMAP PROCESSING ---")
        traceback.print_exc()
        print("-------------------------------------------------")
        return jsonify({'error': 'An internal error occurred during image processing. Check server logs.'}), 500


# Other API routes...
@app.route('/api/get_declination', methods=['POST'])
def get_declination():
    # Fetches celestial coordinates for a target
    data = request.get_json()
    try:
        coords = get_target_coords(data)
        return jsonify({'declination': coords.dec.degree, 'ra': coords.ra.degree})
    except Exception as e:
        return jsonify({'error': f"Could not find coordinates. {e}"}), 404

def get_session_key():
    # Logs into Astrometry.net API
    global session_key
    if session_key: return session_key
    
    if not API_KEY or API_KEY == "YOUR_API_KEY_HERE":
        raise Exception("Astrometry.net API key not configured in config.py.")

    response = requests.post(f'{ASTROMETRY_API_URL}/login', data={'request-json': json.dumps({'apikey': API_KEY})})
    response.raise_for_status()
    data = response.json()
    if data.get('status') == 'success':
        session_key = data['session']
        return session_key
    else:
        raise Exception(f"API login failed: {data.get('errormessage')}")

@app.route('/api/upload', methods=['POST'])
def upload_image():
    # Uploads an image file for analysis
    try:
        current_session_key = get_session_key()
        if 'image' not in request.files: return jsonify({'error': 'No image file in request.'}), 400
        
        file = request.files['image']
        upload_data = {'session': current_session_key, "publicly_visible": "n"}
        files = {'file': (file.filename, file.read(), file.mimetype)}
        
        response = requests.post(f'{ASTROMETRY_API_URL}/upload', data={'request-json': json.dumps(upload_data)}, files=files)
        response.raise_for_status()
        data = response.json()
        if data.get('status') == 'success': 
            return jsonify({'sub_id': data['subid']})
        else: 
            return jsonify({'error': data.get('errormessage', 'Upload failed')}), 500
    except Exception as e: 
        return jsonify({'error': str(e)}), 500

@app.route('/api/status/<int:sub_id>', methods=['GET'])
def get_status(sub_id):
    # Polls for the status of an analysis job
    try:
        response = requests.get(f'{ASTROMETRY_API_URL}/submissions/{sub_id}')
        response.raise_for_status()
        data = response.json()
        job_id, status, annotated_url = None, 'pending', None
        if data.get('jobs') and data['jobs'] and data['jobs'][0] is not None:
            job_id = data['jobs'][0]
            job_response = requests.get(f'{ASTROMETRY_API_URL}/jobs/{job_id}/info')
            job_response.raise_for_status()
            job_data = job_response.json()
            status = job_data.get('status', 'unknown')
            if status == 'success':
                annotated_url = f"http://nova.astrometry.net/annotated_display/{job_id}"
        return jsonify({'status': status, 'job_id': job_id, 'annotated_image_url': annotated_url})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/api/results/<int:job_id>', methods=['GET'])
def get_results(job_id):
    # Retrieves the final annotations for a successful job
    try:
        response = requests.get(f'{ASTROMETRY_API_URL}/jobs/{job_id}/annotations')
        response.raise_for_status()
        return jsonify({'annotations': response.json().get('annotations', [])})
    except Exception as e: return jsonify({'error': str(e)}), 500

# --- Server Startup ---
if __name__ == '__main__':
    print("Starting Flask server...")
    load_skymap_data()
    if not API_KEY or API_KEY == "YOUR_API_KEY_HERE":
        print("\nWARNING: Astrometry.net API key not found.")
        print("Please create and fill in the 'config.py' file with your API key.\n")
    print("Navigate to http://127.0.0.1:5000")
    # Debug mode (interactive debugger, auto-reload) only when explicitly asked for.
    app.run(port=5000, debug=os.environ.get('FLASK_DEBUG') == '1')

