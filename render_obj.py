import math
from PIL import Image, ImageDraw

def rotate_y(x, y, z, angle):
    s = math.sin(angle)
    c = math.cos(angle)
    return (x * c - z * s, y, x * s + z * c)

def project(x, y, z, w, h):
    scale = 450
    z_offset = 50
    factor = scale / (z + z_offset)
    px = x * factor + w / 2
    py = -y * factor + h / 2  # invert Y for image coordinates
    return px, py

width, height = 130, 180

print("Loading OBJ...")
verts = []
with open('assets/FinalBaseMesh.obj', 'r', encoding='utf-8') as f:
    for line in f:
        if line.startswith('v '):
            parts = line.split()
            x = float(parts[1])
            y = float(parts[2]) - 10.34  # center Y roughly around 0
            z = float(parts[3])
            verts.append((x, y, z))

print(f"Loaded {len(verts)} vertices. Rendering frames...")

frames = []
num_frames = 45

for f in range(num_frames):
    img = Image.new("RGBA", (width, height), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    angle = f * (2 * math.pi / num_frames)
    
    # Scanner from top (y=11) to bottom (y=-11)
    scan_y = math.sin(f * (2 * math.pi / num_frames)) * 11
    
    # Pre-calculate colors to avoid repeated tuple creation
    c_bright = (180, 255, 255, 255)
    c_mid = (0, 255, 200, 200)
    c_dim = (0, 150, 120, 80)
    
    # Collect all projected points first so we can Z-sort them for maximum sharpness
    projected_points = []
    
    for (x, y, z) in verts:
        rx, ry, rz = rotate_y(x, y, z, angle)
        px, py = project(rx, ry, rz, width, height)
        
        if px < 0 or px >= width or py < 0 or py >= height:
            continue
            
        dist = abs(ry - scan_y)
        if dist < 0.4:
            col = c_bright
        elif dist < 1.8:
            col = c_mid
        else:
            col = c_dim
            
        projected_points.append((px, py, rz, col))
        
    # Sort by Z (depth). Draw points further away first, closer points last.
    # Assuming lower Z is further away (depends on rotation, but normally yes)
    projected_points.sort(key=lambda p: p[2])
    
    for px, py, rz, col in projected_points:
        draw.point((px, py), fill=col)

    # laser plane line
    laser_py = project(0, scan_y, 0, width, height)[1]
    if 0 <= laser_py < height:
        draw.line([2, laser_py, width-2, laser_py], fill=(0, 255, 220, 180), width=1)
        
    frames.append(img)
    if f % 10 == 0:
        print(f"Rendered frame {f}/{num_frames}")
    
print("Saving PNG frames...")
for i, frame in enumerate(frames):
    frame.save(f'assets/holo_frames/frame_{i}.png')
print("Done!")
