import os
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import numpy as np
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv
import io
import zipfile
from urllib.parse import urlparse
import tempfile
import shutil
import logging
import gc  # Add garbage collection
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import psutil  # For memory monitoring

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Get port from environment variable for deployment
PORT = int(os.environ.get('PORT', 5001))

# Performance optimization constants
MAX_WORKERS = min(4, (os.cpu_count() or 1) + 1)  # Limit concurrent downloads
MEMORY_THRESHOLD = 80  # Stop processing if memory usage exceeds 80%
MAX_IMAGE_SIZE = (2048, 2048)  # Limit maximum image size to save memory

# Global error handlers
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(405)
def method_not_allowed_error(error):
    return jsonify({'error': 'Method not allowed'}), 405

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error occurred'}), 500

@app.errorhandler(Exception)
def handle_exception(error):
    logger.error(f"Unhandled exception: {error}")
    return jsonify({'error': f'An unexpected error occurred: {str(error)}'}), 500

class LastFMWallpaperGenerator:
    def __init__(self):
        self.api_key = os.getenv('LASTFM_API_KEY')
        self.shared_secret = os.getenv('LASTFM_SHARED_SECRET')
        self.base_url = "http://ws.audioscrobbler.com/2.0/"
        
        if not self.api_key:
            raise ValueError("LASTFM_API_KEY environment variable is required")
        if not self.shared_secret:
            raise ValueError("LASTFM_SHARED_SECRET environment variable is required")
    
    def check_memory_usage(self):
        """Check current memory usage and return True if it's safe to continue"""
        try:
            memory_percent = psutil.virtual_memory().percent
            if memory_percent > MEMORY_THRESHOLD:
                logger.warning(f"Memory usage high: {memory_percent}%")
                gc.collect()  # Force garbage collection
                return False
            return True
        except:
            return True  # If psutil fails, assume it's safe to continue
        
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
            response = requests.get(self.base_url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            if 'topalbums' in data and 'album' in data['topalbums']:
                return data['topalbums']['album']
            else:
                return []
        except Exception as e:
            logger.error(f"Error fetching albums for user {username}: {e}")
            return []
    
    def download_image_optimized(self, url):
        """Optimized image download with memory management and quality handling"""
        try:
            # Check memory before downloading
            if not self.check_memory_usage():
                logger.warning("Skipping download due to high memory usage")
                return None
            
            # Try high-resolution URLs first
            high_res_urls = self._get_high_res_urls(url)
            
            for attempt_url in high_res_urls:
                try:
                    # Use streaming download with smaller chunks for memory efficiency
                    response = requests.get(attempt_url, timeout=10, stream=True)
                    response.raise_for_status()
                    
                    # Check content length to avoid downloading huge files
                    content_length = response.headers.get('content-length')
                    if content_length and int(content_length) > 10 * 1024 * 1024:  # 10MB limit
                        logger.warning(f"Image too large: {content_length} bytes")
                        continue
                    
                    # Download in chunks to manage memory
                    image_data = io.BytesIO()
                    total_size = 0
                    for chunk in response.iter_content(chunk_size=4096):
                        total_size += len(chunk)
                        if total_size > 10 * 1024 * 1024:  # 10MB limit
                            break
                        image_data.write(chunk)
                    
                    image_data.seek(0)
                    
                    # Load and immediately optimize image
                    image = Image.open(image_data)
                    
                    # Limit image size to prevent memory issues
                    if image.size[0] > MAX_IMAGE_SIZE[0] or image.size[1] > MAX_IMAGE_SIZE[1]:
                        image.thumbnail(MAX_IMAGE_SIZE, Image.Resampling.LANCZOS)
                    
                    # Convert to RGB immediately
                    if image.mode != 'RGB':
                        image = image.convert('RGB')
                    
                    logger.info(f"Downloaded optimized image: {image.size}")
                    return image
                    
                except Exception as e:
                    logger.debug(f"Failed to download from {attempt_url}: {e}")
                    continue
            
            logger.error(f"All download attempts failed")
            return None
                
        except Exception as e:
            logger.error(f"Error in download_image_optimized: {e}")
            return None
    
    def _get_high_res_urls(self, url):
        """Generate high-resolution URL variants"""
        high_res_urls = []
        
        # Pattern 1: Replace size indicators with larger ones
        high_res_urls.append(url.replace('/300x300/', '/1200x1200/').replace('300x300', '1200x1200'))
        high_res_urls.append(url.replace('/300x300/', '/800x800/').replace('300x300', '800x800'))
        
        # Pattern 2: Replace small size indicators
        high_res_urls.append(url.replace('174s', '800x800').replace('64s', '800x800'))
        
        # Pattern 3: Last.fm specific patterns
        if 'lastfm' in url:
            high_res_urls.append(url.replace('/i/u/300x300/', '/i/u/ar0/').replace('/i/u/174s/', '/i/u/ar0/'))
            high_res_urls.append(url.replace('/i/u/300x300/', '/i/u/770x0/').replace('/i/u/174s/', '/i/u/770x0/'))
        
        # Remove duplicates and add original as fallback
        seen = set()
        unique_urls = []
        for url_attempt in high_res_urls:
            if url_attempt not in seen and url_attempt != url:
                seen.add(url_attempt)
                unique_urls.append(url_attempt)
        unique_urls.append(url)
        
        return unique_urls
    
    def enhance_image_minimal(self, image):
        """Minimal image enhancement to reduce processing overhead"""
        try:
            # Only apply essential enhancements to save processing time
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(1.1)  # Reduced sharpness enhancement
            return image
        except Exception as e:
            logger.warning(f"Failed to enhance image: {e}")
            return image

    def create_wallpaper_optimized(self, album_cover, album_name, artist_name, wallpaper_size=(1920, 1080)):
        """Create wallpaper with album cover filling the entire screen - NO BORDERS"""
        if not album_cover:
            return None
        
        try:
            wallpaper_width, wallpaper_height = wallpaper_size
            
            # Minimal enhancement to save processing time
            album_cover = self.enhance_image_minimal(album_cover)
            
            # Resize album cover to fill the ENTIRE 1920x1080 screen - NO BORDERS
            album_cover = album_cover.resize((wallpaper_width, wallpaper_height), Image.Resampling.LANCZOS)
            
            # Return the resized album cover as the wallpaper (no black canvas needed)
            return album_cover
            
        except Exception as e:
            logger.error(f"Error creating wallpaper for {artist_name} - {album_name}: {e}")
            return None
    
    def process_single_album(self, album_data, temp_dir, index, total):
        """Process a single album - designed for parallel execution"""
        try:
            # Check memory before processing
            if not self.check_memory_usage():
                logger.warning(f"Skipping album {index+1}/{total} due to memory constraints")
                return None
            
            album_name = album_data['name']
            artist_name = album_data['artist']['name']
            
            logger.info(f"Processing {index+1}/{total}: {artist_name} - {album_name}")
            
            # Get image URL
            image_url = self.get_best_album_image(album_data)
            if not image_url:
                logger.warning(f"No image found for {album_name} by {artist_name}")
                return None
            
            # Download album cover
            album_cover = self.download_image_optimized(image_url)
            if not album_cover:
                return None
            
            # Create wallpaper
            wallpaper = self.create_wallpaper_optimized(album_cover, album_name, artist_name)
            if not wallpaper:
                return None
            
            # Save as high-quality PNG
            filename = f"{artist_name} - {album_name}".replace('/', '_').replace('\\', '_')[:100] + '.png'
            filepath = os.path.join(temp_dir, filename)
            
            # Save with PNG optimization
            wallpaper.save(filepath, 'PNG', optimize=True, compress_level=6)
            
            # Clean up memory immediately
            del wallpaper
            del album_cover
            gc.collect()
            
            return {
                'filename': filename,
                'filepath': filepath
            }
            
        except Exception as e:
            logger.error(f"Error processing album {album_data.get('name', 'Unknown')}: {e}")
            return None

    def generate_wallpapers_to_disk(self, username, period="overall", limit=10, temp_dir=None):
        """Generate wallpapers with parallel processing and memory optimization"""
        albums = self.get_user_top_albums(username, period, limit)
        if not albums:
            return [], None
            
        if not temp_dir:
            temp_dir = tempfile.mkdtemp()
        
        # Limit concurrent processing based on available memory
        available_memory_gb = psutil.virtual_memory().available / (1024**3)
        max_workers = min(MAX_WORKERS, max(1, int(available_memory_gb)))
        
        logger.info(f"Processing {len(albums)} albums with {max_workers} workers")
        
        saved_files = []
        
        # Process albums in parallel with limited workers
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_album = {
                executor.submit(self.process_single_album, album, temp_dir, i, len(albums)): album 
                for i, album in enumerate(albums)
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_album):
                try:
                    result = future.result(timeout=60)  # 60 second timeout per album
                    if result:
                        saved_files.append(result)
                except Exception as e:
                    album = future_to_album[future]
                    logger.error(f"Error processing album {album.get('name', 'Unknown')}: {e}")
                
                # Force garbage collection after each completion
                gc.collect()
        
        return saved_files, temp_dir

    def get_best_album_image(self, album_data):
        """Get the best quality image URL from album data"""
        image_url = None
        best_size = 0
        
        # Size priority for better quality
        size_priority = ['mega', 'extralarge', 'large', 'medium', 'small']
        size_values = {
            'mega': 1200,
            'extralarge': 600, 
            'large': 300,
            'medium': 174,
            'small': 64
        }
        
        # Get the largest available size
        for size in size_priority:
            for image in album_data.get('image', []):
                if image.get('size') == size and image.get('#text'):
                    current_size = size_values.get(size, 0)
                    if current_size > best_size:
                        image_url = image['#text']
                        best_size = current_size
        
        # Fallback to any available image
        if not image_url:
            for image in album_data.get('image', []):
                if image.get('#text'):
                    image_url = image['#text']
                    break
        
        return image_url

# Initialize the generator
lastfm_generator = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Test if we can create a generator instance
        generator = LastFMWallpaperGenerator()
        return jsonify({
            'status': 'healthy',
            'message': 'Server is running and API credentials are configured',
            'timestamp': time.time()
        })
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'message': f'Server error: {str(e)}',
            'timestamp': time.time()
        }), 500

@app.route('/validate', methods=['POST'])
def validate_user():
    """Validate Last.fm username"""
    try:
        # Ensure we have JSON data
        if not request.is_json:
            return jsonify({'valid': False, 'message': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({'valid': False, 'message': 'No JSON data provided'}), 400
        
        username = data.get('username', '').strip()
        
        if not username:
            return jsonify({'valid': False, 'message': 'Username is required'}), 400
        
        generator = LastFMWallpaperGenerator()
        is_valid, message = generator.validate_username(username)
        
        return jsonify({
            'valid': is_valid,
            'message': message
        })
    
    except Exception as e:
        logger.error(f"Error in validate_user: {str(e)}")
        return jsonify({'valid': False, 'message': f'Validation error: {str(e)}'}), 500

@app.route('/generate', methods=['POST'])
def generate_wallpapers():
    global lastfm_generator
    
    try:
        # Ensure we have JSON data
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        username = data.get('username', '').strip()
        period = data.get('period', 'overall')
        
        # Safely convert limit to int
        try:
            limit = int(data.get('limit', 10))
        except (ValueError, TypeError):
            limit = 10
        
        if not username:
            return jsonify({'error': 'Username is required'}), 400
        
        # Adjust limit based on available memory
        available_memory_gb = psutil.virtual_memory().available / (1024**3)
        if available_memory_gb < 2:  # Less than 2GB available
            limit = min(limit, 20)
            logger.warning(f"Limited to 20 wallpapers due to low memory")
        elif limit > 50:
            limit = 50
            logger.warning(f"Limited to 50 wallpapers for performance")
        
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
            
            # Create zip file with optimal compression for PNGs
            zip_path = os.path.join(temp_dir, f"{username}_wallpapers.zip")
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
                for saved_file in saved_files:
                    zipf.write(saved_file['filepath'], saved_file['filename'])
                    # Remove individual files after adding to zip
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
                if 'temp_dir' in locals() and temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            except:
                pass
            gc.collect()
            return jsonify({'error': f'Error generating wallpapers: {str(e)}'}), 500
            
    except Exception as e:
        logger.error(f"Error in generate_wallpapers: {str(e)}")
        return jsonify({'error': f'Request processing error: {str(e)}'}), 500

def cleanup_old_temp_files():
    """Clean up old temporary files to prevent disk space issues"""
    try:
        current_time = time.time()
        temp_base = tempfile.gettempdir()
        
        for item in os.listdir(temp_base):
            if item.startswith('tmp'):
                item_path = os.path.join(temp_base, item)
                if os.path.isdir(item_path):
                    # Remove directories older than 30 minutes
                    if current_time - os.path.getctime(item_path) > 1800:
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
                        def cleanup():
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
