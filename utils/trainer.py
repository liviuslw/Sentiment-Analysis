# Version python3.6
# -*- coding: utf-8 -*-
# @Time    : 2018/10/16 10:49 AM
# @Author  : zenRRan
# @Email   : zenrran@qq.com
# @File    : trainer.py
# @Software: PyCharm Community Edition

from utils.build_batch import Build_Batch
from models.CNN import CNN
from models.LSTM import LSTM
from models.Multi_CNN import Multi_CNN
from models.Pooling import Pooling
from utils.Common import padding_key

import torch
import torch.nn.functional as F
import torch.optim as optim

from utils.log import Log

import os


class Trainer:
    def __init__(self, train_dev_test, opts, vocab, label_vocab):
        self.train_features_list = train_dev_test[0]
        self.dev_features_list = train_dev_test[1]
        self.test_features_list = train_dev_test[2]
        self.opts = opts
        self.vocab = vocab
        self.label_vocab = label_vocab
        self.epoch = opts.epoch
        self.model = None

        self.build_batch()
        self.init_model()
        self.init_optim()

        self.print_log = Log(opts)

        #save model switch
        self.save_model_switch = False

    def build_batch(self):
        '''
        build train dev test batches
        '''
        padding_id = self.vocab.from_string(padding_key)
        self.train_build_batch = Build_Batch(features=self.train_features_list, batch_size=self.opts.train_batch_size,
                                             opts=self.opts, pad_idx=padding_id)
        self.dev_build_batch = Build_Batch(features=self.dev_features_list, batch_size=self.opts.dev_batch_size,
                                           opts=self.opts, pad_idx=padding_id)
        self.test_build_batch = Build_Batch(features=self.test_features_list, batch_size=self.opts.test_batch_size,
                                            opts=self.opts, pad_idx=padding_id)

        if self.opts.train_batch_type == 'normal':
            self.train_batch_features, self.train_data_batchs = self.train_build_batch.create_sorted_normal_batch()
        elif self.opts.train_batch_type == 'same':
            self.train_batch_features, self.train_data_batchs = self.train_build_batch.create_same_sents_length_one_batch()
        else:
            raise RuntimeError('not normal or same')

        if self.opts.dev_batch_type == 'normal':
            self.dev_batch_features, self.dev_data_batchs = self.dev_build_batch.create_sorted_normal_batch()
        elif self.opts.dev_batch_type == 'same':
            self.dev_batch_features, self.dev_data_batchs = self.dev_build_batch.create_same_sents_length_one_batch()
        else:
            raise RuntimeError('not normal or same')

        if self.opts.test_batch_type == 'normal':
            self.test_batch_features, self.test_data_batchs = self.test_build_batch.create_sorted_normal_batch()
        elif self.opts.test_batch_type == 'same':
            self.test_batch_features, self.test_data_batchs = self.test_build_batch.create_same_sents_length_one_batch()
        else:
            raise RuntimeError('not normal or same')

    def init_model(self):
        '''
        pooling, rnn, lstm, bilstm, cnn, multi_cnn, gru
        :return:
        '''
        if self.opts.model == 'pooling':
            self.model = Pooling(opts=self.opts, vocab=self.vocab, label_vocab=self.label_vocab)
        elif self.opts.model == 'cnn':
            self.model = CNN(opts=self.opts, vocab=self.vocab, label_vocab=self.label_vocab)
        elif self.opts.model == 'lstm':
            self.model = LSTM(opts=self.opts, vocab=self.vocab, label_vocab=self.label_vocab)
        # elif self.opts.model == 'bilstm':
        #     self.model = CNN(opts=self.opts)
        # elif self.opts.model == 'cnn':
        #     self.model = CNN(opts=self.opts)
        else:
            raise RuntimeError('please choose your model first!')

        if self.opts.use_cuda:
            self.model = self.model.cuda()

    def init_optim(self):
        'sgd, adam'
        if self.opts.optim == 'sgd':
            self.optimizer = optim.SGD(self.model.parameters(), lr=self.opts.lr, weight_decay=self.opts.weight_decay, momentum=self.opts.momentum)
        elif self.opts.optim == 'adam':
            self.optimizer = optim.Adam(self.model.parameters(), lr=self.opts.lr, weight_decay=self.opts.weight_decay)

    def train(self):

        for epoch in range(self.epoch):
            totle_loss = torch.Tensor([0])
            correct_num = 0
            step = 0
            inst_num = 0
            for batch in self.train_data_batchs:

                self.model.train()
                self.optimizer.zero_grad()

                inst_num += len(batch[1])

                data = torch.LongTensor(batch[0])
                label = torch.LongTensor(batch[1])

                if self.opts.use_cuda:
                    data = data.cuda()
                    label = label.cuda()

                pred = self.model(data)

                loss = F.cross_entropy(pred, label)

                loss.backward()
                self.optimizer.step()

                totle_loss += loss.data

                step += 1
                correct_num += (torch.max(pred, 1)[1].view(label.size()).data == label.data).sum()
                if step % self.opts.print_every == 0:
                    avg_loss = totle_loss / inst_num
                    acc = float(correct_num) / inst_num * 100
                    log = "Epoch {} step {} acc: {:.2f}% loss: {:.6f}".format(epoch, step, acc, avg_loss.numpy()[0])
                    self.print_log.print_log(log)
                    print(log)
                    totle_loss = torch.Tensor([0])
                    inst_num = 0
                    correct_num = 0

            self.accurcy(type='dev')
            self.accurcy(type='test')

            self.save_model(epoch)

    def save_model(self, cur_epoch):
        if not os.path.isdir(self.opts.save_model_dir):
            os.mkdir(self.opts.save_model_dir)
        if self.opts.save_model_start_from <= cur_epoch:
            self.save_model_switch = True
        if self.save_model_switch and (cur_epoch - self.opts.save_model_start_from) % self.opts.save_model_every == 0:
            fname = self.opts.save_model_dir + '/model_epoch_' + str(cur_epoch) + '.pt'
            torch.save(self.model, fname)
            self.print_log.print_log('model saved succeed in ' + fname)
            print('model saved succeed in ' + fname)

    def accurcy(self, type):

        totle_loss = torch.Tensor([0])
        correct_num = 0
        inst_num = 0

        data_batchs = None
        if type == 'dev':
            data_batchs = self.dev_data_batchs
        elif type == 'test':
            data_batchs = self.test_data_batchs
        else:
            raise RuntimeError('type wrong!')

        for batch in data_batchs:

            self.model.eval()

            inst_num += len(batch[1])

            data = torch.LongTensor(batch[0])
            label = torch.LongTensor(batch[1])

            if self.opts.use_cuda:
                data = data.cuda()
                label = label.cuda()

            pred = self.model(data)

            loss = F.cross_entropy(pred, label)

            totle_loss += loss.data

            correct_num += (torch.max(pred, 1)[1].view(label.size()).data == label.data).sum()

        avg_loss = totle_loss / inst_num
        acc = float(correct_num) / inst_num * 100
        log = type + " acc: {:.2f}% loss: {:.6f}".format(acc, avg_loss.numpy()[0])
        self.print_log.print_log(log)
        print(log)

