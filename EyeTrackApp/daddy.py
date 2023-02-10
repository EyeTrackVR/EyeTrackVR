from typing import Tuple

import numpy as np
import cv2
import onnxruntime


# DADDY
# Please change the name of this script and the name of the method if you have something better.
video_path = "ezgif.com-gif-maker.avi"
input_size = 192  # Do not change this number.
heatmap_size = 48  # Do not change this number.
kernel_size = 7
model_file = "daddy230210.onnx"  # The model file name will be changed when performance stabilises.
# SHA256 for model version verification
# daddy230210.onnx = 59e59aa2a21024884200dd3acbd5e6a2e8d7209c46555fbdc727d4fe3adb68d3
imshow_enable = True
save_video = False
save_filepath = 'output.mp4'

def get_max_preds(batch_heatmaps):
    # base:https://github.com/ilovepose/DarkPose
    batch_size = batch_heatmaps.shape[0]
    num_joints = batch_heatmaps.shape[1]
    width = batch_heatmaps.shape[3]
    heatmaps_reshaped = batch_heatmaps.reshape((batch_size, num_joints, -1))
    idx = np.argmax(heatmaps_reshaped, 2)
    maxvals = np.amax(heatmaps_reshaped, 2)

    maxvals = maxvals.reshape((batch_size, num_joints, 1))
    idx = idx.reshape((batch_size, num_joints, 1))

    preds = np.tile(idx, (1, 1, 2)).astype(np.float32)

    preds[:, :, 0] = (preds[:, :, 0]) % width
    preds[:, :, 1] = np.floor((preds[:, :, 1]) / width)

    pred_mask = np.tile(np.greater(maxvals, 0.0), (1, 1, 2))
    pred_mask = pred_mask.astype(np.float32)

    preds *= pred_mask
    return preds, maxvals


def taylor(hm, coord):
    # base:https://github.com/ilovepose/DarkPose
    heatmap_height = hm.shape[0]
    heatmap_width = hm.shape[1]
    px = int(coord[0])
    py = int(coord[1])
    if 1 < px < heatmap_width-2 and 1 < py < heatmap_height-2:
        dx  = 0.5 * (hm[py][px+1] - hm[py][px-1])
        dy  = 0.5 * (hm[py+1][px] - hm[py-1][px])
        dxx = 0.25 * (hm[py][px+2] - 2 * hm[py][px] + hm[py][px-2])
        dxy = 0.25 * (hm[py+1][px+1] - hm[py-1][px+1] - hm[py+1][px-1] \
            + hm[py-1][px-1])
        dyy = 0.25 * (hm[py+2*1][px] - 2 * hm[py][px] + hm[py-2*1][px])
        derivative = np.matrix([[dx],[dy]])
        hessian = np.matrix([[dxx,dxy],[dxy,dyy]])
        if dxx * dyy - dxy ** 2 != 0:
            hessianinv = hessian.I
            offset = -hessianinv * derivative
            offset = np.squeeze(np.array(offset.T), axis=0)
            coord += offset
    return coord


def gaussian_blur(hm, kernel):
    # base:https://github.com/ilovepose/DarkPose
    border = (kernel - 1) // 2
    batch_size = hm.shape[0]
    num_joints = hm.shape[1]
    height = hm.shape[2]
    width = hm.shape[3]
    for i in range(batch_size):
        for j in range(num_joints):
            origin_max = np.max(hm[i,j])
            dr = np.zeros((height + 2 * border, width + 2 * border))
            dr[border: -border, border: -border] = hm[i,j].copy()
            dr = cv2.GaussianBlur(dr, (kernel, kernel), 0)
            hm[i,j] = dr[border: -border, border: -border].copy()
            hm[i,j] *= origin_max / np.max(hm[i,j])
    return hm


def get_final_preds(hm,realsize):
    # base:https://github.com/ilovepose/DarkPose
    coords, maxvals = get_max_preds(hm)

    # post-processing
    hm = gaussian_blur(hm, kernel_size)
    hm = np.maximum(hm, 1e-10)
    hm = np.log(hm)
    for n in range(coords.shape[0]):
        for p in range(coords.shape[1]):
            coords[n,p] = taylor(hm[n][p], coords[n][p])

    preds = coords.copy()
    preds=(preds/heatmap_size)*realsize#input_size

    # Transform back
    # for i in range(coords.shape[0]):
    #     preds[i] = transform_preds(
    #         coords[i], center[i], scale[i], [heatmap_width, heatmap_height]
    #     )

    return preds, maxvals

def resize_with_pad(image: np.array,
                    new_shape: Tuple[int, int],
                    padding_color: Tuple[int] = (255, 255, 255)) -> np.array:
    """
    https://gist.github.com/IdeaKing/11cf5e146d23c5bb219ba3508cca89ec
    Maintains aspect ratio and resizes with padding.
    Params:
        image: Image to be resized.
        new_shape: Expected (width, height) of new image.
        padding_color: Tuple in BGR of padding color
    Returns:
        image: Resized image with padding
    """
    original_shape = (image.shape[1], image.shape[0])
    ratio = float(max(new_shape))/max(original_shape)
    new_size = tuple([int(x*ratio) for x in original_shape])
    image = cv2.resize(image, new_size)
    delta_w = new_shape[0] - new_size[0]
    delta_h = new_shape[1] - new_size[1]
    top, bottom = delta_h//2, delta_h-(delta_h//2)
    left, right = delta_w//2, delta_w-(delta_w//2)
    image = cv2.copyMakeBorder(image, top, bottom, left, right, cv2.BORDER_CONSTANT, value=padding_color)
    return image

# Deep leArning lanDmark Detection for eYes
class DADDY_cls(object):
    def __init__(self):
        onnxruntime.disable_telemetry_events()
        options = onnxruntime.SessionOptions()
        options.inter_op_num_threads = 1  # This number should be changed accordingly
        options.intra_op_num_threads = 4  # This number should be changed accordingly
        options.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
    
        ort_session = onnxruntime.InferenceSession(model_file, sess_options=options)
        ort_session.set_providers(['CPUExecutionProvider'])  # only cpu mode
        
        self.ort_session = ort_session
        self.input_name = ort_session.get_inputs()[0].name
        self.output_name = ort_session.get_outputs()[0].name
    
    def open_video(self, video_path):
        # Temporary implementation to run
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise IOError("Error opening video stream or file")
        self.cap = cap
        return True
    
    def read_frame(self):
        # Temporary implementation to run
        if not self.cap.isOpened():
            return False
        ret, frame = self.cap.read()
        if ret:
            # I have set it to grayscale (1ch) just in case, but if the frame is 1ch, this line can be commented out.
            # self.current_image=frame # debug code
            self.current_image_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            return True
        return False
    
    def single_run(self):
        # Temporary implementation to run
        gray_frame = self.current_image_gray

        # frame_resize=resize_with_pad(gray_frame,(input_size,input_size))
        # or
        frame_resize = cv2.resize(gray_frame, (input_size, input_size))
        imgs = np.divide(frame_resize[np.newaxis, np.newaxis], 255, dtype=np.float32)  # input/255.0

        pred_heatmap = self.ort_session.run(None, {self.input_name: imgs})[0]  # .reshape((-1, 2))
        # if imshow_enable:
        #     heatmap = pred_heatmap.reshape((-1, heatmap_size, heatmap_size))
        #     for i in range(heatmap.shape[0]):
        #         cv2.imshow("heatmap_{}".format(i + 1), heatmap[i])
        
        
        pred, max_val = get_final_preds(pred_heatmap,(self.current_image_gray.shape[1],self.current_image_gray.shape[0]))
        pred = pred.reshape((-1, 2))
        # or
        # pred, max_val = get_final_preds(pred_heatmap, input_size)
        # pred = pred.reshape((-1, 2))
        # height, width = self.current_image_gray.shape[:2]
        # scale_x =  input_size/ width
        # scale_y = input_size / height
        # pred[:, 0] *= scale_x
        # pred[:, 1] *= scale_y
        
        kps = pred.astype(np.int32)
        # if save_video or imshow_enable:
        #     for i in range(kps.shape[0]):
        #         if i < 6:
        #             color = (0, 0, 255)
        #         elif i == 6:
        #             color = 128 #(0, 255, 0)
        #         else:
        #             color = (255, 0, 0)
        #         cv2.circle(gray_frame, (kps[i, 0], kps[i, 1]), 1, color, 2)
        #         cv2.putText(gray_frame, str(i), (kps[i, 0] - 10,  kps[i, 1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)
        #     cv2.imshow("gray_frame", gray_frame)
        #     if cv2.waitKey(1) & 0xFF == ord("q"):
        #         pass
        
        
        # kps[i, :] = (x, y)
        # i == [0:6] = Inner and outer corners of eyes and eyelids
        # i == [6] = pupil
        # i == [7:] = iris
        return kps[6, :]


class External_Run_DADDY(object):
    def __init__(self):
        self.algo = DADDY_cls()
    
    def run(self, current_image_gray):
        self.algo.current_image_gray = current_image_gray
        pupil = self.algo.single_run()
        return pupil


if __name__ == "__main__":
    daddy = DADDY_cls()
    daddy.open_video(video_path)
    while daddy.read_frame():
        _ = daddy.single_run()
    