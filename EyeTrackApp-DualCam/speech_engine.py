import pyttsx3
import queue
import threading


class SpeechEngine:
    def __init__(self, queue: "queue.Queue[str | None]"):
        self.engine = pyttsx3.init()
        self.queue = queue

    def say(self, item):
        self.engine.say(item)

    def force_stop(self):
        self.engine.stop()

    def run(self):
        while True:
            print("Waiting for speech item")
            item = self.queue.get()
            if item is None:
                print("Stopping speech engine")
                self.engine.stop()
                return
            self.engine.say(item)
            self.engine.runAndWait()
