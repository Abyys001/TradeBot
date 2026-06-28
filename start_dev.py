"""Start backend (WSGI) and frontend (Vite) dev servers.

Usage: python start_dev.py

NOTE: We DO NOT use "manage.py runserver" because Daphne overrides the
runserver command (even when not in INSTALLED_APPS) and Daphne has
issues with POST request bodies under Python 3.14.

Instead we run Django's WSGI application directly via wsgiref.
"""
import os
import subprocess
import sys
import time
import socket
import threading
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn

BASE = os.path.dirname(os.path.abspath(__file__))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.dev_sqlite'

sys.path.insert(0, BASE)

import django
django.setup()
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()


class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    allow_reuse_address = True


def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def serve_backend():
    if port_in_use(8000):
        print(f'[Backend] Port 8000 already in use — skipping')
        return
    httpd = make_server('0.0.0.0', 8000, application, server_class=ThreadedWSGIServer)
    print(f'[Backend] WSGI on http://0.0.0.0:8000')
    httpd.serve_forever()


def serve_frontend():
    if port_in_use(8080):
        print(f'[Frontend] Port 8080 already in use — skipping')
        return
    vite_script = os.path.join(BASE, 'frontend', 'node_modules', 'vite', 'bin', 'vite.js')
    subprocess.run(['node', vite_script], check=False, cwd=os.path.join(BASE, 'frontend'))


t = threading.Thread(target=serve_backend, daemon=True)
t.start()
time.sleep(1.5)

print(f'\n  Backend  → http://localhost:8000/api/auth/csrf/')
print(f'  Frontend → http://localhost:8080/login')
print(f'  Ctrl+C to stop\n')

try:
    serve_frontend()
except KeyboardInterrupt:
    pass
print('Stopped.')
