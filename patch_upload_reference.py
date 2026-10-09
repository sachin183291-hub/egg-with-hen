import os

def fix_upload_reference():
    filepath = r"c:\Users\sachi\Downloads\giotag project\flask_app.py"
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    old_ref = """@app.route('/upload_reference', methods=['POST'])
def upload_reference():
    file = request.files.get('video') or request.files.get('file')
    if not file:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    
    global reference_settings
    try:
        analyze_reference_video(filepath)
        reference_settings['reference_video'] = filename
        return jsonify({
            "success": True,
            "filename": filename,
            "stats": reference_settings
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500"""

    new_ref = """@app.route('/upload_reference', methods=['POST'])
def upload_reference():
    file = request.files.get('video') or request.files.get('file')
    if not file:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    
    global reference_settings
    try:
        # Analyze it for parameters
        analyze_reference_video(filepath)
        reference_settings['reference_video'] = filename
        
        # Now run FastHenTracker to generate the _output.mp4 video with boxes!
        # This uses the EXACT logic from fast_tracker.py that the user liked.
        import sys
        if os.path.abspath('backend') not in sys.path:
            sys.path.append(os.path.abspath('backend'))
        from app.ai.tracking import process_video
        
        # Process the video; this creates filepath_output.mp4
        process_video(filepath)
        
        output_filename = filename.replace(".mp4", "_output.mp4").replace(".MP4", "_output.mp4")
        if "_output" not in output_filename:
            output_filename += "_output.mp4"
            
        return jsonify({
            "success": True,
            "filename": output_filename,
            "stats": reference_settings
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500"""

    content = content.replace(old_ref, new_ref)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

fix_upload_reference()
