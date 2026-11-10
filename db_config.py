# -*- coding: utf-8 -*-
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "123456",
    "database": "ev_management",
    "charset": "utf8mb4",
}

DATA_DIR = os.path.join(BASE_DIR, "Data")
