#!/usr/bin/env python3
"""
Safe startup script for AI Trading Platform
"""
import os
import sys
import time

def check_dependencies():
    """Check if all required dependencies are available"""
    print("🔍 Checking dependencies...")
    
    required_modules = [
        'flask',
        'requests',
        'openai'
    ]
    
    optional_modules = [
        'cryptography'
    ]
    
    missing_required = []
    missing_optional = []
    
    for module in required_modules:
        try:
            __import__(module)
            print(f"  ✓ {module}")
        except ImportError:
            missing_required.append(module)
            print(f"  ✗ {module} (required)")
    
    for module in optional_modules:
        try:
            __import__(module)
            print(f"  ✓ {module}")
        except ImportError:
            missing_optional.append(module)
            print(f"  ⚠ {module} (optional - will use fallback)")
    
    if missing_required:
        print(f"\n❌ Missing required dependencies: {', '.join(missing_required)}")
        print("Please install them with: pip install -r requirements.txt")
        return False
    
    if missing_optional:
        print(f"\n⚠️  Missing optional dependencies: {', '.join(missing_optional)}")
        print("Some features may use fallback implementations.")
    
    print("✅ All required dependencies available!")
    return True

def check_database():
    """Initialize database safely"""
    print("\n🗄️  Initializing database...")
    
    try:
        from database import Database
        
        db = Database()
        db.init_db()
        
        print("✅ Database initialized successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False

def start_application():
    """Start the Flask application with error handling"""
    print("\n🚀 Starting AI Trading Platform...")
    
    try:
        # Set environment variables for better error handling
        os.environ['FLASK_ENV'] = 'production'
        
        # Import and start the app
        from app import app, db, init_trading_engines, auto_trading, trading_loop
        import threading
        
        print("📊 Initializing trading engines...")
        init_trading_engines()
        
        # Start auto-trading if enabled
        if auto_trading:
            print("🤖 Starting auto-trading loop...")
            trading_thread = threading.Thread(target=trading_loop, daemon=True)
            trading_thread.start()
            print("✅ Auto-trading enabled (dynamic intervals per model)")
        else:
            print("⏸️  Auto-trading disabled")
        
        print("🌐 Starting web server...")
        print("\n" + "=" * 60)
        print("🎯 AI Trading Platform Ready!")
        print("📱 Web Interface: http://localhost:5000")
        print("🤖 Auto Trading: " + ("✅ Enabled" if auto_trading else "❌ Disabled"))
        print("🔧 Configuration: Add models via web interface")
        print("📖 Documentation: See README.md and SETUP_GUIDE.md")
        print("=" * 60 + "\n")
        
        # Start Flask app
        app.run(
            debug=False,
            host='0.0.0.0',
            port=5000,
            use_reloader=False,
            threaded=True
        )
        
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down gracefully...")
        sys.exit(0)
        
    except Exception as e:
        print(f"\n❌ Application startup failed: {e}")
        print("\n🔧 Troubleshooting tips:")
        print("1. Check if port 5000 is available")
        print("2. Verify all dependencies are installed")
        print("3. Check database permissions")
        print("4. Review error logs above")
        sys.exit(1)

def main():
    """Main startup function"""
    print("🤖 AI Trading Platform Startup")
    print("=" * 40)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Initialize database
    if not check_database():
        sys.exit(1)
    
    # Start application
    start_application()

if __name__ == "__main__":
    main()