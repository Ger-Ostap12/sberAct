# -*- coding: utf-8 -*-
"""Общая настройка pytest: добавляет app/ в sys.path для импорта модулей backend."""
import os
import sys

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
