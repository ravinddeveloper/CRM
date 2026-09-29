"""
URLs proxy: forwards to root project config.urls.
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.urls import *  # noqa: F401, F403
from config.urls import urlpatterns  # noqa: F401
