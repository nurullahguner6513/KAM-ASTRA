import tkinter as tk
root=tk.Tk()
frames=[]
try:
    idx=0
    while True:
        frames.append(tk.PhotoImage(file='assets/holo.gif', format=f'gif -index {idx}'))
        idx+=1
except tk.TclError:
    pass
print(f'Loaded {len(frames)} frames.')
