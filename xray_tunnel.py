import os
import json
import sys
import platform
import subprocess
import urllib.parse
import urllib.request
import zipfile
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

XRAY_DIR = Path(__file__).parent / "bin"
IS_WINDOWS = platform.system() == "Windows"
XRAY_EXE = XRAY_DIR / ("xray.exe" if IS_WINDOWS else "xray")
XRAY_CONFIG = XRAY_DIR / "xray_config.json"
LOCAL_PROXY_PORT = 10888

def parse_vless_url(vless_url: str) -> dict:
    """Parses a vless:// URL into an Xray outbound configuration dictionary."""
    if not vless_url.startswith("vless://"):
        raise ValueError("Invalid VLESS URL format")
    
    # Strip prefix and split tag
    main_part = vless_url[8:]
    if "#" in main_part:
        main_part, tag = main_part.split("#", 1)
    
    # Extract user_id@host:port
    userInfo_host, query_str = main_part.split("?", 1)
    user_id, host_port = userInfo_host.split("@", 1)
    host, port = host_port.rsplit(":", 1)
    
    params = urllib.parse.parse_qs(query_str)
    
    def get_p(key, default=""):
        return params.get(key, [default])[0]

    network = get_p("type", "tcp")
    security = get_p("security", "none")
    flow = get_p("flow", "")
    if network != "tcp":
        flow = ""
    fp = get_p("fp", "firefox")
    pbk = get_p("pbk", "")
    sid = get_p("sid", "")
    sni = get_p("sni", "")
    path = get_p("path", "/")
    spx = get_p("spx", "")
    mode = get_p("mode", "auto")

    stream_settings = {
        "network": network,
        "security": security
    }

    if security == "reality":
        stream_settings["realitySettings"] = {
            "show": False,
            "fingerprint": fp,
            "serverName": sni,
            "publicKey": pbk,
            "shortId": sid,
            "spiderX": spx
        }

    if network == "xhttp":
        xhttp_cfg = {
            "path": path,
            "mode": mode
        }
        extra_str = get_p("extra", "")
        if extra_str:
            try:
                xhttp_cfg["extra"] = json.loads(extra_str)
            except Exception:
                pass
        stream_settings["xhttpSettings"] = xhttp_cfg
    elif network == "ws":
        stream_settings["wsSettings"] = {
            "path": path
        }

    outbound = {
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": host,
                    "port": int(port),
                    "users": [
                        {
                            "id": user_id,
                            "encryption": "none",
                            "flow": flow
                        }
                    ]
                }
            ]
        },
        "streamSettings": stream_settings
    }
    return outbound

def generate_xray_config(vless_url: str, local_port: int = LOCAL_PROXY_PORT) -> dict:
    outbound = parse_vless_url(vless_url)
    config = {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "port": local_port,
                "listen": "127.0.0.1",
                "protocol": "http",
                "settings": {}
            }
        ],
        "outbounds": [outbound]
    }
    return config

class XrayTunnelManager:
    def __init__(self, vless_url: str, local_port: int = LOCAL_PROXY_PORT):
        self.vless_url = vless_url
        self.local_port = local_port
        self.process: Optional[subprocess.Popen] = None

    def ensure_xray_binary(self) -> bool:
        """Downloads official Xray-core binary for Windows/Linux if missing."""
        if XRAY_EXE.exists():
            return True
            
        XRAY_DIR.mkdir(parents=True, exist_ok=True)
        zip_path = XRAY_DIR / "xray.zip"
        
        if IS_WINDOWS:
            url = "https://github.com/XTLS/Xray-core/releases/download/v25.2.21/Xray-windows-64.zip"
        else:
            url = "https://github.com/XTLS/Xray-core/releases/download/v25.2.21/Xray-linux-64.zip"
            
        logger.info(f"Downloading Xray core binary from {url}...")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as resp, open(zip_path, 'wb') as out_file:
                out_file.write(resp.read())
                
            logger.info("Extracting Xray binary...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(XRAY_DIR)
                
            if zip_path.exists():
                zip_path.unlink()
                
            if not IS_WINDOWS and XRAY_EXE.exists():
                os.chmod(XRAY_EXE, 0o755)
                
            return XRAY_EXE.exists()
        except Exception as e:
            logger.error(f"Failed to download Xray-core binary: {e}")
            return False

    def start(self) -> Optional[str]:
        """Starts background Xray process and returns local proxy URL."""
        if not self.vless_url:
            return None

        if not self.ensure_xray_binary():
            logger.error("Xray binary unavailable. Cannot start VLESS tunnel.")
            return None

        cfg_data = generate_xray_config(self.vless_url, self.local_port)
        with open(XRAY_CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg_data, f, indent=2)

        logger.info(f"Starting embedded Xray VLESS tunnel on 127.0.0.1:{self.local_port}...")
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
            self.process = subprocess.Popen(
                [str(XRAY_EXE), "run", "-c", str(XRAY_CONFIG)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags
            )
            proxy_url = f"http://127.0.0.1:{self.local_port}"
            logger.info(f"VLESS Tunnel Active -> Proxy: {proxy_url}")
            return proxy_url
        except Exception as e:
            logger.error(f"Error starting Xray process: {e}")
            return None

    def stop(self):
        if self.process:
            logger.info("Stopping Xray tunnel process...")
            self.process.terminate()
            self.process = None
