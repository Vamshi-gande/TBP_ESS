# 🎥 Enhanced Home Surveillance System (ESS)

AI-powered, privacy-preserving home surveillance system using ESP32-CAM modules for capture and a local/cloud server for intelligent processing.

**Team:** Vamshi, Sitanand & Akshith | **Guide:** Dr. Jeetender Reddy | **Institution:** Vasavi College of Engineering

---

## Tech Stack

| Layer | Technology |
|---|---|
| Camera Hardware | ESP32-CAM (OV2640, MJPEG over Wi-Fi) |
| API Framework | FastAPI + Uvicorn |
| AI Detection | YOLOv8 Nano (~3.2M params) |
| Motion Detection | MOG2 Background Subtraction (OpenCV) |
| Face Recognition | InsightFace (ArcFace 512-d embeddings via ONNX Runtime) |
| Behavior Analysis | CSRT Tracking + Lucas-Kanade Optical Flow |
| Video Capture | OpenCV |
| Database | PostgreSQL 16 (via Docker) + asyncpg |
| Realtime Push | WebSocket |
| Notifications | Twilio WhatsApp / SMS |
| Auth | JWT (python-jose) + bcrypt |
| Frontend | React Native (Expo) — runs in browser for debugging |
| Containerisation | Docker + Docker Compose |

---

## Three-Signal Scoring System

| Signal | Condition | Points |
|---|---|---|
| **TIME** | Detection during night hours (20:00–06:00) | +1 |
| **BEHAVIOR** | Loitering detected (dwell > threshold) | +1 |
| **FREQUENCY** | Unknown / novel face | +1 |

**Score 0** → silent log  
**Score 1** → snapshot saved to disk  
**Score 2** → WebSocket alert + WhatsApp snapshot  
**Score 3** → WhatsApp video + buzzer + app alert  

---

## Project Structure

```
TBP_ESS/
├── app/
│   ├── main.py                          # App factory + lifespan hooks
│   ├── core/
│   │   ├── config.py                    # Settings (env vars + DATABASE_URL)
│   │   └── security.py                 # JWT + bcrypt
│   ├── db/
│   │   └── database.py                 # PostgreSQL pool (asyncpg) + schema init
│   ├── models/
│   │   └── schemas.py                  # All Pydantic schemas
│   ├── services/
│   │   ├── camera_gateway.py           # Camera/stream management
│   │   ├── ai_pipeline.py              # YOLOv8 detection workers
│   │   ├── motion_detector.py          # MOG2 background subtraction
│   │   ├── face_engine.py              # InsightFace registration + matching
│   │   ├── loitering_engine.py         # Dwell-time tracker + cleanup timer
│   │   ├── scoring.py                  # Three-Signal suspicion score
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
├── mobile/                             # React Native (Expo) frontend
│   ├── app/
│   │   ├── _layout.js                  # Root layout with auth gate
│   │   ├── login.js                    # Login screen
│   │   └── (tabs)/
│   │       ├── _layout.js              # Tab navigator
│   │       ├── index.js                # Dashboard
│   │       ├── stream.js               # Live MJPEG viewer
│   │       ├── roi.js                  # ROI zone editor
│   │       ├── faces.js                # Face registration
│   │       ├── alerts.js               # Alert history
│   │       └── settings.js             # System settings
│   └── src/
│       ├── api.js                      # API client with JWT auth
│       ├── AuthContext.js              # Auth context provider
│       └── theme.js                    # Design tokens
├── scripts/
│   ├── dashboard.html                  # Full testing console (browser)
│   ├── roi_editor.html                 # Visual ROI editor (browser)
│   └── alert_monitor.html             # Live WS alert viewer (browser)
├── storage/
│   ├── uploads/                        # Uploaded MP4s
│   ├── snapshots/                      # Alert JPEG snapshots
│   ├── clips/                          # Video clips
│   └── faces/                          # Registered face images
├── docker-compose.yml                  # PostgreSQL + API containers
├── Dockerfile                          # Backend container image
├── run.py                              # Start server (dev)
├── requirements.txt
└── .env.example
```

---

## Quick Start

### Option A: Docker (Recommended)

```bash
# 1. Copy and edit environment
cp .env.example .env

# 2. Start PostgreSQL + API
docker compose up -d

# 3. Open the API docs
open http://localhost:8000/docs
```

### Option B: Local Development

```bash
# 1. Start PostgreSQL only
docker compose up -d db

# 2. Install Python dependencies
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — DATABASE_URL defaults to localhost:5432

# 4. Run the backend
python run.py
# or
uvicorn app.main:app --reload
```

### Run the mobile app (browser debugging)

```bash
cd mobile
npm install
npx expo start --web
```

### Open the interactive API docs

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

## Zone Types

| Type | Color | Meaning |
|---|---|---|
| `green` | 🟢 | Safe zone — minimal alerting |
| `amber` | 🟡 | Watch zone — log activity |
| `red` | 🔴 | Alert zone — triggers score +1 |
| `critical` | 🟣 | High-security zone — triggers score +1 |

---

## Hardware Cost (~₹4,730)

| Component | Cost (INR) |
|---|---|
| ESP32-CAM × 2 | ₹1,100 |
| Processing Server (local PC / cloud) | — |
| PIR HC-SR501 & IR LEDs | ₹280 |
| MicroSD 32GB | ₹400 |
| 5V 3A Power Supply | ₹150 |

---

## Privacy & Edge Computing

- **No cloud dependency**: All processing runs locally (or on your own server)
- **Novelty detection**: Only 512-d embedding vectors stored, not identities
- **Embeddings never leave the network**: Aligned with India's DPDPA 2023
- **Open-source stack**: No vendor lock-in or subscription fees

---

## Environment Variables

| Variable | Description |
|---|---|
| `APP_SECRET_KEY` | JWT signing secret |
| `DATABASE_URL` | PostgreSQL connection string |
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_FROM_WHATSAPP` | Sending WhatsApp number |
| `ALERT_PHONE_WHATSAPP` | Destination WhatsApp number |
| `YOLO_MODEL` | YOLO model file (default `yolov8n.pt`) |
| `DETECTION_CONFIDENCE` | Min confidence threshold (default `0.5`) |
| `LOITERING_THRESHOLD_SECONDS` | Seconds before loitering flag (default `30`) |
| `STORAGE_BASE` | Root storage directory (default `./storage`) |
