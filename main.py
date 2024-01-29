import mimetypes
import urllib.parse
import json
import logging
import socket
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from jinja2 import Environment, FileSystemLoader
from datetime import datetime

BASE_DIR = Path()
BUFFER_SIZE = 1024
HTTP_PORT = 3000
HTTP_HOST = "0.0.0.0"
SOCKET_HOST = "127.0.0.1"
SOCKET_PORT = 5000

jinja = Environment(loader=FileSystemLoader("templates"))

storage_dir = BASE_DIR / "storage"
if not storage_dir.exists():
    storage_dir.mkdir()

data_file_path = BASE_DIR / "storage" / "data.json"
if not data_file_path.exists():
    data_file_path.touch()


class GoItFramework(BaseHTTPRequestHandler):

    def do_GET(self):
        route = urllib.parse.urlparse(self.path)
        match route.path:
            case "/":
                self.send_html("index.html")
            case "/message":
                self.send_html("message.html")
            case _:
                file = BASE_DIR.joinpath(route.path[1:])
                if file.exists():
                    self.send_static(file)
                else:
                    self.send_html("error.html", 404)

    def do_POST(self):
        size = self.headers.get("Content-Length")
        data = self.rfile.read(int(size))

        client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client_socket.sendto(data, (SOCKET_HOST, SOCKET_PORT))
        client_socket.close()

        self.send_response(302)
        self.send_header("Location", "/message")
        self.end_headers()

    def send_html(self, filename, status_code=200):
        self.send_response(status_code)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        with open(filename, "rb") as file:
            self.wfile.write(file.read())

    def render_template(self, filename, status_code=200):
        self.send_response(status_code)
        self.send_header("Content-type", "text/html")
        self.end_headers()

        try:
            template = jinja.get_template(filename)
            with open(data_file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            html = template.render(blogs=data)
            self.wfile.write(html.encode("utf-8"))
        except json.decoder.JSONDecodeError:
            data = {}
            template = jinja.get_template(filename)
            html = template.render(blogs=data)
            self.wfile.write(html.encode("utf-8"))
        except jinja2.exceptions.TemplateNotFound:
            logging.error(f"Template not found: {filename}")

    def send_static(self, filename, status_code=200):
        self.send_response(status_code)
        mime_type, *_ = mimetypes.guess_type(filename)
        if mime_type:
            self.send_header("Content-type", mime_type)
        else:
            self.send_header("Content-type", "text/plain")
        self.end_headers()
        with open(filename, "rb") as file:
            self.wfile.write(file.read())


def save_data_from_form(data):
    try:
        parse_data = urllib.parse.unquote_plus(data.decode())
        parse_dict = {key: value for key, value in [el.split("=") for el in parse_data.split("&")]}

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        entry = {timestamp: parse_dict}

        if not data_file_path.exists() or data_file_path.stat().st_size == 0:
           with open(data_file_path, "w", encoding="utf-8") as file:
                json.dump({}, file)

        with open(data_file_path, "r", encoding="utf-8") as file:
            existing_data = json.load(file)

        existing_data.update(entry)

        with open(data_file_path, "w", encoding="utf-8") as file:
            json.dump(existing_data, file, ensure_ascii=False, indent=4)
    except ValueError as err:
        logging.error(f'Error processing form data: {err}')
    except OSError as err:
        logging.error(f'Error input/output data to file: {err}')
    except Exception as err:
        logging.error(f'Unexpected error: {err}')


def run_socket_server(host, port):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((host, port))
    logging.info(f"Socket server started on {host}:{port}")
    try:
        while True:
            msg, address = server_socket.recvfrom(BUFFER_SIZE)
            logging.info(f"Received message from {address}: {msg}")
            save_data_from_form(msg)
    except KeyboardInterrupt:
        pass
    finally:
        server_socket.close()


def run_http_server(host, port):
    address = (host, port)
    http_server = HTTPServer(address, GoItFramework)
    logging.info(f"HTTP server started on {host}:{port}")
    try:
        http_server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        http_server.server_close()


if __name__ == "__main__":
    logging.basicConfig(filename="server_logs.log", level=logging.DEBUG, format="%(threadName)s %(message)s",)
    server = Thread(target=run_http_server, args=(HTTP_HOST, HTTP_PORT))
    server.start()
    server_socket = Thread(target=run_socket_server, args=(SOCKET_HOST, SOCKET_PORT))
    server_socket.start()
