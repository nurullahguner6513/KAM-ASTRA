import math
from PIL import Image, ImageDraw

def rotate_y(x, y, z, angle):
    s = math.sin(angle)
    c = math.cos(angle)
    return (x * c - z * s, y, x * s + z * c)

def project(x, y, z, w, h):
    # Perspective projection
    scale = 110
    z_offset = 150
    factor = scale / (z + z_offset)
    px = x * factor + w / 2
    py = y * factor + h / 2
    return px, py

width, height = 80, 110
rings = []

# Generate Head (Sphere-like)
for v_step in range(1, 10):
    v = v_step * math.pi / 10
    r = 14 * math.sin(v)
    y = -70 + 14 * math.cos(v)
    circle = []
    for u_step in range(16):
        u = u_step * 2 * math.pi / 16
        x = r * math.cos(u)
        z = r * math.sin(u)
        circle.append((x, y, z))
    rings.append(circle)
    
# Generate Torso (Tapered cylinder, flattened in Z)
for v_step in range(16):
    y = -50 + v_step * 3.5
    # Smooth taper for a heroic silhouette
    if v_step < 4: r = 24 - v_step * 0.5 # broad shoulders
    elif v_step < 10: r = 22 - (v_step-4) # waist
    else: r = 16 + (v_step-10) * 1.5 # hips
    circle = []
    for u_step in range(16):
        u = u_step * 2 * math.pi / 16
        x = r * math.cos(u)
        z = r * math.sin(u) * 0.55 # flattened torso depth
        circle.append((x, y, z))
    rings.append(circle)
    
# Generate Arms
for side in [-1, 1]:
    for v_step in range(14):
        y = -45 + v_step * 4
        r = 4.5
        circle = []
        for u_step in range(8):
            u = u_step * 2 * math.pi / 8
            # Arms hanging down slightly outward
            x = side * (26 + v_step * 0.3) + r * math.cos(u)
            z = r * math.sin(u)
            circle.append((x, y, z))
        rings.append(circle)

# Generate Legs
for side in [-1, 1]:
    for v_step in range(16):
        y = 6 + v_step * 4.5
        r = 6 - v_step * 0.15 # tapering down to ankles
        circle = []
        for u_step in range(8):
            u = u_step * 2 * math.pi / 8
            x = side * 10 + r * math.cos(u)
            z = r * math.sin(u)
            circle.append((x, y, z))
        rings.append(circle)

frames = []
num_frames = 45 # Smooth animation

for f in range(num_frames):
    img = Image.new("RGBA", (width, height), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    angle = f * (2 * math.pi / num_frames)
    
    # Scanner beam sweeping up and down
    # math.sin goes from -1 to 1. Map to head (-80) to feet (80)
    scan_y = math.sin(f * (2 * math.pi / num_frames)) * 80
    
    for circle in rings:
        proj_circle = []
        for (x, y, z) in circle:
            rx, ry, rz = rotate_y(x, y, z, angle)
            px, py = project(rx, ry, rz, width, height)
            proj_circle.append((px, py, ry))
            
        # Draw horizontal wireframe loops
        for i in range(len(proj_circle)):
            p1 = proj_circle[i]
            p2 = proj_circle[(i+1)%len(proj_circle)]
            
            # Distance from the scanning laser beam
            dist = abs(p1[2] - scan_y)
            
            if dist < 4:
                # Laser hit! Bright white-cyan, thicker
                col = (180, 255, 255, 255)
                w = 2
            elif dist < 12:
                # Laser glow radius
                col = (0, 255, 200, 180)
                w = 1
            else:
                # Dark holographic background wireframe
                col = (0, 150, 120, 60)
                w = 1
                
            draw.line([p1[:2], p2[:2]], fill=col, width=w)
            
        # Optional: draw vertical connecting lines for a full mesh effect
        # omitted for cleaner "MRI slice" look
            
    # Draw the actual laser plane as a glowing horizontal line across the bounds
    laser_py = project(0, scan_y, 0, width, height)[1]
    draw.line([20, laser_py, width-20, laser_py], fill=(0, 255, 220, 100), width=1)
            
    frames.append(img)
    
frames[0].save('assets/holo.gif', save_all=True, append_images=frames[1:], duration=40, loop=0, disposal=2)
print("Ultra-realistic wireframe hologram generated!")
