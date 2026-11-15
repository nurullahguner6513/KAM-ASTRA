"""
Donanim kontrolu - Ses ve Parlaklik ayarlama
"""

def get_volume_interface():
    try:
        from pycaw.pycaw import AudioUtilities
        devices = AudioUtilities.GetSpeakers()
        return devices.EndpointVolume
    except Exception as e:
        print(f"[Hardware] Ses arayuzu alinamadi: {e}")
        return None

def control_hardware(action: str, value: int = None) -> str:
    """
    action: 'volume_up', 'volume_down', 'volume_set', 'brightness_up', 'brightness_down', 'brightness_set'
    value: 0-100 (opsiyonel)
    """
    if 'brightness' in action:
        try:
            import screen_brightness_control as sbc
            current = sbc.get_brightness()
            if isinstance(current, list):
                current = current[0]
                
            if action == 'brightness_set':
                val = value if value is not None else 50
                sbc.set_brightness(val)
                return f"Parlaklik %{val} olarak ayarlandi."
            elif action == 'brightness_up':
                val = value if value is not None else 20
                new_val = min(100, current + val)
                sbc.set_brightness(new_val)
                return f"Parlaklik %{new_val} seviyesine yukseltildi."
            elif action == 'brightness_down':
                val = value if value is not None else 20
                new_val = max(0, current - val)
                sbc.set_brightness(new_val)
                return f"Parlaklik %{new_val} seviyesine dusuruldu."
        except Exception as e:
            return f"Parlaklik ayarlanirken hata: {e}"

    elif 'volume' in action:
        try:
            volume_obj = get_volume_interface()
            if not volume_obj:
                return "Ses kontrol arayuzune ulasilamadi."
                
            current_scalar = volume_obj.GetMasterVolumeLevelScalar()
            current_pct = int(round(current_scalar * 100))
            
            if action == 'volume_set':
                val = value if value is not None else 50
                val = max(0, min(100, val))
                volume_obj.SetMasterVolumeLevelScalar(val / 100.0, None)
                return f"Ses seviyesi %{val} olarak ayarlandi."
            elif action == 'volume_up':
                val = value if value is not None else 20
                new_pct = min(100, current_pct + val)
                volume_obj.SetMasterVolumeLevelScalar(new_pct / 100.0, None)
                return f"Ses %{new_pct} seviyesine yukseltildi."
            elif action == 'volume_down':
                val = value if value is not None else 20
                new_pct = max(0, current_pct - val)
                volume_obj.SetMasterVolumeLevelScalar(new_pct / 100.0, None)
                return f"Ses %{new_pct} seviyesine dusuruldu."
        except Exception as e:
            return f"Ses ayarlanirken hata: {e}"

    return f"Bilinmeyen donanim eylemi: {action}"
