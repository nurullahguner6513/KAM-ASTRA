import os
import cv2
import numpy as np
import time
from pathlib import Path

FACES_DIR = Path(__file__).resolve().parent.parent / "memory" / "faces"
FACES_DIR.mkdir(parents=True, exist_ok=True)

class FaceBiometrics:
    def __init__(self):
        # OpenCV built-in Haar cascade for frontal face
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        
        self.label_map = {}  # int id -> name
        self.name_map = {}   # name -> int id
        self.is_trained = False
        
        self.train_model()

    def train_model(self):
        faces = []
        labels = []
        current_id = 0
        
        self.label_map = {}
        self.name_map = {}
        
        # Look for images in FACES_DIR. We assume format: name.jpg or name_1.jpg
        for file in FACES_DIR.glob("*.jpg"):
            name = file.stem.split('_')[0].strip().upper()
            
            if name not in self.name_map:
                self.name_map[name] = current_id
                self.label_map[current_id] = name
                current_id += 1
                
            img = cv2.imread(str(file), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                # Detect face to train exactly on the face region
                detected_faces = self.face_cascade.detectMultiScale(img, scaleFactor=1.1, minNeighbors=4)
                if len(detected_faces) > 0:
                    (x, y, w, h) = detected_faces[0]
                    face_roi = img[y:y+h, x:x+w]
                    faces.append(face_roi)
                    labels.append(self.name_map[name])
                else:
                    # If no face strictly detected by cascade, just train on the whole resized image
                    faces.append(cv2.resize(img, (200, 200)))
                    labels.append(self.name_map[name])

        if faces and labels:
            self.recognizer.train(faces, np.array(labels))
            self.is_trained = True
            print(f"[Biometrics] LBPH Modeli egitildi. Kisiler: {list(self.name_map.keys())}")
        else:
            self.is_trained = False
            print("[Biometrics] Veritabaninda yuz yok, model egitilmedi.")

    def register_face(self, name: str, frame_bgr: np.ndarray) -> str:
        """Kameradan alinan karedeki yüzü bulur ve kaydeder."""
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(40, 40))
        
        if len(faces) == 0:
            return "Karede hiç yüz algılanmadı. Lütfen yüzünüze biraz ışık vurduğundan emin olun ve kameraya bakın."
        
        # En büyük yüzü al (bize en yakın olan)
        faces = sorted(faces, key=lambda f: f[2]*f[3], reverse=True)
        (x, y, w, h) = faces[0]
        
        # Sadece yüz bölgesini kaydet
        face_roi = frame_bgr[y:y+h, x:x+w]
        
        # Dosya adi cakismasini onlemek icin timestamp
        timestamp = int(time.time())
        
        # OpenCV cv2.imread/imwrite cannot handle Turkish chars on Windows!
        replacements = {'Ç': 'C', 'ç': 'c', 'Ğ': 'G', 'ğ': 'g', 'İ': 'I', 'ı': 'i', 'Ö': 'O', 'ö': 'o', 'Ş': 'S', 'ş': 's', 'Ü': 'U', 'ü': 'u'}
        safe_name = name
        for s, r in replacements.items():
            safe_name = safe_name.replace(s, r)
            
        safe_name = safe_name.replace(" ", "_").upper()
        filename = f"{safe_name}_{timestamp}.jpg"
        filepath = FACES_DIR / filename
        
        # Use numpy and cv2.imdecode to safely read/write unicode paths if necessary, 
        # but since we stripped Turkish chars, cv2.imwrite is fine.
        cv2.imwrite(str(filepath), face_roi)
        
        # Modeli yeniden egit
        self.train_model()
        
        return f"Yüz başarıyla '{name}' olarak biyometrik veritabanına eklendi."

    def recognize_in_frame(self, frame_bgr: np.ndarray):
        """Karedeki yuzleri bulur, isimleri ve koordinatlari dondurur."""
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 40))
        
        results = []
        for (x, y, w, h) in faces:
            name = "BILINMEYEN"
            confidence = 100.0
            
            if self.is_trained:
                face_roi = gray[y:y+h, x:x+w]
                try:
                    label_id, conf = self.recognizer.predict(face_roi)
                    # LBPH'de conf (distance) 0'a ne kadar yakinsa o kadar iyidir. 
                    # 50-70 arasi genelde iyi bir eslesmedir.
                    if conf < 85: 
                        name = self.label_map.get(label_id, "BILINMEYEN")
                        confidence = conf
                except Exception as e:
                    print(f"[Biometrics] Predict error: {e}")
                    pass
            
            results.append({
                "box": (x, y, w, h),
                "name": name,
                "confidence": confidence
            })
            
        return results

# Singleton instance
biometric_engine = FaceBiometrics()

def register_biometric_face(name: str, current_frame) -> str:
    if current_frame is None:
        return "Kamera açık değil veya son kare alınamadı."
    return biometric_engine.register_face(name, current_frame)

def get_faces(frame_bgr):
    return biometric_engine.recognize_in_frame(frame_bgr)
