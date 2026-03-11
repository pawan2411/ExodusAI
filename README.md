# EvacuAI — AI-Driven City Block Evacuation Simulation

A real-time, parameterized evacuation simulation where **Gemini Live API watches the simulation canvas** and issues live commands — opening/closing exits, redirecting crowds, and managing highway capacity — as the evacuation unfolds.

Built for the **[Gemini Live Agent Challenge](https://geminiliveagentchallenge.devpost.com/)** (Category: Live Agents).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Browser (Vanilla JS)                   │
│  [Config Panel]  [Simulation Canvas]  [AI Decisions Panel]  │
└────────────────────────┬────────────────────────────────────┘
                         │  WebSocket
┌────────────────────────▼────────────────────────────────────┐
│                 FastAPI Backend (Cloud Run)                  │
│                                                             │
│   CityBlock Simulation  ──→  OpenCV Renderer  ──→  JPEG    │
│          ↑ tool actions              ↓ frames               │
│   GeminiLiveSession  ←──────────────────────────────────── │
│   (gemini-2.0-flash-live-001, TEXT mode, function calling)  │
└─────────────────────────────────────────────────────────────┘
```

## How It Works

1. User sets simulation parameters (buildings, exits, population, highway capacity)
2. Backend creates an agent-based city block simulation
3. On start, Gemini is briefed and the simulation begins
4. Every 3 seconds, the rendered simulation canvas is sent to Gemini Live API as a video frame
5. When congestion or milestones are detected, Gemini is alerted via text
6. Gemini responds with text decisions AND tool calls that directly affect the simulation:
   - `control_exit` — open/close exits
   - `control_highway` — adjust highway capacity, block inbound lanes
   - `redirect_building` — redirect a building's population to a specific exit
7. All decisions and actions appear live in the AI Decisions panel

## Quick Start

### 1. Configure

```bash
cd evacuai
cp .env.example .env
# Edit .env — set GOOGLE_API_KEY
```

### 2. Install dependencies

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Run

```bash
python main.py
# or: uvicorn main:app --reload --port 8080
```

### 4. Open browser

Navigate to `http://localhost:8080`

## Usage

1. **Connect** — Click "Connect" to establish WebSocket + Gemini Live session
2. **Configure** — Use sliders (or Randomize) to set simulation parameters
3. **Apply Config** — Sends config to backend, renders initial canvas
4. **Start** — Begins evacuation; Gemini starts watching and commanding
5. **Watch** — People (dots) move toward exits; Gemini issues live decisions on the right panel
6. **Ask** — Type questions in the text box ("Why is Exit 2 congested?")

## Project Structure

```
evacuai/
├── backend/
│   ├── main.py                 # FastAPI + WebSocket server + simulation loop
│   ├── gemini_live.py          # Gemini Live API session (text mode)
│   ├── agents/
│   │   └── evac_agent.py       # System prompt + tool declarations
│   ├── simulation/
│   │   ├── city_block.py       # Agent-based simulation engine
│   │   └── renderer.py         # OpenCV frame renderer
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── index.html              # 3-panel UI (Config | Canvas | AI)
│   ├── main.js                 # App controller
│   └── gemini-client.js        # WebSocket client
├── infra/
│   ├── main.tf                 # Terraform (Cloud Run)
│   ├── variables.tf
│   └── deploy.sh               # Manual deploy script
└── .env.example
```

## Tech Stack

| Layer | Technology |
|---|---|
| AI | Gemini Live API (`gemini-2.0-flash-live-001`), text mode + function calling |
| Backend | Python 3.12, FastAPI, WebSockets, asyncio |
| Simulation | Agent-based (Python), OpenCV rendering |
| Frontend | Vanilla JS, Canvas API |
| Hosting | Google Cloud Run |

## Cloud Deployment

```bash
cd infra
chmod +x deploy.sh
./deploy.sh
# or: terraform init && terraform apply -var="project_id=YOUR_PROJECT"
```

## Competition Category

**Live Agents** — Real-time vision (simulation frames) + function calling for live simulation control.
