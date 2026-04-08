# ExodusAI - AI-Driven City Block Evacuation Simulation

A real-time, parameterized evacuation simulation where **Gemini Live API watches the simulation canvas** and issues live commands - opening/closing exits, redirecting crowds, and managing highway capacity - as the evacuation unfolds.

Built for the **[Gemini Live Agent Challenge](https://geminiliveagentchallenge.devpost.com/)** (Category: Live Agents).

## Architecture

```
+-------------------------------------------------------------+
|                      Browser (Vanilla JS)                    |
|  [Config Panel]  [Simulation Canvas]  [AI Decisions Panel]   |
+----------------------------+--------------------------------+
                             |  WebSocket
+----------------------------v--------------------------------+
|                 FastAPI Backend (Cloud Run)                  |
|                                                              |
|   CityBlock Simulation  -->  OpenCV Renderer  -->  JPEG      |
|          ^ tool actions              | frames                |
|   GeminiLiveSession  <-----------------------------------    |
|   (gemini-2.0-flash-live-001, TEXT mode, function calling)   |
+--------------------------------------------------------------+
```

## How It Works

1. User sets simulation parameters (buildings, exits, population, highway capacity)
2. Backend creates an agent-based city block simulation
3. On start, Gemini is briefed and the simulation begins
4. Every 3 seconds, the rendered simulation canvas is sent to Gemini Live API as a video frame
5. When congestion or milestones are detected, Gemini is alerted via text
6. Gemini responds with text decisions AND tool calls that directly affect the simulation:
   - `control_exit` - open/close exits
   - `control_highway` - adjust highway capacity, block inbound lanes
   - `redirect_building` - redirect a building's population to a specific exit
7. All decisions and actions appear live in the AI Decisions panel

## Prerequisites

- Python 3.10+
- A Google Gemini API key ([get one here](https://aistudio.google.com))

## Setup

### 1. Clone and configure

```bash
cd evacuai
cp .env.example .env
# Edit .env - set GOOGLE_API_KEY
```

### 2. Option A: Run the FastAPI app (full frontend)

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
# or: uvicorn main:app --reload --port 8080
```

Open your browser at `http://localhost:8080`

**Usage:**
1. **Connect** - Click "Connect" to establish WebSocket + Gemini Live session
2. **Configure** - Use sliders (or Randomize) to set simulation parameters
3. **Apply Config** - Sends config to backend, renders initial canvas
4. **Start** - Begins evacuation; Gemini starts watching and commanding
5. **Watch** - People (dots) move toward exits; Gemini issues live decisions on the right panel
6. **Ask** - Type questions in the text box ("Why is Exit 2 congested?")

### 2. Option B: Run the Streamlit app

The Streamlit app is a standalone alternative UI that reuses the backend simulation and agent code.

```bash
# From the project root (evacuai/)
cd streamlit
pip install -r requirements.txt
streamlit run app.py
```

The Streamlit app will open automatically in your browser (default: `http://localhost:8501`).

**Usage:**
1. Enter your Gemini API key in the sidebar Settings
2. Adjust simulation parameters (buildings, exits, population, highway capacity)
3. Optionally configure time scale and simulation speed
4. Click **Apply Config** to initialize the simulation
5. Click **Start Evacuation** - Gemini connects and begins commanding
6. Watch the simulation view and traffic map update in real time
7. Gemini's decisions appear in the right panel
8. Use **Ask Gemini** to ask questions during the evacuation

> **Note:** The Streamlit app imports backend code from `../backend`, so both directories must be present.

## Project Structure

```
evacuai/
|-- backend/
|   |-- main.py                 # FastAPI + WebSocket server + simulation loop
|   |-- gemini_live.py          # Gemini Live API session (text mode)
|   |-- agents/
|   |   |-- evac_agent.py       # System prompt + tool declarations
|   |   |-- agent.py            # Root agent (voice mode)
|   |   |-- vision_agent.py     # Vision analysis prompts
|   |   |-- route_agent.py      # Route planning logic
|   |   +-- report_agent.py     # Situation report generator
|   |-- simulation/
|   |   |-- city_block.py       # Agent-based simulation engine
|   |   |-- renderer.py         # OpenCV frame renderer
|   |   |-- maps_renderer.py    # Traffic map renderer
|   |   |-- video_simulator.py  # Video playback with hazard overlays
|   |   +-- hazard_overlays.py  # Smoke, fire, crowd overlays
|   |-- tools/
|   |   |-- traffic.py          # Traffic status tool
|   |   |-- weather.py          # NWS weather alerts
|   |   +-- building.py         # Building layout tool
|   |-- Dockerfile
|   +-- requirements.txt
|-- frontend/
|   |-- index.html              # 3-panel UI (Config | Canvas | AI)
|   |-- main.js                 # App controller
|   +-- gemini-client.js        # WebSocket client
|-- streamlit/
|   |-- app.py                  # Streamlit version of the app
|   +-- requirements.txt        # Streamlit dependencies
|-- infra/
|   |-- main.tf                 # Terraform (Cloud Run)
|   |-- variables.tf
|   +-- deploy.sh               # Manual deploy script
|-- scenarios/
|   +-- README.md               # Scenario video instructions
+-- .env.example
```

## Tech Stack

| Layer | Technology |
|---|---|
| AI | Gemini Live API (`gemini-2.0-flash-live-001`), text mode + function calling |
| Backend | Python 3.12, FastAPI, WebSockets, asyncio |
| Simulation | Agent-based (Python), OpenCV rendering |
| Frontend | Vanilla JS, Canvas API |
| Streamlit | Streamlit, PIL, OpenCV |
| Hosting | Google Cloud Run |

## Cloud Deployment

```bash
cd infra
chmod +x deploy.sh
./deploy.sh
# or: terraform init && terraform apply -var="project_id=YOUR_PROJECT"
```

## Competition Category

**Live Agents** - Real-time vision (simulation frames) + function calling for live simulation control.
