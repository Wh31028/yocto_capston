from fastapi import FastAPI, Request, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import os
import subprocess
import asyncio
import sys
import socket
import struct
import time

app = FastAPI()

active_connections = []

async def can_sniffer_task():
    try:
        s = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        s.bind(('can0',))
        s.setblocking(False)
    except Exception as e:
        print(f"CAN Sniffer init failed: {e}")
        return

    loop = asyncio.get_event_loop()
    batch = []
    last_send = time.time()
    frames_processed = 0
    total_pps_counter = 0
    
    while True:
        try:
            frame = await loop.sock_recv(s, 16)
            if len(frame) == 16:
                total_pps_counter += 1
                frames_processed += 1
                
                # Only stringify max 50 frames per batch to save BBB CPU
                if len(batch) < 50:
                    can_id, can_dlc, data = struct.unpack("<IB3x8s", frame)
                    can_id &= 0x1FFFFFFF # remove EFF/RTR/ERR flags
                    data_hex = " ".join(f"{b:02X}" for b in data[:can_dlc])
                    
                    batch.append({
                        "id": f"0x{can_id:03X}",
                        "dlc": can_dlc,
                        "data": data_hex
                    })
                
                now = time.time()
                # Send batch every 200ms (5 FPS)
                if (now - last_send) >= 0.2:
                    if active_connections:
                        msg = {"type": "can_frames", "frames": batch, "count": total_pps_counter}
                        for conn in active_connections:
                            try:
                                await conn.send_json(msg)
                            except:
                                pass
                    batch = []
                    total_pps_counter = 0
                    last_send = now
                
                # Force yield every 50 frames so we don't starve the web server!
                if frames_processed % 50 == 0:
                    await asyncio.sleep(0)
                    
        except BlockingIOError:
            await asyncio.sleep(0.01)
        except Exception as e:
            await asyncio.sleep(1)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(can_sniffer_task())

# Setup templates directory
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_dir)

# Absolute paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FIRMWARE_SAVE_PATH = os.path.join(BASE_DIR, "received_fw.bin")

@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/upload")
async def upload_firmware(file: UploadFile = File(...)):
    try:
        content = await file.read()
        with open(FIRMWARE_SAVE_PATH, "wb") as f:
            f.write(content)
        return {"status": "success", "filename": file.filename, "size": len(content)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    process = None
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            
            if action == "start_update":
                protocol = data.get("protocol", "custom")
                board = data.get("board", "f407")
                bitrate = data.get("bitrate", "1000000")
                
                await websocket.send_json({"type": "status", "data": "UPDATING"})
                
                # 1. Configure CAN Interface Bitrate
                await websocket.send_json({"type": "log", "data": f"Configuring CAN interface to {int(bitrate)//1000} kbps..."})
                try:
                    proc_down = await asyncio.create_subprocess_shell("sudo ip link set can0 down")
                    await proc_down.wait()
                    proc_up = await asyncio.create_subprocess_shell(f"sudo ip link set can0 up type can bitrate {bitrate}")
                    await proc_up.wait()
                    
                    if proc_up.returncode == 0:
                        await websocket.send_json({"type": "log", "data": "CAN interface configured successfully."})
                    else:
                        await websocket.send_json({"type": "log", "data": "[Warning] CAN config failed (check sudo privileges). Using existing settings."})
                except Exception as e:
                    await websocket.send_json({"type": "log", "data": f"[Error] CAN config exception: {e}"})

                # 2. Determine target Python script
                script_name = f"{protocol}_lte_gateway.py"
                if board == "f103":
                    script_name = f"{protocol}_lte_gateway_f103.py"
                    
                script_path = os.path.join(BASE_DIR, script_name)
                
                if not os.path.exists(script_path):
                    await websocket.send_json({"type": "log", "data": f"[Error] Script {script_name} not found."})
                    continue

                await websocket.send_json({"type": "log", "data": f"Starting {protocol.upper()} FOTA update on {board.upper()}..."})
                
                # Using sys.executable to run with current python, passing FIRMWARE_SAVE_PATH
                process = await asyncio.create_subprocess_exec(
                    sys.executable, script_path, FIRMWARE_SAVE_PATH,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=BASE_DIR
                )
                
                # Stream logs unbuffered
                import re
                buffer = ""
                while True:
                    chunk = await process.stdout.read(1024)
                    if not chunk:
                        if buffer.strip():
                            decoded_line = buffer.strip()
                            if "진행률:" in decoded_line or "Progress:" in decoded_line:
                                await websocket.send_json({"type": "progress_update", "data": decoded_line})
                            else:
                                await websocket.send_json({"type": "log", "data": decoded_line})
                        break
                    
                    buffer += chunk.decode('utf-8', errors='ignore')
                    parts = re.split(r'[\r\n]', buffer)
                    buffer = parts.pop()
                    
                    for part in parts:
                        decoded_line = part.strip()
                        if decoded_line:
                            # If it's a progress update, only update the circular bar (avoids terminal spam)
                            if "진행률:" in decoded_line or "Progress:" in decoded_line:
                                await websocket.send_json({"type": "progress_update", "data": decoded_line})
                            else:
                                await websocket.send_json({"type": "log", "data": decoded_line})
                
                await process.wait()
                if process.returncode == 0:
                    await websocket.send_json({"type": "log", "data": "Update completed successfully."})
                    await websocket.send_json({"type": "status", "data": "COMPLETED"})
                else:
                    await websocket.send_json({"type": "log", "data": f"Update failed with return code {process.returncode}."})
                    await websocket.send_json({"type": "status", "data": "FAILED"})
                    
            elif action == "stop_update":
                if process and process.returncode is None:
                    process.terminate()
                    await websocket.send_json({"type": "log", "data": "Update forcefully stopped."})
                    await websocket.send_json({"type": "status", "data": "STOPPED"})

    except WebSocketDisconnect:
        active_connections.remove(websocket)
        if process and process.returncode is None:
            process.terminate()
        print("Client disconnected")
