"""
AEGIS PATH: MERGE & ELIXIR (PLAYABLE BALANCED COMBAT)
Portrait Mobile-Ready Lane Defense + Merge + Elixir Game in Python 3.13 & Pygame.
Touch/Mouse-only controls (no keyboard required).
"""

import math
import random
import array
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict
import pygame

# ==============================================================================
# 1. PORTRAIT MOBILE DISPLAY & PALETTE CONSTANTS
# ==============================================================================

SCREEN_WIDTH = 540
SCREEN_HEIGHT = 960
FPS = 60
TITLE = "AEGIS PATH // Merge & Elixir"

# Split Screen Layout (Portrait)
TOP_BAR_H = 74
ARENA_TOP = TOP_BAR_H
ARENA_BOTTOM = 592
DECK_TOP = ARENA_BOTTOM

# Colors
BG_DARK = (9, 12, 20)
BG_TILE_ALT = (13, 17, 28)
BG_DECOR = (24, 33, 52)
BG_LANE = (24, 30, 46)
BG_LANE_INNER = (19, 24, 37)
LANE_CURB_DARK = (34, 44, 66)
LANE_CURB_LIGHT = (76, 102, 146)
LANE_CENTER = (62, 92, 136)
LANE_BORDER = (52, 68, 98)
SHADOW_COLOR = (4, 6, 10, 130)

PANEL_BG = (14, 18, 29)
SLOT_BG = (22, 29, 45)
SLOT_BORDER = (64, 84, 118)

WHITE = (244, 248, 255)
BLACK = (6, 8, 12)
GRAY = (132, 145, 168)
CYAN = (0, 235, 255)
BLUE = (65, 145, 255)
PURPLE = (185, 75, 255)
PINK = (255, 65, 165)
RED = (255, 60, 75)
ORANGE = (255, 140, 30)
YELLOW = (255, 215, 45)
GREEN = (55, 245, 140)
ICE = (110, 220, 255)

# Slow, Deliberate Elixir Economy
MAX_ELIXIR = 10.0
ELIXIR_REGEN_PER_SEC = 0.22


# ==============================================================================
# 2. MATH, SPLINE PATH & DRAWING HELPERS
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


def draw_poly(
    surf: pygame.Surface,
    color: Tuple[int, int, int],
    center: Tuple[float, float],
    radius: float,
    sides: int,
    angle: float = 0.0,
    width: int = 0,
):
    pts = []
    for i in range(sides):
        a = angle + (2.0 * math.pi * i) / sides
        pts.append((center[0] + math.cos(a) * radius, center[1] + math.sin(a) * radius))
    if len(pts) >= 3:
        pygame.draw.polygon(surf, color, pts, width)


def draw_drop_shadow(surf: pygame.Surface, center: Tuple[float, float], radius: float, offset_y: float = 5.0):
    r = max(4, int(radius * 1.15))
    s = pygame.Surface((r * 2 + 6, r * 2 + 6), pygame.SRCALPHA)
    pygame.draw.ellipse(s, SHADOW_COLOR, (3, 3, r * 2, int(r * 1.55)))
    surf.blit(s, (int(center[0] - r - 3), int(center[1] + offset_y - r * 0.75)))


def draw_unit_art(
    surf: pygame.Surface,
    unit_type: str,
    tier: int,
    color: Tuple[int, int, int],
    center: Tuple[float, float],
    angle: float,
    with_shadow: bool = True,
):
    rad = 15.0 + (tier - 1) * 1.2
    if with_shadow:
        draw_drop_shadow(surf, center, rad, 5.0)

    depth_c = (center[0], center[1] + 4.0)

    if unit_type == "sniper":
        sq_ang = angle + math.pi / 4.0
        draw_poly(surf, LANE_CURB_DARK, depth_c, rad * 1.08, 4, sq_ang, 0)
        draw_poly(surf, BLACK, center, rad * 1.08, 4, sq_ang, 0)
        draw_poly(surf, color, center, rad * 1.08, 4, sq_ang, 3)
        draw_poly(surf, color, center, rad * 0.45, 4, angle, 0)
        bx = center[0] + math.cos(angle) * (rad + 10)
        by = center[1] + math.sin(angle) * (rad + 10)
        pygame.draw.line(surf, WHITE, center, (bx, by), 4)
        sx = center[0] + math.cos(angle) * (rad * 0.55) - math.sin(angle) * 5.0
        sy = center[1] + math.sin(angle) * (rad * 0.55) + math.cos(angle) * 5.0
        pygame.draw.circle(surf, color, (int(sx), int(sy)), 3)

    elif unit_type == "gatling":
        draw_poly(surf, LANE_CURB_DARK, depth_c, rad * 1.16, 3, angle, 0)
        draw_poly(surf, BLACK, center, rad * 1.16, 3, angle, 0)
        draw_poly(surf, color, center, rad * 1.16, 3, angle, 3)
        pygame.draw.circle(surf, WHITE, (int(center[0]), int(center[1])), 4)
        px = -math.sin(angle) * 4.5
        py = math.cos(angle) * 4.5
        for sign in (-1.0, 1.0):
            s_pt = (center[0] + px * sign, center[1] + py * sign)
            e_pt = (
                center[0] + px * sign + math.cos(angle) * (rad + 6),
                center[1] + py * sign + math.sin(angle) * (rad + 6),
            )
            pygame.draw.line(surf, WHITE, s_pt, e_pt, 2)

    else:  # mortar (Hexagon)
        draw_poly(surf, LANE_CURB_DARK, depth_c, rad * 1.10, 6, angle, 0)
        draw_poly(surf, BLACK, center, rad * 1.10, 6, angle, 0)
        draw_poly(surf, color, center, rad * 1.10, 6, angle, 3)
        draw_poly(surf, color, center, rad * 0.62, 6, -angle * 0.5, 2)
        bx = center[0] + math.cos(angle) * (rad + 7)
        by = center[1] + math.sin(angle) * (rad + 7)
        pygame.draw.line(surf, WHITE, center, (bx, by), 6)
        pygame.draw.circle(surf, color, (int(bx), int(by)), 4, 2)


def draw_ring_pulse(
    surf: pygame.Surface,
    color: Tuple[int, int, int],
    center: Tuple[float, float],
    radius: float,
    alpha: int,
    width: int = 3,
):
    r = max(2, int(radius))
    s = pygame.Surface((r * 2 + 10, r * 2 + 10), pygame.SRCALPHA)
    pygame.draw.circle(s, (*color, clamp(alpha, 0, 255)), (r + 5, r + 5), r, width)
    surf.blit(s, (int(center[0] - r - 5), int(center[1] - r - 5)))


# ==============================================================================
# 3. PROCEDURAL AUDIO SYNTHESIZER (NO EXTERNAL ASSETS)
# ==============================================================================

class AudioEngine:
    def __init__(self):
        self.enabled = False
        self.sounds: Dict[str, pygame.mixer.Sound] = {}
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            self.enabled = True
            self._build_sounds()
        except Exception:
            self.enabled = False

    def _tone(
        self,
        dur: float,
        f0: float,
        f1: float,
        wave: str = "sine",
        vol: float = 0.2,
        decay: float = 1.3,
    ) -> Optional[pygame.mixer.Sound]:
        if not self.enabled:
            return None
        sr = 22050
        n = max(1, int(sr * dur))
        buf = array.array("h", [0] * n)
        phase = 0.0
        for i in range(n):
            t = i / max(1, n - 1)
            freq = f0 + (f1 - f0) * t
            phase += (2.0 * math.pi * freq) / sr
            if wave == "sine":
                s = math.sin(phase)
            elif wave == "square":
                s = 1.0 if math.sin(phase) >= 0 else -1.0
            elif wave == "saw":
                s = 2.0 * ((phase / (2.0 * math.pi)) % 1.0) - 1.0
            else:
                s = math.sin(phase)
            env = ((1.0 - t) ** decay) * vol
            buf[i] = int(max(-32767, min(32767, s * env * 32767)))
        return pygame.mixer.Sound(buffer=buf)

    def _build_sounds(self):
        self.sounds["sniper"] = self._tone(0.12, 340, 70, "saw", 0.21, 1.5)
        self.sounds["gatling"] = self._tone(0.05, 680, 340, "square", 0.11, 1.8)
        self.sounds["mortar"] = self._tone(0.18, 190, 52, "saw", 0.24, 1.2)
        self.sounds["merge"] = self._tone(0.28, 360, 920, "sine", 0.25, 0.8)
        self.sounds["spawn"] = self._tone(0.14, 240, 520, "sine", 0.18, 1.1)
        self.sounds["enemy_hit"] = self._tone(0.05, 420, 180, "sine", 0.09, 1.6)
        self.sounds["enemy_die"] = self._tone(0.19, 310, 65, "saw", 0.20, 1.3)
        self.sounds["base_hit"] = self._tone(0.32, 140, 42, "square", 0.32, 1.0)
        self.sounds["nova"] = self._tone(0.42, 950, 160, "sine", 0.26, 0.7)

    def play(self, name: str):
        if self.enabled and name in self.sounds and self.sounds[name]:
            self.sounds[name].play()


# ==============================================================================
# 4. VISUAL FX: PARTICLES, SHOCKWAVES & FLOATING LABELS
# ==============================================================================

@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    color: Tuple[int, int, int]
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

    def draw(self, surf: pygame.Surface, shake: Tuple[int, int]):
        ratio = clamp(self.life / self.max_life, 0.0, 1.0)
        r = max(1, int(self.size * ratio))
        col = (int(self.color[0] * ratio), int(self.color[1] * ratio), int(self.color[2] * ratio))
        pygame.draw.circle(surf, col, (int(self.x + shake[0]), int(self.y + shake[1])), r)


@dataclass
class Shockwave:
    x: float
    y: float
    max_radius: float
    color: Tuple[int, int, int]
    life: float = 0.35
    max_life: float = 0.35

    def update(self, dt: float) -> bool:
        self.life -= dt
        return self.life > 0

    def draw(self, surf: pygame.Surface, shake: Tuple[int, int]):
        prog = 1.0 - clamp(self.life / self.max_life, 0.0, 1.0)
        r = 6 + self.max_radius * prog
        alpha = int((1.0 - prog) * 190)
        draw_ring_pulse(surf, self.color, (self.x + shake[0], self.y + shake[1]), r, alpha, 3)


@dataclass
class FloatingPopup:
    x: float
    y: float
    text: str
    color: Tuple[int, int, int]
    life: float = 0.75
    vy: float = -42.0

    def update(self, dt: float) -> bool:
        self.y += self.vy * dt
        self.life -= dt
        return self.life > 0

    def draw(self, surf: pygame.Surface, font: pygame.font.Font, shake: Tuple[int, int]):
        alpha = int(clamp(self.life / 0.75, 0.0, 1.0) * 255)
        img = font.render(self.text, True, self.color)
        img.set_alpha(alpha)
        surf.blit(img, img.get_rect(center=(int(self.x + shake[0]), int(self.y + shake[1]))))


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
    color: Tuple[int, int, int]
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
        # Playable enemy HP & speeds while keeping slow elixir drops
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

    def draw(self, surf: pygame.Surface, font: pygame.font.Font, shake: Tuple[int, int]):
        cx = self.x + shake[0]
        cy = self.y + shake[1]
        draw_drop_shadow(surf, (cx, cy), self.radius, 4.5)

        col = WHITE if self.hit_flash > 0 else (ICE if self.slow_timer > 0 else self.color)
        sides = 8 if self.kind == "boss" else (6 if self.kind == "brute" else (3 if self.kind == "swift" else 4))

        draw_poly(surf, LANE_CURB_DARK, (cx, cy + 3.5), self.radius, sides, self.spin, 0)
        draw_poly(surf, BLACK, (cx, cy), self.radius, sides, self.spin, 0)
        draw_poly(surf, col, (cx, cy), self.radius, sides, self.spin, 3)
        pygame.draw.circle(surf, col, (int(cx), int(cy)), max(3, int(self.radius * 0.35)))

        bw = max(24.0, self.radius * 2.1)
        bh = 5.0 if self.kind != "boss" else 7.0
        bx = cx - bw / 2.0
        by = cy - self.radius - 12.0
        pygame.draw.rect(surf, (35, 40, 55), (bx, by, bw, bh), border_radius=2)
        ratio = clamp(self.hp / max(1.0, self.max_hp), 0.0, 1.0)
        pygame.draw.rect(surf, col, (bx, by, bw * ratio, bh), border_radius=2)

        if self.kind == "boss":
            lbl = font.render("BOSS", True, PINK)
            surf.blit(lbl, lbl.get_rect(center=(cx, by - 10)))


@dataclass
class LaneProjectile:
    x: float
    y: float
    vx: float
    vy: float
    damage: float
    color: Tuple[int, int, int]
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

    def draw(self, surf: pygame.Surface, shake: Tuple[int, int]):
        cx, cy = int(self.x + shake[0]), int(self.y + shake[1])
        draw_drop_shadow(surf, (cx, cy), self.radius * 0.8, 3.0)
        pygame.draw.circle(surf, self.color, (cx, cy), int(self.radius))
        pygame.draw.circle(surf, WHITE, (cx, cy), max(2, int(self.radius * 0.45)))


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
    def color(self) -> Tuple[int, int, int]:
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

    def draw(
        self,
        surf: pygame.Surface,
        font: pygame.font.Font,
        center: Tuple[float, float],
        shake: Tuple[int, int],
        show_name: bool = True,
    ):
        cx = center[0] + shake[0] - math.cos(self.aim_angle) * self.recoil
        cy = center[1] + shake[1] - math.sin(self.aim_angle) * self.recoil
        rad = 15.0 + (self.tier - 1) * 1.2

        draw_unit_art(surf, self.unit_type, self.tier, self.color, (cx, cy), self.aim_angle, with_shadow=True)

        t_lbl = font.render(f"T{self.tier}", True, WHITE)
        surf.blit(t_lbl, t_lbl.get_rect(center=(center[0] + shake[0], center[1] + shake[1])))

        if show_name:
            name_lbl = font.render(str(UNIT_META[self.unit_type]["name"]), True, self.color)
            surf.blit(name_lbl, name_lbl.get_rect(center=(center[0] + shake[0], center[1] + shake[1] + rad + 12)))


# ==============================================================================
# 7. MAIN PORTRAIT GAME ENGINE
# ==============================================================================

class AegisPathGame:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption(TITLE)
        self.clock = pygame.time.Clock()

        self.font_title = pygame.font.SysFont("consolas", 34, bold=True)
        self.font_lg = pygame.font.SysFont("consolas", 22, bold=True)
        self.font_md = pygame.font.SysFont("consolas", 16, bold=True)
        self.font_sm = pygame.font.SysFont("consolas", 12, bold=True)

        self.audio = AudioEngine()
        self.state = "TITLE"

        self.btn_guide = pygame.Rect(SCREEN_WIDTH - 96, 12, 82, 24)
        self.btn_close_guide = pygame.Rect(SCREEN_WIDTH // 2 - 90, SCREEN_HEIGHT - 115, 180, 48)

        self.dock_rects: List[pygame.Rect] = []
        slot_w, slot_h = 74, 78
        gap = 10
        total_w = DOCK_SLOTS_COUNT * slot_w + (DOCK_SLOTS_COUNT - 1) * gap
        start_x = (SCREEN_WIDTH - total_w) // 2
        for i in range(DOCK_SLOTS_COUNT):
            self.dock_rects.append(pygame.Rect(start_x + i * (slot_w + gap), DECK_TOP + 10, slot_w, slot_h))

        btn_y = DECK_TOP + 98
        btn_w, btn_h = 162, 58
        self.spawn_btns: List[Tuple[str, pygame.Rect]] = [
            ("sniper", pygame.Rect(16, btn_y, btn_w, btn_h)),
            ("gatling", pygame.Rect(189, btn_y, btn_w, btn_h)),
            ("mortar", pygame.Rect(362, btn_y, btn_w, btn_h)),
        ]

        up_y = DECK_TOP + 168
        self.btn_up_sniper = pygame.Rect(16, up_y, 162, 46)
        self.btn_up_gatling = pygame.Rect(189, up_y, 162, 46)
        self.btn_nova = pygame.Rect(362, up_y, 162, 46)

        self.reset_game()

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
        self.drag_pos: Tuple[int, int] = (0, 0)

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

    def _spawn_burst(self, x: float, y: float, col: Tuple[int, int, int], count: int = 12):
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

    def handle_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
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
                    self.popups.append(FloatingPopup(self.btn_up_sniper.centerx, self.btn_up_sniper.top - 10, f"SNIPER LV.{self.sniper_up_lvl}", CYAN))
                    return True

                if self.btn_up_gatling.collidepoint(mx, my) and self.elixir >= self.gatling_up_cost:
                    self.elixir -= self.gatling_up_cost
                    self.gatling_up_lvl += 1
                    self.gatling_up_cost += 2
                    self.audio.play("merge")
                    self.popups.append(FloatingPopup(self.btn_up_gatling.centerx, self.btn_up_gatling.top - 10, f"GATLING LV.{self.gatling_up_lvl}", YELLOW))
                    return True

                if self.btn_nova.collidepoint(mx, my) and self.nova_charge >= 100.0:
                    self._trigger_frost_nova()
                    return True

                for i, pt in enumerate(TOWER_PADS):
                    if self.pad_units[i] is not None and dist(mx, my, pt[0], pt[1]) <= 26.0:
                        self.drag_source = ("pad", i)
                        self.drag_pos = (mx, my)
                        return True

                for i, rect in enumerate(self.dock_rects):
                    if self.dock_units[i] is not None and rect.collidepoint(mx, my):
                        self.drag_source = ("dock", i)
                        self.drag_pos = (mx, my)
                        return True

            elif event.type == pygame.MOUSEMOTION:
                if self.drag_source is not None:
                    self.drag_pos = event.pos

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.drag_source is not None:
                    dst = self._find_drop_target(event.pos[0], event.pos[1])
                    self._handle_drop(self.drag_source, dst)
                    self.drag_source = None

        return True

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

    def _shake_offset(self) -> Tuple[int, int]:
        if self.shake_mag <= 0.2:
            return 0, 0
        return int(random.uniform(-self.shake_mag, self.shake_mag)), int(random.uniform(-self.shake_mag, self.shake_mag))

    def _draw_top_hud(self):
        pygame.draw.rect(self.screen, PANEL_BG, (0, 0, SCREEN_WIDTH, TOP_BAR_H))
        pygame.draw.line(self.screen, LANE_BORDER, (0, TOP_BAR_H), (SCREEN_WIDTH, TOP_BAR_H), 2)

        base_txt = self.font_lg.render(f"BASE: {self.base_hp}/{self.max_base_hp}", True, GREEN if self.base_hp > 6 else RED)
        wave_txt = self.font_lg.render(f"WAVE {self.wave}", True, CYAN)
        score_txt = self.font_md.render(f"SCORE {self.score}", True, YELLOW)

        self.screen.blit(base_txt, (16, 22))
        self.screen.blit(wave_txt, wave_txt.get_rect(center=(SCREEN_WIDTH // 2 - 20, 36)))
        self.screen.blit(score_txt, (SCREEN_WIDTH - score_txt.get_width() - 16, 44))

        pygame.draw.rect(self.screen, SLOT_BG, self.btn_guide, border_radius=5)
        pygame.draw.rect(self.screen, CYAN, self.btn_guide, 2, border_radius=5)
        g_lbl = self.font_sm.render("GUIDE", True, CYAN)
        self.screen.blit(g_lbl, g_lbl.get_rect(center=self.btn_guide.center))

    def _draw_lane_and_pads(self, shake: Tuple[int, int]):
        pygame.draw.rect(self.screen, BG_DARK, (0, ARENA_TOP, SCREEN_WIDTH, ARENA_BOTTOM - ARENA_TOP))
        tile = 54
        for gx in range(0, SCREEN_WIDTH, tile):
            for gy in range(ARENA_TOP, ARENA_BOTTOM, tile):
                if ((gx // tile) + (gy // tile)) % 2 == 0:
                    pygame.draw.rect(self.screen, BG_TILE_ALT, (gx + shake[0], gy + shake[1], tile, tile))
                pygame.draw.circle(self.screen, BG_DECOR, (gx + shake[0], gy + shake[1]), 2)

        pts = [(p[0] + shake[0], p[1] + shake[1]) for p in LANE_POINTS]
        shadow_pts = [(p[0], p[1] + 7) for p in pts]
        pygame.draw.lines(self.screen, SHADOW_COLOR, False, shadow_pts, 40)
        pygame.draw.lines(self.screen, LANE_CURB_DARK, False, pts, 38)
        pygame.draw.lines(self.screen, LANE_CURB_LIGHT, False, pts, 34)
        pygame.draw.lines(self.screen, BG_LANE, False, pts, 29)
        pygame.draw.lines(self.screen, BG_LANE_INNER, False, pts, 18)
        pygame.draw.lines(self.screen, LANE_CENTER, False, pts, 2)

        sx, sy = pts[0]
        draw_drop_shadow(self.screen, (sx, sy), 18, 4.0)
        draw_ring_pulse(self.screen, RED, (sx, sy), 18, 180, 2)
        pygame.draw.circle(self.screen, RED, (int(sx), int(sy)), 7)

        bx, by = pts[-1]
        draw_drop_shadow(self.screen, (bx, by), 24, 6.0)
        draw_poly(self.screen, LANE_CURB_DARK, (bx, by + 5), 24, 6, 0.2, 0)
        draw_poly(self.screen, GREEN, (bx, by), 22, 6, 0.2, 3)
        pygame.draw.circle(self.screen, GREEN, (int(bx), int(by)), 8)
        b_lbl = self.font_sm.render("BASE", True, GREEN)
        self.screen.blit(b_lbl, b_lbl.get_rect(center=(bx, by + 34)))

        for idx, pt in enumerate(TOWER_PADS):
            px, py = pt[0] + shake[0], pt[1] + shake[1]
            u = self.pad_units[idx]
            pad_col = u.color if u is not None else SLOT_BORDER
            draw_drop_shadow(self.screen, (px, py), 21, 4.0)
            pygame.draw.circle(self.screen, LANE_CURB_DARK, (int(px), int(py + 3)), 21)
            pygame.draw.circle(self.screen, SLOT_BG, (int(px), int(py)), 21)
            pygame.draw.circle(self.screen, pad_col, (int(px), int(py)), 21, 2)
            if u is not None:
                u.draw(self.screen, self.font_sm, pt, shake, show_name=True)

    def _draw_bottom_deck(self):
        pygame.draw.rect(self.screen, PANEL_BG, (0, DECK_TOP, SCREEN_WIDTH, SCREEN_HEIGHT - DECK_TOP))
        pygame.draw.line(self.screen, CYAN, (0, DECK_TOP), (SCREEN_WIDTH, DECK_TOP), 3)

        bar_x, bar_y, bar_w, bar_h = 16, DECK_TOP - 22, SCREEN_WIDTH - 32, 16
        pygame.draw.rect(self.screen, (20, 24, 36), (bar_x, bar_y, bar_w, bar_h), border_radius=6)
        fill_w = int(bar_w * clamp(self.elixir / MAX_ELIXIR, 0.0, 1.0))
        if fill_w > 0:
            pygame.draw.rect(self.screen, PURPLE, (bar_x, bar_y, fill_w, bar_h), border_radius=6)
        pygame.draw.rect(self.screen, WHITE, (bar_x, bar_y, bar_w, bar_h), 1, border_radius=6)
        el_lbl = self.font_sm.render(f"ELIXIR: {self.elixir:.1f} / {int(MAX_ELIXIR)}", True, WHITE)
        self.screen.blit(el_lbl, (bar_x + 8, bar_y + 1))

        for i, rect in enumerate(self.dock_rects):
            u = self.dock_units[i]
            bcol = u.color if u is not None else SLOT_BORDER
            pygame.draw.rect(self.screen, SLOT_BG, rect, border_radius=8)
            pygame.draw.rect(self.screen, bcol, rect, 2, border_radius=8)
            if u is not None:
                u.draw(
                    self.screen,
                    self.font_sm,
                    (float(rect.centerx), float(rect.centery) - 6.0),
                    (0, 0),
                    show_name=False,
                )
                n_txt = self.font_sm.render(str(UNIT_META[u.unit_type]["name"]), True, u.color)
                self.screen.blit(n_txt, n_txt.get_rect(center=(rect.centerx, rect.bottom - 10)))

        for utype, rect in self.spawn_btns:
            meta = UNIT_META[utype]
            cost = int(meta["cost"])
            col = meta["color"]  # type: ignore
            can_buy = self.elixir >= cost
            pygame.draw.rect(self.screen, SLOT_BG if can_buy else (22, 24, 30), rect, border_radius=8)
            pygame.draw.rect(self.screen, col if can_buy else GRAY, rect, 2, border_radius=8)
            n_surf = self.font_md.render(f"{meta['name']} ({cost})", True, col if can_buy else GRAY)
            s_surf = self.font_sm.render(f"{meta['shape_name']} | {meta['tag']}", True, WHITE if can_buy else GRAY)
            self.screen.blit(n_surf, n_surf.get_rect(center=(rect.centerx, rect.y + 18)))
            self.screen.blit(s_surf, s_surf.get_rect(center=(rect.centerx, rect.y + 40)))

        self._draw_action_btn(self.btn_up_sniper, f"SNIPER+ ({self.sniper_up_cost})", f"LVL {self.sniper_up_lvl}", CYAN, self.elixir >= self.sniper_up_cost)
        self._draw_action_btn(self.btn_up_gatling, f"GATLING+ ({self.gatling_up_cost})", f"LVL {self.gatling_up_lvl}", YELLOW, self.elixir >= self.gatling_up_cost)
        nova_ready = self.nova_charge >= 100.0
        self._draw_action_btn(self.btn_nova, "FROST NOVA", f"{int(self.nova_charge)}%", ICE, nova_ready)

    def _draw_action_btn(
        self,
        rect: pygame.Rect,
        title: str,
        sub: str,
        col: Tuple[int, int, int],
        active: bool,
    ):
        pygame.draw.rect(self.screen, SLOT_BG if active else (20, 23, 30), rect, border_radius=7)
        pygame.draw.rect(self.screen, col if active else GRAY, rect, 2, border_radius=7)
        t1 = self.font_sm.render(title, True, col if active else GRAY)
        t2 = self.font_sm.render(sub, True, WHITE if active else GRAY)
        self.screen.blit(t1, t1.get_rect(center=(rect.centerx, rect.y + 14)))
        self.screen.blit(t2, t2.get_rect(center=(rect.centerx, rect.y + 32)))

    def _draw_guide_modal(self):
        ov = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        ov.fill((8, 11, 18, 240))
        self.screen.blit(ov, (0, 0))

        hdr = self.font_lg.render("UNIT & TACTICS GUIDE", True, CYAN)
        self.screen.blit(hdr, hdr.get_rect(center=(SCREEN_WIDTH // 2, 75)))

        entries = [
            ("sniper", "SNIPER [SQUARE]", "Cost 3 - 1 heavy shot, high dmg", CYAN, 165),
            ("gatling", "GATLING [TRIANGLE]", "Cost 5 - Rapid spray, fast shots", YELLOW, 265),
            ("mortar", "MORTAR [HEXAGON]", "Cost 7 - AoE blast + slow enemies", GREEN, 365),
        ]
        for utype, title_txt, desc_txt, col, yy in entries:
            draw_unit_art(self.screen, utype, 1, col, (62.0, float(yy)), -0.4, with_shadow=False)
            t_s = self.font_md.render(title_txt, True, col)
            d_s = self.font_sm.render(desc_txt, True, WHITE)
            self.screen.blit(t_s, (105, yy - 16))
            self.screen.blit(d_s, (105, yy + 6))

        rules = [
            "MERGE: Drag same type & tier onto each other -> Tier up!",
            "DEPLOY: Drag dock units onto lane pads to fire.",
            "ELIXIR: Slow regen + enemy kills + wave bonus.",
            "NOVA: 100% slows & damages all lane enemies.",
        ]
        for i, line in enumerate(rules):
            rs = self.font_sm.render(line, True, GRAY if i % 2 else WHITE)
            self.screen.blit(rs, (32, 455 + i * 34))

        pygame.draw.rect(self.screen, SLOT_BG, self.btn_close_guide, border_radius=8)
        pygame.draw.rect(self.screen, GREEN, self.btn_close_guide, 2, border_radius=8)
        c_lbl = self.font_md.render("BACK TO GAME", True, GREEN)
        self.screen.blit(c_lbl, c_lbl.get_rect(center=self.btn_close_guide.center))

    def _draw_title(self):
        self.screen.fill(BG_DARK)
        t1 = self.font_title.render("AEGIS PATH", True, CYAN)
        t2 = self.font_lg.render("MERGE & ELIXIR DEFENSE", True, PURPLE)
        go = self.font_lg.render("TAP ANYWHERE TO START", True, GREEN)
        self.screen.blit(t1, t1.get_rect(center=(SCREEN_WIDTH // 2, 340)))
        self.screen.blit(t2, t2.get_rect(center=(SCREEN_WIDTH // 2, 385)))
        self.screen.blit(go, go.get_rect(center=(SCREEN_WIDTH // 2, 520)))

    def _draw_game_over(self):
        ov = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        ov.fill((10, 8, 16, 215))
        self.screen.blit(ov, (0, 0))
        t1 = self.font_title.render("BASE FALLEN", True, RED)
        s1 = self.font_lg.render(f"SCORE: {self.score}   |   WAVE: {self.wave}", True, WHITE)
        s2 = self.font_md.render("TAP TO PLAY AGAIN", True, CYAN)
        self.screen.blit(t1, t1.get_rect(center=(SCREEN_WIDTH // 2, 360)))
        self.screen.blit(s1, s1.get_rect(center=(SCREEN_WIDTH // 2, 420)))
        self.screen.blit(s2, s2.get_rect(center=(SCREEN_WIDTH // 2, 500)))

    def render(self):
        if self.state == "TITLE":
            self._draw_title()
            pygame.display.flip()
            return

        shake = self._shake_offset()
        self._draw_lane_and_pads(shake)

        for pr in self.projectiles:
            pr.draw(self.screen, shake)
        for e in self.enemies:
            e.draw(self.screen, self.font_sm, shake)
        for sw in self.shockwaves:
            sw.draw(self.screen, shake)
        for p in self.particles:
            p.draw(self.screen, shake)
        for pop in self.popups:
            pop.draw(self.screen, self.font_md, shake)

        self._draw_top_hud()
        self._draw_bottom_deck()

        if self.drag_source is not None:
            du = self._get_unit_at(self.drag_source)
            if du is not None:
                du.draw(
                    self.screen,
                    self.font_sm,
                    (float(self.drag_pos[0]), float(self.drag_pos[1])),
                    (0, 0),
                    show_name=True,
                )

        if self.state == "GUIDE":
            self._draw_guide_modal()
        elif self.state == "GAME_OVER":
            self._draw_game_over()

        pygame.display.flip()

    def run(self):
        running = True
        while running:
            dt = min(0.05, self.clock.tick(FPS) / 1000.0)
            running = self.handle_events()
            self.update(dt)
            self.render()
        pygame.quit()


if __name__ == "__main__":
    AegisPathGame().run()
