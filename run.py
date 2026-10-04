#!/usr/bin/env python3
import os
import sys
import webbrowser
import time

def main():
    print("=" * 60)
    print("🚀 Starting Financial Clarity Web Application Backend...")
    print("=" * 60)

    # Change directory to backend
    backend_dir = os.path.join(os.path.dirname(__file__), "backend")
    sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)

    try:
        import uvicorn
    except ImportError:
        print("Uvicorn is not installed. Please run: pip install -r requirements.txt")
        sys.exit(1)

    url = "http://127.0.0.1:8000"
    print(f"\n🌐 Web app will be accessible at: {url}")
    
    # Open browser automatically after brief delay
    def open_browser():
        time.sleep(1.5)
        webbrowser.open(url)

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    # Start Uvicorn Server
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

if __name__ == "__main__":
    main()
