#!/usr/bin/env python3
"""
Entry point for deployment platforms that expect app.py
Imports the Flask app from lastfm_wallpaper.py
"""

from lastfm_wallpaper import app

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000) 