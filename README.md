# 🎥 Smart Surveillance Backend

Production-ready FastAPI backend for an AI-powered home surveillance system.

---

## Tech Stack

| Layer | Library |
|---|---|
| API framework | FastAPI + Uvicorn |
| AI detection | Ultralytics YOLOv8 Nano |
| Face recognition | face_recognition (dlib) |
| Video capture | OpenCV |
| Database | SQLite via aiosqlite |
| Realtime push | WebSocket |
| Notifications | Twilio WhatsApp / SMS |
| Auth | JWT (python-jose) + bcrypt |

---

## Project Structure

```
surveillance/
├── app/
│   ├── main.py                          # App factory + lifespan hooks
│   ├── core/
│   │   ├── config.py                    # Settings (env vars)
│   │   └── security.py                 # JWT + bcrypt
│   ├── db/
│   │   └── database.py                 # SQLite init + get_db dependency
│   ├── models/
│   │   └── schemas.py                  # All Pydantic schemas
│   ├── services/
│   │   ├── camera_gateway.py           # Camera/stream management
│   │   ├── ai_pipeline.py              # YOLOv8 detection workers
│   │   ├── face_engine.py              # Face registration + matching
│   │   ├── loitering_engine.py         # Dwell-time tracker
│   │   ├── scoring.py                  # Suspicion score calculator
│   │   ├── notification.py             # WebSocket + Twilio dispatch
│   │   ├── websocket_manager.py        # WS connection pool
│   │   └── surveillance_orchestrator.py # Ties all services together
│   └── api/
│       ├── deps.py                     # Shared FastAPI dependencies
│       └── routes/
│           ├── auth.py                 # POST /auth/login
│           ├── camera.py               # Camera connect, video upload, stream
│           ├── roi.py                  # ROI CRUD
│           ├── faces.py                # Face registration
│           ├── alerts.py               # Alerts + history
│           ├── settings_route.py       # App settings
│           └── websocket_route.py      # WS /ws/alerts
├── scripts/
│   ├── roi_editor.html                 # Visual ROI editor (browser)
│   └── alert_monitor.html             # Live WS alert viewer (browser)
├── storage/
│   ├── uploads/                        # Uploaded MP4s
│   ├── snapshots/                      # Alert JPEG snapshots
│   ├── clips/                          # Video clips (reserved)
│   └── faces/                          # Registered face images
├── run.py                              # Start server
├── requirements.txt
└── .env.example
```

---

## Quick Start

### 1. Install dependencies

```bash
# System deps (Ubuntu/Debian)
sudo apt-get install -y cmake libopenblas-dev liblapack-dev libx11-dev

# Python
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — set Twilio credentials and other values
```

### 3. Run

```bash
python run.py
# or
uvicorn app.main:app --reload
```

### 4. Open the interactive API docs

```
http://localhost:8000/docs
```

Default credentials: `admin` / `admin123`

---

## API Reference

### Auth
| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/login` | Get JWT token |

### Camera
| Method | Endpoint | Description |
|---|---|---|
| POST | `/camera/connect` | Connect IP camera / ESP32 / webcam |
| POST | `/video/upload` | Upload MP4 video |
| GET | `/stream/live/{source_id}` | MJPEG live stream |
| GET | `/source/frame-preview/{source_id}` | Single JPEG preview frame |
| GET | `/sources` | List all sources |
| DELETE | `/sources/{source_id}` | Remove source |

### ROI
| Method | Endpoint | Description |
|---|---|---|
| POST | `/roi/save` | Create ROI zone |
| GET | `/roi/list/{source_id}` | List ROI zones for a source |
| PUT | `/roi/update/{id}` | Update ROI zone |
| DELETE | `/roi/{id}` | Delete ROI zone |

### Faces
| Method | Endpoint | Description |
|---|---|---|
| POST | `/face/register` | Register known resident (upload photo) |
| GET | `/face/list` | List registered faces |
| DELETE | `/face/{id}` | Remove face |

### Alerts & History
| Method | Endpoint | Description |
|---|---|---|
| GET | `/alerts` | Get alerts (filterable by source_id) |
| GET | `/alerts/{id}/snapshot` | Get alert snapshot image |
| GET | `/history` | Event history |

### Settings
| Method | Endpoint | Description |
|---|---|---|
| GET | `/settings` | All settings |
| POST | `/settings/update` | Update a setting |

### WebSocket
| Endpoint | Description |
|---|---|
| `WS /ws/alerts?token=<jwt>` | Live alert stream |

---

## Suspicion Scoring

| Condition | Points |
|---|---|
| Unknown person | +1 |
| Red / critical zone | +1 |
| Night time (20:00–06:00) | +1 |
| Loitering detected | +1 |

**Score 0–1** → log only  
**Score 2** → WebSocket alert to app  
**Score 3+** → WebSocket + Twilio WhatsApp (SMS fallback)

---

## Visual Tools (Browser)

Open these HTML files directly in a browser (no server needed):

- **`scripts/roi_editor.html`** — Draw and save ROI zones visually on a live camera frame
- **`scripts/alert_monitor.html`** — Monitor real-time WebSocket alerts

---

## Zone Types

| Type | Color | Meaning |
|---|---|---|
| `green` | 🟢 | Safe zone — minimal alerting |
| `amber` | 🟡 | Watch zone — log activity |
| `red` | 🔴 | Alert zone — triggers score +1 |
| `critical` | 🟣 | High-security zone — triggers score +1 |

---

## SQLite Tables

`users` · `sources` · `roi_zones` · `known_faces` · `alerts` · `history` · `settings`

Database file: `surveillance.db` (auto-created on first run).

---

## Mobile App Integration

The backend is REST+WebSocket — connect your mobile app to:

1. `POST /auth/login` to get a JWT
2. `GET /source/frame-preview/{id}` to show a camera thumbnail for ROI drawing
3. `POST /roi/save` with coordinates drawn on the thumbnail
4. `WS /ws/alerts?token=<jwt>` for push alerts

---

## Environment Variables

| Variable | Description |
|---|---|
| `APP_SECRET_KEY` | JWT signing secret |
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_FROM_WHATSAPP` | Sending WhatsApp number |
| `ALERT_PHONE_WHATSAPP` | Destination WhatsApp number |
| `YOLO_MODEL` | YOLO model file (default `yolov8n.pt`) |
| `DETECTION_CONFIDENCE` | Min confidence threshold (default `0.5`) |
| `LOITERING_THRESHOLD_SECONDS` | Seconds before loitering flag (default `30`) |
| `STORAGE_BASE` | Root storage directory (default `./storage`) |
