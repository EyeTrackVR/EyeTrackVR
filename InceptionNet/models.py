import tensorflow
import tensorflow.compat.v1 as tf
import tensorflow_hub as hub

from base_model import BaseModel

tf.disable_v2_behavior()


class Inception(BaseModel):
    """
    Google inception model
    """

    def __init__(self, model_name, cfg):
        super(Inception, self).__init__(model_name, cfg)
        self.m = 0.5
        self.l2_reg = tf.keras.regularizers.l2(cfg["l2_beta"])
        self.init_placeholders()
        self.init_forward()
        self.init_optimizer()
        self.summary_op = tf.summary.merge_all()

    def bn_lrelu(self, x, train_logical):
        x = tf.layers.batch_normalization(
            x, training=train_logical, momentum=0.9997, scale=True, center=True
        )
        x = tf.nn.leaky_relu(x, alpha=0.17)
        return x

    # Inception Block A
    def block_a(self, net, name_scope, is_training):
        with tf.variable_scope(
            name_or_scope=name_scope, default_name="Inception_block_A"
        ):
            # Branch 0, 1x1
            with tf.variable_scope("branch_0"):
                branch_0 = tf.layers.conv2d(
                    inputs=net,
                    filters=96 * self.m,
                    kernel_size=(1, 1),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_0a_1x1",
                )

                branch_0 = self.bn_lrelu(branch_0, is_training)

            # Branch 1: 1x1 + 3x3
            with tf.variable_scope("branch_1"):
                branch_1 = tf.layers.conv2d(
                    inputs=net,
                    filters=64 * self.m,
                    kernel_size=(1, 1),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_1a_1x1",
                )
                branch_1 = self.bn_lrelu(branch_1, is_training)

                branch_1 = tf.layers.conv2d(
                    inputs=branch_1,
                    filters=96 * self.m,
                    kernel_size=(3, 3),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_1b_3x3",
                )
                branch_1 = self.bn_lrelu(branch_1, is_training)

            # Branch 2: 1x1 + 3x3 + 3x3
            with tf.variable_scope("branch_2"):
                branch_2 = tf.layers.conv2d(
                    inputs=net,
                    filters=64 * self.m,
                    kernel_size=(1, 1),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_2a_1x1",
                )
                branch_2 = self.bn_lrelu(branch_2, is_training)

                branch_2 = tf.layers.conv2d(
                    inputs=branch_2,
                    filters=96 * self.m,
                    kernel_size=(3, 3),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_2b_3x3",
                )
                branch_2 = self.bn_lrelu(branch_2, is_training)

                branch_2 = tf.layers.conv2d(
                    inputs=branch_2,
                    filters=96 * self.m,
                    kernel_size=(3, 3),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_2c_3x3",
                )
                branch_2 = self.bn_lrelu(branch_2, is_training)

            # Branch 3: AvgPool + 1x1
            with tf.variable_scope("branch_3"):
                branch_3 = tf.layers.average_pooling2d(
                    inputs=net,
                    pool_size=(3, 3),
                    strides=(1, 1),
                    padding="SAME",
                    name="AvgPool_3a_3x3",
                )

                branch_3 = tf.layers.conv2d(
                    inputs=branch_3,
                    filters=96 * self.m,
                    kernel_size=(1, 1),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_3b_1x1",
                )
                branch_3 = self.bn_lrelu(branch_3, is_training)

            return tf.concat([branch_0, branch_1, branch_2, branch_3], axis=3)

    # Reduction block A
    def block_a_reduction(self, net, name_scope, is_training):
        with tf.variable_scope(
            name_or_scope=name_scope, default_name="Reduction_block_A"
        ):
            # Branch 0, 3x3(V2)
            with tf.variable_scope("branch_0"):
                branch_0 = tf.layers.conv2d(
                    inputs=net,
                    filters=384 * self.m,
                    kernel_size=(3, 3),
                    strides=(2, 2),
                    padding="VALID",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_0a_3x3V2",
                )

                branch_0 = self.bn_lrelu(branch_0, is_training)

            # Branch 1: 1x1 + 3x3 + 3x3V2
            with tf.variable_scope("branch_1"):
                branch_1 = tf.layers.conv2d(
                    inputs=net,
                    filters=192 * self.m,
                    kernel_size=(1, 1),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_1a_1x1",
                )

                branch_1 = self.bn_lrelu(branch_1, is_training)

                branch_1 = tf.layers.conv2d(
                    inputs=branch_1,
                    filters=224 * self.m,
                    kernel_size=(3, 3),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2_1b_3x3",
                )
                branch_1 = self.bn_lrelu(branch_1, is_training)

                branch_1 = tf.layers.conv2d(
                    inputs=branch_1,
                    filters=256 * self.m,
                    kernel_size=(3, 3),
                    strides=(2, 2),
                    padding="VALID",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2_1c_3x3V2",
                )
                branch_1 = self.bn_lrelu(branch_1, is_training)

            # Branch 2: MaxPool(3x3)
            with tf.variable_scope("branch_3"):
                branch_2 = tf.layers.max_pooling2d(
                    inputs=net,
                    pool_size=(3, 3),
                    strides=(2, 2),
                    padding="VALID",
                    name="MaxPool_2a_3x3V2",
                )

        return tf.concat([branch_0, branch_1, branch_2], axis=3)

    # Inception Block B
    def block_b(self, net, name_scope, is_training):
        with tf.variable_scope(
            name_or_scope=name_scope, default_name="Inception_block_B"
        ):
            # Branch 0: 1x1
            with tf.variable_scope("branch_0"):
                branch_0 = tf.layers.conv2d(
                    inputs=net,
                    filters=384 * self.m,
                    kernel_size=(1, 1),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="Conv2d_0a_1x1",
                )
                branch_0 = self.bn_lrelu(branch_0, is_training)

            # branch 1: 1x1 + 1x7 + 7x1
            with tf.variable_scope("branch_1"):
                branch_1 = tf.layers.conv2d(
                    inputs=net,
                    filters=192 * self.m,
                    kernel_size=(1, 1),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="Conv2d_1a_1x1",
                )
                branch_1 = self.bn_lrelu(branch_1, is_training)

                branch_1 = tf.layers.conv2d(
                    inputs=branch_1,
                    filters=224 * self.m,
                    kernel_size=(1, 7),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="Conv2d_1b_1x7",
                )
                branch_1 = self.bn_lrelu(branch_1, is_training)

                branch_1 = tf.layers.conv2d(
                    inputs=branch_1,
                    filters=256 * self.m,
                    kernel_size=(7, 1),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="Conv2d_1c_7x1",
                )
                branch_1 = self.bn_lrelu(branch_1, is_training)

            # branch 2: 1x1 + 1x7 + 7x1 + 1x7 + 7x1
            with tf.variable_scope("branch_2"):
                branch_2 = tf.layers.conv2d(
                    inputs=net,
                    filters=192 * self.m,
                    kernel_size=(1, 1),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="Conv2_2a_1x1",
                )
                branch_2 = self.bn_lrelu(branch_2, is_training)

                branch_2 = tf.layers.conv2d(
                    inputs=branch_2,
                    filters=192 * self.m,
                    kernel_size=(1, 7),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="Conv2d_2b_1x7",
                )
                branch_2 = self.bn_lrelu(branch_2, is_training)

                branch_2 = tf.layers.conv2d(
                    inputs=branch_2,
                    filters=224 * self.m,
                    kernel_size=(7, 1),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="Conv2d_2c_7x1",
                )
                branch_2 = self.bn_lrelu(branch_2, is_training)

                branch_2 = tf.layers.conv2d(
                    inputs=branch_2,
                    filters=224 * self.m,
                    kernel_size=(1, 7),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="Conv2d_2d_1x7",
                )
                branch_2 = self.bn_lrelu(branch_2, is_training)

                branch_2 = tf.layers.conv2d(
                    inputs=branch_2,
                    filters=256 * self.m,
                    kernel_size=(7, 1),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="Conv2d_2e_7x1",
                )
                branch_2 = self.bn_lrelu(branch_2, is_training)

            # Branch 3: AvgPool + 1x1
            with tf.variable_scope("branch_3"):
                branch_3 = tf.layers.average_pooling2d(
                    inputs=net,
                    pool_size=(3, 3),
                    strides=(1, 1),
                    padding="SAME",
                    name="AvgPool_3a_3x3",
                )

                branch_3 = tf.layers.conv2d(
                    inputs=branch_3,
                    filters=128 * self.m,
                    kernel_size=(1, 1),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_3b_1x1",
                )
                branch_3 = self.bn_lrelu(branch_3, is_training)

        return tf.concat([branch_0, branch_1, branch_2, branch_3], axis=3)

    # Reduction block B
    def block_b_reduction(self, net, name_scope, is_training):
        with tf.variable_scope(
            name_or_scope=name_scope, default_name="Reduction_block_B"
        ):
            # Branch 0: 1x1 + 3x3(V,2)
            with tf.variable_scope("branch_0"):
                branch_0 = tf.layers.conv2d(
                    inputs=net,
                    filters=192 * self.m,
                    kernel_size=(1, 1),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_0a_1x1",
                )
                branch_0 = self.bn_lrelu(branch_0, is_training)

                branch_0 = tf.layers.conv2d(
                    inputs=branch_0,
                    filters=192 * self.m,
                    kernel_size=(3, 3),
                    strides=(2, 2),
                    padding="VALID",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_0b_3x3V2",
                )
                branch_0 = self.bn_lrelu(branch_0, is_training)

            # Branch 1: 1x1 + 1x7 + 7x1 + 3x3(V,2)
            with tf.variable_scope("branch_1"):
                branch_1 = tf.layers.conv2d(
                    inputs=net,
                    filters=256 * self.m,
                    kernel_size=(1, 1),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="Conv2d_1a_1x1",
                )
                branch_1 = self.bn_lrelu(branch_1, is_training)

                branch_1 = tf.layers.conv2d(
                    inputs=branch_1,
                    filters=256 * self.m,
                    kernel_size=(1, 7),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_1b_1x7",
                )
                branch_1 = self.bn_lrelu(branch_1, is_training)

                branch_1 = tf.layers.conv2d(
                    inputs=branch_1,
                    filters=320 * self.m,
                    kernel_size=(7, 1),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_1c_7x1",
                )
                branch_1 = self.bn_lrelu(branch_1, is_training)

                branch_1 = tf.layers.conv2d(
                    inputs=branch_1,
                    filters=320 * self.m,
                    kernel_size=(3, 3),
                    strides=(2, 2),
                    padding="VALID",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="Conv2d_1d_3x3V2",
                )
                branch_1 = self.bn_lrelu(branch_1, is_training)

            # Branch 2: MaxPool 3x3 (V,2)
            with tf.variable_scope("branch_2"):
                branch_2 = tf.layers.max_pooling2d(
                    inputs=net,
                    pool_size=(3, 3),
                    strides=(2, 2),
                    padding="VALID",
                    name="MaxPool_2a_3x3V2",
                )

        return tf.concat([branch_0, branch_1, branch_2], axis=3)

    # Inception Block C
    def block_c(self, net, name_scope, is_training):
        with tf.variable_scope(
            name_or_scope=name_scope, default_name="Inception_Block_C"
        ):
            # Branch 0: 1x1
            with tf.variable_scope("branch_0"):
                branch_0 = tf.layers.conv2d(
                    inputs=net,
                    filters=256 * self.m,
                    kernel_size=(1, 1),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="Conv2d_0a_1x1",
                )
                branch_0 = self.bn_lrelu(branch_0, is_training)

            # Branch 1: 1x1 {1x3, 3x1}
            with tf.variable_scope("branch_1"):
                branch_1 = tf.layers.conv2d(
                    inputs=net,
                    filters=384 * self.m,
                    kernel_size=(1, 1),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_1a_1x1",
                )
                branch_1 = self.bn_lrelu(branch_1, is_training)

                branch_1a = tf.layers.conv2d(
                    inputs=branch_1,
                    filters=256 * self.m,
                    kernel_size=(1, 3),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_1b0_1x3",
                )
                branch_1a = self.bn_lrelu(branch_1a, is_training)

                branch_1b = tf.layers.conv2d(
                    inputs=branch_1,
                    filters=256 * self.m,
                    kernel_size=(3, 1),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_1b1_3x1",
                )
                branch_1b = self.bn_lrelu(branch_1b, is_training)

                branch_1 = tf.concat([branch_1a, branch_1b], axis=3)

            # Branch 2: 1x1, 3x1, 1x3 {3x1, 1x3}
            with tf.variable_scope("branch_2"):
                branch_2 = tf.layers.conv2d(
                    inputs=net,
                    filters=384 * self.m,
                    kernel_size=(1, 1),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_2a_1x1",
                )
                branch_2 = self.bn_lrelu(branch_2, is_training)

                branch_2 = tf.layers.conv2d(
                    inputs=branch_2,
                    filters=448 * self.m,
                    kernel_size=(1, 3),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_2b_1x3",
                )
                branch_2 = self.bn_lrelu(branch_2, is_training)

                branch_2 = tf.layers.conv2d(
                    inputs=branch_2,
                    filters=512 * self.m,
                    kernel_size=(3, 1),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_2c_3x1",
                )
                branch_2 = self.bn_lrelu(branch_2, is_training)

                branch_2a = tf.layers.conv2d(
                    inputs=branch_2,
                    filters=256 * self.m,
                    kernel_size=(1, 3),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_2d0_1x3",
                )
                branch_2a = self.bn_lrelu(branch_2a, is_training)

                branch_2b = tf.layers.conv2d(
                    inputs=branch_2,
                    filters=256 * self.m,
                    kernel_size=(3, 1),
                    strides=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="conv2d_2d1_3x1",
                )
                branch_2b = self.bn_lrelu(branch_2b, is_training)

                branch_2 = tf.concat([branch_2a, branch_2b], axis=3)

            # Branch 3: AvgPool, 1x1
            with tf.variable_scope("branch_3"):
                branch_3 = tf.layers.average_pooling2d(
                    inputs=net,
                    pool_size=(3, 3),
                    strides=(1, 1),
                    padding="SAME",
                    name="AvgPool_3a_3x3",
                )
                branch_3 = tf.layers.conv2d(
                    inputs=branch_3,
                    filters=256 * self.m,
                    kernel_size=(1, 1),
                    padding="SAME",
                    kernel_regularizer=self.l2_reg,
                    kernel_initializer=tensorflow.initializers.GlorotUniform(),
                    name="Conv2d_3b_1x1",
                )
                branch_3 = self.bn_lrelu(branch_3, is_training)

        return tf.concat([branch_0, branch_1, branch_2, branch_3], axis=3)

    def init_forward(self):
        # make the stem
        net = self.X

        # Begin Inception Model
        with tf.variable_scope(name_or_scope="InceptionV4"):
            net = tf.layers.conv2d(
                inputs=net,
                filters=32 * self.m,
                kernel_size=(3, 3),
                strides=(2, 2),
                padding="VALID",
                kernel_regularizer=self.l2_reg,
                kernel_initializer=tensorflow.initializers.GlorotUniform(),
                name="conv2d_stem0_3x3V2",
            )
            net = self.bn_lrelu(net, self.train_flag)

            net = tf.layers.conv2d(
                inputs=net,
                filters=32 * self.m,
                kernel_size=(3, 3),
                strides=(1, 1),
                padding="VALID",
                kernel_regularizer=self.l2_reg,
                kernel_initializer=tensorflow.initializers.GlorotUniform(),
                name="conv2d_stem1_3x3V1",
            )
            net = self.bn_lrelu(net, self.train_flag)

            net = tf.layers.conv2d(
                inputs=net,
                filters=64 * self.m,
                kernel_size=(3, 3),
                strides=(1, 1),
                padding="SAME",
                kernel_regularizer=self.l2_reg,
                kernel_initializer=tensorflow.initializers.GlorotUniform(),
                name="Conv2d_stem2_3x3",
            )
            net = self.bn_lrelu(net, self.train_flag)

            with tf.variable_scope("Mixed_3a"):
                with tf.variable_scope("branch_0"):
                    net_a = tf.layers.conv2d(
                        inputs=net,
                        filters=96 * self.m,
                        kernel_size=(3, 3),
                        strides=(2, 2),
                        padding="VALID",
                        kernel_regularizer=self.l2_reg,
                        kernel_initializer=tensorflow.initializers.GlorotUniform(),
                        name="Conv2d_0a_3x3s2",
                    )
                    net_a = self.bn_lrelu(net_a, self.train_flag)

                with tf.variable_scope("branch_1"):
                    net_b = tf.layers.max_pooling2d(
                        inputs=net,
                        pool_size=(3, 3),
                        strides=(2, 2),
                        padding="VALID",
                        name="MaxPool_1a_3x3s2",
                    )

            net = tf.concat([net_a, net_b], axis=3)

            with tf.variable_scope("mixed_4a"):
                # Branch 0: 1x1, 7x1, 1x7, 3x3v
                with tf.variable_scope("branch_0"):
                    branch_0 = tf.layers.conv2d(
                        inputs=net,
                        filters=64 * self.m,
                        kernel_size=(1, 1),
                        strides=(1, 1),
                        padding="SAME",
                        kernel_regularizer=self.l2_reg,
                        kernel_initializer=tensorflow.initializers.GlorotUniform(),
                        name="Conv2d_0a_3x3",
                    )
                    branch_0 = self.bn_lrelu(branch_0, self.train_flag)

                    branch_0 = tf.layers.conv2d(
                        inputs=branch_0,
                        filters=64 * self.m,
                        kernel_size=(7, 1),
                        strides=(1, 1),
                        padding="SAME",
                        kernel_regularizer=self.l2_reg,
                        kernel_initializer=tensorflow.initializers.GlorotUniform(),
                        name="Conv2d_0b_7x1",
                    )
                    branch_0 = self.bn_lrelu(branch_0, self.train_flag)

                    branch_0 = tf.layers.conv2d(
                        inputs=branch_0,
                        filters=64 * self.m,
                        kernel_size=(1, 7),
                        strides=(1, 1),
                        padding="SAME",
                        kernel_regularizer=self.l2_reg,
                        kernel_initializer=tensorflow.initializers.GlorotUniform(),
                        name="Conv2d_0c_1x7",
                    )
                    branch_0 = self.bn_lrelu(branch_0, self.train_flag)

                    branch_0 = tf.layers.conv2d(
                        inputs=branch_0,
                        filters=96 * self.m,
                        kernel_size=(3, 3),
                        strides=(1, 1),
                        padding="VALID",
                        kernel_regularizer=self.l2_reg,
                        kernel_initializer=tensorflow.initializers.GlorotUniform(),
                        name="Conv2d_0d_3x3V",
                    )
                    branch_0 = self.bn_lrelu(branch_0, self.train_flag)

                # Branch 1: 1x1, 3x3v
                with tf.variable_scope("branch_1"):
                    branch_1 = tf.layers.conv2d(
                        inputs=net,
                        filters=64 * self.m,
                        kernel_size=(1, 1),
                        strides=(1, 1),
                        padding="SAME",
                        kernel_regularizer=self.l2_reg,
                        kernel_initializer=tensorflow.initializers.GlorotUniform(),
                        name="Conv2d_0a_3x3",
                    )
                    branch_1 = self.bn_lrelu(branch_1, self.train_flag)

                    branch_1 = tf.layers.conv2d(
                        inputs=branch_1,
                        filters=96 * self.m,
                        kernel_size=(3, 3),
                        strides=(1, 1),
                        padding="VALID",
                        kernel_regularizer=self.l2_reg,
                        kernel_initializer=tensorflow.initializers.GlorotUniform(),
                        name="Conv2d_0b_3x3V",
                    )
                    branch_1 = self.bn_lrelu(branch_1, self.train_flag)

            net = tf.concat([branch_0, branch_1], axis=3)

            with tf.variable_scope("Mixed_5a"):
                # Branch 0: 3x3
                with tf.variable_scope("branch_0"):
                    branch_0 = tf.layers.conv2d(
                        inputs=net,
                        filters=192 * self.m,
                        kernel_size=(3, 3),
                        strides=(2, 2),
                        padding="VALID",
                        kernel_regularizer=self.l2_reg,
                        kernel_initializer=tensorflow.initializers.GlorotUniform(),
                        name="Conv2d_0a_3x3v",
                    )
                    branch_0 = self.bn_lrelu(branch_0, self.train_flag)

                # Branch 1: MaxPool 3x3s2
                with tf.variable_scope("branch_1"):
                    branch_1 = tf.layers.max_pooling2d(
                        inputs=net,
                        pool_size=(3, 3),
                        strides=(2, 2),
                        padding="VALID",
                        name="MaxPool_0a_3x3s2",
                    )

            net = tf.concat([branch_0, branch_1], axis=3)

            # Block A: 3x
            net = self.block_a(net, "Block_A0", self.train_flag)

            net = self.block_a(net, "Block_A1", self.train_flag)

            net = self.block_a(net, "Block_A2", self.train_flag)

            # Block A: Reduction
            net = self.block_a_reduction(net, "Reduction_A", self.train_flag)

            # Block B: 4x
            net = self.block_b(net, "Block_B0", self.train_flag)

            net = self.block_b(net, "Block_B1", self.train_flag)

            net = self.block_b(net, "Block_B2", self.train_flag)

            net = self.block_b(net, "Block_B3", self.train_flag)

            net = tf.nn.dropout(net, self.keep_prob, name="net_dropout")

            self.GAP = tf.reduce_mean(net, axis=[1, 2], name="GAP")

            # Final layer
            units = self.GAP.get_shape().as_list()[1]
            net = tf.reshape(self.GAP, (-1, 1, 1, units), name="reshaping")
            net = tf.layers.conv2d(
                net,
                self.cfg["output_dim"],
                (1, 1),
                padding="VALID",
                kernel_initializer=tensorflow.initializers.GlorotUniform(),
                kernel_regularizer=self.l2_reg,
                use_bias=False,
                name="final_conv",
            )

            net = tf.nn.relu(net, name="logits_relu")

            # Logits
            self.logits = tf.reshape(net, shape=(-1, self.cfg["output_dim"]), name="y")

            self.loss = tf.losses.huber_loss(
                labels=self.Y,
                predictions=self.logits,
                weights=[self.cfg["output_weights"][0 : self.cfg["output_dim"]]],
                delta=1.0,
            )

            # Training summary for the current batch_loss
            tf.summary.scalar("loss", self.loss)
