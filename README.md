# ⸸ Last.fm Wallpaper Generator ⸸

A dark, occult-themed web application that transforms your Last.fm listening history into stunning desktop wallpapers. Generate high-quality wallpapers from your favorite album covers with a black metal aesthetic.

## ✦ Features ✦

- **Real-time Username Validation**: Instant feedback on Last.fm username validity
- **High-Quality Wallpapers**: Letterboxing approach preserves image quality without scaling artifacts
- **Batch Generation**: Create up to 100 wallpapers at once
- **Dark Occult Theme**: Black metal aesthetic with occult symbols and animations
- **ZIP Download**: Get all your wallpapers in a convenient ZIP file
- **Production Ready**: Configured for deployment on free hosting platforms

## ⸸ Setup Instructions ⸸

### 1. Get Last.fm API Credentials

1. Visit [Last.fm API Account Creation](https://www.last.fm/api/account/create)
2. Create an account or log in
3. Create a new API application
4. Note down your **API Key** and **Shared Secret**

### 2. Environment Configuration

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your Last.fm credentials:
   ```bash
   # Last.fm API Configuration
   LASTFM_API_KEY=your_actual_api_key_here
   LASTFM_SHARED_SECRET=your_actual_shared_secret_here
   
   # Flask Configuration
   FLASK_ENV=production
   ```

### 3. Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python lastfm_wallpaper.py
```

Visit `http://localhost:5000` to use the application.

## 🔥 Deployment 🔥

This application is ready for deployment on free hosting platforms:

### Railway (Recommended)
1. Fork this repository
2. Connect to [Railway](https://railway.app)
3. Add environment variables in Railway dashboard:
   - `LASTFM_API_KEY`
   - `LASTFM_SHARED_SECRET`
4. Deploy automatically

### Heroku
```bash
# Install Heroku CLI and login
heroku create your-app-name
heroku config:set LASTFM_API_KEY=your_api_key
heroku config:set LASTFM_SHARED_SECRET=your_shared_secret
git push heroku master
```

### Render
1. Connect your GitHub repository
2. Set environment variables in Render dashboard
3. Deploy with automatic builds

## ⛧ Usage ⛧

1. Enter your Last.fm username
2. Select time period (overall, 7day, 1month, etc.)
3. Choose number of albums (5-100)
4. Click "BEGIN THE RITUAL" to generate wallpapers
5. Download your dark treasures as a ZIP file

## 🖤 Technical Details 🖤

- **Backend**: Flask with PIL/Pillow for image processing
- **Image Quality**: Letterboxing approach preserves original quality
- **Wallpaper Size**: 1920x1080 (Full HD)
- **Format**: High-quality JPEG (100% quality)
- **Security**: Environment variables for API credentials

## ☠ Requirements ☠

- Python 3.8+
- Last.fm API credentials
- Internet connection for album art downloads

## 🔮 Contributing 🔮

Feel free to submit issues and enhancement requests. This project embraces the dark aesthetic while maintaining clean, secure code.

---

*"In darkness, we find beauty. In music, we find wallpapers."* ⸸ 