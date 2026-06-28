import os
import math
from PIL import Image, ImageDraw

def create_futuristic_banner():
    # 1200x500 HD Banner
    width, height = 1200, 500
    image = Image.new("RGBA", (width, height), "#0B0B0E")
    draw = ImageDraw.Draw(image)
    
    # Draw soft radial background glows
    for r in range(450, 0, -15):
        opacity = int((1.0 - (r / 450.0)) * 22) # 0 to 22
        # Soft blue/teal central glow
        draw.ellipse([600 - r, 250 - r, 600 + r, 250 + r], fill=(0, 170, 230, opacity))
        # Soft green offset glow
        draw.ellipse([700 - r, 250 - r, 700 + r, 250 + r], fill=(0, 240, 120, opacity // 2))
        
    # Draw futuristic grid lines
    grid_color = (60, 60, 80, 35) # Very dim grey-blue with opacity
    for x in range(0, width, 40):
        draw.line([x, 0, x, height], fill=grid_color, width=1)
    for y in range(0, height, 40):
        draw.line([0, y, width, y], fill=grid_color, width=1)
        
    # Draw orbital vector rings
    ring_color = (0, 230, 255, 20)
    draw.ellipse([600 - 180, 250 - 180, 600 + 180, 250 + 180], outline=ring_color, width=2)
    draw.ellipse([600 - 240, 250 - 240, 600 + 240, 250 + 240], outline=ring_color, width=1)
    
    # Draw state-machine connection nodes (representing PocketFlow wiring map!)
    nodes = []
    # Generate 16 orbital coordinates representing state-machine nodes
    for i in range(16):
        angle = i * (2 * math.pi / 16)
        r = 180 + (40 if i % 2 == 0 else -40)
        nx = int(600 + r * math.cos(angle))
        ny = int(250 + r * math.sin(angle))
        nodes.append((nx, ny))
        
    # Connect nodes with thin, glowing cybernetic lines
    for i, p1 in enumerate(nodes):
        for j, p2 in enumerate(nodes):
            if i != j and abs(i - j) in (1, 2, 4):
                dist = math.dist(p1, p2)
                op = int(max(0, 255 - dist * 0.35))
                # Soft blue-green connector lines
                col = (0, int(160 + op * 0.35), int(220 + op * 0.15), int(op * 0.35))
                draw.line([p1[0], p1[1], p2[0], p2[1]], fill=col, width=1)
                
    # Draw glowing dots representing state nodes
    for nx, ny in nodes:
        draw.ellipse([nx - 5, ny - 5, nx + 5, ny + 5], fill=(0, 255, 150, 180))
        draw.ellipse([nx - 9, ny - 9, nx + 9, ny + 9], outline=(0, 255, 150, 40), width=2)
        
    # Draw majestic glowing big 'π' (pi) symbol right in the center!
    # Symmetrical pillars holding a double-sided overhang roof
    # Roof: x from 520 to 680, y from 120 to 144
    # Left pillar: x from 555 to 575, y from 144 to 344
    # Right pillar: x from 625 to 645, y from 144 to 344
    pi_color = (0, 255, 180, 240)    # Teal glow
    pi_shadow = (0, 255, 180, 25)
    
    # Draw soft outer glow aura under pi
    for offset in range(12, 0, -2):
        draw.rectangle([520 - offset, 120 - offset, 680 + offset, 144 + offset], fill=pi_shadow, width=0)
        draw.rectangle([555 - offset, 144 - offset, 575 + offset, 344 + offset], fill=pi_shadow, width=0)
        draw.rectangle([625 - offset, 144 - offset, 645 + offset, 344 + offset], fill=pi_shadow, width=0)
        
    # Draw solid pi letter
    draw.rectangle([520, 120, 680, 144], fill=pi_color, width=0) # Roof (matching double overhang)
    draw.rectangle([555, 144, 575, 344], fill=pi_color, width=0) # Left pillar (tighter column)
    draw.rectangle([625, 144, 645, 344], fill=pi_color, width=0) # Right pillar
    
    # Draw cybernetic horizontal flow streams underneath
    draw.line([350, 400, 850, 400], fill=(0, 255, 150, 120), width=2)
    draw.line([480, 410, 720, 410], fill=(0, 180, 255, 120), width=1)
    
    # Save the artwork
    image.save("README_banner.png", "PNG")
    print("🎉 Beautiful POCKET-π futuristic banner generated successfully as README_banner.png!")

if __name__ == "__main__":
    create_futuristic_banner()
