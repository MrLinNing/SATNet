import sys, resource, os
import numpy as np
import cv2
import torch
from torchvision.transforms import Compose, Normalize, ToTensor
import h5py

from SATNet_ThinkNetFuse import ImageGen3DNet, TrainDataLoader
sys.path.append('../../')
import configs

# CUDA_VISIBLE_DEVICES=0 python gen_result_ThinkNetFuse.py
def main():
    resume_path = './save_models/SATNet_ThinkNetFuse/checkpoint.pth.tar' # HERE
    output_path = './results/result_suncg.hdf5'

    dataset = TrainDataLoader(SUNCGRGBD_SAMPLE_TXT_TEST, SUNCGRGBD_NPZ_PATH_TEST, "test")
    data_loader = torch.utils.data.DataLoader(dataset, batch_size = 4,
                                              shuffle = False, num_workers = 1)
    data_loader.pin_memory = True

    # model = SceneCompletionRGBD()
    model = ImageGen3DNet('./save_models/SATNet_RGB/checkpoint.pth.tar',
                          './save_models/SATNet_Depth/checkpoint.pth.tar', (384, 288))
    if not os.path.isfile(resume_path):
        print "=> no checkpoint found at '{}'".format(resume_path)
        exit()
    checkpoint = torch.load(resume_path)
    model.load_state_dict(checkpoint['state_dict'], strict = False)
    model.eval()

    softmax_layer = torch.nn.Softmax(dim = 1).cuda(0)

    predictions = []
    with torch.no_grad():
        for i, (color, depth, label, label_weight, depth_mapping_3d) in enumerate(data_loader):
            print '{0}/{1}'.format(i, len(data_loader))

            input_var = torch.autograd.Variable(color.cuda(0, async=True))
            depth_var = torch.autograd.Variable(depth.cuda(1, async=True))
            depth_mapping_3d_var0 = torch.autograd.Variable(depth_mapping_3d.cuda(0, async=True))
            depth_mapping_3d_var1 = torch.autograd.Variable(depth_mapping_3d.cuda(1, async=True))

            output = model(input_var, depth_var, depth_mapping_3d_var0, depth_mapping_3d_var1)
            output = softmax_layer(output) # HERE
            predictions.append(output.cpu().data.numpy())
        predictions = np.vstack(predictions)

    fp = h5py.File(output_path, 'w')
    result = fp.create_dataset('result', predictions.shape, dtype='f')
    result[...] = predictions
    fp.close()

if __name__ == '__main__':

    resource.setrlimit(resource.RLIMIT_STACK, (-1,-1))
    sys.setrecursionlimit(100000)

    main()