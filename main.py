"""
AEGIS PATH: MERGE & ELIXIR (KIVY EDITION - NO PYGAME REQUIRED)
Portrait Mobile Lane Defense + Merge + Elixir Game in Python & Kivy.
Touch/Mouse-only controls.
"""

import array
import io
import math
import os
import random
import tempfile
import wave
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Mesh, Rectangle
from kivy.uix.widget import Widget

# ==============================================================================
# 1. PORTRAIT MOBILE DISPLAY & PALETTE CONSTANTS
# ==============================================================================

SCREEN_WIDTH = 540
SCREEN_HEIGHT = 960
FPS = 60.0
TITLE = "AEGIS PATH // Merge & Elixir"

TOP_BAR_H = 74
ARENA_TOP = TOP_BAR_H
ARENA_BOTTOM = 592
DECK_TOP = ARENA_BOTTOM


def rgb(r: int, g: int, b: int, a: float = 1.0) -> Tuple[float, float, float, float]:
    return (r / 255.0, g / 255.0, b / 255.0, a)


BG_DARK = rgb(9, 12, 20)
BG_TILE_ALT = rgb(13, 17, 28)
BG_DECOR = rgb(24, 33, 52)
BG_LANE = rgb(24, 30, 46)
BG_LANE_INNER = rgb(19, 24, 37)
LANE_CURB_DARK = rgb(34, 44, 66)
LANE_CURB_LIGHT = rgb(76, 102, 146)
LANE_CENTER = rgb(62, 92, 136)
LANE_BORDER = rgb(52, 68, 98)
SHADOW_COLOR = rgb(4, 6, 10, 0.52)

PANEL_BG = rgb(14, 18, 29)
SLOT_BG = rgb(22, 29, 45)
SLOT_BORDER = rgb(64, 84, 118)

WHITE = rgb(244, 248, 255)
BLACK = rgb(6, 8, 12)
GRAY = rgb(132, 145, 168)
CYAN = rgb(0, 235, 255)
BLUE = rgb(65, 145, 255)
PURPLE = rgb(185, 75, 255)
PINK = rgb(255, 65, 165)
RED = rgb(255, 60, 75)
ORANGE = rgb(255, 140, 30)
YELLOW = rgb(255, 215, 45)
GREEN = rgb(55, 245, 140)
ICE = rgb(110, 220, 255)

MAX_ELIXIR = 10.0
ELIXIR_REGEN_PER_SEC = 0.22


# ==============================================================================
# 2. MATH, SPLINE PATH & COORDINATE CONVERSION
# ==============================================================================

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def dist(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def norm(dx: float, dy: float) -> Tuple[float, float]:
    d = math.hypot(dx, dy)
    if d == 0:
        return 0.0, 0.0
    return dx / d, dy / d


def to_ky(y: float) -> float:
    """Convert top-down logical y (0 at top) to Kivy y (0 at bottom)."""
    return SCREEN_HEIGHT - y


def catmull_rom_point(
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    t: float,
) -> Tuple[float, float]:
    t2 = t * t
    t3 = t2 * t
    x = 0.5 * (
        (2.0 * p1[0])
        + (-p0[0] + p2[0]) * t
        + (2.0 * p0[0] - 5.0 * p1[0] + 4.0 * p2[0] - p3[0]) * t2
        + (-p0[0] + 3.0 * p1[0] - 3.0 * p2[0] + p3[0]) * t3
    )
    y = 0.5 * (
        (2.0 * p1[1])
        + (-p0[1] + p2[1]) * t
        + (2.0 * p0[1] - 5.0 * p1[1] + 4.0 * p2[1] - p3[1]) * t2
        + (-p0[1] + 3.0 * p1[1] - 3.0 * p2[1] + p3[1]) * t3
    )
    return x, y


def build_winding_lane(anchors: List[Tuple[float, float]], steps_per_seg: int = 14) -> List[Tuple[float, float]]:
    if len(anchors) < 2:
        return anchors
    extended = [anchors[0]] + anchors + [anchors[-1]]
    smooth: List[Tuple[float, float]] = []
    for i in range(1, len(extended) - 2):
        p0 = extended[i - 1]
        p1 = extended[i]
        p2 = extended[i + 1]
        p3 = extended[i + 2]
        for s in range(steps_per_seg):
            t = s / float(steps_per_seg)
            smooth.append(catmull_rom_point(p0, p1, p2, p3, t))
    smooth.append(anchors[-1])
    return smooth


RAW_LANE_ANCHORS: List[Tuple[float, float]] = [
    (68.0, 108.0),
    (220.0, 132.0),
    (365.0, 102.0),
    (468.0, 152.0),
    (385.0, 212.0),
    (175.0, 198.0),
    (74.0, 255.0),
    (195.0, 312.0),
    (395.0, 296.0),
    (468.0, 355.0),
    (330.0, 412.0),
    (140.0, 398.0),
    (74.0, 462.0),
    (230.0, 505.0),
    (112.0, 554.0),
]

LANE_POINTS: List[Tuple[float, float]] = build_winding_lane(RAW_LANE_ANCHORS, steps_per_seg=14)

TOWER_PADS: List[Tuple[float, float]] = [
    (155.0, 168.0),
    (305.0, 168.0),
    (430.0, 255.0),
    (275.0, 255.0),
    (145.0, 355.0),
    (285.0, 355.0),
    (265.0, 458.0),
    (385.0, 535.0),
]

DOCK_SLOTS_COUNT = 6


# ==============================================================================
# 3. PROCEDURAL WAV AUDIO ENGINE VIA KIVY SOUNDLOADER
# ==============================================================================

class AudioEngine:
    def __init__(self):
        self.sounds: Dict[str, object] = {}
        self._temp_files: List[str] = []
        self._build_sounds()

    def _make_wav_file(
        self,
        name: str,
        dur: float,
        f0: float,
        f1: float,
        wave_type: str = "sine",
        vol: float = 0.2,
        decay: float = 1.3,
    ):
        sr = 22050
        n = max(1, int(sr * dur))
        samples = array.array("h", [0] * n)
        phase = 0.0
        for i in range(n):
            t = i / max(1, n - 1)
            freq = f0 + (f1 - f0) * t
            phase += (2.0 * math.pi * freq) / sr
            if wave_type == "square":
                s = 1.0 if math.sin(phase) >= 0 else -1.0
            elif wave_type == "saw":
                s = 2.0 * ((phase / (2.0 * math.pi)) % 1.0) - 1.0
            else:
                s = math.sin(phase)
            env = ((1.0 - t) ** decay) * vol
            samples[i] = int(clamp(s * env * 32767.0, -32767.0, 32767.0))

        mem = io.BytesIO()
        with wave.open(mem, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(samples.tobytes())

        try:
            fd, path = tempfile.mkstemp(prefix=f"aegis_{name}_", suffix=".wav")
            with os.fdopen(fd, "wb") as out:
                out.write(mem.getvalue())
            self._temp_files.append(path)
            snd = SoundLoader.load(path)
            if snd:
                self.sounds[name] = snd
        except Exception:
            pass

    def _build_sounds(self):
        self._make_wav_file("sniper", 0.12, 340, 70, "saw", 0.21, 1.5)
        self._make_wav_file("gatling", 0.05, 680, 340, "square", 0.11, 1.8)
        self._make_wav_file("mortar", 0.18, 190, 52, "saw", 0.24, 1.2)
        self._make_wav_file("merge", 0.28, 360, 920, "sine", 0.25, 0.8)
        self._make_wav_file("spawn", 0.14, 240, 520, "sine", 0.18, 1.1)
        self._make_wav_file("enemy_hit", 0.05, 420, 180, "sine", 0.09, 1.6)
        self._make_wav_file("enemy_die", 0.19, 310, 65, "saw", 0.20, 1.3)
        self._make_wav_file("base_hit", 0.32, 140, 42, "square", 0.32, 1.0)
        self._make_wav_file("nova", 0.42, 950, 160, "sine", 0.26, 0.7)

    def play(self, name: str):
        snd = self.sounds.get(name)
        if snd is not None:
            try:
                snd.stop()
                snd.play()
            except Exception:
                pass

    def cleanup(self):
        for p in self._temp_files:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass


# ==============================================================================
# 4. VISUAL FX: PARTICLES, SHOCKWAVES & FLOATING LABELS
# ==============================================================================

@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    color: Tuple[float, float, float, float]
    size: float
    life: float
    max_life: float

    def update(self, dt: float) -> bool:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vx *= 0.93 ** (dt * 60)
        self.vy *= 0.93 ** (dt * 60)
        self.life -= dt
        return self.life > 0


@dataclass
class Shockwave:
    x: float
    y: float
    max_radius: float
    color: Tuple[float, float, float, float]
    life: float = 0.35
    max_life: float = 0.35

    def update(self, dt: float) -> bool:
        self.life -= dt
        return self.life > 0


@dataclass
class FloatingPopup:
    x: float
    y: float
    text: str
    color: Tuple[float, float, float, float]
    life: float = 0.75
    vy: float = -42.0

    def update(self, dt: float) -> bool:
        self.y += self.vy * dt
        self.life -= dt
        return self.life > 0


# ==============================================================================
# 5. LANE ENEMIES & PROJECTILES
# ==============================================================================

@dataclass
class LaneEnemy:
    kind: str
    max_hp: float
    hp: float
    speed: float
    radius: float
    color: Tuple[float, float, float, float]
    base_dmg: int
    elixir_reward: float
    score_reward: int
    seg_idx: int = 0
    x: float = LANE_POINTS[0][0]
    y: float = LANE_POINTS[0][1]
    slow_timer: float = 0.0
    hit_flash: float = 0.0
    spin: float = 0.0

    @classmethod
    def create(cls, kind: str, wave: int) -> "LaneEnemy":
        scale = 1.0 + (wave - 1) * 0.24
        specs = {
            "runner": (88.0, 58.0, 13.0, RED, 1, 0.06, 25),
            "swift": (62.0, 86.0, 11.0, ORANGE, 1, 0.08, 35),
            "brute": (235.0, 39.0, 18.0, PURPLE, 2, 0.15, 70),
            "boss": (1100.0, 30.0, 25.0, PINK, 6, 0.45, 300),
        }
        hp, spd, rad, col, bdmg, rew, scr = specs[kind]
        return cls(
            kind=kind,
            max_hp=hp * scale,
            hp=hp * scale,
            speed=spd * (1.0 + min(0.50, (wave - 1) * 0.035)),
            radius=rad,
            color=col,
            base_dmg=bdmg,
            elixir_reward=rew,
            score_reward=scr,
        )

    def update(self, dt: float) -> bool:
        self.hit_flash = max(0.0, self.hit_flash - dt)
        self.spin += dt * (4.5 if self.kind == "swift" else 1.8)

        mult = 1.0
        if self.slow_timer > 0:
            self.slow_timer -= dt
            mult = 0.42

        move_left = self.speed * mult * dt
        while move_left > 0 and self.seg_idx < len(LANE_POINTS) - 1:
            tx, ty = LANE_POINTS[self.seg_idx + 1]
            d = dist(self.x, self.y, tx, ty)
            if d <= move_left and d > 0:
                self.x, self.y = tx, ty
                move_left -= d
                self.seg_idx += 1
            else:
                nx, ny = norm(tx - self.x, ty - self.y)
                self.x += nx * move_left
                self.y += ny * move_left
                move_left = 0.0

        return self.seg_idx >= len(LANE_POINTS) - 1


@dataclass
class LaneProjectile:
    x: float
    y: float
    vx: float
    vy: float
    damage: float
    color: Tuple[float, float, float, float]
    radius: float = 5.0
    splash_radius: float = 0.0
    slow_duration: float = 0.0
    target: Optional[LaneEnemy] = None
    life: float = 1.6

    def update(self, dt: float) -> bool:
        self.life -= dt
        if self.life <= 0:
            return False
        if self.target is not None and self.target.hp > 0:
            spd = math.hypot(self.vx, self.vy)
            nx, ny = norm(self.target.x - self.x, self.target.y - self.y)
            self.vx, self.vy = nx * spd, ny * spd
        self.x += self.vx * dt
        self.y += self.vy * dt
        return True


# ==============================================================================
# 6. DEFENSIVE UNITS & MERGE PROGRESSION
# ==============================================================================

UNIT_META: Dict[str, Dict[str, object]] = {
    "sniper": {
        "name": "SNIPER",
        "shape_name": "SQUARE",
        "tag": "1 BIG SHOT",
        "cost": 3,
        "color": CYAN,
        "base_dmg": 23.0,
        "fire_rate": 1.35,
        "range": 160.0,
        "proj_spd": 540.0,
    },
    "gatling": {
        "name": "GATLING",
        "shape_name": "TRIANGLE",
        "tag": "RAPID SPRAY",
        "cost": 5,
        "color": YELLOW,
        "base_dmg": 6.8,
        "fire_rate": 0.22,
        "range": 140.0,
        "proj_spd": 560.0,
    },
    "mortar": {
        "name": "MORTAR",
        "shape_name": "HEXAGON",
        "tag": "AOE + SLOW",
        "cost": 7,
        "color": GREEN,
        "base_dmg": 18.5,
        "fire_rate": 1.75,
        "range": 170.0,
        "proj_spd": 410.0,
    },
}


@dataclass
class DefenseUnit:
    unit_type: str
    tier: int = 1
    cooldown: float = 0.0
    aim_angle: float = 0.0
    recoil: float = 0.0

    @property
    def color(self) -> Tuple[float, float, float, float]:
        tier_cols = {
            1: UNIT_META[self.unit_type]["color"],
            2: BLUE,
            3: PURPLE,
            4: PINK,
        }
        return tier_cols.get(self.tier, YELLOW)  # type: ignore

    def get_damage(self, type_bonus_mult: float) -> float:
        base = float(UNIT_META[self.unit_type]["base_dmg"])
        tier_mult = 1.75 ** (self.tier - 1)
        return base * tier_mult * type_bonus_mult

    def get_fire_rate(self) -> float:
        base_rate = float(UNIT_META[self.unit_type]["fire_rate"])
        if self.unit_type == "gatling":
            return max(0.09, base_rate * (0.92 ** (self.tier - 1)))
        return max(0.35, base_rate * (0.94 ** (self.tier - 1)))

    def get_range(self) -> float:
        return float(UNIT_META[self.unit_type]["range"]) + (self.tier - 1) * 12.0

    def update_and_fire(
        self,
        dt: float,
        pos: Tuple[float, float],
        enemies: List[LaneEnemy],
        projectiles: List[LaneProjectile],
        audio: AudioEngine,
        type_bonus_mult: float,
    ):
        self.cooldown = max(0.0, self.cooldown - dt)
        self.recoil = max(0.0, self.recoil - dt * 18.0)

        rng = self.get_range()
        best_enemy: Optional[LaneEnemy] = None
        best_score = -1.0

        for e in enemies:
            if e.hp <= 0:
                continue
            d = dist(pos[0], pos[1], e.x, e.y)
            if d <= rng:
                progress = e.seg_idx * 1000.0 - d * 0.1
                if progress > best_score:
                    best_score = progress
                    best_enemy = e

        if best_enemy is not None:
            self.aim_angle = math.atan2(best_enemy.y - pos[1], best_enemy.x - pos[0])
            if self.cooldown <= 0.0:
                self.cooldown = self.get_fire_rate()
                self.recoil = 5.5
                dmg = self.get_damage(type_bonus_mult)
                spd = float(UNIT_META[self.unit_type]["proj_spd"])
                nx, ny = norm(best_enemy.x - pos[0], best_enemy.y - pos[1])

                if self.unit_type == "sniper":
                    audio.play("sniper")
                    projectiles.append(
                        LaneProjectile(
                            pos[0] + nx * 16,
                            pos[1] + ny * 16,
                            nx * spd,
                            ny * spd,
                            dmg,
                            self.color,
                            radius=6.5 + self.tier,
                            target=best_enemy,
                        )
                    )
                elif self.unit_type == "gatling":
                    audio.play("gatling")
                    jitter = random.uniform(-0.14, 0.14)
                    ang = self.aim_angle + jitter
                    projectiles.append(
                        LaneProjectile(
                            pos[0] + math.cos(ang) * 14,
                            pos[1] + math.sin(ang) * 14,
                            math.cos(ang) * spd,
                            math.sin(ang) * spd,
                            dmg,
                            self.color,
                            radius=4.0,
                            target=best_enemy,
                        )
                    )
                elif self.unit_type == "mortar":
                    audio.play("mortar")
                    projectiles.append(
                        LaneProjectile(
                            pos[0] + nx * 16,
                            pos[1] + ny * 16,
                            nx * spd,
                            ny * spd,
                            dmg,
                            self.color,
                            radius=7.0,
                            splash_radius=60.0 + self.tier * 7.0,
                            slow_duration=1.3 + self.tier * 0.2,
                            target=best_enemy,
                        )
                    )


# ==============================================================================
# 7. KIVY CANVAS WIDGET & GAME ENGINE
# ==============================================================================

@dataclass
class RectBox:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def centerx(self) -> float:
        return self.x + self.w * 0.5

    @property
    def centery(self) -> float:
        return self.y + self.h * 0.5

    def collidepoint(self, px: float, py: float) -> bool:
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h


class AegisPathWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (SCREEN_WIDTH, SCREEN_HEIGHT)

        self.audio = AudioEngine()
        self.state = "TITLE"

        self.btn_guide = RectBox(SCREEN_WIDTH - 96, 12, 82, 24)
        self.btn_close_guide = RectBox(SCREEN_WIDTH // 2 - 90, SCREEN_HEIGHT - 115, 180, 48)

        self.dock_rects: List[RectBox] = []
        slot_w, slot_h = 74, 78
        gap = 10
        total_w = DOCK_SLOTS_COUNT * slot_w + (DOCK_SLOTS_COUNT - 1) * gap
        start_x = (SCREEN_WIDTH - total_w) // 2
        for i in range(DOCK_SLOTS_COUNT):
            self.dock_rects.append(RectBox(start_x + i * (slot_w + gap), DECK_TOP + 10, slot_w, slot_h))

        btn_y = DECK_TOP + 98
        btn_w, btn_h = 162, 58
        self.spawn_btns: List[Tuple[str, RectBox]] = [
            ("sniper", RectBox(16, btn_y, btn_w, btn_h)),
            ("gatling", RectBox(189, btn_y, btn_w, btn_h)),
            ("mortar", RectBox(362, btn_y, btn_w, btn_h)),
        ]

        up_y = DECK_TOP + 168
        self.btn_up_sniper = RectBox(16, up_y, 162, 46)
        self.btn_up_gatling = RectBox(189, up_y, 162, 46)
        self.btn_nova = RectBox(362, up_y, 162, 46)

        self.reset_game()
        Clock.schedule_interval(self.step, 1.0 / FPS)

    def reset_game(self):
        self.elixir = 2.0
        self.base_hp = 20
        self.max_base_hp = 20
        self.score = 0
        self.wave = 1
        self.kills = 0

        self.sniper_up_lvl = 1
        self.sniper_up_cost = 3
        self.gatling_up_lvl = 1
        self.gatling_up_cost = 4

        self.nova_charge = 0.0

        self.pad_units: List[Optional[DefenseUnit]] = [None] * len(TOWER_PADS)
        self.dock_units: List[Optional[DefenseUnit]] = [None] * DOCK_SLOTS_COUNT

        self.drag_source: Optional[Tuple[str, int]] = None
        self.drag_pos: Tuple[float, float] = (0.0, 0.0)

        self.enemies: List[LaneEnemy] = []
        self.projectiles: List[LaneProjectile] = []
        self.particles: List[Particle] = []
        self.shockwaves: List[Shockwave] = []
        self.popups: List[FloatingPopup] = []

        self.spawn_queue: List[str] = []
        self.spawn_timer = 0.95
        self.shake_mag = 0.0

        self.pad_units[0] = DefenseUnit("sniper", tier=1)
        self._queue_wave(self.wave)

    def _queue_wave(self, w: int):
        self.spawn_queue.clear()
        runners = 5 + w * 2
        swifts = max(1, (w - 1) * 2)
        brutes = max(0, (w - 1) * 2)
        for _ in range(runners):
            self.spawn_queue.append("runner")
        for _ in range(swifts):
            self.spawn_queue.append("swift")
        for _ in range(brutes):
            self.spawn_queue.append("brute")
        if w % 2 == 0:
            self.spawn_queue.append("boss")
        random.shuffle(self.spawn_queue)

    def _add_shake(self, amt: float):
        self.shake_mag = min(14.0, self.shake_mag + amt)

    def _spawn_burst(self, x: float, y: float, col: Tuple[float, float, float, float], count: int = 12):
        for _ in range(count):
            a = random.uniform(0, math.pi * 2)
            spd = random.uniform(45, 190)
            life = random.uniform(0.2, 0.55)
            self.particles.append(Particle(x, y, math.cos(a) * spd, math.sin(a) * spd, col, random.uniform(3, 6), life, life))

    def _spawn_unit_to_dock(self, utype: str) -> bool:
        cost = int(UNIT_META[utype]["cost"])
        if self.elixir < cost:
            return False
        free_idx = next((i for i, u in enumerate(self.dock_units) if u is None), None)
        if free_idx is None:
            self.popups.append(FloatingPopup(SCREEN_WIDTH / 2, DECK_TOP - 15, "DOCK FULL!", RED))
            return False
        self.elixir -= cost
        self.dock_units[free_idx] = DefenseUnit(utype, tier=1)
        self.audio.play("spawn")
        r = self.dock_rects[free_idx]
        self._spawn_burst(r.centerx, r.centery, UNIT_META[utype]["color"], 10)  # type: ignore
        return True

    def _get_unit_at(self, src: Tuple[str, int]) -> Optional[DefenseUnit]:
        kind, idx = src
        return self.pad_units[idx] if kind == "pad" else self.dock_units[idx]

    def _set_unit_at(self, src: Tuple[str, int], unit: Optional[DefenseUnit]):
        kind, idx = src
        if kind == "pad":
            self.pad_units[idx] = unit
        else:
            self.dock_units[idx] = unit

    def _get_pos_of(self, src: Tuple[str, int]) -> Tuple[float, float]:
        kind, idx = src
        if kind == "pad":
            return TOWER_PADS[idx]
        r = self.dock_rects[idx]
        return float(r.centerx), float(r.centery)

    def _find_drop_target(self, mx: float, my: float) -> Optional[Tuple[str, int]]:
        for i, pt in enumerate(TOWER_PADS):
            if dist(mx, my, pt[0], pt[1]) <= 34.0:
                return ("pad", i)
        for i, rect in enumerate(self.dock_rects):
            if rect.collidepoint(mx, my):
                return ("dock", i)
        return None

    def _handle_drop(self, src: Tuple[str, int], dst: Optional[Tuple[str, int]]):
        if dst is None or src == dst:
            return
        u_src = self._get_unit_at(src)
        if u_src is None:
            return
        u_dst = self._get_unit_at(dst)

        if u_dst is not None and u_dst.unit_type == u_src.unit_type and u_dst.tier == u_src.tier and u_dst.tier < 5:
            u_dst.tier += 1
            self._set_unit_at(src, None)
            self.audio.play("merge")
            px, py = self._get_pos_of(dst)
            self.shockwaves.append(Shockwave(px, py, 48.0, u_dst.color))
            self._spawn_burst(px, py, u_dst.color, 18)
            self.popups.append(FloatingPopup(px, py - 22, f"MERGED T{u_dst.tier}!", u_dst.color))
            self.score += 60 * u_dst.tier
            return

        self._set_unit_at(src, u_dst)
        self._set_unit_at(dst, u_src)
        self.audio.play("spawn")

    def _trigger_frost_nova(self):
        if self.nova_charge < 100.0:
            return
        self.nova_charge = 0.0
        self.audio.play("nova")
        self._add_shake(8.0)
        bx, by = LANE_POINTS[-1]
        self.shockwaves.append(Shockwave(bx, by, 420.0, ICE, 0.55, 0.55))
        for e in self.enemies:
            e.slow_timer = 3.5
            e.hp -= 25.0
            e.hit_flash = 0.12
            self._spawn_burst(e.x, e.y, ICE, 8)
        self.popups.append(FloatingPopup(SCREEN_WIDTH / 2, 290, "FROST NOVA!", ICE))

    def _to_logical_xy(self, touch) -> Tuple[float, float]:
        scale_x = SCREEN_WIDTH / max(1.0, float(self.width))
        scale_y = SCREEN_HEIGHT / max(1.0, float(self.height))
        lx = (touch.x - self.x) * scale_x
        ly = SCREEN_HEIGHT - ((touch.y - self.y) * scale_y)
        return lx, ly

    def on_touch_down(self, touch):
        mx, my = self._to_logical_xy(touch)
        if self.state == "TITLE":
            self.reset_game()
            self.state = "PLAYING"
            return True

        if self.state == "GUIDE":
            if self.btn_close_guide.collidepoint(mx, my):
                self.state = "PLAYING"
            return True

        if self.state == "GAME_OVER":
            self.reset_game()
            self.state = "PLAYING"
            return True

        if self.btn_guide.collidepoint(mx, my):
            self.drag_source = None
            self.state = "GUIDE"
            return True

        for utype, rect in self.spawn_btns:
            if rect.collidepoint(mx, my):
                self._spawn_unit_to_dock(utype)
                return True

        if self.btn_up_sniper.collidepoint(mx, my) and self.elixir >= self.sniper_up_cost:
            self.elixir -= self.sniper_up_cost
            self.sniper_up_lvl += 1
            self.sniper_up_cost += 2
            self.audio.play("merge")
            self.popups.append(FloatingPopup(self.btn_up_sniper.centerx, self.btn_up_sniper.y - 10, f"SNIPER LV.{self.sniper_up_lvl}", CYAN))
            return True

        if self.btn_up_gatling.collidepoint(mx, my) and self.elixir >= self.gatling_up_cost:
            self.elixir -= self.gatling_up_cost
            self.gatling_up_lvl += 1
            self.gatling_up_cost += 2
            self.audio.play("merge")
            self.popups.append(FloatingPopup(self.btn_up_gatling.centerx, self.btn_up_gatling.y - 10, f"GATLING LV.{self.gatling_up_lvl}", YELLOW))
            return True

        if self.btn_nova.collidepoint(mx, my) and self.nova_charge >= 100.0:
            self._trigger_frost_nova()
            return True

        for i, pt in enumerate(TOWER_PADS):
            if self.pad_units[i] is not None and dist(mx, my, pt[0], pt[1]) <= 28.0:
                self.drag_source = ("pad", i)
                self.drag_pos = (mx, my)
                touch.grab(self)
                return True

        for i, rect in enumerate(self.dock_rects):
            if self.dock_units[i] is not None and rect.collidepoint(mx, my):
                self.drag_source = ("dock", i)
                self.drag_pos = (mx, my)
                touch.grab(self)
                return True

        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current == self and self.drag_source is not None:
            self.drag_pos = self._to_logical_xy(touch)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current == self:
            touch.ungrab(self)
            if self.drag_source is not None:
                mx, my = self._to_logical_xy(touch)
                dst = self._find_drop_target(mx, my)
                self._handle_drop(self.drag_source, dst)
                self.drag_source = None
            return True
        return super().on_touch_up(touch)

    def update(self, dt: float):
        self.shake_mag = max(0.0, self.shake_mag - dt * 35.0)
        self.particles = [p for p in self.particles if p.update(dt)]
        self.shockwaves = [s for s in self.shockwaves if s.update(dt)]
        self.popups = [p for p in self.popups if p.update(dt)]

        if self.state != "PLAYING":
            return

        self.elixir = clamp(self.elixir + ELIXIR_REGEN_PER_SEC * dt, 0.0, MAX_ELIXIR)

        if self.spawn_queue:
            self.spawn_timer -= dt
            if self.spawn_timer <= 0.0:
                kind = self.spawn_queue.pop(0)
                self.enemies.append(LaneEnemy.create(kind, self.wave))
                self.spawn_timer = max(0.50, 1.05 - self.wave * 0.035)
        elif not self.enemies:
            self.wave += 1
            self.elixir = clamp(self.elixir + 0.5, 0.0, MAX_ELIXIR)
            self.popups.append(FloatingPopup(SCREEN_WIDTH / 2, 250, f"WAVE {self.wave}", YELLOW))
            self._queue_wave(self.wave)

        alive_enemies: List[LaneEnemy] = []
        for e in self.enemies:
            if e.update(dt):
                self.base_hp = max(0, self.base_hp - e.base_dmg)
                self.audio.play("base_hit")
                self._add_shake(9.0)
                self._spawn_burst(e.x, e.y, RED, 16)
                self.popups.append(FloatingPopup(e.x, e.y - 16, f"-{e.base_dmg} BASE", RED))
                if self.base_hp <= 0:
                    self.state = "GAME_OVER"
            else:
                alive_enemies.append(e)
        self.enemies = alive_enemies

        sniper_mult = 1.0 + (self.sniper_up_lvl - 1) * 0.22
        gatling_mult = 1.0 + (self.gatling_up_lvl - 1) * 0.22
        for idx, unit in enumerate(self.pad_units):
            if unit is not None:
                mult = sniper_mult if unit.unit_type == "sniper" else (gatling_mult if unit.unit_type == "gatling" else 1.0)
                unit.update_and_fire(dt, TOWER_PADS[idx], self.enemies, self.projectiles, self.audio, mult)

        active_projs: List[LaneProjectile] = []
        for pr in self.projectiles:
            if not pr.update(dt):
                continue
            hit = False
            for e in self.enemies:
                if e.hp > 0 and dist(pr.x, pr.y, e.x, e.y) <= pr.radius + e.radius:
                    hit = True
                    if pr.splash_radius > 0:
                        self.shockwaves.append(Shockwave(pr.x, pr.y, pr.splash_radius, pr.color, 0.22, 0.22))
                        for other in self.enemies:
                            if other.hp > 0 and dist(pr.x, pr.y, other.x, other.y) <= pr.splash_radius + other.radius:
                                other.hp -= pr.damage
                                other.hit_flash = 0.08
                                if pr.slow_duration > 0:
                                    other.slow_timer = max(other.slow_timer, pr.slow_duration)
                    else:
                        e.hp -= pr.damage
                        e.hit_flash = 0.07
                        if pr.slow_duration > 0:
                            e.slow_timer = max(e.slow_timer, pr.slow_duration)
                    self.audio.play("enemy_hit")
                    self._spawn_burst(pr.x, pr.y, pr.color, 5)
                    break
            if not hit:
                active_projs.append(pr)
        self.projectiles = active_projs

        surviving: List[LaneEnemy] = []
        for e in self.enemies:
            if e.hp <= 0:
                self.audio.play("enemy_die")
                self.kills += 1
                self.score += e.score_reward
                self.elixir = clamp(self.elixir + e.elixir_reward, 0.0, MAX_ELIXIR)
                self.nova_charge = clamp(self.nova_charge + (15.0 if e.kind == "boss" else 5.0), 0.0, 100.0)
                self._spawn_burst(e.x, e.y, e.color, 14 if e.kind != "boss" else 34)
                self.popups.append(FloatingPopup(e.x, e.y - 12, f"+{e.elixir_reward:.2f}", PURPLE))
            else:
                surviving.append(e)
        self.enemies = surviving

    def _shake_offset(self) -> Tuple[float, float]:
        if self.shake_mag <= 0.2:
            return 0.0, 0.0
        return random.uniform(-self.shake_mag, self.shake_mag), random.uniform(-self.shake_mag, self.shake_mag)

    def _poly_outline_coords(self, cx: float, cy: float, radius: float, sides: int, angle: float) -> List[float]:
        coords: List[float] = []
        for i in range(sides):
            a = angle + (2.0 * math.pi * i) / sides
            px = cx + math.cos(a) * radius
            py = to_ky(cy + math.sin(a) * radius)
            coords.extend([px, py])
        return coords

    def _draw_poly(
        self,
        cx: float,
        cy: float,
        radius: float,
        sides: int,
        angle: float,
        color: Tuple[float, float, float, float],
    ):
        verts: List[float] = []
        indices: List[int] = []
        for i in range(sides):
            a = angle + (2.0 * math.pi * i) / sides
            px = cx + math.cos(a) * radius
            py = to_ky(cy + math.sin(a) * radius)
            verts.extend([px, py, 0.0, 0.0])
            indices.append(i)
        Color(*color)
        Mesh(vertices=verts, indices=indices, mode="triangle_fan")

    def _draw_circle(
        self,
        cx: float,
        cy: float,
        radius: float,
        color: Tuple[float, float, float, float],
        outline: Optional[Tuple[float, float, float, float]] = None,
        width: float = 2.0,
    ):
        ky = to_ky(cy)
        Color(*color)
        Ellipse(pos=(cx - radius, ky - radius), size=(radius * 2.0, radius * 2.0))
        if outline is not None:
            Color(*outline)
            Line(circle=(cx, ky, radius), width=width)

    def _draw_rect(
        self,
        box: RectBox,
        fill: Tuple[float, float, float, float],
        border: Optional[Tuple[float, float, float, float]] = None,
        width: float = 2.0,
    ):
        ky_bottom = to_ky(box.bottom)
        Color(*fill)
        Rectangle(pos=(box.x, ky_bottom), size=(box.w, box.h))
        if border is not None:
            Color(*border)
            Line(rectangle=(box.x, ky_bottom, box.w, box.h), width=width)

    def _draw_label(
        self,
        text: str,
        cx: float,
        cy: float,
        color: Tuple[float, float, float, float],
        font_size: int = 13,
        align_left: bool = False,
        align_right: bool = False,
    ):
        lbl = CoreLabel(text=text, font_size=font_size, bold=True, color=color)
        lbl.refresh()
        tex = lbl.texture
        if tex is None:
            return
        w, h = tex.size
        if align_left:
            x = cx
        elif align_right:
            x = cx - w
        else:
            x = cx - w * 0.5
        y = to_ky(cy) - h * 0.5
        Color(1, 1, 1, 1)
        Rectangle(texture=tex, pos=(x, y), size=(w, h))

    def _draw_unit_art(self, unit: DefenseUnit, cx: float, cy: float, show_name: bool = True):
        rad = 15.0 + (unit.tier - 1) * 1.2
        angle = unit.aim_angle
        col = unit.color

        self._draw_circle(cx, cy + 4.5, rad * 1.05, SHADOW_COLOR)

        if unit.unit_type == "sniper":
            sq_ang = angle + math.pi / 4.0
            self._draw_poly(cx, cy, rad * 1.08, 4, sq_ang, BLACK)
            Color(*col)
            Line(points=self._poly_outline_coords(cx, cy, rad * 1.08, 4, sq_ang), close=True, width=2.2)
            self._draw_poly(cx, cy, rad * 0.45, 4, angle, col)
            bx = cx + math.cos(angle) * (rad + 10)
            by = cy + math.sin(angle) * (rad + 10)
            Color(*WHITE)
            Line(points=[cx, to_ky(cy), bx, to_ky(by)], width=2.5)
        elif unit.unit_type == "gatling":
            self._draw_poly(cx, cy, rad * 1.16, 3, angle, BLACK)
            Color(*col)
            Line(points=self._poly_outline_coords(cx, cy, rad * 1.16, 3, angle), close=True, width=2.2)
            self._draw_circle(cx, cy, 4.0, WHITE)
            px = -math.sin(angle) * 4.5
            py = math.cos(angle) * 4.5
            Color(*WHITE)
            for sign in (-1.0, 1.0):
                sx, sy = cx + px * sign, cy + py * sign
                ex, ey = sx + math.cos(angle) * (rad + 6), sy + math.sin(angle) * (rad + 6)
                Line(points=[sx, to_ky(sy), ex, to_ky(ey)], width=1.6)
        else:
            self._draw_poly(cx, cy, rad * 1.10, 6, angle, BLACK)
            Color(*col)
            Line(points=self._poly_outline_coords(cx, cy, rad * 1.10, 6, angle), close=True, width=2.2)
            Line(points=self._poly_outline_coords(cx, cy, rad * 0.62, 6, -angle * 0.5), close=True, width=1.6)
            bx = cx + math.cos(angle) * (rad + 7)
            by = cy + math.sin(angle) * (rad + 7)
            Color(*WHITE)
            Line(points=[cx, to_ky(cy), bx, to_ky(by)], width=3.5)

        self._draw_label(f"T{unit.tier}", cx, cy, WHITE, font_size=11)
        if show_name:
            self._draw_label(str(UNIT_META[unit.unit_type]["name"]), cx, cy + rad + 12, col, font_size=11)

    def _draw_lane_and_pads(self, shake: Tuple[float, float]):
        self._draw_rect(RectBox(0, ARENA_TOP, SCREEN_WIDTH, ARENA_BOTTOM - ARENA_TOP), BG_DARK)
        tile = 54
        for gx in range(0, SCREEN_WIDTH, tile):
            for gy in range(ARENA_TOP, ARENA_BOTTOM, tile):
                if ((gx // tile) + (gy // tile)) % 2 == 0:
                    self._draw_rect(RectBox(gx + shake[0], gy + shake[1], tile, tile), BG_TILE_ALT)
                self._draw_circle(gx + shake[0], gy + shake[1], 2.0, BG_DECOR)

        pts_ky: List[float] = []
        shadow_ky: List[float] = []
        for p in LANE_POINTS:
            px, py = p[0] + shake[0], p[1] + shake[1]
            pts_ky.extend([px, to_ky(py)])
            shadow_ky.extend([px, to_ky(py + 7)])

        Color(*SHADOW_COLOR)
        Line(points=shadow_ky, width=18)
        Color(*LANE_CURB_DARK)
        Line(points=pts_ky, width=17)
        Color(*LANE_CURB_LIGHT)
        Line(points=pts_ky, width=15)
        Color(*BG_LANE)
        Line(points=pts_ky, width=13)
        Color(*BG_LANE_INNER)
        Line(points=pts_ky, width=8)
        Color(*LANE_CENTER)
        Line(points=pts_ky, width=1.5)

        sx, sy = LANE_POINTS[0][0] + shake[0], LANE_POINTS[0][1] + shake[1]
        self._draw_circle(sx, sy, 18.0, SHADOW_COLOR)
        self._draw_circle(sx, sy, 7.0, RED, outline=RED, width=2.0)

        bx, by = LANE_POINTS[-1][0] + shake[0], LANE_POINTS[-1][1] + shake[1]
        self._draw_circle(bx, by, 24.0, SHADOW_COLOR)
        self._draw_poly(bx, by, 22.0, 6, 0.2, GREEN)
        self._draw_circle(bx, by, 8.0, GREEN)
        self._draw_label("BASE", bx, by + 34, GREEN, font_size=12)

        for idx, pt in enumerate(TOWER_PADS):
            px, py = pt[0] + shake[0], pt[1] + shake[1]
            u = self.pad_units[idx]
            pad_col = u.color if u is not None else SLOT_BORDER
            self._draw_circle(px, py + 3.0, 21.0, LANE_CURB_DARK)
            self._draw_circle(px, py, 21.0, SLOT_BG, outline=pad_col, width=2.0)
            if u is not None:
                ux = px - math.cos(u.aim_angle) * u.recoil
                uy = py - math.sin(u.aim_angle) * u.recoil
                self._draw_unit_art(u, ux, uy, show_name=True)

    def _draw_top_hud(self):
        self._draw_rect(RectBox(0, 0, SCREEN_WIDTH, TOP_BAR_H), PANEL_BG)
        Color(*LANE_BORDER)
        Line(points=[0, to_ky(TOP_BAR_H), SCREEN_WIDTH, to_ky(TOP_BAR_H)], width=1.5)

        base_col = GREEN if self.base_hp > 6 else RED
        self._draw_label(f"BASE: {self.base_hp}/{self.max_base_hp}", 16, 32, base_col, font_size=18, align_left=True)
        self._draw_label(f"WAVE {self.wave}", SCREEN_WIDTH * 0.5 - 20, 36, CYAN, font_size=18)
        self._draw_label(f"SCORE {self.score}", SCREEN_WIDTH - 16, 48, YELLOW, font_size=15, align_right=True)

        self._draw_rect(self.btn_guide, SLOT_BG, border=CYAN, width=1.5)
        self._draw_label("GUIDE", self.btn_guide.centerx, self.btn_guide.centery, CYAN, font_size=11)

    def _draw_bottom_deck(self):
        self._draw_rect(RectBox(0, DECK_TOP, SCREEN_WIDTH, SCREEN_HEIGHT - DECK_TOP), PANEL_BG)
        Color(*CYAN)
        Line(points=[0, to_ky(DECK_TOP), SCREEN_WIDTH, to_ky(DECK_TOP)], width=2.0)

        bar_x, bar_y, bar_w, bar_h = 16, DECK_TOP - 22, SCREEN_WIDTH - 32, 16
        self._draw_rect(RectBox(bar_x, bar_y, bar_w, bar_h), rgb(20, 24, 36), border=WHITE, width=1.2)
        fill_w = bar_w * clamp(self.elixir / MAX_ELIXIR, 0.0, 1.0)
        if fill_w > 0:
            self._draw_rect(RectBox(bar_x, bar_y, fill_w, bar_h), PURPLE)
        self._draw_label(f"ELIXIR: {self.elixir:.1f} / {int(MAX_ELIXIR)}", bar_x + 8, bar_y + 8, WHITE, font_size=11, align_left=True)

        for i, rect in enumerate(self.dock_rects):
            u = self.dock_units[i]
            bcol = u.color if u is not None else SLOT_BORDER
            self._draw_rect(rect, SLOT_BG, border=bcol, width=1.5)
            if u is not None:
                self._draw_unit_art(u, rect.centerx, rect.centery - 6.0, show_name=False)
                self._draw_label(str(UNIT_META[u.unit_type]["name"]), rect.centerx, rect.bottom - 10, u.color, font_size=11)

        for utype, rect in self.spawn_btns:
            meta = UNIT_META[utype]
            cost = int(meta["cost"])
            col = meta["color"]  # type: ignore
            can_buy = self.elixir >= cost
            self._draw_rect(rect, SLOT_BG if can_buy else rgb(22, 24, 30), border=col if can_buy else GRAY, width=1.5)
            self._draw_label(f"{meta['name']} ({cost})", rect.centerx, rect.y + 18, col if can_buy else GRAY, font_size=14)
            self._draw_label(f"{meta['shape_name']} | {meta['tag']}", rect.centerx, rect.y + 40, WHITE if can_buy else GRAY, font_size=11)

        self._draw_action_btn(self.btn_up_sniper, f"SNIPER+ ({self.sniper_up_cost})", f"LVL {self.sniper_up_lvl}", CYAN, self.elixir >= self.sniper_up_cost)
        self._draw_action_btn(self.btn_up_gatling, f"GATLING+ ({self.gatling_up_cost})", f"LVL {self.gatling_up_lvl}", YELLOW, self.elixir >= self.gatling_up_cost)
        self._draw_action_btn(self.btn_nova, "FROST NOVA", f"{int(self.nova_charge)}%", ICE, self.nova_charge >= 100.0)

    def _draw_action_btn(self, rect: RectBox, title: str, sub: str, col: Tuple[float, float, float, float], active: bool):
        self._draw_rect(rect, SLOT_BG if active else rgb(20, 23, 30), border=col if active else GRAY, width=1.5)
        self._draw_label(title, rect.centerx, rect.y + 14, col if active else GRAY, font_size=11)
        self._draw_label(sub, rect.centerx, rect.y + 32, WHITE if active else GRAY, font_size=11)

    def _draw_guide_modal(self):
        self._draw_rect(RectBox(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT), rgb(8, 11, 18, 0.95))
        self._draw_label("UNIT & TACTICS GUIDE", SCREEN_WIDTH * 0.5, 75, CYAN, font_size=20)

        entries = [
            ("sniper", "SNIPER [SQUARE]", "Cost 3 - 1 heavy shot, high dmg", CYAN, 165),
            ("gatling", "GATLING [TRIANGLE]", "Cost 5 - Rapid spray, fast shots", YELLOW, 265),
            ("mortar", "MORTAR [HEXAGON]", "Cost 7 - AoE blast + slow enemies", GREEN, 365),
        ]
        for utype, title_txt, desc_txt, col, yy in entries:
            dummy = DefenseUnit(utype, tier=1, aim_angle=-0.4)
            self._draw_unit_art(dummy, 62.0, float(yy), show_name=False)
            self._draw_label(title_txt, 105, yy - 14, col, font_size=15, align_left=True)
            self._draw_label(desc_txt, 105, yy + 8, WHITE, font_size=12, align_left=True)

        rules = [
            "MERGE: Drag same type & tier onto each other -> Tier up!",
            "DEPLOY: Drag dock units onto lane pads to fire.",
            "ELIXIR: Slow regen + enemy kills + wave bonus.",
            "NOVA: 100% slows & damages all lane enemies.",
        ]
        for i, line in enumerate(rules):
            self._draw_label(line, 32, 455 + i * 34, GRAY if i % 2 else WHITE, font_size=12, align_left=True)

        self._draw_rect(self.btn_close_guide, SLOT_BG, border=GREEN, width=2.0)
        self._draw_label("BACK TO GAME", self.btn_close_guide.centerx, self.btn_close_guide.centery, GREEN, font_size=15)

    def render(self):
        self.canvas.clear()
        with self.canvas:
            if self.state == "TITLE":
                self._draw_rect(RectBox(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT), BG_DARK)
                self._draw_label("AEGIS PATH", SCREEN_WIDTH * 0.5, 340, CYAN, font_size=32)
                self._draw_label("MERGE & ELIXIR DEFENSE", SCREEN_WIDTH * 0.5, 385, PURPLE, font_size=18)
                self._draw_label("TAP ANYWHERE TO START", SCREEN_WIDTH * 0.5, 520, GREEN, font_size=18)
                return

            shake = self._shake_offset()
            self._draw_lane_and_pads(shake)

            for pr in self.projectiles:
                cx, cy = pr.x + shake[0], pr.y + shake[1]
                self._draw_circle(cx, cy + 3.0, pr.radius * 0.8, SHADOW_COLOR)
                self._draw_circle(cx, cy, pr.radius, pr.color)
                self._draw_circle(cx, cy, max(2.0, pr.radius * 0.45), WHITE)

            for e in self.enemies:
                cx, cy = e.x + shake[0], e.y + shake[1]
                self._draw_circle(cx, cy + 4.5, e.radius, SHADOW_COLOR)
                col = WHITE if e.hit_flash > 0 else (ICE if e.slow_timer > 0 else e.color)
                sides = 8 if e.kind == "boss" else (6 if e.kind == "brute" else (3 if e.kind == "swift" else 4))
                self._draw_poly(cx, cy, e.radius, sides, e.spin, BLACK)
                Color(*col)
                Line(points=self._poly_outline_coords(cx, cy, e.radius, sides, e.spin), close=True, width=2.2)
                self._draw_circle(cx, cy, max(3.0, e.radius * 0.35), col)

                bw = max(24.0, e.radius * 2.1)
                bh = 5.0 if e.kind != "boss" else 7.0
                bx = cx - bw * 0.5
                by = cy - e.radius - 12.0
                self._draw_rect(RectBox(bx, by, bw, bh), rgb(35, 40, 55))
                ratio = clamp(e.hp / max(1.0, e.max_hp), 0.0, 1.0)
                self._draw_rect(RectBox(bx, by, bw * ratio, bh), col)
                if e.kind == "boss":
                    self._draw_label("BOSS", cx, by - 10, PINK, font_size=11)

            for sw in self.shockwaves:
                prog = 1.0 - clamp(sw.life / sw.max_life, 0.0, 1.0)
                r = 6.0 + sw.max_radius * prog
                alpha = (1.0 - prog) * 0.75
                c = (sw.color[0], sw.color[1], sw.color[2], alpha)
                self._draw_circle(sw.x + shake[0], sw.y + shake[1], r, (0, 0, 0, 0), outline=c, width=2.2)

            for p in self.particles:
                ratio = clamp(p.life / p.max_life, 0.0, 1.0)
                c = (p.color[0] * ratio, p.color[1] * ratio, p.color[2] * ratio, ratio)
                self._draw_circle(p.x + shake[0], p.y + shake[1], max(1.5, p.size * ratio), c)

            for pop in self.popups:
                alpha = clamp(pop.life / 0.75, 0.0, 1.0)
                c = (pop.color[0], pop.color[1], pop.color[2], alpha)
                self._draw_label(pop.text, pop.x + shake[0], pop.y + shake[1], c, font_size=14)

            self._draw_top_hud()
            self._draw_bottom_deck()

            if self.drag_source is not None:
                du = self._get_unit_at(self.drag_source)
                if du is not None:
                    self._draw_unit_art(du, self.drag_pos[0], self.drag_pos[1], show_name=True)

            if self.state == "GUIDE":
                self._draw_guide_modal()
            elif self.state == "GAME_OVER":
                self._draw_rect(RectBox(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT), rgb(10, 8, 16, 0.84))
                self._draw_label("BASE FALLEN", SCREEN_WIDTH * 0.5, 360, RED, font_size=30)
                self._draw_label(f"SCORE: {self.score}   |   WAVE: {self.wave}", SCREEN_WIDTH * 0.5, 420, WHITE, font_size=17)
                self._draw_label("TAP TO PLAY AGAIN", SCREEN_WIDTH * 0.5, 500, CYAN, font_size=16)

    def step(self, dt: float):
        self.update(min(0.05, dt))
        self.render()


class AegisPathApp(App):
    def build(self):
        self.title = TITLE
        Window.clearcolor = BG_DARK
        self.game_widget = AegisPathWidget()
        return self.game_widget

    def on_stop(self):
        if hasattr(self, "game_widget"):
            self.game_widget.audio.cleanup()


if __name__ == "__main__":
    AegisPathApp().run()
