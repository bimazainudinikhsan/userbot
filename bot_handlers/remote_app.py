# bmcodexbot/bot_handlers/remote_app.py

# File ini sekarang berfungsi sebagai penghubung (bridge).
# Logika utama telah dipindahkan ke folder 'bot_handlers/remote/' 
# agar kode lebih rapi dan terbagi menjadi beberapa bagian.

from .remote.menu import *
from .remote.apps import *
from .remote.devices import *