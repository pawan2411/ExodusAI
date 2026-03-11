# ExodusAI — Project Story

## Inspiration

Every major evacuation in history — Katrina, Paradise wildfire, the Fukushima disaster — shared one fatal flaw: **decisions were made too slowly**. Humans at command centers received fragmented information, drew on gut instinct, and issued orders minutes after the window to act had already closed.

We asked a simple but terrifying question:

> *What if an AI could watch the entire evacuation unfold — in real time — and make every routing decision faster than any human ever could?*

That question became ExodusAI.

---

## What We Built

ExodusAI is a real-time, AI-commanded city block evacuation simulation. The local engine generates genuine chaos — crowds forming, exits clogging, highways backing up — and **Gemini Live API acts as the autonomous commander**, watching two simultaneous live video feeds and issuing binding decisions to minimize total evacuation time.

### Dual Live Video Feeds

Gemini receives two continuous video streams:

1. **Simulation View** — a top-down rendered canvas showing buildings, moving agents (people), exit markers colored by congestion, and a live highway strip
2. **Traffic Map** — a Google Maps-style dark-mode view showing road-level congestion around the evacuation zone, colored approach roads, and the expressway with inbound/outbound lane traffic

Both frames stream at ~3 fps via `send_realtime_input`, giving Gemini genuine temporal context — it sees the situation *evolve*, not just snapshots.

### Agent-Based Simulation Engine

The evacuation is modeled as a multi-agent system. Each person $p_i$ moves toward their assigned exit $e_j$ with velocity:

$$\vec{v}_i = s_i \cdot \frac{\vec{e}_j - \vec{p}_i}{\|\vec{e}_j - \vec{p}_i\|}$$

where $s_i \sim \mathcal{U}(2.2,\ 4.0)$ px/tick is individual walking speed. The highway processes evacuees at rate:

$$R_{out} = \left\lfloor \frac{C_{highway}}{T_{fps}} \right\rfloor \text{ people/tick}$$

where $C_{highway}$ is the configurable outbound capacity (ppl/sec) and $T_{fps} = 10$ ticks/sec.

Exit congestion is flagged when queue length $q_j > 15$, triggering an immediate alert to Gemini.

### Gemini as the Commander

Gemini uses **function calling** to directly mutate simulation state:

| Tool | Effect |
|---|---|
| `control_exit` | Open or close any exit gate |
| `control_highway` | Adjust outbound capacity or block inbound lanes |
| `redirect_building` | Reroute all occupants of a building to a target exit |
| `get_status` | Poll current evacuation statistics |

Every tool call is reflected back in the live canvas within the next render tick — Gemini can watch its own decisions take effect.

---

## How We Built It

```
Browser (Vanilla JS)
  └─ WebSocket ──► FastAPI Backend (Python)
                      ├─ CityBlock simulation engine (asyncio, 10 Hz)
                      ├─ OpenCV renderer → JPEG frames
                      ├─ Maps renderer → Google Maps-style traffic JPEG
                      └─ GeminiLiveSession
                           ├─ send_realtime_input (sim frames, 3 fps)
                           ├─ send_realtime_input (traffic map, 0.5 fps)
                           ├─ TEXT response modality
                           └─ Function calling → simulation mutations
```

The backend runs three concurrent `asyncio` tasks per session:
- **Client receiver** — handles config, start, pause, reset, text queries
- **Gemini streamer** — forwards Gemini text decisions and tool actions to the browser
- **Simulation runner** — ticks the engine, renders frames, feeds Gemini

---

## Challenges

**1. Gemini seeing its own decisions**
The hardest problem: Gemini issues a `redirect_building` command, but if the next frame arrives before people start visibly moving, Gemini might issue the same command again. We solved this by sending tool results back immediately and including state summaries in alert texts — giving Gemini textual confirmation even before the visual update arrives.

**2. Frame rate vs. model responsiveness**
Sending too many frames flooded the Live API session with no benefit. Too few, and Gemini lacked temporal context to distinguish a developing bottleneck from a resolved one. We landed on **3 fps for simulation, 0.5 fps for traffic map** — enough for temporal reasoning without overwhelming the session.

**3. Dual-view coherence**
The two renderers (simulation canvas + traffic map) use different coordinate systems and visual languages. Teaching Gemini to correlate what it sees in both views required careful system prompt engineering — explicitly labeling what each visual element means in each view.

**4. Making Gemini act proactively**
By default, language models are reactive. Getting Gemini to continuously issue commands — not just when alerted — required framing the task as a **time-optimization competition**: every second of delay is measurable, and Gemini's score is the total evacuation time.

---

## What We Learned

- The Gemini Live API is genuinely designed for continuous visual reasoning — not just single-image captioning. Streaming frames gives the model *context over time* that fundamentally changes response quality.
- Function calling inside a Live session is surprisingly powerful: the model can see a problem, call a tool to fix it, and observe the result — all within a few seconds of real time.
- Simulation fidelity matters for AI decision quality. A richer visual environment (two views, traffic colors, queue indicators) produced measurably more specific and correct Gemini decisions than a plain canvas alone.

---

*Built for the Gemini Live Agent Challenge · Category: Live Agents*
