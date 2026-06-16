#!/usr/bin/env python3
"""
SkinBB Backend Server
Starts the main SkinBB application with Face Analysis integrated
"""

import os
import sys
import subprocess
from pathlib import Path

# Limit BLAS/OpenMP threads before numpy/scipy/torch load (avoids OpenBLAS OOM with --reload)
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

def main():
    """Start the SkinBB backend server"""
    
    # Check if we're in the correct directory
    project_root = Path(__file__).parent
    if not (project_root / "app" / "main.py").exists():
        print("❌ Error: Please run this script from the project root directory")
        sys.exit(1)
    
    print("🚀 Starting SkinBB Backend Server...")
    print("📡 Features: Chatbot, Face Analysis, Formulation Looker")
    print("🎯 Server: http://localhost:8000/")
    print("📚 API Docs: http://localhost:8000/docs")
    print("🛑 Press Ctrl+C to stop the server")
    print("------------------------------------------------------------")
    
    try:
        # Start the server
        subprocess.run([
            sys.executable, "-m", "uvicorn", 
            "app.main:app", 
            "--host", "0.0.0.0", 
            "--port", "8000", 
            "--reload"
        ], check=True)
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
