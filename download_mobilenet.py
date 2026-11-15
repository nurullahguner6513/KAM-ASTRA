import urllib.request
import time
url = 'https://github.com/chuanqi305/MobileNet-SSD/raw/master/voc/MobileNetSSD_deploy.caffemodel'
for i in range(3):
    try:
        print('Downloading...')
        urllib.request.urlretrieve(url, 'actions/MobileNetSSD_deploy.caffemodel')
        print('Success!')
        break
    except Exception as e:
        print('Failed:', e)
        time.sleep(2)
