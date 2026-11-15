from kivy.app import App
from kivy.uix.label import Label
from kivy.core.window import Window

class MessiApp(App):
    def build(self):
        Window.clearcolor = (1, 1, 1, 1)

        return Label(
            text="MISSE IS THE GOAT",
            font_size=40,
            color=(0, 0, 0, 1)
        )

MessiApp().run()