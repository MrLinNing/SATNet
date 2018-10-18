import os
import shutil
import time

import cv2
import numpy as np
import math

import torch
import torch.backends.cudnn as cudnn
import torch.nn.parallel
import torch.optim
import torch.utils.data
from torch.nn import Parameter
import visdom

import IOU

class Engine(object):
    def __init__(self, state={}):

        self.state = state
        if self._state('use_gpu') is None:
            self.state['use_gpu'] = torch.cuda.is_available()

        if self._state('batch_size') is None:
            self.state['batch_size'] = 1

        if self._state('workers') is None:
            self.state['workers'] = 2

        if self._state('multi_gpu') is None:
            self.state['multi_gpu'] = True

        if self._state('device_ids') is None:
            self.state['device_ids'] = [0]

        if self._state('evaluate') is None:
            self.state['evaluate'] = False

        if self._state('start_epoch') is None:
            self.state['start_epoch'] = 0

        if self._state('max_epochs') is None:
            self.state['max_epochs'] = 80

        if self._state('image_visdom_iters') is None:
            self.state['image_visdom_iters'] = self.state['print_freq']

        if self._state('epoch_step') is None:
            self.state['epoch_step'] = []

        if self._state('save_iter') is None:
            self.state['save_iter'] = 300

        # meters
        self.state['meter_loss_total'] = 0.0
        self.state['meter_loss_num'] = 0
        # time measure
        self.state['batch_time_total'] = 0.0
        self.state['batch_time_num'] = 0
        self.state['data_time_total'] = 0.0
        self.state['data_time_num'] = 0
        # display parameters
        if self._state('print_freq') is None:
            self.state['print_freq'] = 1

        self.colormap = np.array([[0,0,0.6667],
                                  [0,0,1.0000],
                                  [0,0.3333,1.0000],
                                  [0,0.6667,1.0000],
                                  [0,1.0000,1.0000],
                                  [0.3333,1.0000,0.6667],
                                  [0.6667,1.0000,0.3333],
                                  [1.0000,1.0000,0],
                                  [1.0000,0.6667,0],
                                  [1.0000,0.3333,0],
                                  [1.0000,0,0],
                                  [0.6667,0,0]],dtype=float)
        self.vis = visdom.Visdom()
        self.linewin = self.vis.line(X=np.array([0,0],dtype=int), Y=np.array([2,2],dtype=float))
        self.visindex = 2
        self.visbatchloss = [0.5]
        self.visloss = [0.5]
        self.imagewin = self.vis.images(np.random.randn(self.state['batch_size']*2*2, 3, 144, 192), nrow=self.state['batch_size']*2)

    def _state(self, name):
        if name in self.state:
            return self.state[name]

    def on_start_epoch(self, training, model, criterion, data_loader, optimizer=None, display=True):
        self.state['meter_loss_total'] = 0.0
        self.state['meter_loss_num'] = 0
        self.state['batch_time_total'] = 0.0
        self.state['batch_time_num'] = 0
        self.state['data_time_total'] = 0.0
        self.state['data_time_num'] = 0

        self.state['accuracy_total'] = np.zeros((11), dtype = np.float32)
        self.state['accuracy_num'] = np.zeros((11), dtype = np.int32)

    def on_end_epoch(self, training, model, criterion, data_loader, optimizer=None, display=True):
        loss = self.state['meter_loss_total'] / self.state['meter_loss_num']
        accuracy = np.mean(self.state['accuracy_total'] / (self.state['accuracy_num']+0.0001))
        if display:
            if training:
                print('Epoch: [{0}]\t'
                      'Loss {loss:.4f}\t'
                      'Accuracy {accuracy:.4f}'.format(self.state['epoch'], loss=loss, accuracy=accuracy))
            else:
                print('Test: \t Loss {loss:.4f} \t Accuracy {accuracy:.4f}'.format(loss=loss, accuracy=accuracy))
        return loss, accuracy

    def on_start_batch(self, training, model, criterion, data_loader, optimizer=None, display=True):
        pass

    def on_end_batch(self, training, model, criterion, data_loader, optimizer=None, display=True):

        # record loss
        self.state['loss_batch'] = self.state['loss'].data[0]
        self.state['meter_loss_total'] = self.state['meter_loss_total'] + self.state['loss_batch']
        self.state['meter_loss_num'] = self.state['meter_loss_num'] + 1

        if display and self.state['print_freq'] != 0 and self.state['iteration'] % self.state['print_freq'] == 0:
            loss = self.state['meter_loss_total'] / self.state['meter_loss_num']
            batch_time = self.state['batch_time_total'] / self.state['batch_time_num']
            data_time = self.state['data_time_total'] / self.state['data_time_num']
            if training:
                print('Epoch: [{0}][{1}/{2}]\t'
                      'Time {batch_time_current:.3f} ({batch_time:.3f})\t'
                      'Data {data_time_current:.3f} ({data_time:.3f})\t'
                      'Loss {loss_current:.4f} ({loss:.4f})\t'.format(
                    self.state['epoch'], self.state['iteration'], len(data_loader),
                    batch_time_current=self.state['batch_time_current'],
                    batch_time=batch_time, data_time_current=self.state['data_time_batch'],
                    data_time=data_time, loss_current=self.state['loss_batch'], loss=loss))
                
                if self.visindex == 2:
                    self.visloss[0] = loss
                    self.visbatchloss[0] = self.state['loss_batch']
                self.visbatchloss.append(self.state['loss_batch'])
                self.visloss.append(loss)
                self.visindex = self.visindex + 1
                self.vis.line(X=np.column_stack([np.arange(1,self.visindex),np.arange(1,self.visindex)]),
                    Y=np.column_stack([np.asarray(self.visbatchloss),np.asarray(self.visloss)]), win=self.linewin)
            else:
                print('Test: [{0}/{1}]\t'
                      'Time {batch_time_current:.3f} ({batch_time:.3f})\t'
                      'Data {data_time_current:.3f} ({data_time:.3f})\t'
                      'Loss {loss_current:.4f} ({loss:.4f})'.format(
                    self.state['iteration'], len(data_loader),
                    batch_time_current=self.state['batch_time_current'],
                    batch_time=batch_time, data_time_current=self.state['data_time_batch'],
                    data_time=data_time, loss_current=self.state['loss_batch'], loss=loss))

    def on_forward(self, training, model, criterion, data_loader, optimizer=None, display=True):

        input_var = torch.autograd.Variable(self.state['input'], requires_grad=True)
        depth_var = torch.autograd.Variable(self.state['depth'], requires_grad=True)
        target_var = torch.autograd.Variable(self.state['target'], requires_grad=False)

        if training:
            self.state['output'] = model(input_var, depth_var)
            self.state['loss'] = criterion(self.state['output'], target_var)

            acc_tmp = IOU.computeIOU(self.state['output'].data, self.state['target'], 12)
            self.state['accuracy_num'] += np.sum((acc_tmp > -0.1).astype(np.int32), axis = 0)
            acc_tmp[acc_tmp < -0.1] = 0.0
            self.state['accuracy_total'] += np.sum(acc_tmp, axis = 0)

            optimizer.zero_grad()
            self.state['loss'].backward()
            optimizer.step()
        else:
            with torch.no_grad():
                self.state['output'] = model(input_var, depth_var)
                self.state['loss'] = criterion(self.state['output'], target_var)

                acc_tmp = IOU.computeIOU(self.state['output'].data, self.state['target'], 12)
                self.state['accuracy_num'] += np.sum((acc_tmp > -0.1).astype(np.int32), axis = 0)
                acc_tmp[acc_tmp < -0.1] = 0.0
                self.state['accuracy_total'] += np.sum(acc_tmp, axis = 0)

        # draw on visdom
        # if self.state['iteration'] != 0 and self.state['iteration'] % self.state['image_visdom_iters'] == 0:
        #     self.draw_images = np.zeros((self.state['batch_size']*2*2, 3, 144, 192), dtype=float)
        #     tout = np.zeros((self.state['batch_size']*2, 144, 192), dtype=float)
        #     # ground truth
        #     aa = self.state['output'].data.cpu().numpy()
        #     toutput = np.argmax(aa, axis=1)
        #     for i in range(self.state['batch_size']*2):
        #         tout[i] = cv2.resize(toutput[i], dsize=(192,144), interpolation=cv2.INTER_NEAREST)
        #     ttarget = self.state['target'][1].cpu().numpy()
        #     for i in range(12):
        #         tind = np.where(ttarget == i)
        #         self.draw_images[tind[0], :, tind[1],tind[2]] = self.colormap[i]
        #         tind = np.where(tout == i)
        #         self.draw_images[tind[0]+self.state['batch_size']*2, :, tind[1],tind[2]] = self.colormap[i]
        #     self.vis.images(self.draw_images, nrow=self.state['batch_size']*2, win=self.imagewin)

    def init_learning(self, model, criterion):

        self.state['best_score'] = 0

    def learning(self, model, criterion, train_dataset, val_dataset, optimizer=None):

        self.init_learning(model, criterion)

        # data loading code
        train_loader = torch.utils.data.DataLoader(train_dataset,
                                                   batch_size=self.state['batch_size'], shuffle=True,
                                                   num_workers=self.state['workers'])

        val_loader = torch.utils.data.DataLoader(val_dataset,
                                                 batch_size=self.state['batch_size'], shuffle=False,
                                                 num_workers=self.state['workers'])

        # optionally resume from a checkpoint
        if self._state('resume') is not None:
            if os.path.isfile(self.state['resume']):
                print("=> loading checkpoint '{}'".format(self.state['resume']))
                checkpoint = torch.load(self.state['resume'])
                self.state['start_epoch'] = checkpoint['epoch']
                self.state['best_score'] = checkpoint['best_score']
                model.load_state_dict(checkpoint['state_dict'])
                print("=> loaded checkpoint '{}' (epoch {})"
                      .format(self.state['evaluate'], checkpoint['epoch']))
            else:
                print("=> no checkpoint found at '{}'".format(self.state['resume']))


        if self.state['use_gpu']:
            train_loader.pin_memory = True
            val_loader.pin_memory = True
            cudnn.benchmark = True

            if self.state['multi_gpu']:
                model = torch.nn.DataParallel(model, device_ids=self.state['device_ids']).cuda()
            else:
                model = torch.nn.DataParallel(model).cuda()

            criterion = criterion.cuda()

        if self.state['evaluate']:
            self.validate(val_loader, model, criterion)
            return

        # TODO define optimizer

        for epoch in range(self.state['start_epoch'], self.state['max_epochs']):
            self.state['epoch'] = epoch
            self.adjust_learning_rate(optimizer)

            # train for one epoch
            self.train(train_loader, model, criterion, optimizer, epoch)

            self.save_checkpoint({
                'epoch': epoch + 1,
                'arch': self._state('arch'),
                'state_dict': model.module.state_dict() if self.state['use_gpu'] else model.state_dict(),
                'best_score': self.state['best_score'],
            }, False)

            # evaluate on validation set
            loss1, prec1 = self.validate(val_loader, model, criterion)

            # remember best prec@1 and save checkpoint
            is_best = prec1 > self.state['best_score']
            self.state['best_score'] = max(prec1, self.state['best_score'])
            self.save_checkpoint({
                'epoch': epoch + 1,
                'arch': self._state('arch'),
                'state_dict': model.module.state_dict() if self.state['use_gpu'] else model.state_dict(),
                'best_score': self.state['best_score'],
            }, is_best)

            print(' *** best={best:.3f}'.format(best=self.state['best_score']))

    def train(self, data_loader, model, criterion, optimizer, epoch):

        # switch to train mode
        model.train()

        self.on_start_epoch(True, model, criterion, data_loader, optimizer)

        end = time.time()
        for i, (color, depth, label) in enumerate(data_loader):
            bs, ch, hi, wi = color.size()

            # measure data loading time
            self.state['iteration'] = i
            self.state['data_time_batch'] = time.time() - end
            self.state['data_time_total'] = self.state['data_time_total'] + self.state['data_time_batch']
            self.state['data_time_num'] = self.state['data_time_num'] + 1

            self.state['input'] = color.view(bs*2, -1, hi, wi)
            self.state['depth'] = depth.view(bs*2, -1, hi, wi)
            self.state['target'] = label.view(bs*2, -1, wi)

            self.on_start_batch(True, model, criterion, data_loader, optimizer)

            if self.state['use_gpu']:
                self.state['input'] = self.state['input'].cuda(async=True)
                self.state['depth'] = self.state['depth'].cuda(async=True)
                self.state['target'] = self.state['target'].cuda(async=True)

            self.on_forward(True, model, criterion, data_loader, optimizer)

            # measure elapsed time
            self.state['batch_time_current'] = time.time() - end
            self.state['batch_time_total'] = self.state['batch_time_total'] + self.state['batch_time_current']
            self.state['batch_time_num'] = self.state['batch_time_num'] + 1
            end = time.time()
            # measure accuracy
            self.on_end_batch(True, model, criterion, data_loader, optimizer)

            if self.state['save_iter'] != 0 and i != 0 and i % self.state['save_iter'] == 0:
                print 'save checkpoint once!'
                self.save_checkpoint({
                    'epoch': epoch + 1,
                    'arch': self._state('arch'),
                    'state_dict': model.module.state_dict() if self.state['use_gpu'] else model.state_dict(),
                    'best_score': self.state['best_score'],
                }, False)

        self.on_end_epoch(True, model, criterion, data_loader, optimizer)

    def validate(self, data_loader, model, criterion):

        # switch to evaluate mode
        model.eval()

        self.on_start_epoch(False, model, criterion, data_loader)

        end = time.time()
        for i, (color, depth, label) in enumerate(data_loader):
            bs, ch, hi, wi = color.size()

            # measure data loading time
            self.state['iteration'] = i
            self.state['data_time_batch'] = time.time() - end
            self.state['data_time_total'] = self.state['data_time_total'] + self.state['data_time_batch']
            self.state['data_time_num'] = self.state['data_time_num'] + 1

            self.state['input'] = color.view(bs*2, -1, hi, wi)
            self.state['depth'] = depth.view(bs*2, -1, hi, wi)
            self.state['target'] = label.view(bs*2, -1, wi)

            self.on_start_batch(False, model, criterion, data_loader)

            if self.state['use_gpu']:
                self.state['input'] = self.state['input'].cuda(async=True)
                self.state['depth'] = self.state['depth'].cuda(async=True)
                self.state['target'] = self.state['target'].cuda(async=True)

            self.on_forward(False, model, criterion, data_loader)

            # measure elapsed time
            self.state['batch_time_current'] = time.time() - end
            self.state['batch_time_total'] = self.state['batch_time_total'] + self.state['batch_time_current']
            self.state['batch_time_num'] = self.state['batch_time_num'] + 1
            end = time.time()
            # measure accuracy
            self.on_end_batch(False, model, criterion, data_loader)

        loss, score = self.on_end_epoch(False, model, criterion, data_loader)

        return loss, score

    def save_checkpoint(self, state, is_best, filename='checkpoint.pth.tar'):
        if self._state('save_model_path') is not None:
            filename_ = filename
            filename = os.path.join(self.state['save_model_path'], filename_)
            if not os.path.exists(self.state['save_model_path']):
                os.makedirs(self.state['save_model_path'])
        print('save model {filename}'.format(filename=filename))
        torch.save(state, filename)

        # my add
        filename_my = os.path.join(self.state['save_model_path'], 'checkpoint_{}.pth.tar'.format(self.state['epoch']+1))
        torch.save(state, filename_my)
        # my add

        if is_best:
            filename_best = 'model_best.pth.tar'
            if self._state('save_model_path') is not None:
                filename_best = os.path.join(self.state['save_model_path'], filename_best)
            shutil.copyfile(filename, filename_best)
            if self._state('save_model_path') is not None:
                if self._state('filename_previous_best') is not None:
                    os.remove(self._state('filename_previous_best'))
                filename_best = os.path.join(self.state['save_model_path'], 'model_best_{score:.4f}.pth.tar'.format(score=state['best_score']))
                shutil.copyfile(filename, filename_best)
                self.state['filename_previous_best'] = filename_best

    def adjust_learning_rate(self, optimizer):
        """Sets the learning rate to the initial LR decayed by 10 every 30 epochs"""
        # lr = args.lr * (0.1 ** (epoch // 30))
        if self.state['epoch'] is not 0 and self.state['epoch'] in self.state['epoch_step']:
            print('update learning rate')
            for param_group in optimizer.param_groups:
                param_group['lr'] = param_group['lr'] * 0.1
                print(param_group['lr'])