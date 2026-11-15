from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.clock import Clock
from random import randint


class TapGame(App):

    def build(self):
        self.score = 0
        self.time_left = 30
        self.playing = False

        self.layout = BoxLayout(
            orientation="vertical",
            padding=25,
            spacing=20
        )

        self.layout.add_widget(Label(
            text="TAP CHALLENGE",
            font_size=32,
            color=(0, 0, 0, 1),
            size_hint=(1, 0.25)
        ))

        self.info = Label(
            text="Score: 0       Time: 30",
            font_size=24,
            color=(0, 0, 0, 1)
        )
        self.layout.add_widget(self.info)

        self.target = Button(
            text="START GAME",
            font_size=28,
            background_color=(0.1, 0.6, 0.9, 1)
        )
        self.target.bind(on_press=self.tap)
        self.layout.add_widget(self.target)

        return self.layout

    def tap(self, instance):
        if not self.playing:
            self.start_game()
            return

        self.score += 1
        self.target.text = "TAP!"
        self.target.background_color = (
            randint(1, 10) / 10,
            randint(1, 10) / 10,
            randint(1, 10) / 10,
            1
        )
        self.update_info()

    def start_game(self):
        self.score = 0
        self.time_left = 30
        self.playing = True
        self.target.text = "TAP ME!"
        self.update_info()
        Clock.schedule_interval(self.countdown, 1)

    def countdown(self, dt):
        self.time_left -= 1
        self.update_info()

        if self.time_left <= 0:
            self.playing = False
            self.target.text = f"GAME OVER!\nYour Score: {self.score}"
            return False

    def update_info(self):
        self.info.text = (
            f"Score: {self.score}       Time: {self.time_left}"
        )


TapGame().run()
