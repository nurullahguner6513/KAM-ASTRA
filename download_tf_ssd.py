import urllib.request
import tarfile
import os

print('Downloading tar.gz...')
url_tar = 'http://download.tensorflow.org/models/object_detection/ssd_mobilenet_v2_coco_2018_03_29.tar.gz'
urllib.request.urlretrieve(url_tar, 'actions/ssd_mobilenet.tar.gz')

print('Extracting...')
with tarfile.open('actions/ssd_mobilenet.tar.gz', 'r:gz') as tar:
    tar.extractall(path='actions')

print('Downloading pbtxt...')
url_pbtxt = 'https://raw.githubusercontent.com/opencv/opencv_extra/master/testdata/dnn/ssd_mobilenet_v2_coco_2018_03_29.pbtxt'
urllib.request.urlretrieve(url_pbtxt, 'actions/ssd_mobilenet_v2_coco_2018_03_29/ssd_mobilenet_v2_coco_2018_03_29.pbtxt')

print('Done!')
