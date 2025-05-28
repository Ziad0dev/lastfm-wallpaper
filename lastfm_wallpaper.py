import os
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import numpy as np
from flask import Flask, render_template, request, jsonify, send_file
from dotenv import load_dotenv
import io
import zipfile
from urllib.parse import urlparse
import tempfile
import shutil
import logging

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Get port from environment variable for deployment
PORT = int(os.environ.get('PORT', 5000))

class LastFMWallpaperGenerator:
    def __init__(self):
        self.api_key = os.getenv('LASTFM_API_KEY')
        self.shared_secret = os.getenv('LASTFM_SHARED_SECRET')
        self.base_url = "http://ws.audioscrobbler.com/2.0/"
        
        if not self.api_key:
            raise ValueError("LASTFM_API_KEY environment variable is required")
        if not self.shared_secret:
            raise ValueError("LASTFM_SHARED_SECRET environment variable is required")
        
    def validate_username(self, username):
        """Validate if a Last.fm username exists"""
        params = {
            'method': 'user.getinfo',
            'user': username,
            'api_key': self.api_key,
            'format': 'json'
        }
        
        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            if response.status_code == 404:
                return False, "Username not found on Last.fm"
            
            response.raise_for_status()
            data = response.json()
            
            if 'error' in data:
                return False, f"Last.fm error: {data.get('message', 'Unknown error')}"
            
            if 'user' in data:
                # Check if user has any scrobbles
                playcount = int(data['user'].get('playcount', 0))
                if playcount == 0:
                    return False, "User has no scrobbles on Last.fm"
                return True, f"Valid user with {playcount:,} scrobbles"
            
            return False, "Invalid response from Last.fm"
            
        except requests.exceptions.Timeout:
            return False, "Request timeout - please try again"
        except requests.exceptions.RequestException as e:
            return False, f"Network error: {str(e)}"
        except Exception as e:
            return False, f"Validation error: {str(e)}"
    
    def get_user_top_albums(self, username, period="overall", limit=50):
        """Fetch user's top albums from Last.fm API"""
        params = {
            'method': 'user.gettopalbums',
            'user': username,
            'api_key': self.api_key,
            'format': 'json',
            'period': period,
            'limit': limit
        }
        
        try:
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if 'topalbums' in data and 'album' in data['topalbums']:
                return data['topalbums']['album']
            else:
                return []
        except Exception as e:
            logger.error(f"Error fetching albums for user {username}: {e}")
            return []
    
    def download_image(self, url):
        """Download image from URL with better quality handling"""
        try:
            # Try to get higher resolution by modifying the URL
            high_res_url = url.replace('/300x300/', '/500x500/').replace('300x300', '500x500')
            if high_res_url == url:
                # Try other common size patterns
                high_res_url = url.replace('174s', '500x500').replace('64s', '500x500')
            
            # Try high resolution first
            try:
                response = requests.get(high_res_url, timeout=10)
                response.raise_for_status()
                image = Image.open(io.BytesIO(response.content))
                logger.info(f"Downloaded high-res image: {image.size}")
                return image
            except:
                # Fall back to original URL
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                image = Image.open(io.BytesIO(response.content))
                logger.info(f"Downloaded standard image: {image.size}")
                return image
                
        except Exception as e:
            logger.error(f"Error downloading image from {url}: {e}")
            return None
    
    def create_wallpaper(self, album_cover, album_name, artist_name, wallpaper_size=(1920, 1080)):
        """Create a wallpaper from album cover using letterboxing to preserve quality"""
        if not album_cover:
            return None
        
        # Convert to RGB if needed
        if album_cover.mode != 'RGB':
            album_cover = album_cover.convert('RGB')
        
        wallpaper_width, wallpaper_height = wallpaper_size
        cover_width, cover_height = album_cover.size
        
        # Create a new wallpaper canvas with black background
        wallpaper = Image.new('RGB', wallpaper_size, color=(0, 0, 0))
        
        # If the album cover is larger than wallpaper dimensions, resize it to fit
        # while maintaining aspect ratio
        if cover_width > wallpaper_width or cover_height > wallpaper_height:
            # Calculate the scaling factor to fit within wallpaper bounds
            scale_factor = min(wallpaper_width / cover_width, wallpaper_height / cover_height)
            new_width = int(cover_width * scale_factor)
            new_height = int(cover_height * scale_factor)
            
            # Resize with high-quality resampling
            album_cover = album_cover.resize((new_width, new_height), Image.Resampling.LANCZOS)
            cover_width, cover_height = new_width, new_height
        
        # Calculate position to center the album cover on the wallpaper
        x_offset = (wallpaper_width - cover_width) // 2
        y_offset = (wallpaper_height - cover_height) // 2
        
        # Paste the album cover onto the center of the wallpaper
        wallpaper.paste(album_cover, (x_offset, y_offset))
        
        return wallpaper
    
    def generate_wallpapers(self, username, period="overall", limit=10):
        """Generate wallpapers for user's top albums"""
        albums = self.get_user_top_albums(username, period, limit)
        wallpapers = []
        
        for i, album in enumerate(albums):
            try:
                album_name = album['name']
                artist_name = album['artist']['name']
                
                # Get the highest quality image available
                image_url = None
                # Try to get the best quality image available, prioritizing larger sizes
                size_priority = ['mega', 'extralarge', 'large', 'medium', 'small']
                for size in size_priority:
                    for image in album['image']:
                        if image['size'] == size and image['#text']:
                            image_url = image['#text']
                            logger.info(f"Found {size} image for {album_name} by {artist_name}")
                            break
                    if image_url:
                        break
                
                if not image_url:
                    logger.warning(f"No image found for {album_name} by {artist_name}")
                    continue
                
                logger.info(f"Processing {i+1}/{len(albums)}: {artist_name} - {album_name}")
                
                # Download album cover
                album_cover = self.download_image(image_url)
                if not album_cover:
                    continue
                
                # Create wallpaper
                wallpaper = self.create_wallpaper(album_cover, album_name, artist_name)
                if wallpaper:
                    wallpapers.append({
                        'image': wallpaper,
                        'filename': f"{artist_name} - {album_name}".replace('/', '_').replace('\\', '_')[:100] + '.jpg'
                    })
                    
            except Exception as e:
                logger.error(f"Error processing album {album.get('name', 'Unknown')}: {e}")
                continue
        
        return wallpapers

# Initialize the generator
lastfm_generator = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/validate', methods=['POST'])
def validate_user():
    """Validate Last.fm username"""
    data = request.json
    username = data.get('username', '').strip()
    
    if not username:
        return jsonify({'valid': False, 'message': 'Username is required'}), 400
    
    generator = LastFMWallpaperGenerator()
    is_valid, message = generator.validate_username(username)
    
    return jsonify({
        'valid': is_valid,
        'message': message
    })

@app.route('/generate', methods=['POST'])
def generate_wallpapers():
    global lastfm_generator
    
    data = request.json
    username = data.get('username', '').strip()
    period = data.get('period', 'overall')
    limit = int(data.get('limit', 10))
    
    if not username:
        return jsonify({'error': 'Username is required'}), 400
    
    try:
        lastfm_generator = LastFMWallpaperGenerator()
        
        # Validate username first
        is_valid, validation_message = lastfm_generator.validate_username(username)
        if not is_valid:
            return jsonify({'error': validation_message}), 400
        
        wallpapers = lastfm_generator.generate_wallpapers(username, period, limit)
        
        if not wallpapers:
            return jsonify({'error': 'No wallpapers could be generated. The user might not have enough album data.'}), 400
        
        # Create a temporary directory to store wallpapers
        temp_dir = tempfile.mkdtemp()
        
        # Save wallpapers to temporary directory
        for wallpaper_data in wallpapers:
            filepath = os.path.join(temp_dir, wallpaper_data['filename'])
            wallpaper_data['image'].save(filepath, 'JPEG', quality=100, optimize=True)
        
        # Create zip file
        zip_path = os.path.join(temp_dir, f"{username}_wallpapers.zip")
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for wallpaper_data in wallpapers:
                filepath = os.path.join(temp_dir, wallpaper_data['filename'])
                zipf.write(filepath, wallpaper_data['filename'])
        
        return jsonify({
            'success': True,
            'count': len(wallpapers),
            'download_url': f'/download/{username}',
            'validation_message': validation_message
        })
        
    except Exception as e:
        return jsonify({'error': f'Error generating wallpapers: {str(e)}'}), 500

@app.route('/download/<username>')
def download_wallpapers(username):
    try:
        # Find the zip file in temp directory
        temp_dirs = [d for d in os.listdir('/tmp') if d.startswith('tmp')]
        for temp_dir in temp_dirs:
            zip_path = os.path.join('/tmp', temp_dir, f"{username}_wallpapers.zip")
            if os.path.exists(zip_path):
                return send_file(zip_path, as_attachment=True, download_name=f"{username}_wallpapers.zip")
        
        return jsonify({'error': 'Wallpapers not found'}), 404
    except Exception as e:
        return jsonify({'error': f'Error downloading wallpapers: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=PORT)
