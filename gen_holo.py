import math
import random
from PIL import Image, ImageDraw

def rotate_y(p, angle):
    x, y, z = p
    s = math.sin(angle)
    c = math.cos(angle)
    return (x * c - z * s, y, x * s + z * c)

def project(p, width, height, scale, z_offset):
    x, y, z = p
    factor = scale / (z + z_offset)
    x_proj = x * factor + width / 2
    y_proj = y * factor + height / 2
    return (x_proj, y_proj)

points = []

def add_cylinder(x_off, y_start, y_end, r_start, r_end, density=100):
    for _ in range(density):
        t = random.random()
        y = y_start + t * (y_end - y_start)
        r = r_start + t * (r_end - r_start)
        angle = random.uniform(0, 2 * math.pi)
        px = r * math.cos(angle) + x_off
        pz = r * math.sin(angle)
        points.append((px, y, pz))

def add_sphere(x_off, y_off, r, density=100):
    for _ in range(density):
        u = random.uniform(0, 2 * math.pi)
        v = random.uniform(0, math.pi)
        px = r * math.sin(v) * math.cos(u) + x_off
        py = r * math.sin(v) * math.sin(u) + y_off
        pz = r * math.cos(v)
        points.append((px, py, pz))

# Head
add_sphere(0, -60, 15, 200)
# Neck
add_cylinder(0, -45, -35, 5, 6, 50)
# Torso
add_cylinder(0, -35, 10, 20, 15, 400)
# Left Arm
add_cylinder(-28, -30, 20, 6, 4, 150)
# Right Arm
add_cylinder(28, -30, 20, 6, 4, 150)
# Left Leg
add_cylinder(-10, 10, 70, 7, 5, 200)
# Right Leg
add_cylinder(10, 10, 70, 7, 5, 200)

frames = []
width, height = 150, 200
for i in range(30):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    angle = i * (2 * math.pi / 30)
    
    rotated = [rotate_y(p, angle) for p in points]
    projected = [project(p, width, height, scale=400, z_offset=150) for p in rotated]
    
    # Sort by Z depth so back points are drawn first (or just draw all)
    # Actually, they are dots so order doesn't matter much.
    
    for x, y in projected:
        # Sci-fi green/cyan dots
        draw.rectangle([x-0.5, y-0.5, x+1, y+1], fill=(0, 255, 200, 200))
        
    frames.append(img)

frames[0].save('assets/holo.gif', save_all=True, append_images=frames[1:], duration=50, loop=0, disposal=2)
print("Hologram generated with", len(points), "points!")
