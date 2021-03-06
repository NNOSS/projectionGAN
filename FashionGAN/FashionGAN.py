from __future__ import print_function
import tensorflow as tf
import numpy as np
from tensorlayer.layers import *
import testerModel
from projectionMethods import *

MODELS_NAME = ['Classical', 'SOTA', 'Ours']
# WHICH_MODEL = 2
BASE_X = 7
BASE_Y = 7
IMAGE_SIZE = 28,28,1
Z_SIZE = 32
D_CONVOLUTIONS = [-32, -64, 128]
D_HIDDEN_SIZE = 1000
G_CONVOLUTIONS = [128, -64,-32]
G_PROJECTIONS = [16,16,16]
NUM_CLASSES = 10
D_LEARNING_RATE = 2e-5
G_LEARNING_RATE = 1e-4
MOMENTUM = .5
BATCH_SIZE = 256
FILEPATH = '/Data/FashionMNIST/'
TRAIN_INPUT = FILEPATH + 'train-images-idx3-ubyte'
TRAIN_LABEL = FILEPATH + 'train-labels-idx1-ubyte'
# PERM_MODEL_FILEPATH = '/Models/FashionMNIST/'+ MODELS_NAME[WHICH_MODEL] + '/model.ckpt' #filepaths to model and summaries
# SUMMARY_FILEPATH ='/Models/FashionMNIST/'+ MODELS_NAME[WHICH_MODEL] + '/Summaries/'

RESTORE = False
WHEN_DISP = 500
WHEN_TEST = 50
NUM_OUTPUTS = 30
WHEN_SAVE = 2000
ITERATIONS = 25000

def decode_image(image):
    # Normalize from [0, 255] to [0.0, 1.0]
    image = tf.decode_raw(image, tf.uint8)
    image = tf.cast(image, tf.float32)
    image = tf.reshape(image, [IMAGE_SIZE[0], IMAGE_SIZE[1], 1])
    return image / 255.0

def decode_label(label):
    label = tf.decode_raw(label, tf.uint8)
    label = tf.reshape(label, [1])
    return  label

def return_datatset_train():
    images = tf.data.FixedLengthRecordDataset(
      TRAIN_INPUT, IMAGE_SIZE[0] * IMAGE_SIZE[1] * 1, header_bytes=16).map(decode_image)
    labels = tf.data.FixedLengthRecordDataset(
      TRAIN_LABEL, 1, header_bytes=8).map(decode_label)
    return tf.data.Dataset.zip((images, labels))


def create_discriminator(x_image, classes, reuse = False):
    '''Create a discrimator, not the convolutions may be negative to represent
        downsampling'''
    with tf.variable_scope("d_discriminator") as scope:
        if reuse: #get previous variable if we are reusing the discriminator but with fake images
            scope.reuse_variables()
        xs, ys = IMAGE_SIZE[0],IMAGE_SIZE[1]
        inputs = InputLayer(x_image, name='d_inputs')

        convVals = inputs
        res = inputs
        for i,v in enumerate(D_CONVOLUTIONS):
            '''Similarly tile for constant reference to class'''
            convVals = Conv2d(convVals,abs(v), (1, 1), act=tf.nn.leaky_relu,strides =(1,1),name='d_conv_0_%i'%(i))
            if WHICH_MODEL ==0:
                batch = BatchNormLayer(convVals,act=tf.nn.leaky_relu, is_train=True,name='d_bn_1_%i'%(i))
                batch = feature_concat(batch.outputs, classes)
            else:
                batch = batch_norm_disc(convVals.outputs,classes, v, i)
                batch = tf.nn.leaky_relu(batch)
            batch = InputLayer(batch)
            conv = Conv2d(batch,abs(v), (3, 3), strides =(1,1),name='d_conv_1_%i'%(i))
            batch = BatchNormLayer(conv,act=tf.nn.leaky_relu, is_train=True,name='d_bn_2_%i'%(i))
            conv = Conv2d(batch,abs(v), (3, 3), strides =(1,1),name='d_conv_2_%i'%(i))
            convVals = InputLayer(convVals.outputs + conv.outputs, name='d_res_sum_%i'%(i))
            if v < 0:
                v *= -1
                convVals = Conv2d(convVals,v, (3, 3), act=tf.nn.leaky_relu,strides =(2,2),name='d_conv_3_%i'%(i))
            else:
                convVals = Conv2d(convVals,v, (3, 3), act=tf.nn.leaky_relu,strides =(1,1),name='d_conv_3_%i'%(i))

            #add necessary convolutional layers
                # fully connecter layer
        flat3 = FlattenLayer(convVals, name = 'd_flatten')
        inputClass =InputLayer(classes, name='d_class_inputs')
        concat = ConcatLayer([flat3, inputClass], 1, name ='d_concat_layer')
        hid3 = DenseLayer(concat, D_HIDDEN_SIZE,act = tf.nn.relu, name = 'd_fcl')
        y_conv = DenseLayer(hid3, 1,  name = 'd_output').outputs
        return y_conv

def create_generator(z, classes):
    '''Function to create the enerator and give its output
    Note that in convolutions, negative convolutions mean downsampling'''
    # Generator Net
    with tf.variable_scope("gen_generator") as scope:
        if WHICH_MODEL == 2:
            class_matrix = tf.get_variable("gen_mapping_w", [NUM_CLASSES, Z_SIZE])
            bias_matrix = tf.get_variable("gen_mapping_b", [NUM_CLASSES, Z_SIZE])
            class_selection = tf.expand_dims(tf.argmax(classes, axis = 1), -1)
            selected_weights = tf.gather_nd(class_matrix, class_selection)
            selected_biases =  tf.gather_nd(bias_matrix, class_selection)
            z = z * selected_weights + selected_biases
        inputs = InputLayer(z, name='gen_inputs')
        inputClass =InputLayer(classes, name='gen_class_inputs_z')
        numPools = sum([1 for i in G_CONVOLUTIONS if i < 0]) #count number of total convolutions
        print(numPools)
        xs, ys = IMAGE_SIZE[0]/(2**numPools), IMAGE_SIZE[1]/(2**numPools) #calculate start image size from numPools
        sizeDeconv = xs * ys * abs(G_CONVOLUTIONS[0])
        # conat_layer = ConcatLayer([inputs, inputClass], 1, name ='gen_concat_layer_z2')
        # print(conat_layer.get_shape())
        deconveInputFlat = DenseLayer(inputs, sizeDeconv, act = tf.nn.relu, name = 'gen_fdeconv')#dense layer to input to be reshaped
        convVals = ReshapeLayer(deconveInputFlat, (-1, BASE_X, BASE_Y, abs(G_CONVOLUTIONS[0])), name = 'gen_unflatten')

        for i,v in enumerate(G_CONVOLUTIONS[1:]):#for every convolution
            convVals = Conv2d(convVals,abs(v), (1, 1), act=tf.nn.leaky_relu,strides =(1,1),name='gen_conv_0_%i'%(i))
            if WHICH_MODEL == 0:
                batch = BatchNormLayer(convVals,act=tf.nn.leaky_relu, is_train=True,name='gen_bn_1_%i'%(i))
                batch = feature_concat(batch.outputs, classes)
            elif WHICH_MODEL ==1:
                batch = batch_norm_sota(convVals.outputs,classes, v, i)
                batch = tf.nn.leaky_relu(batch)
            elif WHICH_MODEL == 2:
                batch = batch_norm_map(convVals.outputs,classes, v, i)
                batch = tf.nn.leaky_relu(batch)
            batch = InputLayer(batch)
            conv = Conv2d(batch,abs(v), (3, 3), strides =(1,1),name='gen_deconv_1_%i'%(i))
            batch = BatchNormLayer(conv,act=tf.nn.leaky_relu, is_train=True,name='gen_bn_2_%i'%(i))
            conv = Conv2d(batch,abs(v), (3, 3), strides =(1,1),name='gen_deconv_2_%i'%(i))
            convVals = InputLayer(convVals.outputs + conv.outputs, name='res_sum_%i'%(i))
            if v < 0:
                v *= -1
                convVals = UpSampling2dLayer(convVals, (2,2),name='gen_upsample_%i'%(i))
                convVals = Conv2d(convVals,v, (3, 3), strides =(1,1),name='gen_deconv_3_%i'%(i))
            else:
                convVals = Conv2d(convVals,v, (3, 3), strides =(1,1),name='gen_deconv_3_%i'%(i))

        batch = BatchNormLayer(convVals,act=tf.nn.relu, is_train=True,name='gen_bn_final')
        convVals = Conv2d(batch,IMAGE_SIZE[2], (1, 1), strides = (1,1), act=tf.nn.tanh,name='gen_fake_input')
        return tf.nn.relu(convVals.outputs) #return flattened outputs

def build_model(x, og_classes):
    # classes = tf.squeeze(classes, axis = 1)
    classes = tf.squeeze(og_classes, 1)
    classes_one =tf.one_hot(classes, NUM_CLASSES)
    fake_classes_one = tf.one_hot(classes, NUM_CLASSES)
    y = tf.expand_dims(tf.ones_like(classes, dtype=tf.float32),-1)
    fake_y = tf.expand_dims(tf.zeros_like(classes, dtype=tf.float32),-1)
    y_conv = create_discriminator(x,classes_one) #real image discrimator
        # print(classes.get_shape())
        # m = classes.get_shape()
    m = tf.shape(classes)
    m = tf.concat([m,[Z_SIZE]],0)
    z = tf.random_normal(m)

    fake_input = create_generator(z,fake_classes_one) #generator
    test_summary, _ = testerModel.build_model(fake_input, tf.cast(og_classes,dtype=tf.int32))
    fake_y_conv = create_discriminator(fake_input,fake_classes_one,reuse = True)#fake image discrimator
    with tf.variable_scope('logistics') as scope:
        fake_input_summary = tf.summary.image("fake_inputs", fake_input,max_outputs = NUM_OUTPUTS)#show fake image
        real_input_summary = tf.summary.image("real_inputs", x,max_outputs = NUM_OUTPUTS)#show real image
        t_vars = tf.trainable_variables()
    # print(t_vars)

        d_vars = [var for var in t_vars if 'd_' in var.name] #find trainable discriminator variable
        print(d_vars)
        gen_vars = [var for var in t_vars if 'gen_' in var.name] #find trainable discriminator variable
        # print(gen_vars)
        print(y.get_shape())
        print(y_conv.get_shape())
        d_cross_entropy = tf.reduce_mean(
            tf.nn.sigmoid_cross_entropy_with_logits(labels=y, logits=y_conv)) + tf.reduce_mean(
                tf.nn.sigmoid_cross_entropy_with_logits(labels=fake_y, logits=fake_y_conv))# reduce mean for discriminator
        d_cross_entropy_summary = tf.summary.scalar('d_loss',d_cross_entropy)
        gen_cross_entropy = tf.reduce_mean(
            tf.nn.sigmoid_cross_entropy_with_logits(labels=y, logits=fake_y_conv))#reduce mean for generator
        final_true = tf.round(tf.sigmoid(y_conv))
        final_false = tf.round(tf.sigmoid(fake_y_conv))
        accuracy_real = tf.reduce_mean(tf.cast(tf.equal(final_true, y), tf.float32))#determine various accuracies
        accuracy_fake = tf.reduce_mean(tf.cast(tf.equal(final_false,fake_y), tf.float32))
        accuracy_summary_real = tf.summary.scalar('accuracy_real',accuracy_real)
        accuracy_summary_fake = tf.summary.scalar('accuracy_fake',accuracy_fake)
    train_step = tf.train.AdamOptimizer(D_LEARNING_RATE,beta1=MOMENTUM).minimize(d_cross_entropy, var_list = d_vars)
    gen_train_step = tf.train.AdamOptimizer(G_LEARNING_RATE,beta1=MOMENTUM).minimize(gen_cross_entropy,var_list = gen_vars)
    gen_cross_entropy_summary = tf.summary.scalar('g_loss',gen_cross_entropy)
    scalar_summary = tf.summary.merge([d_cross_entropy_summary,gen_cross_entropy_summary,accuracy_summary_real,accuracy_summary_fake])
    image_summary = tf.summary.merge([real_input_summary,fake_input_summary])
    return scalar_summary, image_summary, train_step, gen_train_step,test_summary

def train_model():
    sess = tf.Session()#start the session
    ##############GET DATA###############
    train_ship = return_datatset_train().repeat().batch(BATCH_SIZE)
    train_iterator = train_ship.make_initializable_iterator()
    train_input, train_label = train_iterator.get_next()
    sess.run([train_iterator.initializer])
    scalar_summary, image_summary, train_step, gen_train_step, test_summary = build_model(train_input, train_label)

    ##########################################################################
    #Call function to make tf models
    ##########################################################################
    sess.run(tf.global_variables_initializer())
    t_vars = tf.trainable_variables()
    _ =testerModel.init_model(sess)

    d_vars = [var for var in t_vars if 'd_' in var.name] #find trainable discriminator variable
    print(d_vars)
    gen_vars = [var for var in t_vars if 'gen_' in var.name]
    saver_perm = tf.train.Saver(var_list =d_vars + gen_vars)
    if PERM_MODEL_FILEPATH is not None and RESTORE:
        saver_perm.restore(sess, PERM_MODEL_FILEPATH)
    else:
        print('SAVE')
        saver_perm.save(sess, PERM_MODEL_FILEPATH)
    train_writer = tf.summary.FileWriter(SUMMARY_FILEPATH,
                                  sess.graph)
    trains = [train_step,train_step,gen_train_step]
    for i in range(ITERATIONS):
        train = trains[i%3]
        if not i % WHEN_DISP:
            input_summary_ex, image_summary_ex,_= sess.run([scalar_summary, image_summary, train])
            train_writer.add_summary(image_summary_ex, i)
        else:
            input_summary_ex, _= sess.run([scalar_summary, train])
        train_writer.add_summary(input_summary_ex, i)

        if not i % WHEN_TEST:
            test_summary_ex= sess.run(test_summary)
            train_writer.add_summary(test_summary_ex, i)

        if not i % WHEN_SAVE:
            saver_perm.save(sess, PERM_MODEL_FILEPATH)
        # if not i % EST_ITERATIONS:
        #     print('Epoch' + str(i / EST_ITERATIONS))

if __name__ == "__main__":
    NUM_TRIALS = 5
    tf.reset_default_graph()

    for i in range(NUM_TRIALS):
        for j in range(len(MODELS_NAME)):
            WHICH_MODEL = j
            PERM_MODEL_FILEPATH = '/Models/FashionMNIST/'+ MODELS_NAME[WHICH_MODEL]\
                + '/Trial'+ str(i)+'/model.ckpt' #filepaths to model and summaries
            SUMMARY_FILEPATH = '/Models/FashionMNIST/'+ MODELS_NAME[WHICH_MODEL]\
                + '/Trial'+ str(i)+'/Summaries/' #filepaths to model and summaries
            train_model()
            tf.reset_default_graph()
