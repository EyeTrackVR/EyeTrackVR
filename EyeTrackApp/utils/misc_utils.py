import os
is_nt = True if os.name == "nt" else False

def PlaySound(*args, **kwargs): pass
SND_FILENAME = SND_ASYNC = 1

if is_nt:
    import winsound
    PlaySound = winsound.PlaySound
    SND_FILENAME = winsound.SND_FILENAME
    SND_ASYNC = winsound.SND_ASYNC

def clamp(x, low, high):
    return max(low, min(x, high))
