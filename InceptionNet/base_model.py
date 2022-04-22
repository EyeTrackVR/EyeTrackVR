import tensorflow.compat.v1 as tf
from tensorflow.python.ops import control_flow_ops

tf.disable_v2_behavior()

# YOLO implementation
# https://github.com/WojciechMormul/yolo2/blob/master/train.py
class BaseModel(object):
    """
    This class serve basic methods for other models
    """

    def __init__(self, model_name, cfg):
        self.cfg = cfg
        self.model_name = model_name
        self.l2beta = cfg["l2_beta"]
        self.model_dir = "models/" + model_name + "/"
        self.mode = 'train'
        self.max_gradient_norm = cfg["MAX_GRADIANT_NORM"]
        self.global_step = tf.Variable(0, trainable=False, name='global_step')
        self.global_epoch_step = tf.Variable(0, trainable=False, name='global_epoch_step')
        self.global_epoch_step_op = tf.assign(self.global_epoch_step, self.global_epoch_step + 1)

        self.update = None
        self.loss = None
        self.logits = None

    def init_placeholders(self):
        # shape: [Batch_size, Width, Height, Channels]
        self.X = tf.placeholder(dtype=tf.float32,
                                shape=(None,
                                       self.cfg["input_height"],
                                       self.cfg["input_width"],
                                       self.cfg["input_channel"]),
                                name="images_input")

        # shape: [Batch_size, 5] (x,y,w,h,a)
        self.Y = tf.placeholder(dtype=tf.float32,
                                shape=(None, self.cfg["output_dim"]),
                                name="ground_truth")

        self.keep_prob = tf.placeholder(dtype=tf.float32,
                                        shape=(),
                                        name="keep_prob")

        self.train_flag = tf.placeholder(dtype=tf.bool, name='flag_placeholder')

        self.learning_rate = tf.placeholder(dtype=tf.float32, shape=(), name="learning_rate")

    def init_optimizer(self):
        print("setting optimizer..")

        # add L2 loss to main loss, do backpropagation
        self.l2_loss = tf.losses.get_regularization_loss()
        tf.summary.scalar("l2_loss", self.l2_loss)

        self.total_loss = tf.add(self.loss, self.l2_loss)
        tf.summary.scalar('final_loss', self.total_loss)

        # we need to define a dependency before calculating the total_loss
        update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
        if update_ops:
            updates = tf.group(*update_ops)
            self.final_loss = control_flow_ops.with_dependencies([updates], self.total_loss)

        with tf.control_dependencies(update_ops):
            trainable_params = tf.trainable_variables()

            opt = tf.train.AdamOptimizer(learning_rate=self.learning_rate)

            # Compute gradients of loss w.r.t. all trainable variables
            gradients = tf.gradients(self.final_loss, trainable_params)

            # Clip gradients by a given maximum_gradient_norm
            clip_gradients, _ = tf.clip_by_global_norm(gradients, self.max_gradient_norm)

            # Update the model
            self.update = opt.apply_gradients(zip(clip_gradients, trainable_params),
                                              global_step=self.global_step)

    def train(self, sess, images, labels, keep_prob, lr):
        """Run a train step of the model feeding the given inputs.
        Args:
        session: tensorflow session to use.
        encoder_inputs: a numpy int matrix of [batch_size, max_source_time_steps]
            to feed as encoder inputs
        encoder_inputs_length: a numpy int vector of [batch_size]
            to feed as sequence lengths for each element in the given batch
        Returns:
            A triple consisting of gradient norm (or None if we did not do backward),
        average perplexity, and the outputs.
        """
        # Check if the model is 'training' mode
        self.mode = 'train'

        input_feed = {self.X.name: images,
                      self.Y.name: labels,
                      self.keep_prob.name: keep_prob,
                      self.train_flag.name: True,
                      self.learning_rate.name: lr}

        output_feed = [self.update,  # Update Op that does optimization
                       self.loss,  # Loss for current batch
                       self.summary_op]

        outputs = sess.run(output_feed, input_feed)
        return outputs[1], outputs[2]

    def eval(self, sess, images, labels):
        """Run a evaluation step of the model feeding the given inputs.
        Args:
        session: tensorflow session to use.
        encoder_inputs: a numpy int matrix of [batch_size, max_source_time_steps]
        to feed as encoder inputs
        encoder_inputs_length: a numpy int vector of [batch_size]
        to feed as sequence lengths for each element in the given batch
        Returns:
        A triple consisting of gradient norm (or None if we did not do backward),
        average perplexity, and the outputs.
        """
        self.mode = "eval"
        input_feed = {self.X.name: images,
                      self.Y.name: labels,
                      self.keep_prob.name: 1.0,
                      self.train_flag.name: False}

        output_feed = [self.loss,  # Loss for current batch
                       self.summary_op,
                       self.logits]

        outputs = sess.run(output_feed, input_feed)
        return outputs[0], outputs[1], outputs[2]

    def predict(self, sess, images):
        """
        predict the label for the given images
        :param sess: current tf.session
        :param images: input test images
        :return: predicted labels
        """
        self.mode = 'test'
        # Input feeds for dropout
        input_feed = {self.X.name: images,
                      self.keep_prob.name: 1.0,
                      self.train_flag.name: False}

        output_feed = [self.logits]
        outputs = sess.run(output_feed, input_feed)

        return outputs[0]

    def restore(self, sess, path, var_list=None):
        """
        restore a model from file
        :param sess: active (current) tf.session
        :param path: path to saved folder
        :param var_list: load desire variables, if none, all variables will be returned
        :return: load model to graph
        """
        # var_list = None returns the list of all saveable variables
        saver = tf.train.Saver(var_list)
        saver.restore(sess, save_path=path)