config = dict()
# There are 342176 images in train set
# There are 38019 images in validation set
config["total_train"] = 342176
config["total_test"] = 38019
config["batch_size"] = 64

# calculate the validate every based on the number of available data
config["validate_every"] = int(
    config["total_train"] / config["batch_size"]
)  # Usually equal to one epoch
config["validate_for"] = int(config["total_test"] / config["batch_size"])
config["save_every"] = 3 * config["validate_every"]

# number of epochs
config["total_steps"] = config["validate_every"] * 60

# BASIC MODEL hyperparameters
config["n_filters"] = [16, 32, 128, 128, 256, 256]
config["filter_sizes"] = [3, 3, 3, 3, 3, 3]
config["max_pool"] = [1, 1, 1, 1, 1, 1]
config["fc_layers"] = [256, 128]

# # OPTIMIZATION hyperparameters
config["learning_rate"] = [
    0.001,
    0.0009,
    0.0006,
    0.0003,
    0.0001,
    0.00005,
    0.00001,
    0.000005,
    0.000001,
]
config["decay_rate"] = 0.96

# Usually decay every half of epochs
config["decay_step"] = 5 * config["validate_every"]

config["optimizer"] = "ADAM"
config["keep_prob"] = 0.85
config["MAX_GRADIANT_NORM"] = 5.0

# L2 regularization
config["l2_beta"] = 0.0005

# input info
config["input_width"] = 192
config["input_height"] = 192
config["input_channel"] = 1

# Output shape
config["output_dim"] = 3
config["output_weights"] = [1.0, 1.0, 1.0, 1.0, 0.5]

# Augmentation parameters
config["prob_downscale"] = 0.75
config["max_downscale"] = 0.95
config["min_downscale"] = 0.5

config["prob_reflection"] = 0.25
config["min_reflection"] = 0.25
config["max_reflection"] = 0.75

config["prob_blur"] = 0.25
config["min_blurSize"] = 3
config["max_blurSize"] = 9
config["min_sigmaRatio"] = 0.25
config["max_sigmaRatio"] = 0.75

# config["prob_occlusion"] = 0.5
config["min_occlusion"] = 0.05
config["max_occlusion"] = 0.25
config["occlusion_max_obj"] = 6

# exposure on noisy frames
config["prob_exposure"] = 0.25
config["min_exposure"] = 0.7
config["max_exposure"] = 1.2

# crop input image
config["crop_probability"] = 0.5
config["crop_min_ratio"] = 0.5
config["crop_max_ratio"] = 0.95

# flip image
config["flip_probability"] = 0.5

# add Pupil
config["prob_pupil"] = 0.25
