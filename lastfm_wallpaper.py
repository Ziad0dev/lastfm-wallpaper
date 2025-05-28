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
import gc  # Add garbage collection

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
        """Download image from URL with enhanced quality handling and multiple resolution attempts"""
        try:
            # Try multiple high-resolution URL patterns
            high_res_urls = []
            
            # Pattern 1: Replace size indicators with larger ones
            high_res_urls.append(url.replace('/300x300/', '/1200x1200/').replace('300x300', '1200x1200'))
            high_res_urls.append(url.replace('/300x300/', '/800x800/').replace('300x300', '800x800'))
            high_res_urls.append(url.replace('/300x300/', '/500x500/').replace('300x300', '500x500'))
            
            # Pattern 2: Replace small size indicators
            high_res_urls.append(url.replace('174s', '1200x1200').replace('64s', '1200x1200'))
            high_res_urls.append(url.replace('174s', '800x800').replace('64s', '800x800'))
            high_res_urls.append(url.replace('174s', '500x500').replace('64s', '500x500'))
            
            # Pattern 3: Try removing size parameters entirely (sometimes gives original size)
            if '?' in url:
                base_url = url.split('?')[0]
                high_res_urls.append(base_url)
            
            # Pattern 4: Try common Last.fm size patterns
            if 'lastfm' in url:
                high_res_urls.append(url.replace('/i/u/300x300/', '/i/u/ar0/').replace('/i/u/174s/', '/i/u/ar0/'))
                high_res_urls.append(url.replace('/i/u/300x300/', '/i/u/770x0/').replace('/i/u/174s/', '/i/u/770x0/'))
            
            # Remove duplicates while preserving order
            seen = set()
            unique_urls = []
            for url_attempt in high_res_urls:
                if url_attempt not in seen and url_attempt != url:
                    seen.add(url_attempt)
                    unique_urls.append(url_attempt)
            
            # Add original URL as fallback
            unique_urls.append(url)
            
            # Try each URL in order of preference
            for attempt_url in unique_urls:
                try:
                    response = requests.get(attempt_url, timeout=15, stream=True)
                    response.raise_for_status()
                    
                    # Load image directly from stream to save memory
                    image_data = io.BytesIO()
                    for chunk in response.iter_content(chunk_size=8192):
                        image_data.write(chunk)
                    image_data.seek(0)
                    
                    image = Image.open(image_data)
                    
                    # Convert to RGB immediately to avoid issues later
                    if image.mode != 'RGB':
                        image = image.convert('RGB')
                    
                    # Log successful download with size info
                    if attempt_url != url:
                        logger.info(f"Downloaded enhanced image: {image.size} from high-res URL")
                    else:
                        logger.info(f"Downloaded standard image: {image.size}")
                    
                    return image
                    
                except Exception as e:
                    # Log failed attempts for debugging
                    if attempt_url != url:
                        logger.debug(f"Failed to download from {attempt_url}: {e}")
                    continue
            
            # If all attempts failed
            logger.error(f"All download attempts failed for image URLs")
            return None
                
        except Exception as e:
            logger.error(f"Error in download_image: {e}")
            return None
    
    def enhance_image_quality(self, image):
        """Apply various enhancement techniques to improve image quality"""
        try:
            # Apply unsharp mask for better sharpness
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(1.2)  # Increase sharpness by 20%
            
            # Enhance contrast slightly
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.1)  # Increase contrast by 10%
            
            # Enhance color saturation slightly
            enhancer = ImageEnhance.Color(image)
            image = enhancer.enhance(1.05)  # Increase saturation by 5%
            
            return image
        except Exception as e:
            logger.warning(f"Failed to enhance image quality: {e}")
            return image
    
    def smart_upscale_image(self, image, target_size):
        """Intelligently upscale small images using high-quality resampling"""
        current_width, current_height = image.size
        target_width, target_height = target_size
        
        # If image is significantly smaller than target, upscale it
        if current_width < target_width * 0.7 or current_height < target_height * 0.7:
            # Calculate upscale factor
            scale_factor = min(target_width / current_width, target_height / current_height)
            
            # Limit upscaling to avoid too much quality loss
            if scale_factor > 3.0:
                scale_factor = 3.0
            
            new_width = int(current_width * scale_factor)
            new_height = int(current_height * scale_factor)
            
            # Use LANCZOS for high-quality upscaling
            upscaled = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            logger.info(f"Upscaled image from {image.size} to {upscaled.size}")
            return upscaled
        
        return image

    def create_wallpaper(self, album_cover, album_name, artist_name, wallpaper_size=(1920, 1080)):
        """Create a wallpaper from album cover using letterboxing and quality enhancement"""
        if not album_cover:
            return None
        
        try:
            wallpaper_width, wallpaper_height = wallpaper_size
            
            # Enhance image quality first
            album_cover = self.enhance_image_quality(album_cover)
            
            # Smart upscaling for small images
            album_cover = self.smart_upscale_image(album_cover, wallpaper_size)
            
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
            
        except Exception as e:
            logger.error(f"Error creating wallpaper for {artist_name} - {album_name}: {e}")
            return None
    
    def generate_wallpapers_to_disk(self, username, period="overall", limit=10, temp_dir=None):
        """Generate wallpapers for user's top albums and save directly to disk to optimize memory"""
        albums = self.get_user_top_albums(username, period, limit)
        if not albums:
            return []
            
        if not temp_dir:
            temp_dir = tempfile.mkdtemp()
            
        saved_files = []
        
        for i, album in enumerate(albums):
            try:
                album_name = album['name']
                artist_name = album['artist']['name']
                
                # Get the highest quality image available using enhanced method
                image_url = self.get_best_album_image(album)
                
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
                    # Save immediately to disk and free memory
                    filename = f"{artist_name} - {album_name}".replace('/', '_').replace('\\', '_')[:100] + '.jpg'
                    filepath = os.path.join(temp_dir, filename)
                    
                    # Save with enhanced quality settings
                    wallpaper.save(filepath, 'JPEG', quality=95, optimize=True, progressive=True)
                    saved_files.append({
                        'filename': filename,
                        'filepath': filepath
                    })
                    
                    # Explicitly delete objects and force garbage collection
                    del wallpaper
                    del album_cover
                    gc.collect()
                    
            except Exception as e:
                logger.error(f"Error processing album {album.get('name', 'Unknown')}: {e}")
                continue
        
        return saved_files, temp_dir

    def get_best_album_image(self, album_data):
        """Get the best quality image URL from album data with enhanced prioritization"""
        image_url = None
        best_size = 0
        
        # Enhanced size priority with more options
        size_priority = ['mega', 'extralarge', 'large', 'medium', 'small']
        size_values = {
            'mega': 1200,
            'extralarge': 600, 
            'large': 300,
            'medium': 174,
            'small': 64
        }
        
        # First pass: try to get the largest available size
        for size in size_priority:
            for image in album_data.get('image', []):
                if image.get('size') == size and image.get('#text'):
                    current_size = size_values.get(size, 0)
                    if current_size > best_size:
                        image_url = image['#text']
                        best_size = current_size
                        logger.info(f"Found {size} image ({current_size}px) for {album_data.get('name', 'Unknown')}")
        
        # If no good image found, try any available image
        if not image_url:
            for image in album_data.get('image', []):
                if image.get('#text'):
                    image_url = image['#text']
                    logger.warning(f"Using fallback image for {album_data.get('name', 'Unknown')}")
                    break
        
        return image_url

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
    
    # Limit the maximum number of wallpapers to prevent memory issues
    if limit > 50:
        limit = 50
        logger.warning(f"Limiting wallpaper generation to 50 albums for memory optimization")
    
    try:
        lastfm_generator = LastFMWallpaperGenerator()
        
        # Validate username first
        is_valid, validation_message = lastfm_generator.validate_username(username)
        if not is_valid:
            return jsonify({'error': validation_message}), 400
        
        # Force garbage collection before starting
        gc.collect()
        
        saved_files, temp_dir = lastfm_generator.generate_wallpapers_to_disk(username, period, limit)
        
        if not saved_files:
            return jsonify({'error': 'No wallpapers could be generated. The user might not have enough album data.'}), 400
        
        # Create zip file with compression
        zip_path = os.path.join(temp_dir, f"{username}_wallpapers.zip")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
            for saved_file in saved_files:
                zipf.write(saved_file['filepath'], saved_file['filename'])
                # Remove individual files after adding to zip to save space
                try:
                    os.remove(saved_file['filepath'])
                except:
                    pass
        
        # Force garbage collection after processing
        gc.collect()
        
        return jsonify({
            'success': True,
            'count': len(saved_files),
            'download_url': f'/download/{username}',
            'validation_message': validation_message
        })
        
    except Exception as e:
        logger.error(f"Error generating wallpapers: {str(e)}")
        # Clean up any temporary files on error
        try:
            if 'temp_dir' in locals() and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except:
            pass
        gc.collect()
        return jsonify({'error': f'Error generating wallpapers: {str(e)}'}), 500

def cleanup_old_temp_files():
    """Clean up old temporary files to prevent disk space issues"""
    try:
        import time
        current_time = time.time()
        temp_base = tempfile.gettempdir()
        
        for item in os.listdir(temp_base):
            if item.startswith('tmp'):
                item_path = os.path.join(temp_base, item)
                if os.path.isdir(item_path):
                    # Remove directories older than 1 hour
                    if current_time - os.path.getctime(item_path) > 3600:
                        try:
                            shutil.rmtree(item_path)
                            logger.info(f"Cleaned up old temp directory: {item_path}")
                        except:
                            pass
    except Exception as e:
        logger.error(f"Error cleaning up temp files: {e}")

@app.route('/download/<username>')
def download_wallpapers(username):
    try:
        # Clean up old files first
        cleanup_old_temp_files()
        
        # Find the zip file in temp directory
        temp_dirs = [d for d in os.listdir('/tmp') if d.startswith('tmp')]
        for temp_dir in temp_dirs:
            zip_path = os.path.join('/tmp', temp_dir, f"{username}_wallpapers.zip")
            if os.path.exists(zip_path):
                def remove_file_after_send():
                    try:
                        # Schedule cleanup after file is sent
                        import threading
                        def cleanup():
                            import time
                            time.sleep(30)  # Wait 30 seconds before cleanup
                            try:
                                if os.path.exists(zip_path):
                                    os.remove(zip_path)
                                if os.path.exists(os.path.dirname(zip_path)):
                                    shutil.rmtree(os.path.dirname(zip_path))
                            except:
                                pass
                        threading.Thread(target=cleanup, daemon=True).start()
                    except:
                        pass
                
                remove_file_after_send()
                return send_file(zip_path, as_attachment=True, download_name=f"{username}_wallpapers.zip")
        
        return jsonify({'error': 'Wallpapers not found or expired'}), 404
    except Exception as e:
        logger.error(f"Error downloading wallpapers: {str(e)}")
        return jsonify({'error': f'Error downloading wallpapers: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=PORT)
