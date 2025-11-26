from flask import Flask, jsonify, request
from flask_cors import CORS
import os

# --- 1. FLASK APP SETUP ---
# Flask is often named 'app'
app = Flask(__name__)

# --- 2. CORS CONFIGURATION (Fixes the "CRITICAL ERROR" / CORS block) ---
# Define the origins allowed to make requests to this API.
ALLOWED_ORIGINS = [
    "null",                                     # Allows local file testing (index.html running from your desktop)
    "https://your-published-site.webflow.io",   # *** REPLACE with your actual Webflow domain after publishing ***
    "https://sonifai-backend.onrender.com"      # Allows your own service to call itself
]

# Apply the CORS configuration
CORS(app, resources={r"/api/*": {"origins": ALLOWED_ORIGINS}})
# The 'r"/api/*"' part tells Flask to apply this CORS rule to all endpoints starting with /api/

# --- 3. THE MISSING API ROUTE ---
@app.route('/api/get-transcription-url', methods=['GET'])
def get_transcription_url():
    """
    Handles the request from the frontend to retrieve the public URL
    of the generated MusicXML file for a specific session.
    """
    # 3a. Get the unique ID from the frontend request (e.g., session_id=1)
    session_id = request.args.get('session_id')
    
    # Error check for missing ID
    if not session_id:
        return jsonify({"error": "Missing session_id parameter"}), 400

    # 3b. *** CRITICAL: YOUR REAL LOGIC GOES HERE ***
    # This is where your code should communicate with your cloud storage (S3/GCS) 
    # to find the specific MusicXML URL associated with the session_id.
    
    # --- DUMMY SUCCESS RESPONSE FOR INITIAL TESTING ---
    # We use a placeholder XML file to confirm the API connection works.
    if session_id == '1':
        # This MUST be the public URL of a valid MusicXML file.
        music_xml_url = "https://www.musicxml.com/for-developers/hello-world/hello-world.xml" 
    else:
        # If the ID is not '1', assume score is not found for this test.
        return jsonify({"error": f"Score with ID {session_id} not found for testing."}), 404
    # --- END DUMMY RESPONSE ---

    # 3c. Return the required JSON response format
    return jsonify({
        "musicXmlUrl": music_xml_url
    }), 200 # HTTP 200 OK

# --- 4. RUNNING THE APP ---
if __name__ == '__main__':
    # Render often sets the PORT environment variable; use 5000 as a local default
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
