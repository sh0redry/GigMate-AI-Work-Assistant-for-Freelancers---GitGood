"""Browser-level CSP check with synthetic audio and sandboxed blob navigation.

This checks CSP delivery, not a platform's native PDF viewer or a real attachment.
"""

import argparse
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import wave


def check(browser):
    root = Path(__file__).resolve().parents[1]
    policy = subprocess.check_output(
        [
            "node",
            "-e",
            "process.stdout.write(require('./apps/desktop/web-security.cjs').CSP)",
        ],
        cwd=root,
        text=True,
    )
    audio_bytes = io.BytesIO()
    with wave.open(audio_bytes, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 800)
    script = """
const result={audio:false,frame:false,violations:[]};
const show=()=>document.querySelector('#result').textContent=JSON.stringify(result);
document.addEventListener('securitypolicyviolation',e=>{result.violations.push(e.effectiveDirective);show();});
const audio=document.createElement('audio');
audio.onloadedmetadata=()=>{result.audio=audio.duration>0;show();};
audio.src=URL.createObjectURL(new Blob([Uint8Array.from(atob('AUDIO_BASE64'),c=>c.charCodeAt(0))],{type:'audio/wav'}));
document.body.append(audio);audio.load();
const frame=document.createElement('iframe');frame.sandbox='';
frame.onload=()=>{result.frame=true;show();};
frame.src=URL.createObjectURL(new Blob(['synthetic attachment navigation'],{type:'text/html'}));
document.body.append(frame);
""".replace("AUDIO_BASE64", base64.b64encode(audio_bytes.getvalue()).decode())

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            is_script = self.path == "/test.js"
            self.send_response(200)
            self.send_header(
                "Content-Type", "application/javascript" if is_script else "text/html"
            )
            self.send_header("Content-Security-Policy", policy)
            self.end_headers()
            self.wfile.write(
                script.encode()
                if is_script
                else b'<html><body><pre id="result">{}</pre><script src="/test.js"></script></body></html>'
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(
            prefix="gigmate-desktop-preview-", ignore_cleanup_errors=True
        ) as profile:
            assert (
                Path(profile)
                .resolve()
                .is_relative_to(Path(tempfile.gettempdir()).resolve())
            )
            result = subprocess.run(
                [
                    browser,
                    "--headless",
                    "--disable-gpu",
                    "--no-first-run",
                    "--disable-extensions",
                    "--user-data-dir=" + profile,
                    "--virtual-time-budget=3000",
                    "--dump-dom",
                    f"http://127.0.0.1:{server.server_port}/",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=True,
            )
            found = re.search(r'<pre id="result">(.*?)</pre>', result.stdout)
            value = json.loads(found.group(1)) if found else {}
            if value != {"audio": True, "frame": True, "violations": []}:
                raise RuntimeError("DESKTOP_PREVIEW_CSP_FAILED: " + json.dumps(value))
            print(json.dumps(value))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", required=True, help="Chromium/Edge executable")
    check(parser.parse_args().browser)
