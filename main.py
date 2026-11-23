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
from typing import Dict, List, Optional, Tuple

from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.core.image import Image as CoreImage
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, PopMatrix, PushMatrix, Rectangle, Rotate, Scale, Translate
from kivy.uix.widget import Widget

# ==============================================================================
# 1. PORTRAIT MOBILE DISPLAY & PALETTE CONSTANTS.
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
BG_LANE = rgb(24, 30, 46)
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


def load_turret_textures() -> Dict[Tuple[str, int], object]:
    textures: Dict[Tuple[str, int], object] = {}
    assets_dir = resolve_assets_dir()
    for unit_type, suffix in TURRET_FILE_PREFIX.items():
        for tier in range(1, 6):
            path = os.path.join(assets_dir, f"T{tier}_{suffix}.png")
            if os.path.exists(path):
                try:
                    img = CoreImage(path)
                    if img.texture is not None:
                        textures[(unit_type, tier)] = img.texture
                except Exception as exc:
                    print(f"[ASSET ERROR] {path}: {exc}")
    return textures


def load_enemy_textures() -> Dict[str, object]:
    textures: Dict[str, object] = {}
    assets_dir = resolve_assets_dir()
    for enemy_kind, filename in ENEMY_FILE_NAMES.items():
        path = os.path.join(assets_dir, filename)
        if os.path.exists(path):
            try:
                img = CoreImage(path)
                if img.texture is not None:
                    textures[enemy_kind] = img.texture
            except Exception as exc:
                print(f"[ASSET ERROR] {path}: {exc}")
    return textures


def load_info_texture() -> Optional[object]:
    info_path = os.path.join(resolve_assets_dir(), "info.png")
    if os.path.exists(info_path):
        try:
            img = CoreImage(info_path)
            return img.texture
        except Exception as exc:
            print(f"[ASSET ERROR] {info_path}: {exc}")
    return None


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
# 5. VISUAL FX: PARTICLES, SHOCKWAVES & FLOATING LABELS
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
# 6. LANE ENEMIES & PROJECTILES
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
            "spiked": (310.0, 48.0, 19.0, CYAN, 2, 0.18, 90),
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
        self.spin += dt * (4.5 if self.kind in ("swift", "spiked") else 1.8)

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
        self.size_hint = (1, 1)

        self._text_cache: Dict[Tuple[str, int], Tuple[object, int, int]] = {}
        self.best_score, self.best_wave = load_best_stats()

        self.audio = AudioEngine()
        self.turret_textures: Dict[Tuple[str, int], object] = load_turret_textures()
        self.enemy_textures: Dict[str, object] = load_enemy_textures()
        self.info_texture: Optional[object] = load_info_texture()
        self.state = "TITLE"
        self._state_before_guide = "TITLE"

        self.btn_guide = RectBox(SCREEN_WIDTH - 92, 10, 78, 24)
        self.btn_pause = RectBox(SCREEN_WIDTH - 92, 40, 78, 24)
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
        Clock.schedule_interval(self.step, 1.0 / FPS)

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
        self._active_touch_uid = None

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
        spiked = max(0, (w - 2) * 2)
        has_boss = (w % 2 == 0) or (w >= 3)

        seq: List[str] = []
        for i in range(max(runners, swifts, brutes, spiked)):
            if i < runners:
                seq.append("runner")
            if i < swifts and i % 2 == 0:
                seq.append("swift")
            if i < brutes and i % 2 == 1:
                seq.append("brute")
            if i < spiked and i % 3 == 2:
                seq.append("spiked")
        if has_boss:
            seq.append("boss")
        self.spawn_queue = seq
        self.spawn_timer = 0.7

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

    def _can_merge(self, a: Optional[DefenseUnit], b: Optional[DefenseUnit]) -> bool:
        if a is None or b is None:
            return False
        return a.unit_type == b.unit_type and a.tier == b.tier and a.tier < 5

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
            self._set_unit_at(src, None)
            self._set_unit_at(dst, merged)
            self.audio.play("merge")
            self.nova_charge = min(1.0, self.nova_charge + 0.16)
            self.score += 40 * merged.tier
            self._sync_best_stats()
            tx, ty = self._loc_center(dst)
            self._add_particles(tx, ty, merged.color, count=16, spd=150.0)
            self.shockwaves.append(Shockwave(tx, ty, 44.0, merged.color, 0.30, 0.30))
            self._add_popup(tx, ty - 14, f"T{merged.tier} MERGE!", merged.color)
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
        w = max(1.0, float(self.width))
        h = max(1.0, float(self.height))
        scale = min(w / SCREEN_WIDTH, h / SCREEN_HEIGHT)
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
        lx, ly = self._event_to_logical(touch.x, touch.y)

        if self.state == "TITLE":
            if self.btn_guide.collidepoint(lx, ly):
                self._state_before_guide = "TITLE"
                self.state = "GUIDE"
            else:
                self.reset_game()
                self.state = "PLAYING"
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

        for idx, (px, py) in enumerate(TOWER_PADS):
            if dist(lx, ly, px, py) <= 34.0 and self.pad_units[idx] is not None:
                self.drag_source = ("pad", idx)
                self.drag_pos = (lx, ly)
                self._active_touch_uid = touch.uid
                touch.grab(self)
                return True

        for idx, rect in enumerate(self.dock_rects):
            if rect.collidepoint(lx, ly) and self.dock_units[idx] is not None:
                self.drag_source = ("dock", idx)
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
                        self._handle_drop(self.drag_source, dst)
            self.drag_source = None
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
        self.shake_mag = max(0.0, self.shake_mag - dt * 28.0)
        self.particles = [p for p in self.particles if p.update(dt)]
        self.shockwaves = [s for s in self.shockwaves if s.update(dt)]
        self.popups = [p for p in self.popups if p.update(dt)]

    def _update_playing(self, dt: float):
        self.elixir = min(MAX_ELIXIR, self.elixir + ELIXIR_REGEN_PER_SEC * dt)

        if self.spawn_queue:
            self.spawn_timer -= dt
            if self.spawn_timer <= 0.0:
                kind = self.spawn_queue.pop(0)
                self.enemies.append(LaneEnemy.create(kind, self.wave))
                self.spawn_timer = 0.55 if kind == "swift" else 0.92
        elif not self.enemies:
            self.wave += 1
            self._sync_best_stats()
            self.elixir = min(MAX_ELIXIR, self.elixir + 2.5)
            self._add_popup(SCREEN_WIDTH * 0.5, 250, f"WAVE {self.wave}", GREEN)
            self._queue_wave(self.wave)

        for e in list(self.enemies):
            reached_end = e.update(dt)
            if reached_end:
                if e in self.enemies:
                    self.enemies.remove(e)
                self.base_hp = max(0, self.base_hp - e.base_dmg)
                self.shake_mag = 7.0
                self.audio.play("base_hit")
                self._add_particles(e.x, e.y, RED, count=12, spd=120.0)
                if self.base_hp <= 0:
                    self._sync_best_stats()
                    self.state = "GAMEOVER"
                    return

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
                    hit_enemy.hit_flash = hit_enemy.hit_flash = 0.09
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

    def _draw_enemy_shape(self, e: LaneEnemy):
        r = e.radius
        ky = to_ky(e.y)
        tex = self.enemy_textures.get(e.kind)

        if tex is not None:
            sprite_size = r * 2.5
            deg = -math.degrees(e.spin) if e.kind in ("swift", "spiked") else 0.0
            PushMatrix()
            Rotate(angle=deg, origin=(e.x, ky))
            if e.hit_flash > 0:
                Color(1.0, 0.45, 0.45, 1.0)
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
    ):
        recoil_x = -math.cos(unit.aim_angle) * unit.recoil if show_aim else 0.0
        recoil_y = -math.sin(unit.aim_angle) * unit.recoil if show_aim else 0.0
        ux = cx + recoil_x
        uy = cy + recoil_y
        ky = to_ky(uy)

        self._draw_circle(cx + 2, cy + 3, radius * 1.05, SHADOW_COLOR)
        self._draw_circle(cx, cy, radius * 0.96, PANEL_BG)
        self._draw_circle(cx, cy, radius * 0.96, unit.color, line_width=2.0)

        tex = self.turret_textures.get((unit.unit_type, unit.tier))
        if tex is not None:
            sprite_size = radius * 2.25
            deg = -math.degrees(unit.aim_angle) if show_aim else 0.0
            PushMatrix()
            Rotate(angle=deg, origin=(ux, ky))
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
                Color(*unit.color)
                Line(points=[ux, ky, bx, to_ky(by)], width=3.5)

        self._draw_text(
            f"T{unit.tier}",
            cx,
            cy + radius + 3,
            size=11,
            color=unit.color,
            center=True,
        )

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
            Rectangle(pos=(0, 0), size=(self.width, self.height))

            PushMatrix()
            Translate(off_x + sx * scale, off_y - sy * scale)
            Scale(scale, scale, origin=(0, 0))

            if self.state == "TITLE":
                self._draw_title_screen()
            elif self.state == "GUIDE":
                self._draw_guide_screen()
            else:
                self._draw_arena()
                self._draw_top_bar()
                self._draw_bottom_deck()
                self._draw_drag_overlays()
                if self.state == "PAUSED":
                    self._draw_pause_overlay()
                elif self.state == "GAMEOVER":
                    self._draw_gameover_overlay()

            PopMatrix()

    def _draw_arena(self):
        self._draw_rect(0, ARENA_TOP, SCREEN_WIDTH, ARENA_BOTTOM - ARENA_TOP, BG_DARK)

        for gx in range(0, SCREEN_WIDTH, 36):
            for gy in range(ARENA_TOP, ARENA_BOTTOM, 36):
                if ((gx // 36) + (gy // 36)) % 2 == 0:
                    self._draw_rect(gx, gy, 36, 36, BG_TILE_ALT)

        if len(LANE_POINTS) >= 2:
            pts_kivy: List[float] = []
            for px, py in LANE_POINTS:
                pts_kivy.extend([px, to_ky(py)])

            Color(*LANE_BORDER)
            Line(points=pts_kivy, width=26, cap="round", joint="round")
            Color(*BG_LANE)
            Line(points=pts_kivy, width=21, cap="round", joint="round")
            Color(*LANE_CENTER)
            Line(points=pts_kivy, width=2, cap="round", joint="round")

            sx, sy = LANE_POINTS[0]
            ex, ey = LANE_POINTS[-1]
            self._draw_circle(sx, sy, 14, RED, line_width=2.5)
            self._draw_circle(ex, ey, 16, GREEN, line_width=2.5)

        for idx, (px, py) in enumerate(TOWER_PADS):
            u = self.pad_units[idx]
            ring_col = u.color if u is not None else SLOT_BORDER
            self._draw_circle(px, py, 24, SLOT_BG)
            self._draw_circle(px, py, 24, ring_col, line_width=2.0)
            if u is not None and self.drag_source != ("pad", idx):
                self._draw_unit_art(u, px, py, 19.0, show_aim=True)

        for e in self.enemies:
            self._draw_enemy_shape(e)

        for proj in self.projectiles:
            self._draw_circle(proj.x, proj.y, proj.radius, proj.color)

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

    def _draw_top_bar(self):
        self._draw_rect(0, 0, SCREEN_WIDTH, TOP_BAR_H, PANEL_BG)
        self._draw_rect(0, TOP_BAR_H - 2, SCREEN_WIDTH, 2, SLOT_BORDER)
        self._draw_text(f"WAVE {self.wave}", 14, 10, size=15, color=GREEN)
        self._draw_text(
            f"HP {self.base_hp}/{self.max_base_hp}",
            14,
            38,
            size=14,
            color=RED if self.base_hp <= 6 else WHITE,
        )
        self._draw_text(f"SCORE {self.score}", 138, 10, size=15, color=YELLOW)
        self._draw_text(f"BEST {self.best_score} (W{self.best_wave})", 138, 38, size=12, color=CYAN)
        self._draw_text(f"KILLS {self.kills}", 320, 12, size=13, color=GRAY)

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

        for idx, rect in enumerate(self.dock_rects):
            self._draw_rect(rect.x, rect.y, rect.w, rect.h, SLOT_BG)
            self._draw_rect(rect.x, rect.y, rect.w, rect.h, SLOT_BORDER, line_width=1.5)
            u = self.dock_units[idx]
            if u is not None and self.drag_source != ("dock", idx):
                self._draw_unit_art(u, rect.centerx, rect.centery + 4, 18.0, show_aim=False)

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
        self._draw_text("TAP ANYWHERE TO START", SCREEN_WIDTH * 0.5, 470, size=20, color=GREEN, center=True)
        self._draw_rect(self.btn_guide.x, self.btn_guide.y, self.btn_guide.w, self.btn_guide.h, SLOT_BG)
        self._draw_rect(self.btn_guide.x, self.btn_guide.y, self.btn_guide.w, self.btn_guide.h, CYAN, line_width=1.5)
        self._draw_text("GUIDE", self.btn_guide.centerx, self.btn_guide.y + 5, size=11, color=CYAN, center=True)

    def _draw_guide_screen(self):
        self._draw_rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, BG_DARK)
        self._draw_text("HOW TO PLAY & STATS", SCREEN_WIDTH * 0.5, 36, size=24, color=CYAN, center=True)

        if self.info_texture is not None:
            tex_w, tex_h = self.info_texture.size
            top_y = 76.0
            max_w = SCREEN_WIDTH - 24
            max_h = self.btn_close_guide.y - 16.0 - top_y
            scale = min(max_w / max(1.0, float(tex_w)), max_h / max(1.0, float(tex_h)))
            draw_w = tex_w * scale
            draw_h = tex_h * scale
            draw_x = (SCREEN_WIDTH - draw_w) * 0.5
            ky = to_ky(top_y + draw_h)

            Color(1.0, 1.0, 1.0, 1.0)
            Rectangle(texture=self.info_texture, pos=(draw_x, ky), size=(draw_w, draw_h))
        else:
            lines = [
                "1. SPAWN SNIPER, GATLING OR MORTAR USING ELIXIR.",
                "2. DRAG UNITS ONTO TOWER PADS TO DEFEND THE LANE.",
                "3. DRAG SAME TYPE + SAME TIER ONTO EACH OTHER TO MERGE (T1..T5).",
                "4. DRAG ONTO SELL BUTTON TO REFUND PARTIAL ELIXIR.",
                "5. USE PAUSE OR NOVA BAR TO CONTROL THE WAVE.",
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
        try:
            Window.size = (SCREEN_WIDTH, SCREEN_HEIGHT)
        except Exception:
            pass
        return AegisPathWidget()


if __name__ == "__main__":
    AegisPathApp().run()
