#!/bin/bash


SELECTEDIMAGE_PATH=/home/jason/lscCcode/selectImageFromRawSUNCG/selectedImage
CUDA_VISIBLE_DEVICES=1 python seg_fuse_suncg.py $SELECTEDIMAGE_PATH 2>&1 | tee logs/seg_fuse_suncg.log