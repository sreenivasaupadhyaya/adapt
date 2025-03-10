"""
DANN
"""

import warnings
import numpy as np
import tensorflow as tf

from adapt.base import BaseAdaptDeep, make_insert_doc

EPS = np.finfo(np.float32).eps


@make_insert_doc(["encoder", "task", "discriminator"])
class DANN(BaseAdaptDeep):
    """
    DANN: Discriminative Adversarial Neural Network
    
    DANN is a feature-based domain adaptation method.
    
    The goal of DANN is to find a new representation of the input features
    in which source and target data could not be distinguished by any
    **discriminator** network. This new representation is learned by an
    **encoder** network in an adversarial fashion. A **task** network is
    learned on the encoded space in parallel to the **encoder** and 
    **discriminator** networks.
    
    The three network paremeters are optimized according to the
    following objectives:
    
    .. math::
    
        \min_{\phi, F} & \; \mathcal{L}_{task}(F(\phi(X_S)), y_S) -
        \lambda \\left(
        \log(1 - D(\phi(X_S))) + \log(D(\phi(X_T))) \\right) \\\\
        \max_{D} & \; \log(1 - D(\phi(X_S))) + \log(D(\phi(X_T)))
        
    Where:
    
    - :math:`(X_S, y_S), (X_T)` are respectively the labeled source data
      and the unlabeled target data.
    - :math:`\phi, F, D` are respectively the **encoder**, the **task**
      and the **discriminator** networks
    - :math:`\lambda` is the trade-off parameter.
    
    The adversarial training is done through a **reversal gradient layer**
    placed between the **encoder** and the **discriminator** networks.
    This layer inverses the gradient sign in backpropagation, thus the
    two networks are optimized according to two opposite objective functions.
    
    The method has been originally introduced for **unsupervised**
    classification DA but it could be widen to other task in
    **supervised** DA straightforwardly.
    
    .. figure:: ../_static/images/dann.png
        :align: center
        
        DANN architecture (source: [1])
    
    Parameters
    ----------        
    lambda_ : float or tensorflow Variable (default=0.1)
        Trade-off parameter.
    
    Attributes
    ----------
    encoder_ : tensorflow Model
        encoder network.
        
    task_ : tensorflow Model
        task network.
        
    discriminator_ : tensorflow Model
        discriminator network.
        
    history_ : dict
        history of the losses and metrics across the epochs.
        
    Examples
    --------
    >>> from adapt.utils import make_classification_da
    >>> from adapt.feature_based import DANN
    >>> Xs, ys, Xt, yt = make_classification_da()
    >>> model = DANN(lambda_=0.1, Xt=Xt, metrics=["acc"], random_state=0)
    >>> model.fit(Xs, ys, epochs=100, verbose=0)
    >>> model.score(Xt, yt)
    1/1 [==============================] - 0s 108ms/step - loss: 0.1732 - acc: 0.8100
    0.17324252426624298
    
    See also
    --------
    ADDA
    DeepCORAL
        
    References
    ----------
    .. [1] `[1] <http://jmlr.org/papers/volume17/15-239/15-239.pdf>`_ Y. Ganin, \
E. Ustinova, H. Ajakan, P. Germain, H. Larochelle, F. Laviolette, M. Marchand, \
and V. Lempitsky. "Domain-adversarial training of neural networks". In JMLR, 2016.
    """
    def __init__(self,
                 encoder=None,
                 task=None,
                 discriminator=None,
                 Xt=None,
                 yt=None,
                 lambda_=0.1,
                 verbose=1,
                 copy=True,
                 random_state=None,
                 descriminator_type=None,
                 **params):
        # print('inside init1')
        
        if "gamma" in params:
            warnings.warn("the `gamma` argument has been removed from DANN."
                          " If you want to use the lambda update process, please"
                          " use the `UpdateLambda` callback from adapt.utils")
            params.pop("gamma")
        
        names = self._get_param_names()
        kwargs = {k: v for k, v in locals().items() if k in names}
        kwargs.update(params)
        super().__init__(**kwargs)

    def _unpack_data2(self, data):
        # print("unpack data 2")
        data_src = data[0]
        data_tgt = data[1]
        Xs = data_src[0]
        ys,ys2 = data_src[1]
        # print(data_src)
        # print(data_tgt)
        # print("up1")
        if  isinstance(data_tgt, tuple):
            # print("up2")
            Xt = data_tgt[0]
            yt,yt2 = data_tgt[1]
            return Xs, Xt, (ys,ys2), (yt,yt2)
        else:
            # print("up3")
            Xt = data_tgt[0]
            yt,yt2 = data_tgt[1]
            return Xs, Xt, ys, None    
    def train_step(self, data):
        # Unpack the data.
        # Xs, Xt, ys, yt= self._unpack_data(data)
        Xs, Xt, (ys,ys2), (yt,yt2)= self._unpack_data2(data)
        # print('1:',Xs.shape, Xt.shape, ys.shape, ys2.shape,yt.shape, yt2.shape)
        # loss
        with tf.GradientTape() as task_tape, tf.GradientTape() as enc_tape, tf.GradientTape() as disc_tape:
            # Forward pass
            Xs_enc = self.encoder_(Xs, training=True)
            ys_pred = self.task_(Xs_enc, training=True)
            ys_disc = self.discriminator_(Xs_enc, training=True)
            
            Xt_enc = self.encoder_(Xt, training=True)
            yt_disc = self.discriminator_(Xt_enc, training=True)
            
            # Reshape
            ys_pred = tf.reshape(ys_pred, tf.shape(ys))
            
            # Compute the loss value
            # print('3:', ys.shape, ys_pred.shape)
            task_loss = self.task_loss_(ys, ys_pred)
            if 0:
                disc_loss = (-tf.math.log(ys_disc + EPS)
                            -tf.math.log(1-yt_disc + EPS))
            else:
                if self.descriminator_type == 'regression':
                    disc_loss = 0.5*(tf.metrics.mape(ys2,ys_disc)  + tf.metrics.mape(yt2,yt_disc))
                elif self.descriminator_type == 'regression_outnorm':
                    disc_loss = 0.5*(tf.metrics.msle(ys2,ys_disc)  + tf.metrics.msle(yt2,yt_disc))
                elif self.descriminator_type == 'binaryclass':
                    disc_loss = 0.5*(tf.metrics.binary_crossentropy(ys2,ys_disc)  + tf.metrics.binary_crossentropy(yt2,yt_disc))
                elif self.descriminator_type == 'binaryclass_defloss':
                    disc_loss = (-tf.math.log(ys_disc + EPS)
                            -tf.math.log(1-yt_disc + EPS))
                elif 'ordinal_calc_drr_rt60' in self.descriminator_type:
                    disc_loss = 0.5*(tf.metrics.categorical_crossentropy(ys2[0],ys_disc[0])  + tf.metrics.categorical_crossentropy(yt2[0],yt_disc[0]) + tf.metrics.categorical_crossentropy(ys2[1],ys_disc[1])  + tf.metrics.categorical_crossentropy(yt2[1],yt_disc[1]))
                else:
                    disc_loss = 0.5*(tf.metrics.categorical_crossentropy(ys2,ys_disc)  + tf.metrics.categorical_crossentropy(yt2,yt_disc))
                # print('2:', ys2.shape, yt2.shape,ys_disc.shape, yt_disc.shape)
                # disc_loss = 0.5*(tf.metrics.mse(ys2,ys_disc)  + tf.metrics.mse(yt2,yt_disc))
                # print('disc loss 1:, ',disc_loss)
            
            task_loss = tf.reduce_mean(task_loss)
            disc_loss = tf.reduce_mean(disc_loss)
            # print('disc loss 2:, ',disc_loss)
            
            enc_loss = task_loss - self.lambda_ * disc_loss
            
            task_loss += sum(self.task_.losses)
            disc_loss += sum(self.discriminator_.losses)
            enc_loss += sum(self.encoder_.losses)
            # print('disc loss 3:, ',disc_loss)
            # print(enc_loss,task_loss,disc_loss)
            
            
        # Compute gradients
        trainable_vars_task = self.task_.trainable_variables
        trainable_vars_enc = self.encoder_.trainable_variables
        trainable_vars_disc = self.discriminator_.trainable_variables
        
        gradients_task = task_tape.gradient(task_loss, trainable_vars_task)
        gradients_enc = enc_tape.gradient(enc_loss, trainable_vars_enc)
        gradients_disc = disc_tape.gradient(disc_loss, trainable_vars_disc)
        
        # Update weights
        self.optimizer.apply_gradients(zip(gradients_task, trainable_vars_task))
        self.optimizer_enc.apply_gradients(zip(gradients_enc, trainable_vars_enc))
        self.optimizer_disc.apply_gradients(zip(gradients_disc, trainable_vars_disc))
        
        # Update metrics
        self.compiled_metrics.update_state(ys, ys_pred)
        self.compiled_loss(ys, ys_pred)
        # Return a dict mapping metric names to current value
        logs = {m.name: m.result() for m in self.metrics}
        # disc_metrics = self._get_disc_metrics(ys_disc, yt_disc)
        logs.update({"disc_loss": disc_loss})
        # logs.update(disc_metrics)
        return logs
        
    
    def _get_disc_metrics(self, ys_disc, yt_disc):
        disc_dict = {}
        for m in self.disc_metrics:
            disc_dict["disc_%s"%m.name] = tf.reduce_mean(0.5 * (
                m(tf.ones_like(ys_disc), ys_disc)+
                m(tf.zeros_like(yt_disc), yt_disc)
            ))
        return disc_dict