import zlib
import struct
import math
import os

def write_png(filename, width, height, rgba_data):
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    
    header = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
    
    raw_lines = []
    for y in range(height):
        raw_lines.append(b'\x00' + rgba_data[y * width * 4 : (y + 1) * width * 4])
    
    idat = chunk(b'IDAT', zlib.compress(b''.join(raw_lines), 9))
    iend = chunk(b'IEND', b'')
    
    with open(filename, 'wb') as f:
        f.write(header + ihdr + idat + iend)

def create_icon(size, out_path):
    pixels = bytearray(size * size * 4)
    scale = size / 48.0
    
    # Precompute logo geometry
    # Token background: rounded rect at (2, 2) to (46, 46), rx=10
    corner_r = 11.0 * scale
    
    def dist_rounded_box(x, y, bx, by, bw, bh, r):
        # centered box
        cx = bx + bw / 2.0
        cy = by + bh / 2.0
        dx = abs(x - cx) - (bw / 2.0 - r)
        dy = abs(y - cy) - (bh / 2.0 - r)
        return math.hypot(max(0, dx), max(0, dy)) + min(0, max(dx, dy)) - r

    def dist_capsule(x, y, x1, y1, x2, y2, r):
        l2 = (x2 - x1)**2 + (y2 - y1)**2
        if l2 == 0:
            return math.hypot(x - x1, y - y1) - r
        t = max(0, min(1, ((x - x1) * (x2 - x1) + (y - y1) * (y2 - y1)) / l2))
        proj_x = x1 + t * (x2 - x1)
        proj_y = y1 + t * (y2 - y1)
        return math.hypot(x - proj_x, y - proj_y) - r

    def dist_spark(x, y, cx, cy, rx, ry):
        # 4 pointed star distance
        dx = abs(x - cx) / rx
        dy = abs(y - cy) / ry
        if dx + dy == 0:
            return -1.0
        # approximate distance to astroid/star shape
        # boundary is (dx^0.5 + dy^0.5) = 1
        d = (dx**0.5 + dy**0.5) - 1.0
        return d * min(rx, ry)

    for py in range(size):
        for px in range(size):
            sx = px / scale
            sy = py / scale
            
            # Base background: dark rounded token
            d_box = dist_rounded_box(px, py, 1.5 * scale, 1.5 * scale, 45.0 * scale, 45.0 * scale, corner_r)
            
            if d_box > 1.5:
                # Transparent outside token
                alpha = 0
                r, g, b = 0, 0, 0
            else:
                # Inside or border of token
                aa = max(0.0, min(1.0, 0.5 - d_box))
                
                # Dark navy background
                r = int(10 * aa)
                g = int(17 * aa)
                b = int(30 * aa)
                alpha = int(255 * aa)
                
                # Border glow ring
                d_ring = abs(d_box + 0.8 * scale) - 0.75 * scale
                if d_ring < 1.0:
                    ring_aa = max(0.0, min(1.0, 0.5 - d_ring)) * 0.4
                    # gradient from cyan to emerald
                    t_grad = (px + py) / (2.0 * size)
                    gr_r = 6 + int(t_grad * 10)
                    gr_g = 182 + int(t_grad * 3)
                    gr_b = 212 - int(t_grad * 83)
                    r = int(r * (1 - ring_aa) + gr_r * ring_aa)
                    g = int(g * (1 - ring_aa) + gr_g * ring_aa)
                    b = int(b * (1 - ring_aa) + gr_b * ring_aa)
                
                # Rupee Symbol geometry:
                # Top bar: (13, 14) to (29, 14), width 4 (r = 2)
                d1 = dist_capsule(sx, sy, 13, 14, 29, 14, 2.0)
                # Mid bar: (13, 20.5) to (26, 20.5), width 4 (r = 2)
                d2 = dist_capsule(sx, sy, 13, 20.5, 26, 20.5, 2.0)
                # Stem: (19, 14) to (19, 27), width 4 (r = 2)
                d3 = dist_capsule(sx, sy, 19, 14, 19, 27, 2.0)
                # Bowl arc: circle center (19, 17.25), radius 3.5, width 4
                # only for x >= 19 and 14 <= y <= 20.5
                d_bowl_arc = 999.0
                if sx >= 18.5 and 13.0 <= sy <= 21.5:
                    d_bowl_arc = abs(math.hypot(sx - 19.0, sy - 17.25) - 3.25) - 2.0
                
                # Diagonal leg: (19.5, 26.5) to (30, 38), width 4.5 (r = 2.25)
                d4 = dist_capsule(sx, sy, 19.5, 26.5, 30.5, 38, 2.25)
                
                d_rupee = min(d1, d2, d3, d_bowl_arc, d4) * scale
                
                if d_rupee < 1.0:
                    rupee_aa = max(0.0, min(1.0, 0.5 - d_rupee))
                    # Gradient cyan to emerald to blue
                    t = (sy - 12) / 26.0
                    t = max(0.0, min(1.0, t))
                    if t < 0.5:
                        f = t / 0.5
                        lr = int(6 + f * (16 - 6))
                        lg = int(182 + f * (185 - 182))
                        lb = int(212 + f * (129 - 212))
                    else:
                        f = (t - 0.5) / 0.5
                        lr = int(16 + f * (59 - 16))
                        lg = int(185 + f * (130 - 185))
                        lb = int(129 + f * (246 - 129))
                    
                    r = int(r * (1 - rupee_aa) + lr * rupee_aa)
                    g = int(g * (1 - rupee_aa) + lg * rupee_aa)
                    b = int(b * (1 - rupee_aa) + lb * rupee_aa)
                
                # AI Spark geometry at (37, 10):
                # Central spark diamond
                # distance to diamond: |x-37|/6 + |y-10|/6 - 1
                dx_sp = abs(sx - 37.0)
                dy_sp = abs(sy - 10.0)
                d_spark = (math.pow(dx_sp / 6.0, 0.6) + math.pow(dy_sp / 6.0, 0.6) - 1.0) * 4.0 * scale
                
                if d_spark < 1.0:
                    spark_aa = max(0.0, min(1.0, 0.5 - d_spark))
                    # Spark glow cyan-white
                    d_center = math.hypot(sx - 37.0, sy - 10.0)
                    if d_center < 1.5:
                        sr, sg, sb = 255, 255, 255
                    else:
                        sr, sg, sb = 34, 211, 238
                    
                    r = int(r * (1 - spark_aa) + sr * spark_aa)
                    g = int(g * (1 - spark_aa) + sg * spark_aa)
                    b = int(b * (1 - spark_aa) + sb * spark_aa)

            idx = (py * size + px) * 4
            pixels[idx]     = max(0, min(255, r))
            pixels[idx + 1] = max(0, min(255, g))
            pixels[idx + 2] = max(0, min(255, b))
            pixels[idx + 3] = max(0, min(255, alpha))

    write_png(out_path, size, size, bytes(pixels))
    print(f"Generated {out_path} ({size}x{size}) successfully!")

if __name__ == "__main__":
    os.makedirs("frontend", exist_ok=True)
    create_icon(192, "frontend/icon-192.png")
    create_icon(512, "frontend/icon-512.png")
