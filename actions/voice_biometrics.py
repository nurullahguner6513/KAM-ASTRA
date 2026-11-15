import os
import pickle
import numpy as np
import warnings
from pathlib import Path

VOICE_DIR = Path(__file__).resolve().parent.parent / "memory" / "voices"
VOICE_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PATH = VOICE_DIR / "voice_model.pkl"

class VoiceBiometrics:
    def __init__(self):
        self.models = {}
        self.is_trained = False
        self.load_models()
        self.enrolling_user = None
        self.enroll_buffer = []
        self.enroll_required_frames = 60 # 60 frames * 1024 / 16000 ~= 3.84 seconds
        self.last_predicted = "Bilinmeyen"

    def load_models(self):
        if MODEL_PATH.exists():
            try:
                with open(MODEL_PATH, "rb") as f:
                    self.models = pickle.load(f)
                if self.models:
                    self.is_trained = True
                print(f"[VoiceBiometrics] Yüklü ses modelleri: {list(self.models.keys())}")
            except Exception as e:
                print(f"[VoiceBiometrics] Modeller yuklenemedi: {e}")

    def save_models(self):
        try:
            with open(MODEL_PATH, "wb") as f:
                pickle.dump(self.models, f)
            self.is_trained = True
        except Exception as e:
            print(f"[VoiceBiometrics] Modeller kaydedilemedi: {e}")

    def extract_features(self, y, sr):
        import librosa
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
        delta = librosa.feature.delta(mfcc)
        features = np.vstack([mfcc, delta]).T
        return features

    def start_enrollment(self, username: str) -> str:
        self.enrolling_user = username
        self.enroll_buffer = []
        return f"'{username}' için ses kaydı başlatıldı. Lütfen 4 saniye boyunca normal bir şekilde konuşun..."

    def process_enrollment_chunk(self, chunk_bytes):
        self.enroll_buffer.append(chunk_bytes)
        if len(self.enroll_buffer) >= self.enroll_required_frames:
            user = self.enrolling_user
            self.enrolling_user = None
            audio_data = b"".join(self.enroll_buffer)
            self.enroll_buffer = []
            
            try:
                import librosa
                from sklearn.mixture import GaussianMixture
                audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
                audio_np, _ = librosa.effects.trim(audio_np, top_db=30)
                
                if len(audio_np) < 16000:
                    print(f"[VoiceBiometrics] '{user}' için yeterli ses alınamadı (Çok sessiz). Lütfen tekrar deneyin.")
                    return
                    
                features = self.extract_features(audio_np, 16000)
                gmm = GaussianMixture(n_components=16, covariance_type='diag', n_init=3)
                gmm.fit(features)
                
                self.models[user] = gmm
                self.save_models()
                print(f"[VoiceBiometrics] '{user}' sesi başarıyla kaydedildi ve GMM modeli eğitildi!")
            except Exception as e:
                print(f"[VoiceBiometrics] Eğitim hatası: {e}")

    def predict_speaker(self, audio_bytes, sr=16000) -> str:
        if not self.is_trained or not self.models:
            return ""
            
        try:
            import librosa
            audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            audio_np, _ = librosa.effects.trim(audio_np, top_db=30)
            
            if len(audio_np) < sr * 0.5:
                return ""
                
            features = self.extract_features(audio_np, sr)
            
            best_score = -999999
            best_speaker = "Bilinmeyen"
            
            for user, gmm in self.models.items():
                score = np.mean(gmm.score_samples(features))
                if score > best_score:
                    best_score = score
                    best_speaker = user
                    
            if best_score < -45: # Threshold ayarı
                best_speaker = "Bilinmeyen"
                
            self.last_predicted = best_speaker
            return best_speaker
        except Exception as e:
            return ""

voice_engine = VoiceBiometrics()

def register_voice(name: str) -> str:
    return voice_engine.start_enrollment(name)
