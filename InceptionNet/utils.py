import os

import cv2
import numpy as np

from config import config
  

def check_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)


def rf(low, high):
    """
    return a random float number between [low, high)
    :param low: lower bound
    :param high: higher bound (excluded)
    :return: a float number between [low, high)
    """
    if low >= high:
        return low
    return np.random.uniform(low, high)


def ri(low, high):
    """
    return a random int number between [low, high)
    :param low: lower bound
    :param high: higher bound (excluded)
    :return: an int number between [low, high)
    """
    if low >= high:
        return low
    return np.random.randint(low, high)


def annotator(color, img, x, y, w=10, h=None, a=0):
    """
    draw a circle around predicted pupil
    :param img: input frame
    :param x: x-position
    :param y: y-position
    :param w: width of pupil
    :param h: height of pupil
    :return: an image with a circle around the pupil
    """
    if color is None:
        color = (0, 250, 250)

    c = 1
    if np.ndim(img) == 2:
        img = np.expand_dims(img, -1)
    elif np.ndim(img) == 3:
        c = img.shape[2]

    if c == 1:
        img = np.concatenate((img, img, img), axis=2)

    l1xs = int(x - 3)
    l1ys = int(y)
    l1xe = int(x + 3)
    l1ye = int(y)

    l2xs = int(x)
    l2ys = int(y - 3)
    l2xe = int(x)
    l2ye = int(y + 3)

    img = cv2.line(img, (l1xs, l1ys), (l1xe, l1ye), color, 1)
    img = cv2.line(img, (l2xs, l2ys), (l2xe, l2ye), color, 1)

    # We predict only width!
    if h is None:
        h = w

    # draw ellipse
    img = cv2.ellipse(img, ((x, y), (w, h), a), color, 1)

    return img


def create_noisy_video(data_path='data/valid_data.csv', length=60, fps=5, with_label=False, augmentor=None):
    """
    create a sample video based random image.
    Of course it is not a valid solution to test the model with already seen images.
    It is just to check the speed of model. based on different FPS
    :param data_path: CSV file for input data
    :param length: length of video in second
    :param fps: number of frame per second
    :param with_label: if true, show true label on the video
    :return: a noisy video (file name) for test purpose.
    """

    # read CSV
    data_list = []
    with open(data_path, "r") as f:
        for line in f:
            #  values: [ img_path, x, y, w, h , a]
            values = line.strip().split(",")
            data_list.append([values[0],  # image path
                              values[1],  # x
                              values[2]])  # y

    # number image to make the video
    images_len = fps * length
    np.random.shuffle(data_list)
    start_idx = np.random.randint(0, len(data_list) - images_len)
    selected_images = data_list[start_idx:start_idx + images_len]

    output_fn = 'video_{}s_{}fps.avi'.format(length, fps)
    video = cv2.VideoWriter(output_fn, cv2.VideoWriter_fourcc(*"XVID"), fps,
                            (config["input_height"], config["input_width"]))

    for i in selected_images:
        img = cv2.imread(i[0], cv2.IMREAD_GRAYSCALE)
        x = float(i[1])
        y = float(i[2])
        # w = float(i[3])
        # h = float(i[4])
        # a = float(i[5])
        label = [x, y]
        if augmentor is not None:
            img, label = augmentor.addNoise(img, label)
            img = np.asarray(img, dtype=np.uint8)

        if with_label:
            img = annotator((0, 250, 0), img, *label)
            font = cv2.FONT_HERSHEY_PLAIN
            texts = i[0].split("/")
            text = texts[2] + "/" + texts[3] + "/" + texts[4]
            img = cv2.putText(img, text, (5, 10), font, 0.8, (0, 250, 0), 1, cv2.LINE_8)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

        video.write(img)

    cv2.destroyAllWindows()
    video.release()

    return output_fn


def change_channel(img, num_channel=1):
    """
    Get frame and normalize values between 0 and 1 and then based num channel reshape it to desired channel
    :param frame: the input image, a numpy array
    :param num_channel: desired number of channel
    :return: normalized frame with num_channel
    """
    img = np.expand_dims(img, -1)
    if num_channel == 3:
        img = np.concatenate((img, img, img), axis=2)

    return img


def gray_normalizer(gray):
    """
    get a grayscale image with pixel value 0-255
    and return normalized pixel with value between -1,1
    :param gray: input grayscale image
    :return: normalized grayscale image
    """
    # average mean over all training images ( without noise)
    gray = gray * 1/255
    out_gray = np.asarray(gray - 0.5, dtype=np.float32)
    return out_gray


def gray_denormalizer(gray):
    """
    Get a normalized gray image and convert to value 0-255
    :param gray: normalized grayscale image
    :return: denormalized grayscale image
    """
    # average mean over all training images ( without noise)
    out_gray = gray + 0.5
    out_gray = np.asarray(out_gray * 255, dtype=np.uint8)

    return out_gray


def save_dict(dict, save_path):
    with open(save_path, mode="w") as f:
        for key, val in dict.items():
            f.write(key+";"+str(val)+"\n")
    print("Class dict saved successfully at: {}".format(save_path))


def load_dict(load_path):
    dict = {}
    with open(load_path, mode="r") as f:
        for line in f:
            key, val = line.split(";")
            dict[key] = int(val)

    print("Class dict loaded successfuly at: {}".format(load_path))
    return dict

if __name__ == "__main__":
    ag = Augmentor('data/noisy_videos', config)
    create_noisy_video(with_label=True, augmentor=ag)