import cv2
import numpy as np
import os

_tf_net = None

COCO_CLASSES = {
    1: 'person', 2: 'bicycle', 3: 'car', 4: 'motorcycle', 5: 'airplane',
    6: 'bus', 7: 'train', 8: 'truck', 9: 'boat', 10: 'traffic light',
    11: 'fire hydrant', 13: 'stop sign', 14: 'parking meter', 15: 'bench',
    16: 'bird', 17: 'cat', 18: 'dog', 19: 'horse', 20: 'sheep', 21: 'cow',
    22: 'elephant', 23: 'bear', 24: 'zebra', 25: 'giraffe', 27: 'backpack',
    28: 'umbrella', 31: 'handbag', 32: 'tie', 33: 'suitcase', 34: 'frisbee',
    35: 'skis', 36: 'snowboard', 37: 'sports ball', 38: 'kite', 39: 'baseball bat',
    40: 'baseball glove', 41: 'skateboard', 42: 'surfboard', 43: 'tennis racket',
    44: 'bottle', 46: 'wine glass', 47: 'cup', 48: 'fork', 49: 'knife', 50: 'spoon',
    51: 'bowl', 52: 'banana', 53: 'apple', 54: 'sandwich', 55: 'orange',
    56: 'broccoli', 57: 'carrot', 58: 'hot dog', 59: 'pizza', 60: 'donut',
    61: 'cake', 62: 'chair', 63: 'couch', 64: 'potted plant', 65: 'bed',
    67: 'dining table', 70: 'toilet', 72: 'tv', 73: 'laptop', 74: 'mouse',
    75: 'remote', 76: 'keyboard', 77: 'cell phone', 78: 'microwave', 79: 'oven',
    80: 'toaster', 81: 'sink', 82: 'refrigerator', 84: 'book', 85: 'clock',
    86: 'vase', 87: 'scissors', 88: 'teddy bear', 89: 'hair drier', 90: 'toothbrush'
}

def get_net():
    global _tf_net
    if _tf_net is None:
        try:
            base_path = os.path.join(os.path.dirname(__file__), "ssd_mobilenet_v2_coco_2018_03_29")
            pb = os.path.join(base_path, "frozen_inference_graph.pb")
            pbtxt = os.path.join(base_path, "ssd_mobilenet_v2_coco_2018_03_29.pbtxt")
            if os.path.exists(pb) and os.path.exists(pbtxt):
                _tf_net = cv2.dnn.readNetFromTensorflow(pb, pbtxt)
        except Exception as e:
            print("[ObjectDetection] OpenCV DNN yuklenirken hata:", e)
    return _tf_net

def detect_objects(frame: np.ndarray):
    net = get_net()
    if net is None:
        return []
        
    h, w = frame.shape[:2]
    blob = cv2.dnn.blobFromImage(frame, size=(300, 300), swapRB=True, crop=False)
    net.setInput(blob)
    
    try:
        detections = net.forward()
    except:
        return []
        
    detected = []
    # detections shape is (1, 1, N, 7)
    for i in range(detections.shape[2]):
        conf = float(detections[0, 0, i, 2])
        if conf > 0.4:
            class_id = int(detections[0, 0, i, 1])
            if class_id in COCO_CLASSES:
                label = COCO_CLASSES[class_id]
                x1 = int(detections[0, 0, i, 3] * w)
                y1 = int(detections[0, 0, i, 4] * h)
                x2 = int(detections[0, 0, i, 5] * w)
                y2 = int(detections[0, 0, i, 6] * h)
                box_w = x2 - x1
                box_h = y2 - y1
                detected.append({
                    "box": (x1, y1, box_w, box_h),
                    "label": label,
                    "confidence": conf
                })
                
    return detected
