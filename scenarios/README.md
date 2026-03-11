# Scenario Videos

Place demo scenario video files in this directory.

## Expected Files

- `fire_scenario.mp4` — A 2-3 minute video clip of a building interior for the fire evacuation demo.

## When No Video Is Present

The video simulator automatically generates synthetic frames showing a building floor plan layout when no video file is found. This means you can run the full system in simulation mode without any video files.

## Creating Your Own Scenario Video

### Option 1: Stock Footage
Search for royalty-free footage on Pexels, Pixabay, or Videvo:
- "building corridor"
- "office hallway"
- "fire alarm evacuation"
- "smoke in hallway"

### Option 2: Record Your Own
Record a walkthrough of a building interior (2-3 minutes). The system will overlay simulated hazards automatically.

### Option 3: Generate with OpenCV
```python
import cv2
import numpy as np

fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter('fire_scenario.mp4', fourcc, 1.0, (768, 768))
for i in range(180):  # 3 minutes at 1 FPS
    frame = np.zeros((768, 768, 3), dtype=np.uint8)
    frame[:] = (40, 35, 30)
    cv2.putText(frame, f"Frame {i}", (50, 384),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (200, 200, 200), 2)
    out.write(frame)
out.release()
```

## Timeline Configuration

The hazard overlay timeline is configured in `backend/simulation/video_simulator.py`. By default:
- 0-30s: Normal conditions
- 30-60s: Smoke detected
- 60-90s: Smoke increasing
- 90-120s: Fire visible
- 120-150s: Exit blocked
- 150-180s: Crowd gathering
