"""Route the three unchanged ForeAgent Chat Completions model names on a private interface."""
import argparse
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import urllib.error
import urllib.request

MODELS = {"DeepSeek-V3.2", "DeepSeek-V3.2-Thinking", "gpt-4o-mini-2024-07-18"}

def route(body):
    model = body["model"]
    if model not in MODELS or body.get("stream"):
        raise ValueError("unsupported request")
    if model.startswith("DeepSeek"):
        enabled = model == "DeepSeek-V3.2-Thinking"
        if body.pop("thinking", None) != ({"type": "enabled"} if enabled else None):
            raise ValueError("unexpected thinking setting")
        body.update(model="deepseek-ai/DeepSeek-V3.2", enable_thinking=enabled)
        return "siliconflow", "https://api.siliconflow.cn/v1/chat/completions"
    return "openai", "https://api.openai.com/v1/chat/completions"

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None

class Gateway(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/v1/chat/completions":
            return self.send_error(404)
        if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer "+self.server.keys["gateway"]):
            return self.send_error(401)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 4194304:
                return self.send_error(413)
            body = json.loads(self.rfile.read(size))
            provider, url = route(body)
        except (KeyError, TypeError, ValueError):
            return self.send_error(400)
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
            "Content-Type": "application/json", "Authorization": "Bearer "+self.server.keys[provider]})
        try:
            try:
                resp = urllib.request.build_opener(NoRedirect).open(req, timeout=600)
            except urllib.error.HTTPError as e:
                resp = e
            with resp:
                data = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except (TimeoutError, OSError):
            self.send_error(502)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", required=True, help="Docker bridge gateway address on the VM")
    parser.add_argument("--keys", type=Path, required=True)
    args = parser.parse_args()
    if args.bind == "0.0.0.0":
        parser.error("use the private bridge address")
    server = ThreadingHTTPServer((args.bind, 18731), Gateway)
    server.keys = {name:(args.keys/(name+".key")).read_text().strip() for name in ["openai","siliconflow","gateway"]}
    if not all(server.keys.values()):
        raise ValueError("missing gateway or provider credentials")
    server.serve_forever()
