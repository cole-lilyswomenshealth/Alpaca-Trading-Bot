#!/usr/bin/env python3
"""
Simple HTTP server to serve the daily performance dashboard
Run this alongside the Flask server
"""
import http.server
import socketserver
import os

PORT = 8080
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

print(f"Starting dashboard server on http://localhost:{PORT}")
print(f"Daily Performance Dashboard: http://localhost:{PORT}/daily-performance.html")
print("Press Ctrl+C to stop")

with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
    httpd.serve_forever()
