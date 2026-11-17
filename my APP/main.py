import math
import random
import os
from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.core.image import Image as CoreImage
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle, PushMatrix, PopMatrix, Translate
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.widget import Widget

Window.clearcolor = (0.06, 0.10, 0.16, 1)

PLAYERS = [
    ("Lamine", (0.95, 0.75, 0.10)),
    ("Mbappe", (0.15, 0.65, 0.95)),
    ("Suarez", (0.15, 0.80, 0.40)),
    ("Ronaldo", (0.90, 0.25, 0.25)),
    ("Messi", (0.70, 0.35, 0.95)),
]

RADII = [22, 32, 44, 58, 74]


class GameArea(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # تحميل الصور بأمان
        image_files = ["lamine.png", "mbappe.jpg", "suarez.jpg", "ronaldo.jpg", "messi.jpg"]
        self.player_textures = []
        for f in image_files:
            path = os.path.join("assets", f)
            if os.path.exists(path):
                self.player_textures.append(CoreImage(path).texture)
            else:
                self.player_textures.append(None)

        # تحميل الأصوات
        sound_files = ["lamine.mp3", "mbappe.mp3", None, "ronaldo.mp3", "messi.mp3"]
        self.merge_sounds = []
        for s in sound_files:
            if s and os.path.exists(os.path.join("assets/sounds", s)):
                self.merge_sounds.append(SoundLoader.load(os.path.join("assets/sounds", s)))
            else:
                self.merge_sounds.append(None)

        self.balls = []
        self.effects = []
        self.score = 0
        self.high_score = 0
        self.gravity = 750
        
        # ارتداد فائق القوة في كل الاتجاهات
        self.wall_bounce = 0.96
        self.ball_bounce = 0.98
        
        self.running = False

        self.spawn_interval = 1.5
        self.spawn_timer = 0
        self.aim_x = None
        self.next_level = 0
        
        self.shake_timer = 0
        self.game_over = False
        self.danger_timer = 0

        self.score_label = Label(text="Score: 0", font_size=18, bold=True, color=(1, 1, 1, 1))
        self.high_score_label = Label(text="Best: 0", font_size=16, color=(0.8, 0.85, 0.9, 1))
        self.status_label = Label(text="", font_size=32, bold=True, color=(1, 0.3, 0.3, 1))

        self.add_widget(self.score_label)
        self.add_widget(self.high_score_label)
        self.add_widget(self.status_label)

        Clock.schedule_interval(self.update_game, 1 / 60)

    def bowl(self):
        cx = self.width / 2
        cy = self.height * 0.35
        radius = min(self.width * 0.42, self.height * 0.32)
        return cx, cy, radius

    # نظام إدارة الأصوات حسب الأولوية المطلوبة (ميسي > كريستيانو > مبابي > لامين)
    def play_sound(self, level):
        sound = self.merge_sounds[level]
        if sound is None:
            return

        # فحص ما إذا كان هناك صوت يعمل حالياً ومعرفة مستواه
        active_level = -1
        for idx, s in enumerate(self.merge_sounds):
            if s is not None and getattr(s, 'state', '') == 'play':
                active_level = idx
                break

        # إذا كان هناك صوت يعمل حالياً، نقارن الأولوية (المستوى الأعلى هو الأهم)
        if active_level != -1:
            # إذا كان الصوت الجديد مستواه أقل أو يساوي الصوت الحالي، ولا يدخل في أولوية أعلى، نتجاهله
            # ولكن إذا كان المستوى الجديد أكبر (أهم)، فنوقف القديم ونشغل الجديد
            if level >= active_level:
                for s in self.merge_sounds:
                    if s is not None:
                        try:
                            s.stop()
                        except:
                            pass
                sound.play()
            else:
                # الصوت الحالي أهم (مثل ميسي أو كريستيانو)، لذا لا نسمح للصوت الأقل مقاطعته
                return
        else:
            sound.play()

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and self.running and not self.game_over:
            self.update_aim(touch.x)
            self.spawn_ball()
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if self.collide_point(*touch.pos) and self.running and not self.game_over:
            self.update_aim(touch.x)
            return True
        return super().on_touch_move(touch)

    def update_aim(self, x):
        cx, cy, radius = self.bowl()
        if self.aim_x is None:
            self.aim_x = cx
        r = RADII[self.next_level]
        left_limit = cx - radius * 0.707 + r + 5
        right_limit = cx + radius * 0.707 - r - 5
        self.aim_x = max(left_limit, min(right_limit, x))

    def spawn_ball(self):
        cx, cy, radius = self.bowl()
        if self.aim_x is None:
            self.aim_x = cx

        ball = {
            "x": self.aim_x,
            "y": cy + radius + 95,
            "vx": random.uniform(-40, 40),
            "vy": 0,
            "level": self.next_level,
            "age": 0
        }
        self.balls.append(ball)

        self.play_sound(self.next_level)

        self.next_level = random.choice([0, 0, 1])
        self.spawn_timer = 0

    def merge_balls(self, first, second):
        if first["level"] >= len(PLAYERS) - 1:
            return False

        level = first["level"] + 1
        mx = (first["x"] + second["x"]) / 2
        my = (first["y"] + second["y"]) / 2

        new_ball = {
            "x": mx,
            "y": my,
            "vx": (first["vx"] + second["vx"]) / 2 + random.uniform(-30, 30),
            "vy": 220,  # دفعة قوية للأعلى عند الدمج
            "level": level,
            "age": 1.0
        }

        self.balls.remove(first)
        self.balls.remove(second)
        self.balls.append(new_ball)

        self.effects.append({
            "x": mx,
            "y": my,
            "r": RADII[level] * 0.8,
            "max_r": RADII[level] * 1.8,
            "alpha": 1.0,
            "color": PLAYERS[level][1]
        })

        self.shake_timer = 0.25
        self.play_sound(level)

        self.score += 10 * (level + 1)
        if self.score > self.high_score:
            self.high_score = self.score

        self.score_label.text = f"Score: {self.score}"
        self.high_score_label.text = f"Best: {self.high_score}"
        return True

    def update_game(self, dt):
        if self.width <= 0 or self.height <= 0:
            return

        dt = min(dt, 0.03)
        cx, cy, radius = self.bowl()
        if self.aim_x is None:
            self.aim_x = cx

        if not self.running or self.game_over:
            self.draw_game()
            return

        self.spawn_timer += dt
        if self.spawn_timer >= self.spawn_interval:
            self.spawn_ball()

        if self.shake_timer > 0:
            self.shake_timer -= dt

        for eff in self.effects[:]:
            eff["r"] += 140 * dt
            eff["alpha"] -= 3.0 * dt
            if eff["alpha"] <= 0:
                self.effects.remove(eff)

        left_wall = cx - radius * 0.707
        right_wall = cx + radius * 0.707
        wall_joint_y = cy + radius * 0.707
        danger_line_y = cy + radius + 55

        in_danger = False

        for ball in self.balls:
            ball["age"] += dt
            r = RADII[ball["level"]]

            ball["vy"] -= self.gravity * dt
            ball["x"] += ball["vx"] * dt
            ball["y"] += ball["vy"] * dt

            ball["vx"] *= 0.999
            ball["vy"] *= 0.999

            # اهتزاز وترجف مستمر وسريع للكرات
            ball["x"] += random.uniform(-1.2, 1.2)
            ball["y"] += random.uniform(-1.2, 1.2)

            # التصادم مع الوعاء الدائري السفلي بارتداد قوي
            if ball["y"] <= wall_joint_y:
                dx = ball["x"] - cx
                dy = ball["y"] - cy
                dist = math.hypot(dx, dy)
                max_dist = radius - r

                if dist > max_dist and dist > 0:
                    nx = dx / dist
                    ny = dy / dist
                    ball["x"] = cx + nx * max_dist
                    ball["y"] = cy + ny * max_dist

                    vn = ball["vx"] * nx + ball["vy"] * ny
                    if vn > 0:
                        ball["vx"] -= (1 + self.wall_bounce) * vn * nx
                        ball["vy"] -= (1 + self.wall_bounce) * vn * ny

            # التصادم مع الجدران الجانبية العليا
            else:
                if ball["x"] < left_wall + r:
                    ball["x"] = left_wall + r
                    ball["vx"] = abs(ball["vx"]) * self.wall_bounce
                    ball["vy"] += random.uniform(-20, 20)
                elif ball["x"] > right_wall - r:
                    ball["x"] = right_wall - r
                    ball["vx"] = -abs(ball["vx"]) * self.wall_bounce
                    ball["vy"] += random.uniform(-20, 20)

            if ball["age"] > 1.2 and (ball["y"] + r) > danger_line_y:
                in_danger = True

        if in_danger:
            self.danger_timer += dt
            if self.danger_timer >= 2.0:
                self.game_over = True
                self.status_label.text = "GAME OVER!"
        else:
            self.danger_timer = 0

        # دمج الكرات وإحداث ارتداد انفجاري متبادل
        for _ in range(2):
            merged_pair = False
            for i in range(len(self.balls)):
                for j in range(i + 1, len(self.balls)):
                    a = self.balls[i]
                    b = self.balls[j]
                    ra = RADII[a["level"]]
                    rb = RADII[b["level"]]

                    dx = b["x"] - a["x"]
                    dy = b["y"] - a["y"]
                    distance = math.hypot(dx, dy)
                    minimum = ra + rb

                    if distance < minimum:
                        if a["level"] == b["level"]:
                            if self.merge_balls(a, b):
                                merged_pair = True
                                break

                        if distance == 0:
                            distance = 1
                            dx, dy = 1, 0

                        nx = dx / distance
                        ny = dy / distance
                        overlap = minimum - distance

                        a["x"] -= nx * overlap * 0.5
                        a["y"] -= ny * overlap * 0.5
                        b["x"] += nx * overlap * 0.5
                        b["y"] += ny * overlap * 0.5

                        rel_vel = (b["vx"] - a["vx"]) * nx + (b["vy"] - a["vy"]) * ny
                        if rel_vel < 0:
                            impulse = -(1 + self.ball_bounce) * rel_vel * 0.5
                            a["vx"] -= impulse * nx
                            a["vy"] -= impulse * ny
                            b["vx"] += impulse * nx
                            b["vy"] += impulse * ny
                if merged_pair:
                    break

        self.draw_game()

    def draw_game(self):
        cx, cy, radius = self.bowl()
        self.canvas.clear()

        self.score_label.pos = (20, self.height - 45)
        self.score_label.size = (150, 40)
        self.high_score_label.pos = (self.width - 170, self.height - 45)
        self.high_score_label.size = (150, 40)
        self.status_label.center = (cx, cy + 40)

        with self.canvas:
            PushMatrix()
            if self.shake_timer > 0:
                Translate(random.uniform(-8, 8), random.uniform(-8, 8))

            Color(0.10, 0.16, 0.25, 0.7)
            Ellipse(pos=(cx - radius, cy - radius), size=(radius * 2, radius * 2), angle_start=135, angle_end=405)

            left_x = cx - radius * 0.707
            right_x = cx + radius * 0.707
            wall_y = cy + radius * 0.707
            top_y = cy + radius + 80
            danger_y = cy + radius + 55

            Color(0.95, 0.25, 0.25, 0.8 if self.danger_timer > 0 else 0.35)
            Line(points=[left_x, danger_y, right_x, danger_y], width=1.5, dash_length=8, dash_offset=4)

            if self.running and not self.game_over:
                drop_y = cy + radius + 95
                Color(1, 1, 1, 0.3)
                Line(points=[self.aim_x, drop_y, self.aim_x, cy - radius + 20], width=1.2, dash_length=6)
                self.draw_player_ball(self.aim_x, drop_y, self.next_level)

            Color(0.25, 0.70, 1.0, 1)
            Line(circle=(cx, cy, radius), angle_start=135, angle_end=405, segments=100, width=3.5)
            Line(points=[left_x, wall_y, left_x, top_y], width=3.5)
            Line(points=[right_x, wall_y, right_x, top_y], width=3.5)

            for ball in self.balls:
                self.draw_player_ball(ball["x"], ball["y"], ball["level"])

            for eff in self.effects:
                c = eff["color"]
                Color(c[0], c[1], c[2], max(0, eff["alpha"]))
                Line(circle=(eff["x"], eff["y"], eff["r"]), width=3)

            PopMatrix()

    def draw_player_ball(self, x, y, level):
        r = RADII[level]
        color = PLAYERS[level][1]
        tex = self.player_textures[level]

        Color(1, 1, 1, 1) if tex else Color(*color, 1)
        Ellipse(texture=tex, pos=(x - r, y - r), size=(r * 2, r * 2))

        Color(*color, 1)
        Line(circle=(x, y, r), width=2.5)


class FootballMergeApp(App):
    def build(self):
        root = BoxLayout(orientation="vertical", padding=10, spacing=8)

        title = Label(
            text="FOOTBALL MERGE",
            font_size=22,
            bold=True,
            size_hint_y=None,
            height=40,
            color=(0.25, 0.75, 1.0, 1)
        )
        root.add_widget(title)

        controls = BoxLayout(size_hint_y=None, height=45, spacing=6)

        speed_spinner = Spinner(
            text="1.5 sec",
            values=("1.0 sec", "1.5 sec", "2.5 sec"),
            size_hint_x=0.35
        )

        game = GameArea()

        def change_speed(spinner, value):
            speeds = {"1.0 sec": 1.0, "1.5 sec": 1.5, "2.5 sec": 2.5}
            game.spawn_interval = speeds[value]

        speed_spinner.bind(text=change_speed)

        start_btn = Button(
            text="START",
            background_normal="",
            background_color=(0.12, 0.55, 0.25, 1),
            bold=True
        )
        start_btn.bind(on_press=lambda x: setattr(game, 'running', True))

        pause_btn = Button(
            text="PAUSE",
            background_normal="",
            background_color=(0.85, 0.55, 0.10, 1),
            bold=True
        )
        pause_btn.bind(on_press=lambda x: setattr(game, 'running', False))

        reset_btn = Button(
            text="RESTART",
            background_normal="",
            background_color=(0.85, 0.25, 0.30, 1),
            bold=True
        )

        def restart_game(instance):
            game.balls.clear()
            game.effects.clear()
            game.score = 0
            game.game_over = False
            game.danger_timer = 0
            game.spawn_timer = 0
            game.score_label.text = "Score: 0"
            game.status_label.text = ""
            game.running = True

        reset_btn.bind(on_press=restart_game)

        controls.add_widget(speed_spinner)
        controls.add_widget(start_btn)
        controls.add_widget(pause_btn)
        controls.add_widget(reset_btn)

        root.add_widget(controls)
        root.add_widget(game)
        return root


if __name__ == "__main__":
    FootballMergeApp().run()