import http.server
import socketserver
import os
import cgi

PORT = 8000

class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        # 파일 업로드 처리
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={'REQUEST_METHOD': 'POST'}
        )
        
        if "file" in form:
            file_item = form["file"]
            filename = os.path.basename(file_item.filename)
            with open(filename, 'wb') as f:
                f.write(file_item.file.read())
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write(f"Success! {filename} uploaded to Mac.\n".encode())
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Failed: No file found in request.\n")

with socketserver.TCPServer(("", PORT), CustomHTTPRequestHandler) as httpd:
    print(f"Upload server running on port {PORT}...")
    httpd.serve_forever()
