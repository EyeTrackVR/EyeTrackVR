import random
import time
from machine import Pin, Timer
led = Pin(15, Pin.OUT)

while True:
    t = random.randint(5, 45)
    print(t)
    print('PING')
    led.toggle()
    time.sleep(t * 60)
