#!/usr/bin/env python3
"""
KRA Deadline Tracker — Standalone Website Launcher
Start the web dashboard accessible from any device on your network.
"""
import sys
import os
import socket
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

def get_local_ip():
    """Get the local IP address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def main():
    print("\n" + "="*60)
    print("  🛡️  KRA Deadline Tracker — Tax Compliance Dashboard")
    print("="*60)
    print()
    
    local_ip = get_local_ip()
    port = int(os.getenv("HELMET_API_PORT", "8000"))
    
    print(f"  Starting web server...")
    print()
    print(f"  📱 Access from this device:")
    print(f"     http://localhost:{port}")
    print()
    print(f"  📱 Access from other devices (phone/tablet):")
    print(f"     http://{local_ip}:{port}")
    print()
    print(f"  📚 API Documentation:")
    print(f"     http://localhost:{port}/docs")
    print()
    print(f"  Press Ctrl+C to stop the server")
    print("="*60)
    print()
    
    # Start the API server
    import uvicorn
    uvicorn.run(
        "api:app",
        host="0.0.0.0",  # Listen on all network interfaces
        port=port,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()
