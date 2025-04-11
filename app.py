from flask import Flask, jsonify

# Create a simple Flask app for gunicorn to run
app = Flask(__name__)

@app.route('/')
def index():
    """Status page - directs users to use Telegram"""
    return jsonify({
        "status": "active",
        "message": "Proxy Checker Telegram Bot is running",
        "instructions": "Please use the Telegram bot to check proxies"
    })

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)