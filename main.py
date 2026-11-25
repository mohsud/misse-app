"""
AEGIS PATH: MERGE & ELIXIR (KIVY EDITION - NO PYGAME REQUIRED)
Portrait Mobile Lane Defense + Merge + Elixir Game in Python & Kivy.
Touch/Mouse-only controls.
"""

import array
import io
import json
import math
import os
import random
import tempfile
import traceback
import wave
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.core.image import Image as CoreImage
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, PopMatrix, PushMatrix, Rectangle, Rotate, Scale, Translate
from kivy.uix.widget import Widget
from kivy.utils import platform

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


BG_DARK = rgb(7, 10, 18)
BG_TILE_ALT = rgb(11, 16, 27)
BG_GRID_ACCENT = rgb(22, 32, 50, 0.50)
BG_LANE = rgb(19, 27, 44)
LANE_CENTER = rgb(0, 215, 255, 0.72)
LANE_INNER_DASH = rgb(155, 240, 255, 0.85)
LANE_BORDER = rgb(44, 72, 112, 0.95)
LANE_GLOW = rgb(0, 180, 255, 0.14)
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
BASE_ELIXIR_REGEN_PER_SEC = 0.30
ELIXIR_REGEN_PER_SEC = BASE_ELIXIR_REGEN_PER_SEC

DIFFICULTY_CONFIGS: Dict[str, Dict[str, object]] = {
    "EASY": {
        "label": "EASY",
        "color": GREEN,
        "elixir_regen": BASE_ELIXIR_REGEN_PER_SEC * 1.5,
        "enemy_speed_mult": 0.70,
        "enemy_hp_mult": 0.80,
        "enemy_base_dmg_mult": 0.90,
        "boss6_dmg_mult": 0.85,
    },
    "MEDIUM": {
        "label": "MEDIUM",
        "color": YELLOW,
        "elixir_regen": BASE_ELIXIR_REGEN_PER_SEC,
        "enemy_speed_mult": 1.0,
        "enemy_hp_mult": 1.0,
        "enemy_base_dmg_mult": 1.0,
        "boss6_dmg_mult": 1.0,
    },
    "HARD": {
        "label": "HARD",
        "color": RED,
        "elixir_regen": BASE_ELIXIR_REGEN_PER_SEC,
        "enemy_speed_mult": 1.33,
        "enemy_hp_mult": 1.30,
        "enemy_base_dmg_mult": 1.33,
        "boss6_dmg_mult": 1.35,
    },
}
DIFFICULTY_ORDER = ["EASY", "MEDIUM", "HARD"]
CURRENT_DIFFICULTY = "MEDIUM"


def get_difficulty_cfg(diff: Optional[str] = None) -> Dict[str, object]:
    key = diff or CURRENT_DIFFICULTY
    return DIFFICULTY_CONFIGS.get(key, DIFFICULTY_CONFIGS["MEDIUM"])


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
    (120.0, 168.0),
    (305.0, 168.0),
    (430.0, 255.0),
    (275.0, 255.0),
    (145.0, 355.0),
    (285.0, 355.0),
    (265.0, 458.0),
    (385.0, 535.0),
]

DOCK_SLOTS_COUNT = 6

MAPS = [
    {"name": "MAP 1 - AEGIS PATH", "lane": LANE_POINTS, "pads": TOWER_PADS},
    {"name": "MAP 2 - VERTICAL",
     "lane": [(270.0, 92.0), (270.0, 570.0)],
     "pads": [(205.0, 145.0), (335.0, 145.0), (205.0, 245.0), (335.0, 245.0),
              (205.0, 345.0), (335.0, 345.0), (205.0, 455.0), (335.0, 455.0)]},
    {"name": "MAP 3 - SPIRAL",
     "lane": [(65.0, 100.0), (65.0, 540.0), (475.0, 540.0),
              (475.0, 100.0), (160.0, 100.0), (160.0, 430.0),
              (380.0, 430.0), (380.0, 220.0), (260.0, 220.0),
              (260.0, 340.0)],
     "pads": [(112.0, 250.0), (427.0, 300.0),
              (210.0, 165.0), (210.0, 350.0),
              (320.0, 165.0), (320.0, 350.0),
              (270.0, 485.0)]},
    {"name": "MAP 4 - THREE RUNS",
     "lane": [(80.0, 105.0), (80.0, 500.0), (250.0, 500.0),
              (250.0, 105.0), (420.0, 105.0), (420.0, 500.0)],
     "pads": [(165.0, 205.0), (165.0, 305.0), (165.0, 405.0),
              (335.0, 205.0), (335.0, 305.0), (335.0, 405.0)]},
]
CURRENT_MAP = 0


# ==============================================================================
# 3. TURRET, ENEMY & GUIDE SPRITE ASSETS LOADER + SAVE DATA
# ==============================================================================

TURRET_FILE_PREFIX: Dict[str, str] = {
    "sniper": "sniper",
    "gatling": "machine_gun",
    "mortar": "cannon",
}

ENEMY_FILE_NAMES: Dict[str, str] = {
    "swift": "enemy_1_small_triangle.png",
    "runner": "enemy_2_diamond.png",
    "brute": "enemy_3_round_drone.png",
    "spiked": "enemy_4_spiked_drone.png",
    "boss": "enemy_5_boss.png",
    "boss6": "boss.png",
    "saboteur": "en7.png",
}

ENEMY_FALLBACK_COLORS: Dict[str, Tuple[float, float, float, float]] = {
    "runner": RED,
    "swift": ORANGE,
    "brute": PURPLE,
    "spiked": CYAN,
    "saboteur": ORANGE,
    "boss": PINK,
    "boss6": PURPLE,
}


def resolve_base_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def resolve_assets_dir() -> str:
    return os.path.join(resolve_base_dir(), "assets")


def resolve_save_path() -> str:
    return os.path.join(resolve_base_dir(), "aegis_save.json")


def load_best_stats() -> Tuple[int, int]:
    path = resolve_save_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return int(data.get("best_score", 0)), int(data.get("best_wave", 1))
        except Exception:
            pass
    return 0, 1


def save_best_stats(best_score: int, best_wave: int):
    path = resolve_save_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"best_score": int(best_score), "best_wave": int(best_wave)}, f)
    except Exception:
        pass


def load_texture_by_name(filename: str) -> Optional[object]:
    for candidate in (
        os.path.join(resolve_assets_dir(), filename),
        os.path.join(resolve_base_dir(), filename),
    ):
        if os.path.exists(candidate):
            try:
                img = CoreImage(candidate)
                if img.texture is not None:
                    return img.texture
            except Exception as exc:
                print(f"[ASSET ERROR] {candidate}: {exc}")
    return None


def load_turret_textures() -> Dict[Tuple[str, int], object]:
    textures: Dict[Tuple[str, int], object] = {}
    for unit_type, suffix in TURRET_FILE_PREFIX.items():
        for tier in range(1, 6):
            tex = load_texture_by_name(f"T{tier}_{suffix}.png")
            if tex is not None:
                textures[(unit_type, tier)] = tex
    return textures


def load_enemy_textures() -> Dict[str, object]:
    textures: Dict[str, object] = {}
    for enemy_kind, filename in ENEMY_FILE_NAMES.items():
        tex = load_texture_by_name(filename)
        if tex is not None:
            textures[enemy_kind] = tex
    return textures


def load_info_texture() -> Optional[object]:
    return load_texture_by_name("info.png")


def load_info2_texture() -> Optional[object]:
    return load_texture_by_name("info2.png")


# ==============================================================================
# 4. PROCEDURAL WAV AUDIO ENGINE VIA KIVY SOUNDLOADER
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
        self._make_wav_file("emp", 0.22, 520, 130, "saw", 0.22, 1.1)

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
# 5. VISUAL FX: PARTICLES, SHOCKWAVES, IMPACT FLASHES & FLOATING LABELS
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
class ImpactFlash:
    x: float
    y: float
    dx: float
    dy: float
    color: Tuple[float, float, float, float]
    length: float = 14.0
    width: float = 2.6
    life: float = 0.11
    max_life: float = 0.11

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


@dataclass
class WaveWarningAlert:
    kind: str
    title: str
    subtitle: str
    color: Tuple[float, float, float, float]
    life: float = 3.2
    max_life: float = 3.2

    def update(self, dt: float) -> bool:
        self.life -= dt
        return self.life > 0


# ==============================================================================
# 6. LANE ENEMIES & PROJECTILES
# ==============================================================================

def _wave_hp_scale(wave: int) -> float:
    if wave == 1:
        return 0.55
    if wave == 2:
        return 0.68
    if wave <= 10:
        return 0.78 + (wave - 3) * 0.14
    if wave <= 15:
        base_10 = 0.78 + 7 * 0.14
        return base_10 + (wave - 10) * 0.24
    if wave <= 30:
        base_15 = (0.78 + 7 * 0.14) + 5 * 0.24
        return base_15 + (wave - 15) * 0.38
    base_30 = ((0.78 + 7 * 0.14) + 5 * 0.24) + 15 * 0.38
    return base_30 + (wave - 30) * 0.65


def build_wave_sequence(w: int) -> List[str]:
    if w == 1:
        return ["runner"] * 5
    if w == 2:
        return ["runner"] * 5 + ["swift"] * 2

    runners = 5 + w * 2
    swifts = max(1, (w - 1) * 2)
    brutes = max(0, (w - 2) * 2) if w <= 10 else max(0, (w - 1) * 2)
    spiked = max(0, (w - 4) * 2) if w <= 10 else max(0, (w - 2) * 2)
    saboteurs = max(1, 1 + (w - 10) // 6) if (w >= 10 and (w - 10) % 3 == 0) else 0
    has_boss = (w % 2 == 0) or (w >= 3)

    seq: List[str] = []
    max_len = max(runners, swifts, brutes, spiked, saboteurs)
    for i in range(max_len):
        if i < runners:
            seq.append("runner")
        if i < swifts and i % 2 == 0:
            seq.append("swift")
        if i < brutes and i % 2 == 1:
            seq.append("brute")
        if i < spiked and i % 3 == 2:
            seq.append("spiked")
        if i < saboteurs and i % 2 == 0:
            seq.append("saboteur")
    if has_boss:
        seq.append("boss")
    if w >= 15 and w % 5 == 0:
        seq.append("boss6")
    if w > 30:
        extra_pack = ["saboteur", "brute", "spiked"] * min(5, 1 + (w - 30) // 3)
        seq.extend(extra_pack)
    return seq


def summarize_wave_counts(w: int) -> List[Tuple[str, int]]:
    seq = build_wave_sequence(w)
    counts: Dict[str, int] = {}
    order: List[str] = []
    for kind in seq:
        if kind not in counts:
            counts[kind] = 0
            order.append(kind)
        counts[kind] += 1
    return [(k, counts[k]) for k in order]


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
    facing_angle: float = 0.0
    slow_timer: float = 0.0
    hit_flash: float = 0.0
    spin: float = 0.0
    spin_direction: float = 1.0
    tower_attack_timer: float = 2.0
    saboteur_timer: float = 3.0
    glow_timer: float = 0.0

    @classmethod
    def create(cls, kind: str, wave: int) -> "LaneEnemy":
        cfg = get_difficulty_cfg()
        hp_mult = float(cfg["enemy_hp_mult"])
        spd_mult = float(cfg["enemy_speed_mult"])
        dmg_mult = float(cfg["enemy_base_dmg_mult"])

        scale = _wave_hp_scale(wave) * hp_mult
        if wave <= 2:
            wave_spd_factor = 0.85 if wave == 1 else 0.90
        elif wave <= 10:
            wave_spd_factor = 0.92 + (wave - 3) * 0.025
        elif wave <= 15:
            wave_spd_factor = 1.12 + (wave - 10) * 0.045
        elif wave <= 30:
            wave_spd_factor = 1.35 + (wave - 15) * 0.035
        else:
            wave_spd_factor = min(2.65, 1.875 + (wave - 30) * 0.045)

        specs = {
            "runner": (88.0, 58.0, 13.0, RED, 1, 0.06, 25),
            "swift": (62.0, 86.0, 11.0, ORANGE, 1, 0.08, 35),
            "brute": (235.0, 39.0, 18.0, PURPLE, 2, 0.15, 70),
            "spiked": (310.0, 48.0, 19.0, CYAN, 2, 0.18, 90),
            "saboteur": (215.0, 46.0, 17.0, ORANGE, 2, 0.16, 85),
            "boss": (1100.0, 30.0, 25.0, PINK, 6, 0.45, 300),
            "boss6": (1650.0, 24.0, 31.0, PURPLE, 8, 0.70, 500),
        }
        hp, spd, rad, col, bdmg, rew, scr = specs[kind]
        adj_bdmg = max(1, int(round(bdmg * dmg_mult)))
        start_x, start_y = LANE_POINTS[0]
        if len(LANE_POINTS) > 1:
            first_dx = LANE_POINTS[1][0] - start_x
            first_dy = LANE_POINTS[1][1] - start_y
            initial_heading = (
                180.0
                if (kind == "saboteur" and first_dx < 0)
                else (0.0 if kind == "saboteur" else -math.degrees(math.atan2(first_dy, first_dx)))
            )
        else:
            initial_heading = 0.0
        return cls(
            kind=kind,
            max_hp=hp * scale,
            hp=hp * scale,
            speed=spd * wave_spd_factor * spd_mult,
            radius=rad,
            color=col,
            base_dmg=adj_bdmg,
            elixir_reward=rew,
            score_reward=scr,
            x=start_x,
            y=start_y,
            facing_angle=initial_heading,
        )

    def update(self, dt: float) -> bool:
        self.hit_flash = max(0.0, self.hit_flash - dt)
        self.glow_timer = max(0.0, self.glow_timer - dt)
        if self.kind != "saboteur":
            spin_rate = 4.5 if self.kind in ("swift", "spiked") else 1.8
            self.spin += dt * spin_rate * self.spin_direction

        mult = 1.0
        if self.slow_timer > 0:
            self.slow_timer -= dt
            mult = 0.42

        move_left = self.speed * mult * dt
        while move_left > 0 and self.seg_idx < len(LANE_POINTS) - 1:
            tx, ty = LANE_POINTS[self.seg_idx + 1]
            dx = tx - self.x
            dy = ty - self.y
            d = math.hypot(dx, dy)
            if d > 0:
                if self.kind == "saboteur":
                    self.facing_angle = 180.0 if dx < 0 else 0.0
                else:
                    self.facing_angle = -math.degrees(math.atan2(dy, dx))
                if abs(dx) >= abs(dy):
                    self.spin_direction = 1.0 if dx > 0 else -1.0
                else:
                    self.spin_direction = 1.0 if dy > 0 else -1.0
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
    unit_type: str = "sniper"
    tier: int = 1
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
# 7. DEFENSIVE UNITS & MERGE PROGRESSION
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
    hp: float = 0.0
    max_hp: float = 0.0
    cooldown: float = 0.0
    aim_angle: float = 0.0
    recoil: float = 0.0
    disabled_timer: float = 0.0
    overdrive_timer: float = 0.0

    def __post_init__(self):
        tier_hp = {1: 100.0, 2: 150.0, 3: 225.0, 4: 337.0, 5: 506.0}
        self.max_hp = tier_hp.get(self.tier, 100.0)
        if self.hp <= 0:
            self.hp = self.max_hp

    @property
    def color(self) -> Tuple[float, float, float, float]:
        tier_cols = {
            1: UNIT_META[self.unit_type]["color"],
            2: BLUE,
            3: PURPLE,
            4: PINK,
        }
        return tier_cols.get(self.tier, YELLOW)  # type: ignore

    def get_refund_elixir(self) -> float:
        base_cost = int(UNIT_META[self.unit_type]["cost"])
        return float(max(1, (base_cost * self.tier) // 2))

    def get_damage(self, type_bonus_mult: float) -> float:
        base = float(UNIT_META[self.unit_type]["base_dmg"])
        tier_mult = 1.75 ** (self.tier - 1)
        return base * tier_mult * type_bonus_mult

    def get_fire_rate(self) -> float:
        base_rate = float(UNIT_META[self.unit_type]["fire_rate"])
        if self.unit_type == "gatling":
            rate = max(0.09, base_rate * (0.92 ** (self.tier - 1)))
        else:
            rate = max(0.35, base_rate * (0.94 ** (self.tier - 1)))
        if self.overdrive_timer > 0.0:
            rate = max(0.06, rate * 0.68)
        return rate

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
        self.overdrive_timer = max(0.0, self.overdrive_timer - dt)
        if self.disabled_timer > 0.0:
            self.disabled_timer = max(0.0, self.disabled_timer - dt)
            return

        rng = self.get_range()
        best_enemy: Optional[LaneEnemy] = None
        best_distance = float("inf")

        for e in enemies:
            if e.hp <= 0:
                continue
            d = dist(pos[0], pos[1], e.x, e.y)
            if d <= rng and d < best_distance:
                best_distance = d
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
                            unit_type="sniper",
                            tier=self.tier,
                            radius=8.5 + self.tier,
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
                            unit_type="gatling",
                            tier=self.tier,
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
                            unit_type="mortar",
                            tier=self.tier,
                            radius=7.0,
                            splash_radius=60.0 + self.tier * 7.0,
                            slow_duration=1.3 + self.tier * 0.2,
                            target=best_enemy,
                        )
                    )


# ==============================================================================
# 8. KIVY CANVAS WIDGET & GAME ENGINE
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
        self.pos = (0, 0)
        self.size = (Window.width, Window.height)

        self.state = "TITLE"
        self._state_before_guide = "TITLE"
        self._text_cache: Dict[Tuple[str, int], Tuple[object, int, int]] = {}
        self.best_score, self.best_wave = load_best_stats()

        self.audio = AudioEngine()
        self.turret_textures: Dict[Tuple[str, int], object] = load_turret_textures()
        self.enemy_textures: Dict[str, object] = load_enemy_textures()
        self.healer_texture: Optional[object] = load_texture_by_name("hel.png")
        self.info_texture: Optional[object] = load_info_texture()
        self.info2_texture: Optional[object] = load_info2_texture()

        self.btn_guide = RectBox(SCREEN_WIDTH - 92, 10, 78, 24)
        self.difficulty_rects = [RectBox(44 + i * 156, 200, 140, 44) for i in range(3)]
        self.map_select_rects = [RectBox(54, 275 + i * 88, 432, 62) for i in range(4)]
        self.btn_pause = RectBox(SCREEN_WIDTH - 92, 40, 78, 24)
        self.btn_skip_wave = RectBox(SCREEN_WIDTH - 104, ARENA_TOP + 8, 94, 28)
        self.btn_swap = RectBox(SCREEN_WIDTH - 104, ARENA_TOP + 42, 94, 26)
        self.btn_close_guide = RectBox(SCREEN_WIDTH // 2 - 90, SCREEN_HEIGHT - 86, 180, 48)
        self.btn_sell = RectBox(SCREEN_WIDTH // 2 - 96, DECK_TOP - 36, 192, 30)

        self.dock_rects: List[RectBox] = []
        slot_w, slot_h = 74, 78
        gap = 10
        total_w = DOCK_SLOTS_COUNT * slot_w + (DOCK_SLOTS_COUNT - 1) * gap
        start_x = (SCREEN_WIDTH - total_w) // 2
        for i in range(DOCK_SLOTS_COUNT):
            self.dock_rects.append(RectBox(start_x + i * (slot_w + gap), DECK_TOP + 10, slot_w, slot_h))

        sbtn_y = DECK_TOP + 98
        btn_w, btn_h = 162, 58
        self.spawn_btns: List[Tuple[str, RectBox]] = [
            ("sniper", RectBox(16, sbtn_y, btn_w, btn_h)),
            ("gatling", RectBox(189, sbtn_y, btn_w, btn_h)),
            ("mortar", RectBox(362, sbtn_y, btn_w, btn_h)),
        ]

        up_y = DECK_TOP + 168
        self.btn_up_sniper = RectBox(16, up_y, btn_w, 46)
        self.btn_up_gatling = RectBox(189, up_y, btn_w, 46)
        self.btn_nova = RectBox(362, up_y, btn_w, 46)

        self._active_touch_uid: Optional[int] = None

        self.reset_game()
        Window.bind(size=self._on_window_resize)
        Clock.schedule_interval(self.step, 1.0 / FPS)

    def _on_window_resize(self, instance, value):
        self.size = value

    def _apply_difficulty_regen(self):
        global ELIXIR_REGEN_PER_SEC
        cfg = get_difficulty_cfg()
        ELIXIR_REGEN_PER_SEC = float(cfg["elixir_regen"])

    def _sync_best_stats(self):
        updated = False
        if self.score > self.best_score:
            self.best_score = self.score
            updated = True
        if self.wave > self.best_wave:
            self.best_wave = self.wave
            updated = True
        if updated:
            save_best_stats(self.best_score, self.best_wave)

    def reset_game(self):
        self._apply_difficulty_regen()
        self.elixir = 2.0
        self.base_hp = 20
        self.max_base_hp = 20
        self.base_hit_pulse_timer = 0.0
        self.lane_flow_phase = 0.0
        self.anim_time = 0.0
        self.score = 0
        self.wave = 1
        self.kills = 0

        self.sniper_up_lvl = 1
        self.sniper_up_cost = 3
        self.gatling_up_lvl = 1
        self.gatling_up_cost = 4

        self.nova_charge = 0.0

        self.pad_units: List[Optional[DefenseUnit]] = [None] * len(TOWER_PADS)
        self.healer_tier = 0
        self.healer_upgrade_paid = 0.0
        self.healer_timer = 0.0
        self.healer_target: Optional[Tuple[int, float, float]] = None
        self.healer_pos_by_map = [(485.0, 555.0), (475.0, 555.0), (320.0, 280.0), (485.0, 555.0)]
        self.dock_units: List[Optional[DefenseUnit]] = [None] * DOCK_SLOTS_COUNT

        self.drag_source: Optional[Tuple[str, int]] = None
        self.selected_unit_loc: Optional[Tuple[str, int]] = None
        self.drag_pos: Tuple[float, float] = (0.0, 0.0)
        self._active_touch_uid = None

        self.swap_mode = False
        self.swap_first_pad: Optional[int] = None

        self.enemies: List[LaneEnemy] = []
        self.projectiles: List[LaneProjectile] = []
        self.particles: List[Particle] = []
        self.shockwaves: List[Shockwave] = []
        self.impact_flashes: List[ImpactFlash] = []
        self.boss_lasers: List[Tuple[float, float, float, float, float]] = []
        self.saboteur_beams: List[Tuple[float, float, float, float, float]] = []
        self.popups: List[FloatingPopup] = []
        self.wave_alerts: List[WaveWarningAlert] = []

        self.spawn_queue: List[str] = []
        self.spawn_timer = 0.7
        self.shake_mag = 0.0

        self.pad_units[0] = DefenseUnit("sniper", tier=1)
        self._queue_wave(self.wave)

    def _trigger_special_wave_alerts(self, seq: List[str]):
        has_boss6 = "boss6" in seq
        has_saboteur = "saboteur" in seq
        if has_boss6:
            self.wave_alerts.append(
                WaveWarningAlert(
                    kind="boss6",
                    title="BOSS6 INCOMING!",
                    subtitle="LASER & TOWER BREAKER",
                    color=RED,
                    life=3.2,
                    max_life=3.2,
                )
            )
        if has_saboteur:
            delay = 3.2 if has_boss6 else 0.0
            self.wave_alerts.append(
                WaveWarningAlert(
                    kind="saboteur",
                    title="SABOTEUR INCOMING!",
                    subtitle="DISABLES TOWERS FOR 5s",
                    color=ORANGE,
                    life=3.2 + delay,
                    max_life=3.2,
                )
            )

    def _queue_wave(self, w: int):
        seq = build_wave_sequence(w)
        self.spawn_queue = seq
        self.spawn_timer = 0.45 if w > 2 else 0.75
        self._trigger_special_wave_alerts(seq)

    def _skip_to_next_wave(self):
        self.wave += 1
        self._sync_best_stats()
        next_seq = build_wave_sequence(self.wave)
        self.spawn_queue.extend(next_seq)
        self.spawn_timer = min(self.spawn_timer, 0.25)
        self.elixir = min(MAX_ELIXIR, self.elixir + 1.0)
        self.nova_charge = min(1.0, self.nova_charge + 0.10)
        self._trigger_special_wave_alerts(next_seq)
        self.audio.play("spawn")
        self._add_popup(SCREEN_WIDTH * 0.5, 220, f"WAVE {self.wave} JOINED!", YELLOW)

    def _toggle_swap_mode(self):
        self.swap_mode = not self.swap_mode
        self.swap_first_pad = None
        if self.swap_mode:
            self._add_popup(SCREEN_WIDTH * 0.5, ARENA_TOP + 76, "SWAP LOCKED ON: TAP TO CLOSE", CYAN)
        else:
            self._add_popup(SCREEN_WIDTH * 0.5, ARENA_TOP + 76, "SWAP OFF", GRAY)

    def _swap_pads(self, idx_a: int, idx_b: int):
        if idx_a == idx_b:
            return
        self.pad_units[idx_a], self.pad_units[idx_b] = self.pad_units[idx_b], self.pad_units[idx_a]
        self.audio.play("spawn")
        ax, ay = TOWER_PADS[idx_a]
        bx, by = TOWER_PADS[idx_b]
        self.shockwaves.append(Shockwave(ax, ay, 30.0, CYAN, 0.24, 0.24))
        self.shockwaves.append(Shockwave(bx, by, 30.0, CYAN, 0.24, 0.24))
        self._add_particles(ax, ay, CYAN, count=7, spd=95.0)
        self._add_particles(bx, by, CYAN, count=7, spd=95.0)
        self._add_popup((ax + bx) * 0.5, (ay + by) * 0.5 - 14, "SWAPPED!", CYAN)

    def _get_type_bonus_mult(self, unit_type: str) -> float:
        if unit_type == "sniper":
            return 1.0 + (self.sniper_up_lvl - 1) * 0.22
        if unit_type == "gatling":
            return 1.0 + (self.gatling_up_lvl - 1) * 0.22
        return 1.0

    def _add_popup(self, x: float, y: float, text: str, color: Tuple[float, float, float, float]):
        self.popups.append(FloatingPopup(x, y, text, color))

    def _add_particles(
        self,
        x: float,
        y: float,
        color: Tuple[float, float, float, float],
        count: int = 10,
        spd: float = 120.0,
    ):
        for _ in range(count):
            ang = random.uniform(0.0, math.tau)
            v = random.uniform(spd * 0.25, spd)
            life = random.uniform(0.22, 0.48)
            self.particles.append(
                Particle(
                    x,
                    y,
                    math.cos(ang) * v,
                    math.sin(ang) * v,
                    color,
                    random.uniform(2.5, 5.5),
                    life,
                    life,
                )
            )

    def _add_impact_flash(
        self,
        x: float,
        y: float,
        vx: float,
        vy: float,
        color: Tuple[float, float, float, float],
        length: float = 15.0,
        width: float = 2.6,
    ):
        nx, ny = norm(vx, vy)
        if nx == 0.0 and ny == 0.0:
            nx, ny = 1.0, 0.0
        self.impact_flashes.append(
            ImpactFlash(x=x, y=y, dx=nx, dy=ny, color=color, length=length, width=width)
        )
        for _ in range(4):
            spread = random.uniform(-0.85, 0.85)
            cos_s, sin_s = math.cos(spread), math.sin(spread)
            sdx = nx * cos_s - ny * sin_s
            sdy = nx * sin_s + ny * cos_s
            spd = random.uniform(90.0, 175.0)
            life = random.uniform(0.14, 0.26)
            self.particles.append(
                Particle(x, y, sdx * spd, sdy * spd, color, random.uniform(2.2, 4.2), life, life)
            )

    def _can_merge(self, a: Optional[DefenseUnit], b: Optional[DefenseUnit]) -> bool:
        if a is None or b is None:
            return False
        return a.unit_type == b.unit_type and a.tier == b.tier and a.tier < 5

    def _get_merge_hint_locations(self) -> Set[Tuple[str, int]]:
        entries: List[Tuple[Tuple[str, int], DefenseUnit]] = []
        for i, u in enumerate(self.pad_units):
            if u is not None and u.tier < 5:
                entries.append((("pad", i), u))
        for i, u in enumerate(self.dock_units):
            if u is not None and u.tier < 5:
                entries.append((("dock", i), u))

        hinted: Set[Tuple[str, int]] = set()
        for idx_a in range(len(entries)):
            loc_a, u_a = entries[idx_a]
            for idx_b in range(idx_a + 1, len(entries)):
                loc_b, u_b = entries[idx_b]
                if self._can_merge(u_a, u_b):
                    hinted.add(loc_a)
                    hinted.add(loc_b)
        return hinted

    def _get_unit_at(self, loc: Tuple[str, int]) -> Optional[DefenseUnit]:
        kind, idx = loc
        if kind == "pad" and 0 <= idx < len(self.pad_units):
            return self.pad_units[idx]
        if kind == "dock" and 0 <= idx < len(self.dock_units):
            return self.dock_units[idx]
        return None

    def _set_unit_at(self, loc: Tuple[str, int], unit: Optional[DefenseUnit]):
        kind, idx = loc
        if kind == "pad" and 0 <= idx < len(self.pad_units):
            self.pad_units[idx] = unit
        elif kind == "dock" and 0 <= idx < len(self.dock_units):
            self.dock_units[idx] = unit

    def _find_drop_target(self, lx: float, ly: float) -> Optional[Tuple[str, int]]:
        for idx, (px, py) in enumerate(TOWER_PADS):
            if dist(lx, ly, px, py) <= 36.0:
                return ("pad", idx)
        for idx, rect in enumerate(self.dock_rects):
            if rect.collidepoint(lx, ly):
                return ("dock", idx)
        return None

    def _handle_drop(self, src: Tuple[str, int], dst: Tuple[str, int]):
        if src == dst:
            return
        u_src = self._get_unit_at(src)
        if u_src is None:
            return
        u_dst = self._get_unit_at(dst)

        if self._can_merge(u_src, u_dst):
            merged = DefenseUnit(u_src.unit_type, tier=u_src.tier + 1)
            merged.hp = merged.max_hp
            if merged.tier >= 5:
                merged.overdrive_timer = 5.5
            self._set_unit_at(src, None)
            self._set_unit_at(dst, merged)
            self.audio.play("merge")
            self.nova_charge = min(1.0, self.nova_charge + 0.16)
            self.score += 40 * merged.tier
            self._sync_best_stats()
            tx, ty = self._loc_center(dst)
            self._add_particles(tx, ty, merged.color, count=16, spd=150.0)
            self.shockwaves.append(Shockwave(tx, ty, 44.0, merged.color, 0.30, 0.30))
            if merged.tier >= 5:
                self._add_popup(tx, ty - 16, "T5 OVERDRIVE!", YELLOW)
            else:
                self._add_popup(tx, ty - 14, f"T{merged.tier} MERGE! HP {merged.hp:.0f}/{merged.max_hp:.0f}", merged.color)
            return

        self._set_unit_at(src, u_dst)
        self._set_unit_at(dst, u_src)

    def _sell_dragged_unit(self):
        if self.drag_source is None:
            return
        unit = self._get_unit_at(self.drag_source)
        if unit is None:
            return
        refund = unit.get_refund_elixir()
        self._set_unit_at(self.drag_source, None)
        self.elixir = min(MAX_ELIXIR, self.elixir + refund)
        self.audio.play("spawn")
        self._add_popup(
            self.btn_sell.centerx,
            self.btn_sell.y - 10,
            f"+{refund:.0f} ELIXIR",
            GREEN,
        )

    def _loc_center(self, loc: Tuple[str, int]) -> Tuple[float, float]:
        kind, idx = loc
        if kind == "pad":
            return TOWER_PADS[idx]
        r = self.dock_rects[idx]
        return r.centerx, r.centery

    def _spawn_unit(self, unit_type: str):
        cost = int(UNIT_META[unit_type]["cost"])
        if self.elixir < cost:
            self._add_popup(SCREEN_WIDTH * 0.5, DECK_TOP - 18, "LOW ELIXIR", RED)
            return
        empty_dock = next((i for i, u in enumerate(self.dock_units) if u is None), None)
        if empty_dock is None:
            self._add_popup(SCREEN_WIDTH * 0.5, DECK_TOP - 18, "DOCK FULL", RED)
            return
        self.elixir -= cost
        self.dock_units[empty_dock] = DefenseUnit(unit_type, tier=1)
        self.audio.play("spawn")
        r = self.dock_rects[empty_dock]
        self._add_particles(r.centerx, r.centery, UNIT_META[unit_type]["color"], count=10, spd=95.0)  # type: ignore

    def _trigger_nova(self):
        if self.nova_charge < 1.0:
            return
        self.nova_charge = 0.0
        self.audio.play("nova")
        self.shake_mag = 9.0
        cx, cy = SCREEN_WIDTH * 0.5, (ARENA_TOP + ARENA_BOTTOM) * 0.5
        self.shockwaves.append(Shockwave(cx, cy, 320.0, CYAN, 0.55, 0.55))
        self._add_popup(cx, cy, "AEGIS NOVA!", CYAN)

        nova_dmg = 75.0 + self.wave * 22.0
        for e in list(self.enemies):
            if e.hp > 0:
                e.hp -= nova_dmg
                e.slow_timer = max(e.slow_timer, 2.2)
                e.hit_flash = 0.14
                self._add_particles(e.x, e.y, CYAN, count=8, spd=130.0)
                if e.hp <= 0:
                    self._on_enemy_killed(e)

    def _on_enemy_killed(self, e: LaneEnemy):
        if e in self.enemies:
            self.enemies.remove(e)
        self.kills += 1
        self.score += e.score_reward
        self._sync_best_stats()
        self.elixir = min(MAX_ELIXIR, self.elixir + e.elixir_reward)
        self.nova_charge = min(1.0, self.nova_charge + 0.05)
        self._add_particles(e.x, e.y, e.color, count=12, spd=135.0)
        self.audio.play("enemy_die")

    # --------------------------------------------------------------------------
    # TOUCH / MOUSE INPUT HANDLERS
    # --------------------------------------------------------------------------

    def _viewport_transform(self) -> Tuple[float, float, float]:
        w = max(1.0, float(Window.width))
        h = max(1.0, float(Window.height))
        scale = min(w / float(SCREEN_WIDTH), h / float(SCREEN_HEIGHT))
        off_x = (w - SCREEN_WIDTH * scale) * 0.5
        off_y = (h - SCREEN_HEIGHT * scale) * 0.5
        return scale, off_x, off_y

    def _event_to_logical(self, x: float, y: float) -> Tuple[float, float]:
        scale, off_x, off_y = self._viewport_transform()
        lx = (x - off_x) / scale
        ky = (y - off_y) / scale
        ly = SCREEN_HEIGHT - ky
        return lx, ly

    def on_touch_down(self, touch):
        if not hasattr(self, "state"):
            return False
        lx, ly = self._event_to_logical(touch.x, touch.y)

        if self.state == "TITLE":
            if self.btn_guide.collidepoint(lx, ly):
                self._state_before_guide = "TITLE"
                self.state = "GUIDE"
            else:
                self.state = "MAP_SELECT"
            return True

        if self.state == "MAP_SELECT":
            if self.btn_guide.collidepoint(lx, ly):
                self._state_before_guide = "MAP_SELECT"
                self.state = "GUIDE"
                return True
            for d_idx, rect in enumerate(self.difficulty_rects):
                if rect.collidepoint(lx, ly):
                    global CURRENT_DIFFICULTY
                    CURRENT_DIFFICULTY = DIFFICULTY_ORDER[d_idx]
                    self._apply_difficulty_regen()
                    return True
            for map_idx, rect in enumerate(self.map_select_rects):
                if rect.collidepoint(lx, ly):
                    global CURRENT_MAP, LANE_POINTS, TOWER_PADS
                    CURRENT_MAP = map_idx
                    LANE_POINTS = MAPS[map_idx]["lane"]
                    TOWER_PADS = MAPS[map_idx]["pads"]
                    self.reset_game()
                    self.state = "PLAYING"
                    break
            return True

        if self.state == "GUIDE":
            if self.btn_close_guide.collidepoint(lx, ly) or ly <= TOP_BAR_H:
                self.state = self._state_before_guide
            return True

        if self.state == "PAUSED":
            if self.btn_guide.collidepoint(lx, ly):
                self._state_before_guide = "PAUSED"
                self.state = "GUIDE"
            elif self.btn_pause.collidepoint(lx, ly) or (ARENA_TOP <= ly <= ARENA_BOTTOM):
                self.state = "PLAYING"
            return True

        if self.state == "GAMEOVER":
            self._sync_best_stats()
            self.reset_game()
            self.state = "PLAYING"
            return True

        if self.btn_guide.collidepoint(lx, ly):
            self._state_before_guide = "PLAYING"
            self.state = "GUIDE"
            return True

        if self.btn_pause.collidepoint(lx, ly):
            self.state = "PAUSED"
            return True

        if self.btn_skip_wave.collidepoint(lx, ly):
            self._skip_to_next_wave()
            return True

        if self.btn_swap.collidepoint(lx, ly):
            self._toggle_swap_mode()
            return True

        hx, hy = self._healer_position()
        if dist(lx, ly, hx, hy) <= 38.0:
            self._tap_healer_spot()
            return True

        for idx, (px, py) in enumerate(TOWER_PADS):
            if dist(lx, ly, px, py) <= 34.0:
                if self.swap_mode:
                    if self.swap_first_pad is None:
                        if self.pad_units[idx] is not None:
                            self.swap_first_pad = idx
                            self.selected_unit_loc = ("pad", idx)
                        else:
                            self._add_popup(px, py - 24, "EMPTY PAD", GRAY)
                    else:
                        if self.swap_first_pad != idx:
                            self._swap_pads(self.swap_first_pad, idx)
                        self.swap_first_pad = None
                        self.selected_unit_loc = None
                    return True
                if self.pad_units[idx] is not None:
                    self.drag_source = ("pad", idx)
                    self.selected_unit_loc = ("pad", idx)
                    self.drag_pos = (lx, ly)
                    self._active_touch_uid = touch.uid
                    touch.grab(self)
                    return True

        for idx, rect in enumerate(self.dock_rects):
            if rect.collidepoint(lx, ly) and self.dock_units[idx] is not None:
                self.swap_mode = False
                self.swap_first_pad = None
                self.drag_source = ("dock", idx)
                self.selected_unit_loc = ("dock", idx)
                self.drag_pos = (lx, ly)
                self._active_touch_uid = touch.uid
                touch.grab(self)
                return True

        for utype, rect in self.spawn_btns:
            if rect.collidepoint(lx, ly):
                self._spawn_unit(utype)
                return True

        if self.btn_up_sniper.collidepoint(lx, ly):
            if self.elixir >= self.sniper_up_cost:
                self.elixir -= self.sniper_up_cost
                self.sniper_up_lvl += 1
                self.sniper_up_cost += 2
                self.audio.play("merge")
                self._add_popup(
                    self.btn_up_sniper.centerx,
                    self.btn_up_sniper.y - 10,
                    f"SNIPER LVL {self.sniper_up_lvl}",
                    CYAN,
                )
            return True

        if self.btn_up_gatling.collidepoint(lx, ly):
            if self.elixir >= self.gatling_up_cost:
                self.elixir -= self.gatling_up_cost
                self.gatling_up_lvl += 1
                self.gatling_up_cost += 2
                self.audio.play("merge")
                self._add_popup(
                    self.btn_up_gatling.centerx,
                    self.btn_up_gatling.y - 10,
                    f"GATLING LVL {self.gatling_up_lvl}",
                    YELLOW,
                )
            return True

        if self.btn_nova.collidepoint(lx, ly):
            if self.nova_charge >= 1.0:
                self._trigger_nova()
            return True

        return False

    def on_touch_move(self, touch):
        if self._active_touch_uid == touch.uid and self.drag_source is not None:
            lx, ly = self._event_to_logical(touch.x, touch.y)
            self.drag_pos = (lx, ly)
            return True
        return False

    def on_touch_up(self, touch):
        if self._active_touch_uid == touch.uid:
            if touch.grab_current is self:
                try:
                    touch.ungrab(self)
                except Exception:
                    pass
            if self.drag_source is not None:
                lx, ly = self._event_to_logical(touch.x, touch.y)
                if self.btn_sell.collidepoint(lx, ly):
                    self._sell_dragged_unit()
                else:
                    dst = self._find_drop_target(lx, ly)
                    if dst is not None:
                        src_loc = self.drag_source
                        self._handle_drop(src_loc, dst)
                        if self._get_unit_at(dst) is not None:
                            self.selected_unit_loc = dst
                        elif self._get_unit_at(src_loc) is not None:
                            self.selected_unit_loc = src_loc
            self.drag_source = None
            self.selected_unit_loc = None
            self._active_touch_uid = None
            return True
        return False

    # --------------------------------------------------------------------------
    # SIMULATION STEP
    # --------------------------------------------------------------------------

    def step(self, dt: float):
        try:
            dt = min(dt, 0.05)
            if self.state == "PLAYING":
                self._update_playing(dt)
                self._update_fx(dt)
            elif self.state == "GAMEOVER":
                self._update_fx(dt)
            self._redraw()
        except Exception as exc:
            traceback.print_exc()
            print(f"[STEP CRASH] {exc}")

    def _update_fx(self, dt: float):
        self.anim_time += dt
        self.lane_flow_phase = (self.lane_flow_phase + dt * 0.55) % 1.0
        self.base_hit_pulse_timer = max(0.0, self.base_hit_pulse_timer - dt)
        self.shake_mag = max(0.0, self.shake_mag - dt * 28.0)
        self.particles = [p for p in self.particles if p.update(dt)]
        self.shockwaves = [s for s in self.shockwaves if s.update(dt)]
        self.impact_flashes = [f for f in self.impact_flashes if f.update(dt)]
        self.boss_lasers = [(x1, y1, x2, y2, life - dt) for x1, y1, x2, y2, life in self.boss_lasers if life - dt > 0]
        self.saboteur_beams = [(x1, y1, x2, y2, life - dt) for x1, y1, x2, y2, life in self.saboteur_beams if life - dt > 0]
        self.popups = [p for p in self.popups if p.update(dt)]
        self.wave_alerts = [a for a in self.wave_alerts if a.update(dt)]

    def _healer_position(self) -> Tuple[float, float]:
        return self.healer_pos_by_map[min(CURRENT_MAP, len(self.healer_pos_by_map) - 1)]

    def _healer_upgrade_cost(self) -> int:
        costs = {1: 8, 2: 9, 3: 10, 4: 15}
        return costs.get(self.healer_tier, 0)

    def _tap_healer_spot(self):
        if self.healer_tier == 0:
            cost = 10
            if self.elixir < cost:
                self._add_popup(*self._healer_position(), "NEED 10 ELIXIR", RED)
                return
            self.elixir -= cost
            self.healer_tier = 1
            self.healer_upgrade_paid = 0.0
            self._add_popup(*self._healer_position(), "HEALER T1", GREEN)
            self.audio.play("spawn")
            return
        if self.healer_tier >= 5:
            self._add_popup(*self._healer_position(), "HEALER MAX", YELLOW)
            return
        cost = self._healer_upgrade_cost()
        remaining = max(0.0, cost - self.healer_upgrade_paid)
        payment = min(self.elixir, remaining)
        if payment <= 0:
            self._add_popup(*self._healer_position(), f"REMAIN {remaining:.0f}", YELLOW)
            return
        self.elixir -= payment
        self.healer_upgrade_paid += payment
        if self.healer_upgrade_paid + 1e-6 >= cost:
            self.healer_tier += 1
            self.healer_upgrade_paid = 0.0
            self._add_popup(*self._healer_position(), f"HEALER T{self.healer_tier}", GREEN)
            self.audio.play("merge")
        else:
            remain = cost - self.healer_upgrade_paid
            self._add_popup(*self._healer_position(), f"PAID {self.healer_upgrade_paid:.0f}/{cost}  LEFT {remain:.0f}", YELLOW)

    def _boss6_tier_for_wave(self) -> int:
        if self.wave < 15:
            return 0
        return min(5, 1 + (self.wave - 15) // 5)

    def _update_healer(self, dt: float):
        self.healer_target = None
        if self.healer_tier <= 0:
            return
        self.healer_tier = max(self.healer_tier, self._boss6_tier_for_wave())
        self.healer_timer = max(0.0, self.healer_timer - dt)
        damaged = [(i, u) for i, u in enumerate(self.pad_units) if u is not None and u.hp < u.max_hp]
        if not damaged:
            return
        target_idx, target_unit = min(damaged, key=lambda pair: pair[1].hp / max(1.0, pair[1].max_hp))
        tx, ty = TOWER_PADS[target_idx]
        self.healer_target = (target_idx, tx, ty)
        if self.healer_timer <= 0.0:
            heal = 7.0 + self.healer_tier * 3.0
            old_hp = target_unit.hp
            target_unit.hp = min(target_unit.max_hp, target_unit.hp + heal)
            actual_heal = target_unit.hp - old_hp
            self.healer_timer = max(1.65, 2.55 - self.healer_tier * 0.12)
            if actual_heal > 0.01:
                self._add_popup(tx, ty + 26, f"+{actual_heal:.0f} HP  {target_unit.hp:.0f}/{target_unit.max_hp:.0f}", GREEN)
                self._add_particles(tx, ty, GREEN, count=5, spd=65.0)

    def _saboteur_attack_towers(self, enemy: LaneEnemy, dt: float):
        if enemy.kind != "saboteur" or enemy.hp <= 0:
            return
        enemy.saboteur_timer -= dt
        if enemy.saboteur_timer > 0.0:
            return

        candidates = [
            (i, u, dist(enemy.x, enemy.y, *TOWER_PADS[i]))
            for i, u in enumerate(self.pad_units)
            if u is not None
        ]
        candidates = [c for c in candidates if c[2] <= 155.0]
        if not candidates:
            enemy.saboteur_timer = 0.40
            return

        idx, unit, _ = min(candidates, key=lambda c: c[2])
        enemy.saboteur_timer = 3.0
        enemy.glow_timer = 0.45
        unit.disabled_timer = max(unit.disabled_timer, 5.0)

        tx, ty = TOWER_PADS[idx]
        self.saboteur_beams.append((enemy.x, enemy.y, tx, ty, 0.45))
        self.shockwaves.append(Shockwave(enemy.x, enemy.y, 46.0, ORANGE, 0.30, 0.30))
        self._add_particles(tx, ty, ORANGE, count=10, spd=105.0)
        self._add_popup(tx, ty - 28, "DISABLED 5s!", ORANGE)
        self.audio.play("emp")

    def _boss6_attack_towers(self, enemy: LaneEnemy, dt: float):
        if enemy.kind != "boss6":
            return
        enemy.tower_attack_timer -= dt
        if enemy.tower_attack_timer > 0.0:
            return
        candidates = [(i, u, dist(enemy.x, enemy.y, *TOWER_PADS[i]))
                     for i, u in enumerate(self.pad_units) if u is not None]
        candidates = [c for c in candidates if c[2] <= 125.0]
        if not candidates:
            enemy.tower_attack_timer = 0.45
            return
        idx, unit, _ = min(candidates, key=lambda c: c[2])
        tier = max(1, self._boss6_tier_for_wave())
        boss6_mult = float(get_difficulty_cfg()["boss6_dmg_mult"])
        damage = (25.0 + max(0, tier - 1) * 5.0) * boss6_mult
        unit.hp -= damage
        enemy.tower_attack_timer = max(0.90, 1.50 - max(0, tier - 1) * 0.10)
        tx, ty = TOWER_PADS[idx]
        self.boss_lasers.append((enemy.x, enemy.y, tx, ty, 0.42))
        self._add_particles(tx, ty, RED, count=10, spd=110.0)
        self._add_popup(tx, ty + 28, f"-{damage:.0f} HP", RED)
        self._add_particles(tx, ty, RED, count=5, spd=80.0)
        self.shake_mag = 2.0
        if unit.hp <= 0:
            self.pad_units[idx] = None
            self._add_popup(tx, ty, "TOWER DESTROYED", RED)
            self._add_particles(tx, ty, RED, count=16, spd=120.0)

    def _update_playing(self, dt: float):
        self.elixir = min(MAX_ELIXIR, self.elixir + ELIXIR_REGEN_PER_SEC * dt)

        if self.spawn_queue:
            self.spawn_timer -= dt
            if self.spawn_timer <= 0.0:
                kind = self.spawn_queue.pop(0)
                self.enemies.append(LaneEnemy.create(kind, self.wave))
                if self.wave <= 2:
                    self.spawn_timer = 0.72
                elif self.wave <= 10:
                    self.spawn_timer = 0.42 if kind == "swift" else 0.52
                elif self.wave <= 30:
                    self.spawn_timer = 0.24 if kind == "swift" else 0.34
                else:
                    self.spawn_timer = 0.18 if kind == "swift" else 0.26
        elif not self.enemies:
            self.wave += 1
            self._sync_best_stats()
            self.elixir = min(MAX_ELIXIR, self.elixir + 2.5)
            stage_tag = ""
            if self.wave == 16:
                stage_tag = " - MID STAGE"
            elif self.wave == 31:
                stage_tag = " - SURVIVAL!"
            self._add_popup(SCREEN_WIDTH * 0.5, 250, f"WAVE {self.wave}{stage_tag}", GREEN if self.wave <= 30 else RED)
            self._queue_wave(self.wave)

        for e in list(self.enemies):
            reached_end = e.update(dt)
            self._saboteur_attack_towers(e, dt)
            self._boss6_attack_towers(e, dt)
            if reached_end:
                if e in self.enemies:
                    self.enemies.remove(e)
                self.base_hp = max(0, self.base_hp - e.base_dmg)
                self.base_hit_pulse_timer = 1.1
                self.shake_mag = 7.0
                self.audio.play("base_hit")
                self._add_particles(e.x, e.y, RED, count=12, spd=120.0)
                if self.base_hp <= 0:
                    self._sync_best_stats()
                    self.state = "GAMEOVER"
                    return

        self._update_healer(dt)

        for idx, unit in enumerate(self.pad_units):
            if unit is not None:
                mult = self._get_type_bonus_mult(unit.unit_type)
                unit.update_and_fire(
                    dt,
                    TOWER_PADS[idx],
                    self.enemies,
                    self.projectiles,
                    self.audio,
                    mult,
                )

        for proj in list(self.projectiles):
            if not proj.update(dt):
                if proj in self.projectiles:
                    self.projectiles.remove(proj)
                continue

            hit_enemy: Optional[LaneEnemy] = None
            for e in self.enemies:
                if e.hp > 0 and dist(proj.x, proj.y, e.x, e.y) <= proj.radius + e.radius:
                    hit_enemy = e
                    break

            if hit_enemy is not None:
                if proj.unit_type in ("gatling", "mortar"):
                    self._add_impact_flash(
                        proj.x,
                        proj.y,
                        proj.vx,
                        proj.vy,
                        proj.color,
                        length=18.0 if proj.unit_type == "mortar" else 13.0,
                        width=3.2 if proj.unit_type == "mortar" else 2.2,
                    )
                if proj.splash_radius > 0.0:
                    self.shockwaves.append(
                        Shockwave(proj.x, proj.y, proj.splash_radius, proj.color, 0.24, 0.24)
                    )
                    self._add_particles(proj.x, proj.y, proj.color, count=12, spd=130.0)
                    for e in list(self.enemies):
                        if e.hp > 0 and dist(proj.x, proj.y, e.x, e.y) <= proj.splash_radius + e.radius:
                            e.hp -= proj.damage
                            e.hit_flash = 0.09
                            if proj.slow_duration > 0:
                                e.slow_timer = max(e.slow_timer, proj.slow_duration)
                            if e.hp <= 0:
                                self._on_enemy_killed(e)
                else:
                    hit_enemy.hp -= proj.damage
                    hit_enemy.hit_flash = 0.09
                    self.audio.play("enemy_hit")
                    self._add_particles(proj.x, proj.y, proj.color, count=5, spd=85.0)
                    if hit_enemy.hp <= 0:
                        self._on_enemy_killed(hit_enemy)

                if proj in self.projectiles:
                    self.projectiles.remove(proj)

    # --------------------------------------------------------------------------
    # KIVY CANVAS DRAWING HELPERS (WITH TEXT CACHE)
    # --------------------------------------------------------------------------

    def _get_cached_text_texture(self, text: str, size: int) -> Tuple[object, int, int]:
        key = (text, size)
        cached = self._text_cache.get(key)
        if cached is not None:
            return cached
        lbl = CoreLabel(text=text, font_size=size, bold=True)
        lbl.refresh()
        tex = lbl.texture
        tw, th = tex.size
        if len(self._text_cache) > 256:
            self._text_cache.clear()
        self._text_cache[key] = (tex, tw, th)
        return tex, tw, th

    def _draw_text(
        self,
        text: str,
        x: float,
        y: float,
        size: int = 16,
        color=WHITE,
        center: bool = False,
    ):
        tex, tw, th = self._get_cached_text_texture(text, size)
        dx = x - tw * 0.5 if center else x
        ky = to_ky(y + th)
        Color(*color)
        Rectangle(texture=tex, pos=(dx, ky), size=(tw, th))

    def _draw_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        color,
        line_width: float = 0.0,
    ):
        ky = to_ky(y + h)
        if line_width > 0:
            Color(*color)
            Line(rectangle=(x, ky, w, h), width=line_width)
        else:
            Color(*color)
            Rectangle(pos=(x, ky), size=(w, h))

    def _draw_circle(
        self,
        cx: float,
        cy: float,
        r: float,
        color,
        line_width: float = 0.0,
    ):
        ky = to_ky(cy)
        if line_width > 0:
            Color(*color)
            Line(circle=(cx, ky, r), width=line_width)
        else:
            Color(*color)
            Ellipse(pos=(cx - r, ky - r), size=(r * 2.0, r * 2.0))

    def _draw_poly_points(self, pts_topdown: List[Tuple[float, float]], color, line_width: float = 2.0):
        flat: List[float] = []
        for px, py in pts_topdown:
            flat.extend([px, to_ky(py)])
        Color(*color)
        Line(points=flat, width=line_width, close=True)

    def _draw_zigzag_beam(self, x1: float, y1: float, x2: float, y2: float, alpha: float):
        dx = x2 - x1
        dy = y2 - y1
        length = max(1.0, math.hypot(dx, dy))
        nx, ny = -dy / length, dx / length
        segments = 7
        amp = 9.0
        pts_outer: List[float] = [x1, to_ky(y1)]
        pts_inner: List[float] = [x1, to_ky(y1)]
        for i in range(1, segments):
            t = i / float(segments)
            zig = amp * (1.0 if i % 2 == 1 else -1.0)
            px = x1 + dx * t + nx * zig
            py = y1 + dy * t + ny * zig
            ky = to_ky(py)
            pts_outer.extend([px, ky])
            pts_inner.extend([px, ky])
        pts_outer.extend([x2, to_ky(y2)])
        pts_inner.extend([x2, to_ky(y2)])

        Color(1.0, 0.45, 0.05, alpha * 0.95)
        Line(points=pts_outer, width=4.2)
        Color(1.0, 0.92, 0.35, alpha)
        Line(points=pts_inner, width=1.8)

    def _draw_lane_flow_chevrons(self):
        if len(LANE_POINTS) < 2:
            return
        seg_lengths: List[float] = []
        total_len = 0.0
        for i in range(len(LANE_POINTS) - 1):
            d = dist(LANE_POINTS[i][0], LANE_POINTS[i][1], LANE_POINTS[i + 1][0], LANE_POINTS[i + 1][1])
            seg_lengths.append(d)
            total_len += d
        if total_len <= 1.0:
            return

        spacing = 54.0
        offset = self.lane_flow_phase * spacing
        distance_cursor = offset

        while distance_cursor < total_len:
            accum = 0.0
            for i, d in enumerate(seg_lengths):
                if accum + d >= distance_cursor and d > 0.001:
                    t = (distance_cursor - accum) / d
                    x1, y1 = LANE_POINTS[i]
                    x2, y2 = LANE_POINTS[i + 1]
                    px = x1 + (x2 - x1) * t
                    py = y1 + (y2 - y1) * t
                    nx, ny = norm(x2 - x1, y2 - y1)
                    perp_x, perp_y = -ny, nx
                    tip_x, tip_y = px + nx * 5.0, py + ny * 5.0
                    left_x, left_y = px - nx * 4.0 + perp_x * 4.5, py - ny * 4.0 + perp_y * 4.5
                    right_x, right_y = px - nx * 4.0 - perp_x * 4.5, py - ny * 4.0 - perp_y * 4.5
                    Color(0.25, 0.92, 1.0, 0.52)
                    Line(
                        points=[
                            left_x,
                            to_ky(left_y),
                            tip_x,
                            to_ky(tip_y),
                            right_x,
                            to_ky(right_y),
                        ],
                        width=1.8,
                    )
                    break
                accum += d
            distance_cursor += spacing

    def _draw_base_core_pulse(self, ex: float, ey: float):
        hp_ratio = self.base_hp / max(1.0, float(self.max_base_hp))
        low_hp = hp_ratio <= 0.30
        recently_hit = self.base_hit_pulse_timer > 0.0
        if not (low_hp or recently_hit):
            return

        pulse_speed = 9.5 if low_hp else 12.0
        wave_val = 0.5 + 0.5 * math.sin(self.anim_time * pulse_speed)
        warn_col = RED if low_hp else ORANGE
        outer_r = 18.0 + wave_val * 11.0
        alpha = 0.22 + wave_val * 0.45

        self._draw_circle(ex, ey, outer_r, (warn_col[0], warn_col[1], warn_col[2], alpha * 0.45))
        self._draw_circle(ex, ey, outer_r, (warn_col[0], warn_col[1], warn_col[2], alpha), line_width=2.4)

    def _draw_merge_hint_ring(self, cx: float, cy: float, radius: float):
        pulse = 0.5 + 0.5 * math.sin(self.anim_time * 7.5)
        ring_r = radius * (1.16 + 0.08 * pulse)
        alpha = 0.35 + 0.40 * pulse
        self._draw_circle(cx, cy, ring_r, (0.25, 0.98, 0.58, alpha), line_width=1.8)

    def _draw_projectile(self, proj: LaneProjectile):
        if proj.unit_type == "sniper":
            tex = self.turret_textures.get(("sniper", proj.tier))
            ang_deg = -math.degrees(math.atan2(proj.vy, proj.vx))
            ky = to_ky(proj.y)
            size = proj.radius * 2.4
            if tex is not None:
                PushMatrix()
                Rotate(angle=ang_deg, origin=(proj.x, ky))
                Color(1.0, 1.0, 1.0, 1.0)
                Rectangle(
                    texture=tex,
                    pos=(proj.x - size * 0.5, ky - size * 0.5),
                    size=(size, size),
                )
                PopMatrix()
            else:
                nx, ny = norm(proj.vx, proj.vy)
                px, py = -ny, nx
                tip = (proj.x + nx * 12, proj.y + ny * 12)
                back_l = (proj.x - nx * 8 + px * 6, proj.y - ny * 8 + py * 6)
                back_r = (proj.x - nx * 8 - px * 6, proj.y - ny * 8 - py * 6)
                self._draw_poly_points([tip, back_l, back_r], proj.color, line_width=2.2)
        elif proj.unit_type == "gatling":
            nx, ny = norm(proj.vx, proj.vy)
            half_len = 8.5
            x1 = proj.x - nx * half_len
            y1 = proj.y - ny * half_len
            x2 = proj.x + nx * half_len
            y2 = proj.y + ny * half_len
            Color(*proj.color)
            Line(points=[x1, to_ky(y1), x2, to_ky(y2)], width=2.4)
        elif proj.unit_type == "mortar":
            nx, ny = norm(proj.vx, proj.vy)
            half_len = 13.0
            x1 = proj.x - nx * half_len
            y1 = proj.y - ny * half_len
            x2 = proj.x + nx * half_len
            y2 = proj.y + ny * half_len
            Color(*proj.color)
            Line(points=[x1, to_ky(y1), x2, to_ky(y2)], width=4.0)
            Color(*WHITE)
            Line(points=[x1, to_ky(y1), x2, to_ky(y2)], width=1.4)
        else:
            self._draw_circle(proj.x, proj.y, proj.radius, proj.color)

    def _draw_next_wave_panel(self):
        next_w = self.wave + 1
        items = summarize_wave_counts(next_w)
        if not items:
            return

        panel_x = 8.0
        panel_y = ARENA_TOP + 6.0
        row_h = 26.0
        header_h = 18.0
        panel_w = 88.0
        panel_h = header_h + len(items) * row_h + 4.0

        self._draw_rect(panel_x, panel_y, panel_w, panel_h, rgb(12, 16, 26, 0.78))
        self._draw_rect(panel_x, panel_y, panel_w, panel_h, SLOT_BORDER, line_width=1.2)
        self._draw_text(f"W{next_w} NEXT", panel_x + panel_w * 0.5, panel_y + 3, size=10, color=YELLOW, center=True)

        for idx, (kind, count) in enumerate(items):
            ry = panel_y + header_h + idx * row_h
            icon_cx = panel_x + 18.0
            icon_cy = ry + row_h * 0.5
            icon_size = 18.0
            tex = self.enemy_textures.get(kind)
            if tex is not None:
                Color(1.0, 1.0, 1.0, 1.0)
                Rectangle(
                    texture=tex,
                    pos=(icon_cx - icon_size * 0.5, to_ky(icon_cy + icon_size * 0.5)),
                    size=(icon_size, icon_size),
                )
            else:
                self._draw_circle(icon_cx, icon_cy, 7.0, ENEMY_FALLBACK_COLORS.get(kind, RED))

            self._draw_text(f"x{count}", panel_x + 34.0, ry + 5, size=12, color=WHITE, center=False)

    def _draw_wave_alerts(self):
        active_alerts = [a for a in self.wave_alerts if a.life <= a.max_life]
        if not active_alerts:
            return
        alert = active_alerts[0]
        fade_in = clamp((alert.max_life - alert.life) / 0.25, 0.0, 1.0)
        fade_out = clamp(alert.life / 0.45, 0.0, 1.0)
        alpha = min(fade_in, fade_out)
        pulse = 0.75 + 0.25 * math.sin(alert.life * 14.0)

        bx = 104.0
        by = ARENA_TOP + 8.0
        bw = SCREEN_WIDTH - 216.0
        bh = 58.0

        self._draw_rect(bx, by, bw, bh, (0.06, 0.08, 0.14, 0.90 * alpha))
        self._draw_rect(
            bx,
            by,
            bw,
            bh,
            (alert.color[0], alert.color[1], alert.color[2], (0.65 + 0.35 * pulse) * alpha),
            line_width=2.2,
        )

        icon_cx = bx + 28.0
        icon_cy = by + bh * 0.5
        icon_size = 38.0
        self._draw_circle(icon_cx, icon_cy, 21.0, (alert.color[0], alert.color[1], alert.color[2], 0.20 * alpha))
        tex = self.enemy_textures.get(alert.kind)
        if tex is not None:
            Color(1.0, 1.0, 1.0, alpha)
            Rectangle(
                texture=tex,
                pos=(icon_cx - icon_size * 0.5, to_ky(icon_cy + icon_size * 0.5)),
                size=(icon_size, icon_size),
            )
        else:
            self._draw_circle(icon_cx, icon_cy, 15.0, (alert.color[0], alert.color[1], alert.color[2], alpha))

        text_x = bx + 58.0
        self._draw_text(
            alert.title,
            text_x,
            by + 8.0,
            size=14,
            color=(alert.color[0], alert.color[1], alert.color[2], alpha),
            center=False,
        )
        self._draw_text(
            alert.subtitle,
            text_x,
            by + 30.0,
            size=11,
            color=(WHITE[0], WHITE[1], WHITE[2], alpha),
            center=False,
        )

    def _draw_skip_wave_button(self):
        r = self.btn_skip_wave
        self._draw_rect(r.x, r.y, r.w, r.h, SLOT_BG)
        self._draw_rect(r.x, r.y, r.w, r.h, YELLOW, line_width=1.8)
        self._draw_text(f"SKIP >W{self.wave + 1}", r.centerx, r.y + 7, size=11, color=YELLOW, center=True)

    def _draw_swap_button(self):
        r = self.btn_swap
        active = self.swap_mode
        col = CYAN if active else GRAY
        self._draw_rect(r.x, r.y, r.w, r.h, rgb(20, 42, 62) if active else SLOT_BG)
        self._draw_rect(r.x, r.y, r.w, r.h, col, line_width=2.0 if active else 1.4)
        self._draw_text("SWAP LOCK" if active else "SWAP", r.centerx, r.y + 6, size=11, color=col, center=True)

    def _draw_enemy_shape(self, e: LaneEnemy):
        r = e.radius
        ky = to_ky(e.y)
        tex = self.enemy_textures.get(e.kind)

        if e.glow_timer > 0.0:
            glow_alpha = clamp(e.glow_timer / 0.45, 0.0, 1.0)
            self._draw_circle(e.x, e.y, r + 9.0, (1.0, 0.55, 0.10, 0.35 * glow_alpha))
            self._draw_circle(e.x, e.y, r + 6.0, (1.0, 0.85, 0.25, 0.90 * glow_alpha), line_width=2.5)

        if tex is not None:
            sprite_size = r * 2.5
            deg = e.facing_angle if e.kind == "saboteur" else (e.facing_angle + math.degrees(e.spin))
            PushMatrix()
            Rotate(angle=deg, origin=(e.x, ky))
            if e.hit_flash > 0:
                Color(1.0, 0.45, 0.45, 1.0)
            elif e.glow_timer > 0.0:
                Color(1.0, 0.92, 0.55, 1.0)
            else:
                Color(1.0, 1.0, 1.0, 1.0)
            Rectangle(
                texture=tex,
                pos=(e.x - sprite_size * 0.5, ky - sprite_size * 0.5),
                size=(sprite_size, sprite_size),
            )
            PopMatrix()
        else:
            col = WHITE if e.hit_flash > 0 else e.color
            if e.kind == "runner":
                pts = [(e.x, e.y - r), (e.x + r, e.y), (e.x, e.y + r), (e.x - r, e.y)]
                self._draw_circle(e.x, e.y, r * 0.72, col)
                self._draw_poly_points(pts, col, line_width=2.0)
            elif e.kind == "swift":
                pts = [
                    (e.x + math.cos(e.spin) * r, e.y + math.sin(e.spin) * r),
                    (e.x + math.cos(e.spin + 2.4) * r, e.y + math.sin(e.spin + 2.4) * r),
                    (e.x + math.cos(e.spin - 2.4) * r, e.y + math.sin(e.spin - 2.4) * r),
                ]
                self._draw_poly_points(pts, col, line_width=2.5)
                self._draw_circle(e.x, e.y, r * 0.42, WHITE)
            elif e.kind == "brute":
                pts = []
                for k in range(6):
                    a = e.spin * 0.35 + k * (math.tau / 6.0)
                    pts.append((e.x + math.cos(a) * r, e.y + math.sin(a) * r))
                self._draw_circle(e.x, e.y, r * 0.65, PANEL_BG)
                self._draw_poly_points(pts, col, line_width=2.5)
                self._draw_circle(e.x, e.y, r * 0.32, col)
            elif e.kind == "saboteur":
                pts = [(e.x - r, e.y - r * 0.55), (e.x + r, e.y - r * 0.55), (e.x + r, e.y + r * 0.55), (e.x - r, e.y + r * 0.55)]
                self._draw_circle(e.x, e.y, r * 0.68, PANEL_BG)
                self._draw_poly_points(pts, col, line_width=2.8)
                self._draw_circle(e.x, e.y, r * 0.34, YELLOW if e.glow_timer > 0 else col)
            elif e.kind == "boss6":
                pts = []
                for k in range(10):
                    a = e.spin * 0.2 + k * (math.tau / 10.0)
                    rr = r if k % 2 == 0 else r * 0.66
                    pts.append((e.x + math.cos(a) * rr, e.y + math.sin(a) * rr))
                self._draw_circle(e.x, e.y, r * 0.68, PANEL_BG)
                self._draw_poly_points(pts, col, line_width=3.5)
                self._draw_circle(e.x, e.y, r * 0.38, PURPLE if e.hit_flash <= 0 else WHITE)
            else:
                pts = []
                for k in range(8):
                    a = e.spin * 0.25 + k * (math.tau / 8.0)
                    pts.append((e.x + math.cos(a) * r, e.y + math.sin(a) * r))
                self._draw_circle(e.x, e.y, r * 0.78, PANEL_BG)
                self._draw_poly_points(pts, col, line_width=3.0)
                self._draw_circle(e.x, e.y, r * 0.45, YELLOW if e.hit_flash <= 0 else WHITE)

        if e.slow_timer > 0:
            self._draw_circle(e.x, e.y, r + 3.5, ICE, line_width=2.0)

        hp_ratio = clamp(e.hp / max(1.0, e.max_hp), 0.0, 1.0)
        bw = r * 2.1
        self._draw_rect(e.x - r * 1.05, e.y - r - 9, bw, 4, BLACK)
        self._draw_rect(
            e.x - r * 1.05,
            e.y - r - 9,
            bw * hp_ratio,
            4,
            GREEN if hp_ratio > 0.4 else RED,
        )

    def _draw_unit_art(
        self,
        unit: DefenseUnit,
        cx: float,
        cy: float,
        radius: float,
        show_aim: bool = True,
        merge_hint: bool = False,
    ):
        if merge_hint:
            self._draw_merge_hint_ring(cx, cy, radius)

        recoil_x = -math.cos(unit.aim_angle) * unit.recoil if (show_aim and unit.disabled_timer <= 0.0) else 0.0
        recoil_y = -math.sin(unit.aim_angle) * unit.recoil if (show_aim and unit.disabled_timer <= 0.0) else 0.0
        ux = cx + recoil_x
        uy = cy + recoil_y
        ky = to_ky(uy)

        if unit.overdrive_timer > 0.0:
            pulse = radius * (1.24 + 0.10 * math.sin(unit.overdrive_timer * 14.0))
            self._draw_circle(cx, cy, pulse, (1.0, 0.85, 0.15, 0.22))
            self._draw_circle(cx, cy, pulse, YELLOW, line_width=2.2)

        border_col = ORANGE if unit.disabled_timer > 0.0 else (YELLOW if unit.overdrive_timer > 0.0 else unit.color)
        self._draw_circle(cx + 2, cy + 3, radius * 1.05, SHADOW_COLOR)
        self._draw_circle(cx, cy, radius * 0.96, PANEL_BG)
        self._draw_circle(cx, cy, radius * 0.96, border_col, line_width=2.0)

        tex = self.turret_textures.get((unit.unit_type, unit.tier))
        if tex is not None:
            sprite_size = radius * 2.25
            deg = -math.degrees(unit.aim_angle) if show_aim else 0.0
            PushMatrix()
            Rotate(angle=deg, origin=(ux, ky))
            if unit.disabled_timer > 0.0:
                Color(0.55, 0.55, 0.62, 0.85)
            else:
                Color(1.0, 1.0, 1.0, 1.0)
            Rectangle(
                texture=tex,
                pos=(ux - sprite_size * 0.5, ky - sprite_size * 0.5),
                size=(sprite_size, sprite_size),
            )
            PopMatrix()
        else:
            if show_aim:
                bx = ux + math.cos(unit.aim_angle) * (radius + 9)
                by = uy + math.sin(unit.aim_angle) * (radius + 9)
                Color(*border_col)
                Line(points=[ux, ky, bx, to_ky(by)], width=3.5)

        if unit.disabled_timer > 0.0:
            self._draw_circle(cx, cy, radius * 0.88, (1.0, 0.45, 0.08, 0.25))
            self._draw_text(
                f"{unit.disabled_timer:.1f}s",
                cx,
                cy - 7,
                size=11,
                color=ORANGE,
                center=True,
            )
        elif unit.overdrive_timer > 0.0:
            self._draw_text(
                f"OD {unit.overdrive_timer:.1f}s",
                cx,
                cy - radius - 20,
                size=10,
                color=YELLOW,
                center=True,
            )

        self._draw_text(
            f"T{unit.tier}",
            cx,
            cy + radius + 3,
            size=11,
            color=unit.color,
            center=True,
        )
        hp_ratio = clamp(unit.hp / max(1.0, unit.max_hp), 0.0, 1.0)
        bar_w = radius * 2.0
        self._draw_rect(cx - bar_w / 2, cy - radius - 9, bar_w, 4, BLACK)
        self._draw_rect(cx - bar_w / 2, cy - radius - 9, bar_w * hp_ratio, 4,
                        GREEN if hp_ratio > 0.4 else RED)

    def _draw_selected_unit_overlay(self):
        if self.selected_unit_loc is None or self.selected_unit_loc == self.drag_source:
            return
        unit = self._get_unit_at(self.selected_unit_loc)
        if unit is None:
            self.selected_unit_loc = None
            return
        cx, cy = self._loc_center(self.selected_unit_loc)
        rng = unit.get_range()
        self._draw_circle(cx, cy, rng, (unit.color[0], unit.color[1], unit.color[2], 0.055))
        self._draw_circle(cx, cy, rng, (unit.color[0], unit.color[1], unit.color[2], 0.30), line_width=1.2)
        hp_ratio = clamp(unit.hp / max(1.0, unit.max_hp), 0.0, 1.0)
        hp_color = GREEN if hp_ratio > 0.4 else RED
        self._draw_rect(cx - 39, cy + 34, 78, 17, BLACK)
        self._draw_rect(cx - 37, cy + 36, 74 * hp_ratio, 13, hp_color)
        self._draw_text(f"HP {unit.hp:.0f}/{unit.max_hp:.0f}", cx, cy + 38, size=10, color=WHITE, center=True)

    def _draw_drag_overlays(self):
        if self.drag_source is None:
            return
        dragged = self._get_unit_at(self.drag_source)
        if dragged is None:
            return

        rng = dragged.get_range()
        dx, dy = self.drag_pos

        self._draw_circle(dx, dy, rng, (dragged.color[0], dragged.color[1], dragged.color[2], 0.10))
        self._draw_circle(dx, dy, rng, (dragged.color[0], dragged.color[1], dragged.color[2], 0.65), line_width=1.6)
        self._draw_text(f"HP {dragged.hp:.0f}/{dragged.max_hp:.0f}", dx, dy + 42, size=12, color=GREEN if dragged.hp / max(1.0, dragged.max_hp) > 0.4 else RED, center=True)

        for idx, (px, py) in enumerate(TOWER_PADS):
            if self.drag_source == ("pad", idx):
                continue
            target_u = self.pad_units[idx]
            if self._can_merge(dragged, target_u):
                self._draw_circle(px, py, 28, GREEN, line_width=2.5)
                self._draw_circle(px, py, rng, (GREEN[0], GREEN[1], GREEN[2], 0.45), line_width=1.3)
            elif target_u is None and dist(dx, dy, px, py) <= 44.0:
                self._draw_circle(px, py, 26, CYAN, line_width=2.0)
                self._draw_circle(px, py, rng, (CYAN[0], CYAN[1], CYAN[2], 0.40), line_width=1.3)

        for idx, rect in enumerate(self.dock_rects):
            if self.drag_source == ("dock", idx):
                continue
            if self._can_merge(dragged, self.dock_units[idx]):
                self._draw_rect(rect.x - 2, rect.y - 2, rect.w + 4, rect.h + 4, GREEN, line_width=2.5)

        refund = dragged.get_refund_elixir()
        self._draw_rect(self.btn_sell.x, self.btn_sell.y, self.btn_sell.w, self.btn_sell.h, SLOT_BG)
        self._draw_rect(self.btn_sell.x, self.btn_sell.y, self.btn_sell.w, self.btn_sell.h, RED, line_width=2.0)
        self._draw_text(
            f"SELL +{refund:.0f} ELIXIR",
            self.btn_sell.centerx,
            self.btn_sell.y + 7,
            size=13,
            color=RED,
            center=True,
        )

        self._draw_unit_art(dragged, dx, dy, 22.0, show_aim=False)

    # --------------------------------------------------------------------------
    # MAIN RENDER LOOP
    # --------------------------------------------------------------------------

    def _redraw(self):
        self.canvas.clear()
        scale, off_x, off_y = self._viewport_transform()

        sx = random.uniform(-self.shake_mag, self.shake_mag) if self.shake_mag > 0 else 0.0
        sy = random.uniform(-self.shake_mag, self.shake_mag) if self.shake_mag > 0 else 0.0

        with self.canvas:
            Color(*BG_DARK)
            Rectangle(pos=(0, 0), size=(Window.width, Window.height))

            PushMatrix()
            Translate(off_x + sx * scale, off_y - sy * scale)
            Scale(scale, scale, 1.0, origin=(0, 0))

            if self.state == "TITLE":
                self._draw_title_screen()
            elif self.state == "MAP_SELECT":
                self._draw_map_select_screen()
            elif self.state == "GUIDE":
                self._draw_guide_screen()
            else:
                self._draw_arena()
                self._draw_top_bar()
                self._draw_bottom_deck()
                self._draw_selected_unit_overlay()
                self._draw_drag_overlays()
                if self.state == "PAUSED":
                    self._draw_pause_overlay()
                elif self.state == "GAMEOVER":
                    self._draw_gameover_overlay()

            PopMatrix()

    def _draw_arena(self):
        self._draw_rect(0, ARENA_TOP, SCREEN_WIDTH, ARENA_BOTTOM - ARENA_TOP, BG_DARK)

        tile = 36
        for gx in range(0, SCREEN_WIDTH, tile):
            for gy in range(ARENA_TOP, ARENA_BOTTOM, tile):
                if ((gx // tile) + (gy // tile)) % 2 == 0:
                    self._draw_rect(gx, gy, tile, tile, BG_TILE_ALT)
                if ((gx // tile) % 2 == 0) and ((gy // tile) % 2 == 0):
                    self._draw_circle(gx + tile * 0.5, gy + tile * 0.5, 1.6, BG_GRID_ACCENT)

        if len(LANE_POINTS) >= 2:
            pts_kivy: List[float] = []
            for px, py in LANE_POINTS:
                pts_kivy.extend([px, to_ky(py)])

            Color(*LANE_GLOW)
            Line(points=pts_kivy, width=34, cap="round", joint="round")
            Color(*LANE_BORDER)
            Line(points=pts_kivy, width=27, cap="round", joint="round")
            Color(*BG_LANE)
            Line(points=pts_kivy, width=21, cap="round", joint="round")
            Color(*LANE_CENTER)
            Line(points=pts_kivy, width=3.0, cap="round", joint="round")
            Color(*LANE_INNER_DASH)
            Line(points=pts_kivy, width=1.2, dash_length=8, dash_offset=4, cap="round", joint="round")
            self._draw_lane_flow_chevrons()

            sx, sy = LANE_POINTS[0]
            ex, ey = LANE_POINTS[-1]
            self._draw_circle(sx, sy, 15, RED, line_width=2.5)
            self._draw_circle(sx, sy, 6, RED)
            self._draw_base_core_pulse(ex, ey)
            self._draw_circle(ex, ey, 17, GREEN, line_width=2.5)
            self._draw_circle(ex, ey, 7, GREEN)

        merge_hints = self._get_merge_hint_locations()

        for idx, (px, py) in enumerate(TOWER_PADS):
            u = self.pad_units[idx]
            is_swap_first = self.swap_mode and self.swap_first_pad == idx
            if is_swap_first:
                ring_col = CYAN
            elif u is not None and u.disabled_timer > 0.0:
                ring_col = ORANGE
            elif u is not None:
                ring_col = u.color
            else:
                ring_col = CYAN if self.swap_mode else SLOT_BORDER
            self._draw_circle(px, py, 24, SLOT_BG)
            self._draw_circle(px, py, 24, ring_col, line_width=2.6 if is_swap_first else 2.0)
            if is_swap_first:
                self._draw_circle(px, py, 29, CYAN, line_width=1.4)
            if u is not None and self.drag_source != ("pad", idx):
                self._draw_unit_art(
                    u,
                    px,
                    py,
                    19.0,
                    show_aim=True,
                    merge_hint=("pad", idx) in merge_hints,
                )

        hx, hy = self._healer_position()
        self._draw_circle(hx, hy, 28, SLOT_BG)
        self._draw_circle(hx, hy, 28, GREEN if self.healer_tier else SLOT_BORDER, line_width=2.2)
        if self.healer_tier > 0:
            if self.healer_texture is not None:
                Color(1, 1, 1, 1)
                Rectangle(texture=self.healer_texture, pos=(hx - 26, to_ky(hy + 26)), size=(52, 52))
            else:
                self._draw_circle(hx, hy, 18, GREEN)
                self._draw_rect(hx - 4, hy - 12, 8, 24, WHITE)
                self._draw_rect(hx - 12, hy - 4, 24, 8, WHITE)
            self._draw_text(f"T{self.healer_tier}", hx, hy + 34, size=11, color=GREEN, center=True)
            if self.healer_tier < 5:
                cost = self._healer_upgrade_cost()
                if self.healer_upgrade_paid > 0:
                    self._draw_text(f"{self.healer_upgrade_paid:.0f}/{cost}", hx, hy - 38, size=10, color=YELLOW, center=True)
                else:
                    self._draw_text(f"UP {cost}", hx, hy - 38, size=10, color=GREEN, center=True)
        else:
            self._draw_text("HEALER 10", hx, hy - 38, size=10, color=GREEN, center=True)
        if self.healer_target is not None:
            _, tx, ty = self.healer_target
            Color(0.25, 1.0, 0.25, 0.75)
            Line(points=[hx, to_ky(hy), tx, to_ky(ty)], width=2.5)
            self._draw_circle(tx, ty, 24, GREEN, line_width=2.0)

        for x1, y1, x2, y2, life in self.saboteur_beams:
            alpha = clamp(life / 0.45, 0.0, 1.0)
            self._draw_zigzag_beam(x1, y1, x2, y2, alpha)

        for x1, y1, x2, y2, life in self.boss_lasers:
            alpha = clamp(life / 0.42, 0.0, 1.0)
            Color(1.0, 0.12, 0.20, alpha * 0.95)
            Line(points=[x1, to_ky(y1), x2, to_ky(y2)], width=5.0)
            Color(1.0, 0.75, 0.80, alpha)
            Line(points=[x1, to_ky(y1), x2, to_ky(y2)], width=1.7)

        for e in self.enemies:
            self._draw_enemy_shape(e)

        for proj in self.projectiles:
            self._draw_projectile(proj)

        for fl in self.impact_flashes:
            alpha = clamp(fl.life / max(0.01, fl.max_life), 0.0, 1.0)
            hx_d = fl.dx * fl.length * 0.5
            hy_d = fl.dy * fl.length * 0.5
            x1, y1 = fl.x - hx_d, fl.y - hy_d
            x2, y2 = fl.x + hx_d, fl.y + hy_d
            Color(fl.color[0], fl.color[1], fl.color[2], alpha)
            Line(points=[x1, to_ky(y1), x2, to_ky(y2)], width=fl.width)
            Color(1.0, 1.0, 1.0, alpha * 0.9)
            Line(points=[x1, to_ky(y1), x2, to_ky(y2)], width=max(1.0, fl.width * 0.45))

        for sw in self.shockwaves:
            prog = 1.0 - (sw.life / max(0.01, sw.max_life))
            r = max(4.0, sw.max_radius * prog)
            alpha = clamp(1.0 - prog, 0.0, 1.0)
            self._draw_circle(
                sw.x,
                sw.y,
                r,
                (sw.color[0], sw.color[1], sw.color[2], alpha),
                line_width=2.5,
            )

        for p in self.particles:
            alpha = clamp(p.life / max(0.01, p.max_life), 0.0, 1.0)
            self._draw_circle(p.x, p.y, p.size, (p.color[0], p.color[1], p.color[2], alpha))

        for pop in self.popups:
            self._draw_text(pop.text, pop.x, pop.y, size=14, color=pop.color, center=True)

        self._draw_next_wave_panel()
        self._draw_wave_alerts()
        self._draw_skip_wave_button()
        self._draw_swap_button()

    def _draw_top_bar(self):
        self._draw_rect(0, 0, SCREEN_WIDTH, TOP_BAR_H, PANEL_BG)
        self._draw_rect(0, TOP_BAR_H - 2, SCREEN_WIDTH, 2, SLOT_BORDER)
        pressure = len(self.enemies) + len(self.spawn_queue)
        self._draw_text(f"WAVE {self.wave}", 14, 10, size=15, color=GREEN)
        self._draw_text(f"ENEMIES {pressure}", 14, 38, size=12, color=ORANGE if pressure >= 15 else WHITE)
        self._draw_text(
            f"HP {self.base_hp}/{self.max_base_hp}",
            138,
            10,
            size=14,
            color=RED if self.base_hp <= 6 else WHITE,
        )
        self._draw_text(f"SCORE {self.score}", 138, 38, size=14, color=YELLOW)
        self._draw_text(f"BEST {self.best_score} (W{self.best_wave})", 246, 38, size=11, color=CYAN)
        self._draw_text(f"KILLS {self.kills} [{CURRENT_DIFFICULTY[0]}]", 286, 12, size=12, color=get_difficulty_cfg()["color"])

        self._draw_rect(self.btn_guide.x, self.btn_guide.y, self.btn_guide.w, self.btn_guide.h, SLOT_BG)
        self._draw_rect(self.btn_guide.x, self.btn_guide.y, self.btn_guide.w, self.btn_guide.h, CYAN, line_width=1.5)
        self._draw_text("GUIDE", self.btn_guide.centerx, self.btn_guide.y + 5, size=11, color=CYAN, center=True)

        p_col = YELLOW if self.state == "PAUSED" else GREEN
        p_lbl = "RESUME" if self.state == "PAUSED" else "PAUSE"
        self._draw_rect(self.btn_pause.x, self.btn_pause.y, self.btn_pause.w, self.btn_pause.h, SLOT_BG)
        self._draw_rect(self.btn_pause.x, self.btn_pause.y, self.btn_pause.w, self.btn_pause.h, p_col, line_width=1.5)
        self._draw_text(p_lbl, self.btn_pause.centerx, self.btn_pause.y + 5, size=11, color=p_col, center=True)

    def _draw_bottom_deck(self):
        self._draw_rect(0, DECK_TOP, SCREEN_WIDTH, SCREEN_HEIGHT - DECK_TOP, PANEL_BG)
        self._draw_rect(0, DECK_TOP, SCREEN_WIDTH, 2, SLOT_BORDER)
        merge_hints = self._get_merge_hint_locations()

        for idx, rect in enumerate(self.dock_rects):
            self._draw_rect(rect.x, rect.y, rect.w, rect.h, SLOT_BG)
            self._draw_rect(rect.x, rect.y, rect.w, rect.h, SLOT_BORDER, line_width=1.5)
            u = self.dock_units[idx]
            if u is not None and self.drag_source != ("dock", idx):
                self._draw_unit_art(
                    u,
                    rect.centerx,
                    rect.centery + 4,
                    18.0,
                    show_aim=False,
                    merge_hint=("dock", idx) in merge_hints,
                )

        for utype, rect in self.spawn_btns:
            meta = UNIT_META[utype]
            cost = int(meta["cost"])
            can_buy = self.elixir >= cost
            col = meta["color"]  # type: ignore
            self._draw_rect(rect.x, rect.y, rect.w, rect.h, SLOT_BG)
            self._draw_rect(rect.x, rect.y, rect.w, rect.h, col if can_buy else GRAY, line_width=2.0)
            self._draw_text(
                str(meta["name"]),
                rect.centerx,
                rect.y + 8,
                size=14,
                color=col if can_buy else GRAY,
                center=True,
            )
            self._draw_text(
                f"{cost} ELIXIR",
                rect.centerx,
                rect.y + 30,
                size=13,
                color=PINK if can_buy else GRAY,
                center=True,
            )

        self._draw_rect(self.btn_up_sniper.x, self.btn_up_sniper.y, self.btn_up_sniper.w, self.btn_up_sniper.h, SLOT_BG)
        self._draw_rect(self.btn_up_sniper.x, self.btn_up_sniper.y, self.btn_up_sniper.w, self.btn_up_sniper.h, CYAN, line_width=1.5)
        self._draw_text(
            f"SNIPER+ L{self.sniper_up_lvl} ({self.sniper_up_cost})",
            self.btn_up_sniper.centerx,
            self.btn_up_sniper.y + 13,
            size=12,
            color=CYAN,
            center=True,
        )

        self._draw_rect(self.btn_up_gatling.x, self.btn_up_gatling.y, self.btn_up_gatling.w, self.btn_up_gatling.h, SLOT_BG)
        self._draw_rect(self.btn_up_gatling.x, self.btn_up_gatling.y, self.btn_up_gatling.w, self.btn_up_gatling.h, YELLOW, line_width=1.5)
        self._draw_text(
            f"GATLING+ L{self.gatling_up_lvl} ({self.gatling_up_cost})",
            self.btn_up_gatling.centerx,
            self.btn_up_gatling.y + 13,
            size=12,
            color=YELLOW,
            center=True,
        )

        nova_ready = self.nova_charge >= 1.0
        self._draw_rect(self.btn_nova.x, self.btn_nova.y, self.btn_nova.w, self.btn_nova.h, SLOT_BG)
        self._draw_rect(
            self.btn_nova.x,
            self.btn_nova.y,
            self.btn_nova.w,
            self.btn_nova.h,
            CYAN if nova_ready else GRAY,
            line_width=2.0,
        )
        nova_lbl = "NOVA READY!" if nova_ready else f"NOVA {int(self.nova_charge * 100)}%"
        self._draw_text(
            nova_lbl,
            self.btn_nova.centerx,
            self.btn_nova.y + 13,
            size=12,
            color=CYAN if nova_ready else GRAY,
            center=True,
        )

        bar_y = SCREEN_HEIGHT - 36
        bar_w = SCREEN_WIDTH - 32
        ratio = clamp(self.elixir / MAX_ELIXIR, 0.0, 1.0)
        self._draw_rect(16, bar_y, bar_w, 22, SLOT_BG)
        self._draw_rect(16, bar_y, bar_w * ratio, 22, PINK)
        self._draw_rect(16, bar_y, bar_w, 22, SLOT_BORDER, line_width=1.5)
        self._draw_text(
            f"ELIXIR: {self.elixir:.1f} / {MAX_ELIXIR:.0f}",
            SCREEN_WIDTH * 0.5,
            bar_y + 3,
            size=14,
            color=WHITE,
            center=True,
        )

    def _draw_title_screen(self):
        self._draw_rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, BG_DARK)
        self._draw_text("AEGIS PATH", SCREEN_WIDTH * 0.5, 220, size=42, color=CYAN, center=True)
        self._draw_text("MERGE & ELIXIR DEFENSE", SCREEN_WIDTH * 0.5, 275, size=18, color=YELLOW, center=True)
        self._draw_text(
            f"BEST SCORE: {self.best_score}  |  BEST WAVE: {self.best_wave}",
            SCREEN_WIDTH * 0.5,
            335,
            size=15,
            color=PINK,
            center=True,
        )
        self._draw_text("TAP TO CHOOSE A MAP", SCREEN_WIDTH * 0.5, 470, size=20, color=GREEN, center=True)
        self._draw_rect(self.btn_guide.x, self.btn_guide.y, self.btn_guide.w, self.btn_guide.h, SLOT_BG)
        self._draw_rect(self.btn_guide.x, self.btn_guide.y, self.btn_guide.w, self.btn_guide.h, CYAN, line_width=1.5)
        self._draw_text("GUIDE", self.btn_guide.centerx, self.btn_guide.y + 5, size=11, color=CYAN, center=True)

    def _draw_map_select_screen(self):
        self._draw_rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, BG_DARK)
        self._draw_text("SELECT DIFFICULTY & MAP", SCREEN_WIDTH * 0.5, 82, size=28, color=CYAN, center=True)
        self._draw_text("Choose difficulty first, then tap a map", SCREEN_WIDTH * 0.5, 132, size=15, color=GRAY, center=True)

        for d_idx, rect in enumerate(self.difficulty_rects):
            d_key = DIFFICULTY_ORDER[d_idx]
            d_cfg = DIFFICULTY_CONFIGS[d_key]
            d_col = d_cfg["color"]  # type: ignore
            selected = (d_key == CURRENT_DIFFICULTY)
            self._draw_rect(rect.x, rect.y, rect.w, rect.h, SLOT_BG)
            self._draw_rect(rect.x, rect.y, rect.w, rect.h, d_col if selected else SLOT_BORDER, line_width=2.5 if selected else 1.5)
            self._draw_text(
                str(d_cfg["label"]),
                rect.centerx,
                rect.y + 12,
                size=15,
                color=d_col if selected else GRAY,
                center=True,
            )

        descriptions = ["Original winding route", "Straight vertical lane", "Spiral toward the center", "Long straight zigzag route"]
        for i, rect in enumerate(self.map_select_rects):
            accent = [CYAN, GREEN, PURPLE, ORANGE][i]
            self._draw_rect(rect.x, rect.y, rect.w, rect.h, SLOT_BG)
            self._draw_rect(rect.x, rect.y, rect.w, rect.h, accent, line_width=2.0)
            self._draw_text(MAPS[i]["name"], rect.centerx, rect.y + 11, size=17, color=accent, center=True)
            self._draw_text(descriptions[i], rect.centerx, rect.y + 37, size=12, color=WHITE, center=True)
        self._draw_rect(self.btn_guide.x, self.btn_guide.y, self.btn_guide.w, self.btn_guide.h, SLOT_BG)
        self._draw_rect(self.btn_guide.x, self.btn_guide.y, self.btn_guide.w, self.btn_guide.h, CYAN, line_width=1.5)
        self._draw_text("GUIDE", self.btn_guide.centerx, self.btn_guide.y + 5, size=11, color=CYAN, center=True)

    def _draw_fitted_texture(self, tex: object, box_x: float, box_y: float, box_w: float, box_h: float):
        tex_w, tex_h = tex.size
        scale = min(box_w / max(1.0, float(tex_w)), box_h / max(1.0, float(tex_h)))
        draw_w = tex_w * scale
        draw_h = tex_h * scale
        draw_x = box_x + (box_w - draw_w) * 0.5
        draw_y = box_y + (box_h - draw_h) * 0.5
        ky = to_ky(draw_y + draw_h)
        Color(1.0, 1.0, 1.0, 1.0)
        Rectangle(texture=tex, pos=(draw_x, ky), size=(draw_w, draw_h))

    def _draw_guide_screen(self):
        self._draw_rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, BG_DARK)
        self._draw_text("HOW TO PLAY & STATS", SCREEN_WIDTH * 0.5, 36, size=24, color=CYAN, center=True)

        top_y = 76.0
        avail_h = self.btn_close_guide.y - 16.0 - top_y
        max_w = SCREEN_WIDTH - 24.0

        if self.info_texture is not None and self.info2_texture is not None:
            gap = 12.0
            half_h = (avail_h - gap) * 0.5
            self._draw_fitted_texture(self.info_texture, 12.0, top_y, max_w, half_h)
            self._draw_fitted_texture(self.info2_texture, 12.0, top_y + half_h + gap, max_w, half_h)
        elif self.info_texture is not None:
            self._draw_fitted_texture(self.info_texture, 12.0, top_y, max_w, avail_h)
        elif self.info2_texture is not None:
            self._draw_fitted_texture(self.info2_texture, 12.0, top_y, max_w, avail_h)
        else:
            lines = [
                "1. SPAWN SNIPER, GATLING OR MORTAR USING ELIXIR.",
                "2. DRAG UNITS ONTO TOWER PADS TO DEFEND THE LANE.",
                "3. DRAG SAME TYPE + SAME TIER ONTO EACH OTHER TO MERGE (T1..T5).",
                "4. SABOTEUR (en7.png) APPEARS W10+ EVERY 3 WAVES & DISABLES TOWERS 5s.",
                "5. HEALER HELPS RECOVER TOWERS; BOSS6 FIRES LASER & DAMAGES TOWERS.",
            ]
            for i, line in enumerate(lines):
                self._draw_text(line, SCREEN_WIDTH * 0.5, 180 + i * 54, size=13, color=WHITE, center=True)

        self._draw_rect(self.btn_close_guide.x, self.btn_close_guide.y, self.btn_close_guide.w, self.btn_close_guide.h, SLOT_BG)
        self._draw_rect(self.btn_close_guide.x, self.btn_close_guide.y, self.btn_close_guide.w, self.btn_close_guide.h, GREEN, line_width=2.0)
        self._draw_text("BACK", self.btn_close_guide.centerx, self.btn_close_guide.y + 13, size=18, color=GREEN, center=True)

    def _draw_pause_overlay(self):
        self._draw_rect(0, ARENA_TOP, SCREEN_WIDTH, ARENA_BOTTOM - ARENA_TOP, rgb(6, 8, 12, 0.72))
        self._draw_text("GAME PAUSED", SCREEN_WIDTH * 0.5, 290, size=32, color=YELLOW, center=True)
        self._draw_text("TAP RESUME OR ARENA TO CONTINUE", SCREEN_WIDTH * 0.5, 345, size=16, color=GREEN, center=True)

    def _draw_gameover_overlay(self):
        self._draw_rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, rgb(6, 8, 12, 0.78))
        self._draw_text("BASE OVERRUN", SCREEN_WIDTH * 0.5, 320, size=34, color=RED, center=True)
        self._draw_text(f"WAVE {self.wave}  |  SCORE {self.score}", SCREEN_WIDTH * 0.5, 375, size=20, color=YELLOW, center=True)
        self._draw_text(
            f"BEST SCORE: {self.best_score}  |  BEST WAVE: {self.best_wave}",
            SCREEN_WIDTH * 0.5,
            415,
            size=16,
            color=CYAN,
            center=True,
        )
        self._draw_text("TAP TO PLAY AGAIN", SCREEN_WIDTH * 0.5, 475, size=18, color=GREEN, center=True)

    def on_parent(self, widget, parent):
        if parent is None:
            self._sync_best_stats()
            self.audio.cleanup()


class AegisPathApp(App):
    def build(self):
        self.title = TITLE
        if platform not in ("android", "ios"):
            try:
                Window.size = (SCREEN_WIDTH, SCREEN_HEIGHT)
            except Exception:
                pass
        return AegisPathWidget()


if __name__ == "__main__":
    AegisPathApp().run()
