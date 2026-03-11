"""Agent-based city block evacuation simulation engine."""

import math
import random
from typing import List, Optional

# Canvas dimensions (pixels)
CANVAS_W = 900
CANVAS_H = 680

# Layout constants
STATS_H = 55       # Top stats bar height
HIGHWAY_H = 80     # Bottom highway strip height
BLOCK_MARGIN_X = 60
BLOCK_X1 = BLOCK_MARGIN_X
BLOCK_X2 = CANVAS_W - BLOCK_MARGIN_X
BLOCK_Y1 = STATS_H
BLOCK_Y2 = CANVAS_H - HIGHWAY_H
BLOCK_W = BLOCK_X2 - BLOCK_X1   # 780
BLOCK_H = BLOCK_Y2 - BLOCK_Y1   # 545
ROAD_BORDER = 40   # Road width around the block interior


class Person:
    _id_counter = 0

    def __init__(self, x: float, y: float, building_id: str):
        Person._id_counter += 1
        self.id = Person._id_counter
        self.x = x
        self.y = y
        self.building_id = building_id
        self.target_exit: Optional["Exit"] = None
        # status: in_building | evacuating | queued | evacuated
        self.status = "in_building"
        self.speed = random.uniform(2.2, 4.0)   # px/tick

    def assign_exit(self, exit_obj: "Exit"):
        self.target_exit = exit_obj
        self.status = "evacuating"

    def move(self):
        if self.status != "evacuating" or self.target_exit is None:
            return
        dx = self.target_exit.x - self.x
        dy = self.target_exit.y - self.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 8:
            self.x = self.target_exit.x
            self.y = self.target_exit.y
            self.status = "queued"
            self.target_exit.queue.append(self)
            return
        # Move toward exit with slight jitter for realism
        self.x += (dx / dist) * self.speed + random.uniform(-0.4, 0.4)
        self.y += (dy / dist) * self.speed + random.uniform(-0.4, 0.4)


class Building:
    def __init__(self, id: str, x: float, y: float, w: float, h: float, population: int):
        self.id = id
        self.x = x   # center
        self.y = y
        self.w = w
        self.h = h
        self.total_population = population
        self.persons: List[Person] = []
        # Bounding box
        self.x1 = x - w / 2
        self.y1 = y - h / 2
        self.x2 = x + w / 2
        self.y2 = y + h / 2

    @property
    def remaining(self) -> int:
        return sum(1 for p in self.persons if p.status in ("in_building", "evacuating", "queued"))

    @property
    def evacuated(self) -> int:
        return sum(1 for p in self.persons if p.status == "evacuated")


class Exit:
    def __init__(self, id: str, x: float, y: float, name: str):
        self.id = id
        self.name = name
        self.x = x
        self.y = y
        self.status = "open"   # open | closed
        self.queue: List[Person] = []
        self.total_through = 0

    @property
    def queue_length(self) -> int:
        return len(self.queue)

    @property
    def is_congested(self) -> bool:
        return self.queue_length > 15


class Highway:
    def __init__(self, out_capacity: int = 20):
        self.outbound_capacity = out_capacity   # people/second
        self.inbound_blocked = False
        self.queue: List[Person] = []
        self.evacuated_count = 0
        self.congestion_level = "clear"   # clear | moderate | heavy

    def update_congestion(self):
        q = len(self.queue)
        if q < 20:
            self.congestion_level = "clear"
        elif q < 50:
            self.congestion_level = "moderate"
        else:
            self.congestion_level = "heavy"


class CityBlock:
    """Manages the full city block evacuation simulation."""

    TICKS_PER_SEC = 10   # 10 simulation ticks per real second

    def __init__(self, config: dict):
        Person._id_counter = 0

        n_buildings = max(1, min(10, config.get("buildings", 5)))
        n_exits = max(1, min(6, config.get("exits", 3)))
        avg_pop = max(10, min(200, config.get("avg_pop", 50)))
        highway_out = max(5, min(100, config.get("highway_out", 20)))

        self.buildings: List[Building] = []
        self.exits: List[Exit] = []
        self.persons: List[Person] = []
        self.highway = Highway(out_capacity=highway_out)
        self.tick = 0
        self.running = False
        self.config = config
        self._congestion_alerted: set = set()
        self._milestones_fired: set = set()

        self._create_buildings(n_buildings, avg_pop)
        self._create_exits(n_exits)
        self._populate_buildings()

    # ── Setup ──────────────────────────────────────────────────────────

    def _create_buildings(self, n: int, avg_pop: int):
        inner_x1 = BLOCK_X1 + ROAD_BORDER
        inner_y1 = BLOCK_Y1 + ROAD_BORDER
        inner_x2 = BLOCK_X2 - ROAD_BORDER
        inner_y2 = BLOCK_Y2 - ROAD_BORDER
        inner_w = inner_x2 - inner_x1
        inner_h = inner_y2 - inner_y1

        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)

        gap = 40
        bw = max(70, min(160, (inner_w - gap * (cols - 1)) // cols))
        bh = max(55, min(120, (inner_h - gap * (rows - 1)) // rows))

        count = 0
        for row in range(rows):
            for col in range(cols):
                if count >= n:
                    break
                cx = inner_x1 + col * (bw + gap) + bw // 2
                cy = inner_y1 + row * (bh + gap) + bh // 2
                pop = int(avg_pop * random.uniform(0.6, 1.4))
                self.buildings.append(Building(
                    id=f"B{count + 1}",
                    x=float(cx), y=float(cy),
                    w=float(bw), h=float(bh),
                    population=pop,
                ))
                count += 1

    def _create_exits(self, n: int):
        # Predefined placement map for 1-6 exits
        placement_map = {
            1: [("S", 0.5)],
            2: [("N", 0.5), ("S", 0.5)],
            3: [("N", 0.5), ("S", 0.3), ("S", 0.7)],
            4: [("N", 0.5), ("S", 0.5), ("W", 0.5), ("E", 0.5)],
            5: [("N", 0.3), ("N", 0.7), ("S", 0.5), ("W", 0.5), ("E", 0.5)],
            6: [("N", 0.3), ("N", 0.7), ("S", 0.3), ("S", 0.7), ("W", 0.5), ("E", 0.5)],
        }
        positions = placement_map.get(n, placement_map[6])[:n]

        for i, (side, frac) in enumerate(positions):
            if side == "N":
                x, y = BLOCK_X1 + BLOCK_W * frac, float(BLOCK_Y1)
            elif side == "S":
                x, y = BLOCK_X1 + BLOCK_W * frac, float(BLOCK_Y2)
            elif side == "W":
                x, y = float(BLOCK_X1), BLOCK_Y1 + BLOCK_H * frac
            else:  # E
                x, y = float(BLOCK_X2), BLOCK_Y1 + BLOCK_H * frac
            self.exits.append(Exit(id=f"E{i + 1}", x=x, y=y, name=f"Exit {i + 1} ({side})"))

    def _populate_buildings(self):
        for b in self.buildings:
            for _ in range(b.total_population):
                px = b.x1 + random.uniform(8, b.w - 8)
                py = b.y1 + random.uniform(8, b.h - 8)
                p = Person(px, py, b.id)
                b.persons.append(p)
                self.persons.append(p)

    # ── Simulation Control ──────────────────────────────────────────────

    def start_evacuation(self):
        """Assign exits to people and begin the evacuation."""
        self.running = True
        open_exits = [e for e in self.exits if e.status == "open"]
        if not open_exits:
            open_exits = self.exits
        for p in self.persons:
            if p.status == "in_building":
                target = min(open_exits, key=lambda e: math.hypot(e.x - p.x, e.y - p.y))
                p.assign_exit(target)

    def step(self):
        """Advance simulation by one tick (1/10 second)."""
        if not self.running:
            return
        self.tick += 1

        # Move evacuating people
        for p in self.persons:
            if p.status == "evacuating":
                p.move()

        # Process each exit's queue
        for exit_ in self.exits:
            if exit_.status == "closed":
                # Reassign queued people to nearest open exit
                open_exits = [e for e in self.exits if e.status == "open"]
                for p in list(exit_.queue):
                    if open_exits:
                        new_e = min(open_exits, key=lambda e: math.hypot(e.x - p.x, e.y - p.y))
                        p.assign_exit(new_e)
                        exit_.queue.remove(p)
                # Also reassign evacuating people heading to this exit
                for p in self.persons:
                    if p.status == "evacuating" and p.target_exit is exit_:
                        if open_exits:
                            new_e = min(open_exits, key=lambda e: math.hypot(e.x - p.x, e.y - p.y))
                            p.assign_exit(new_e)
                continue

            # Move up to 3 people per tick from exit queue to highway queue
            for _ in range(min(3, len(exit_.queue))):
                p = exit_.queue.pop(0)
                self.highway.queue.append(p)
                exit_.total_through += 1

        # Process highway queue → evacuated
        rate = max(1, self.highway.outbound_capacity // self.TICKS_PER_SEC)
        for _ in range(rate):
            if self.highway.queue:
                p = self.highway.queue.pop(0)
                p.status = "evacuated"
                self.highway.evacuated_count += 1

        self.highway.update_congestion()

        # Check completion
        if all(p.status == "evacuated" for p in self.persons):
            self.running = False

    # ── Gemini Tool Actions ─────────────────────────────────────────────

    def set_exit_status(self, exit_id: str, status: str) -> dict:
        """Open or close an exit by ID. Returns result dict."""
        for e in self.exits:
            if e.id == exit_id:
                e.status = status
                return {"success": True, "exit_id": exit_id, "new_status": status}
        return {"success": False, "error": f"Exit {exit_id} not found"}

    def set_highway_capacity(self, capacity: int) -> dict:
        """Set highway outbound capacity (people/second)."""
        self.highway.outbound_capacity = max(5, min(100, capacity))
        return {"success": True, "outbound_capacity": self.highway.outbound_capacity}

    def block_highway_inbound(self, blocked: bool) -> dict:
        """Block or unblock highway inbound lanes."""
        self.highway.inbound_blocked = blocked
        return {"success": True, "inbound_blocked": blocked}

    def redirect_building(self, building_id: str, exit_id: str) -> dict:
        """Redirect all people from a building to a specific exit."""
        target = next((e for e in self.exits if e.id == exit_id), None)
        if not target:
            return {"success": False, "error": f"Exit {exit_id} not found"}
        if target.status == "closed":
            return {"success": False, "error": f"Exit {exit_id} is closed"}
        building = next((b for b in self.buildings if b.id == building_id), None)
        if not building:
            return {"success": False, "error": f"Building {building_id} not found"}
        count = 0
        for p in building.persons:
            if p.status in ("in_building", "evacuating"):
                p.assign_exit(target)
                count += 1
        return {"success": True, "redirected": count, "building": building_id, "exit": exit_id}

    # ── Event Detection ─────────────────────────────────────────────────

    def get_new_alerts(self) -> List[dict]:
        """Return alerts for newly congested exits or cleared exits."""
        alerts = []
        for e in self.exits:
            if e.is_congested and e.id not in self._congestion_alerted:
                self._congestion_alerted.add(e.id)
                alerts.append({
                    "type": "congestion",
                    "exit_id": e.id,
                    "exit_name": e.name,
                    "queue": e.queue_length,
                    "message": f"Congestion at {e.name}: {e.queue_length} people queued",
                })
            elif not e.is_congested and e.id in self._congestion_alerted:
                self._congestion_alerted.discard(e.id)

        if self.highway.congestion_level == "heavy" and "highway_heavy" not in self._congestion_alerted:
            self._congestion_alerted.add("highway_heavy")
            alerts.append({
                "type": "highway_congestion",
                "message": f"Highway severely congested: {len(self.highway.queue)} vehicles queued",
            })
        elif self.highway.congestion_level != "heavy" and "highway_heavy" in self._congestion_alerted:
            self._congestion_alerted.discard("highway_heavy")

        return alerts

    def get_new_milestones(self) -> List[str]:
        """Return milestone messages (50%, 75%, complete)."""
        stats = self.get_stats()
        pct = stats["percent_complete"]
        milestones = []
        for threshold in [25, 50, 75, 90]:
            key = f"milestone_{threshold}"
            if pct >= threshold and key not in self._milestones_fired:
                self._milestones_fired.add(key)
                milestones.append(
                    f"{threshold}% evacuated ({stats['evacuated']}/{stats['total']} people, "
                    f"{int(stats['elapsed_seconds'])}s elapsed)"
                )
        if not self.running and self.tick > 0 and "complete" not in self._milestones_fired:
            all_out = all(p.status == "evacuated" for p in self.persons)
            if all_out:
                self._milestones_fired.add("complete")
                milestones.append(
                    f"Evacuation COMPLETE: All {stats['total']} people evacuated "
                    f"in {int(stats['elapsed_seconds'])} seconds."
                )
        return milestones

    # ── Serialization ────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        total = len(self.persons)
        evacuated = sum(1 for p in self.persons if p.status == "evacuated")
        return {
            "total": total,
            "evacuated": evacuated,
            "in_transit": sum(1 for p in self.persons if p.status in ("evacuating", "queued")),
            "in_building": sum(1 for p in self.persons if p.status == "in_building"),
            "percent_complete": round(evacuated / total * 100, 1) if total > 0 else 0.0,
            "elapsed_seconds": round(self.tick / self.TICKS_PER_SEC, 1),
        }

    def to_dict(self) -> dict:
        """Full simulation state for WebSocket broadcast and Gemini."""
        stats = self.get_stats()
        return {
            "tick": self.tick,
            "running": self.running,
            "buildings": [
                {
                    "id": b.id, "x": b.x, "y": b.y, "w": b.w, "h": b.h,
                    "total": b.total_population,
                    "remaining": b.remaining,
                    "evacuated": b.evacuated,
                }
                for b in self.buildings
            ],
            "exits": [
                {
                    "id": e.id, "name": e.name, "x": e.x, "y": e.y,
                    "status": e.status,
                    "queue": e.queue_length,
                    "congested": e.is_congested,
                }
                for e in self.exits
            ],
            "highway": {
                "outbound_capacity": self.highway.outbound_capacity,
                "inbound_blocked": self.highway.inbound_blocked,
                "queue": len(self.highway.queue),
                "evacuated": self.highway.evacuated_count,
                "congestion": self.highway.congestion_level,
            },
            "agents": [
                {"x": round(p.x, 1), "y": round(p.y, 1), "status": p.status}
                for p in self.persons
                if p.status != "evacuated"
            ],
            "stats": stats,
        }

    def get_road_traffic(self) -> dict:
        """Derive road traffic levels for the maps renderer."""
        order = {"clear": 0, "moderate": 1, "heavy": 2, "blocked": 3}

        def worse(a, b):
            return a if order.get(a, 0) >= order.get(b, 0) else b

        traffic = {
            "highway":          self.highway.congestion_level,
            "highway_inbound":  "blocked" if self.highway.inbound_blocked else "clear",
            "north": "clear", "south": "clear", "east": "clear", "west": "clear",
            "south_approach": "clear",
        }
        for e in self.exits:
            n = e.name
            q = e.queue_length
            lvl = "heavy" if e.is_congested else ("moderate" if q > 5 else "clear")
            if "(N)" in n:
                traffic["north"] = worse(traffic["north"], lvl)
            elif "(S)" in n:
                traffic["south"] = worse(traffic["south"], lvl)
                traffic["south_approach"] = worse(traffic["south_approach"], lvl)
            elif "(E)" in n:
                traffic["east"] = worse(traffic["east"], lvl)
            elif "(W)" in n:
                traffic["west"] = worse(traffic["west"], lvl)
        if self.highway.congestion_level == "heavy":
            traffic["south_approach"] = worse(traffic["south_approach"], "moderate")
        return traffic

    def summary_text(self) -> str:
        """Return a brief text summary of the current state for Gemini context."""
        s = self.get_stats()
        exits_info = ", ".join(
            f"{e.id}({e.status}, Q:{e.queue_length}{'!' if e.is_congested else ''})"
            for e in self.exits
        )
        hw = self.highway
        return (
            f"Tick {self.tick} | {s['percent_complete']}% evacuated "
            f"({s['evacuated']}/{s['total']}) | "
            f"Elapsed: {s['elapsed_seconds']}s | "
            f"Exits: {exits_info} | "
            f"Highway queue: {len(hw.queue)} (cap:{hw.outbound_capacity}/s, {hw.congestion_level})"
        )
