"""
run.py  — start the server directly with: python run.py
"""
import sys
import uvicorn
from app.core.config import get_settings

# Runtime guard: detect NumPy >= 2 which can cause crashes
# when binary extensions (e.g. OpenCV) are built against NumPy 1.x.
try:
    import numpy as _np
    _major = int(str(_np.__version__).split(".")[0])
    if _major >= 2:
        sys.stderr.write(
            "Detected NumPy >= 2. Some compiled modules (cv2, pybind11 extensions) "
            "may be incompatible. Recommend installing `numpy<2` or upgrading the "
            "affected modules (e.g. rebuild with NumPy 2 compatible wheels).")
        sys.stderr.write("\n\nQuick fix: run `pip install 'numpy<2'` and restart.\n")
        sys.exit(1)
except Exception:
    # If numpy import itself fails, continue and let the normal import error surface.
    pass

settings = get_settings()

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
    )
