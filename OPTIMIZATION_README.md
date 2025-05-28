# Last.fm Wallpaper Generator - Performance Optimizations

## Overview
This document outlines the performance optimizations implemented to make the Last.fm wallpaper generator run efficiently on limited hardware while producing high-quality PNG wallpapers.

## Key Optimizations

### 1. Memory Management
- **Memory Monitoring**: Added `psutil` to monitor memory usage in real-time
- **Memory Threshold**: Processing stops if memory usage exceeds 80%
- **Garbage Collection**: Explicit garbage collection after each image processing
- **Image Size Limits**: Maximum image size capped at 2048x2048 to prevent memory overflow
- **Streaming Downloads**: Images downloaded in 4KB chunks to manage memory usage

### 2. Parallel Processing
- **ThreadPoolExecutor**: Parallel album processing with configurable worker limits
- **Dynamic Worker Count**: Number of workers adjusted based on available memory
- **Memory-Aware Scaling**: Reduces workers on systems with less than 2GB available memory
- **Timeout Protection**: 60-second timeout per album to prevent hanging

### 3. Image Quality & Format
- **PNG Output**: Switched from JPEG to high-quality PNG format
- **PNG Optimization**: Enabled PNG compression (level 6) for smaller file sizes
- **Enhanced Resolution**: Improved high-resolution image URL detection
- **Quality Preservation**: Minimal processing to maintain image quality

### 4. Performance Optimizations
- **Faster Resampling**: Uses BILINEAR instead of LANCZOS for better performance
- **Reduced Enhancement**: Minimal image enhancement to save processing time
- **Immediate Cleanup**: Images deleted from memory immediately after processing
- **Optimized Downloads**: 10MB file size limit and content-length checking

### 5. Resource Management
- **Temporary File Cleanup**: Automatic cleanup of files older than 30 minutes
- **Disk Space Management**: Individual files removed after adding to ZIP
- **Background Cleanup**: Threaded cleanup after file downloads
- **Error Recovery**: Graceful handling of memory and processing errors

## Hardware Requirements

### Minimum Requirements
- **RAM**: 1GB available memory
- **CPU**: Single core (will use 1 worker)
- **Storage**: 500MB temporary space

### Recommended Requirements
- **RAM**: 2GB+ available memory
- **CPU**: 2+ cores (will use multiple workers)
- **Storage**: 1GB+ temporary space

## Performance Metrics

### Memory Usage
- **Low Memory Mode**: Automatically activates with <2GB available
- **Processing Limit**: Maximum 20 wallpapers on low-memory systems
- **Memory Monitoring**: Real-time monitoring with automatic throttling

### Processing Speed
- **Parallel Processing**: Up to 4 concurrent album downloads
- **Optimized I/O**: Streaming downloads and immediate disk writes
- **Reduced Processing**: Minimal image enhancement for faster generation

### File Sizes
- **PNG Quality**: High-quality lossless compression
- **File Size**: Typically 2-5MB per wallpaper (vs 1-3MB JPEG)
- **ZIP Compression**: Level 6 compression for final download

## Usage Examples

### Basic Usage
```python
from lastfm_wallpaper import LastFMWallpaperGenerator

generator = LastFMWallpaperGenerator()
saved_files, temp_dir = generator.generate_wallpapers_to_disk(
    username="your_username",
    period="overall",
    limit=10
)
```

### Memory-Conscious Usage
```python
# For limited hardware, use smaller limits
generator = LastFMWallpaperGenerator()

# Check memory before processing
if generator.check_memory_usage():
    saved_files, temp_dir = generator.generate_wallpapers_to_disk(
        username="your_username",
        limit=5  # Smaller limit for limited hardware
    )
```

## Testing

Run the optimization test script to verify performance:

```bash
cd lastfm-wallpaper-app
python test_optimization.py
```

This will test:
- Memory monitoring functionality
- Optimized image downloads
- PNG wallpaper creation
- Performance metrics display

## Configuration

### Environment Variables
- `LASTFM_API_KEY`: Your Last.fm API key
- `LASTFM_SHARED_SECRET`: Your Last.fm shared secret
- `PORT`: Server port (default: 5000)

### Performance Tuning
- **MAX_WORKERS**: Adjust in code based on your hardware
- **MEMORY_THRESHOLD**: Lower for more conservative memory usage
- **MAX_IMAGE_SIZE**: Reduce for lower memory usage

## Troubleshooting

### High Memory Usage
- Reduce the number of wallpapers generated
- Lower the `MEMORY_THRESHOLD` value
- Ensure adequate swap space is available

### Slow Performance
- Check available CPU cores and memory
- Reduce concurrent workers if system is overloaded
- Use SSD storage for temporary files if possible

### Image Quality Issues
- Verify Last.fm API is returning high-resolution images
- Check network connectivity for image downloads
- Ensure sufficient disk space for temporary files

## Dependencies

```
Flask==3.0.0
Pillow==10.1.0
requests==2.31.0
python-dotenv==1.0.0
numpy==1.24.4
gunicorn==21.2.0
psutil==5.9.6  # Added for memory monitoring
```

## Changelog

### v2.0 - Performance Optimization
- Switched to PNG format for better quality
- Added parallel processing with ThreadPoolExecutor
- Implemented memory monitoring and management
- Optimized image downloads and processing
- Added automatic resource cleanup
- Improved error handling and recovery 