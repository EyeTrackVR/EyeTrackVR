import numpy as np
import socket
import threading


class TimeoutError(RuntimeError):
    pass


class AsyncCall(object):
    def __init__(self, fnc, callback=None):
        self.Callable = fnc
        self.Callback = callback

    def __call__(self, *args, **kwargs):
        self.Thread = threading.Thread(target=self.run, name=self.Callable.__name__, args=args, kwargs=kwargs)
        self.Thread.start()
        return self

    def wait(self, timeout=None):
        self.Thread.join(timeout)
        if self.Thread.isAlive():
            raise TimeoutError()
        else:
            return self.Result

    def run(self, *args, **kwargs):
        self.Result = self.Callable(*args, **kwargs)
        if self.Callback:
            self.Callback(self.Result)


class AsyncMethod(object):
    def __init__(self, fnc, callback=None):
        self.Callable = fnc
        self.Callback = callback

    def __call__(self, *args, **kwargs):
        return AsyncCall(self.Callable, self.Callback)(*args, **kwargs)


def Async(fnc=None, callback=None):
    if fnc == None:

        def AddAsyncCallback(fnc):
            return AsyncMethod(fnc, callback)

        return AddAsyncCallback
    else:
        return AsyncMethod(fnc, callback)


@Async
def overlay_calibrate_3d(self):
    try:
        if self.overlay_active != True:
            dirname = os.getcwd()
            overlay_path = os.path.join(dirname, "calibrate.bat")  # start overlay
            os.startfile(overlay_path)
            self.overlay_active = True
            while var.overlay_active:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                server_address = ("localhost", 2112)
                sock.bind(server_address)
                data, address = sock.recvfrom(4096)
                received_int = struct.unpack("!l", data)[0]  # this will hold until message received
                self.point_trigger = True
                self.calib_step = reveived_int

                print(received_int)
    except:
        print("[WARN] Calibration overlay error. Make sure SteamVR is Running.")
        self.settings.gui_recenter_eyes = False
        var.overlay_active = False


class calibrate_3d:
    overlay_active = False
    point_trigger = False
    calib_step = 0
    calib_matrix = np.zeros((9, 2))

    def nine_point_3d_calib(x, y):  # dummy format

        if calibrate_3d.point_trigger:
            calibrate_3d.calib_matrix[calibrate_3d.calib_step][0] = x
            calibrate_3d.calib_matrix[calibrate_3d.calib_step][1] = y
            print(calibrate_3d.calib_matrix)
        calibrate_3d.point_trigger = True


calibrate_3d.nine_point_3d_calib(1, 2)
