#!/usr/bin/env python3
"""The picture that tastes of one ingredient.

A pure-stdlib (struct + zlib + math + random) program that paints one
delicious picture: a big golden honeycomb slab, glossy with fresh honey,
a wooden honey dipper resting across it, a slow drip falling into a
glistening pool of honey on a warm wooden board.

No network, no third-party packages. Writes /output/entry.png
(1024x1024 RGB PNG, well under the 1 MiB cap).

Run:  python3 main.py
"""

import math
import os
import random
import struct
import zlib

W = 1024
H = 1024
OUT = os.environ.get("OUTPUT_PATH", "/output/entry.png")

rng = random.Random(20261122)  # deterministic: same picture every run

# ---------------------------------------------------------------- framebuffer

px = bytearray(W * H * 3)


def _idx(x, y):
    return (y * W + x) * 3


def put(x, y, r, g, b):
    if 0 <= x < W and 0 <= y < H:
        i = _idx(x, y)
        px[i] = r
        px[i + 1] = g
        px[i + 2] = b


def blend(x, y, r, g, b, a):
    """Blend colour (r,g,b) over the pixel at (x,y) with alpha a in [0,1]."""
    if not (0 <= x < W and 0 <= y < H) or a <= 0.0:
        return
    if a >= 1.0:
        put(x, y, int(r), int(g), int(b))
        return
    i = _idx(x, y)
    px[i] = int(px[i] * (1.0 - a) + r * a)
    px[i + 1] = int(px[i + 1] * (1.0 - a) + g * a)
    px[i + 2] = int(px[i + 2] * (1.0 - a) + b * a)


def clamp(v, lo=0.0, hi=255.0):
    return lo if v < lo else hi if v > hi else v


def smoothstep(a, b, t):
    t = (t - a) / (b - a) if b != a else 0.0
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
    return t * t * (3.0 - 2.0 * t)


def mix(c1, c2, t):
    return (c1[0] + (c2[0] - c1[0]) * t,
            c1[1] + (c2[1] - c1[1]) * t,
            c1[2] + (c2[2] - c1[2]) * t)


# ---------------------------------------------------------------- shapes

def disc(cx, cy, r, colour, alpha=1.0, soft=0.0):
    """Filled disc; soft>0 feather the rim over that many pixels."""
    r0 = int(max(0.0, r - soft))
    r1 = int(r + soft) + 1
    x0 = max(0, int(cx - r1))
    x1 = min(W - 1, int(cx + r1))
    y0 = max(0, int(cy - r1))
    y1 = min(H - 1, int(cy + r1))
    rr = r * r
    for y in range(y0, y1 + 1):
        dy = y - cy
        for x in range(x0, x1 + 1):
            dx = x - cx
            d2 = dx * dx + dy * dy
            if d2 <= rr:
                if soft > 0.0:
                    d = math.sqrt(d2)
                    a = alpha * (1.0 - smoothstep(r - soft, r, d))
                else:
                    a = alpha
                blend(x, y, colour[0], colour[1], colour[2], a)


def ellipse(cx, cy, rx, ry, colour, alpha=1.0, soft=0.0):
    x0 = max(0, int(cx - rx - soft - 1))
    x1 = min(W - 1, int(cx + rx + soft + 1))
    y0 = max(0, int(cy - ry - soft - 1))
    y1 = min(H - 1, int(cy + ry + soft + 1))
    for y in range(y0, y1 + 1):
        ny = (y - cy) / ry
        for x in range(x0, x1 + 1):
            nx = (x - cx) / rx
            d = nx * nx + ny * ny
            if d <= 1.0:
                if soft > 0.0:
                    a = alpha * (1.0 - smoothstep(1.0 - soft / max(rx, ry), 1.0,
                                                  math.sqrt(d)))
                else:
                    a = alpha
                blend(x, y, colour[0], colour[1], colour[2], a)


def ellipse_radial(cx, cy, rx, ry, centre_col, edge_col, alpha=1.0):
    """Ellipse shaded by a radial gradient (bright centre -> edge colour)."""
    x0 = max(0, int(cx - rx - 1))
    x1 = min(W - 1, int(cx + rx + 1))
    y0 = max(0, int(cy - ry - 1))
    y1 = min(H - 1, int(cy + ry + 1))
    for y in range(y0, y1 + 1):
        ny = (y - cy) / ry
        for x in range(x0, x1 + 1):
            nx = (x - cx) / rx
            d = nx * nx + ny * ny
            if d <= 1.0:
                t = math.sqrt(d)
                c = mix(centre_col, edge_col, t)
                blend(x, y, c[0], c[1], c[2], alpha)


def poly(points, colour, alpha=1.0):
    """Scanline fill of a simple polygon."""
    if len(points) < 3:
        return
    ys = [p[1] for p in points]
    y0 = max(0, int(min(ys)))
    y1 = min(H - 1, int(max(ys)) + 1)
    n = len(points)
    for y in range(y0, y1 + 1):
        xs = []
        for i in range(n):
            x1, y1p = points[i]
            x2, y2p = points[(i + 1) % n]
            if (y1p <= y < y2p) or (y2p <= y < y1p):
                t = (y - y1p) / (y2p - y1p)
                xs.append(x1 + t * (x2 - x1))
        xs.sort()
        for k in range(0, len(xs) - 1, 2):
            xa = max(0, int(math.ceil(xs[k])))
            xb = min(W - 1, int(math.floor(xs[k + 1])))
            for x in range(xa, xb + 1):
                blend(x, y, colour[0], colour[1], colour[2], alpha)


def poly_outline(points, colour, width=2, alpha=1.0):
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        line(x1, y1, x2, y2, colour, width, alpha)


def line(x1, y1, x2, y2, colour, width=2, alpha=1.0):
    length = math.hypot(x2 - x1, y2 - y1)
    steps = max(1, int(length))
    r = width / 2.0
    for s in range(steps + 1):
        t = s / steps
        disc(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, r, colour, alpha)


def rot(px_, py_, cx, cy, ang):
    c, s = math.cos(ang), math.sin(ang)
    dx, dy = px_ - cx, py_ - cy
    return (cx + dx * c - dy * s, cy + dx * s + dy * c)


def hex_points(cx, cy, r, angle_offset=0.0):
    return [(cx + r * math.cos(angle_offset + i * math.pi / 3.0),
             cy + r * math.sin(angle_offset + i * math.pi / 3.0))
            for i in range(6)]


def point_in_poly(x, y, points):
    inside = False
    n = len(points)
    j = n - 1
    for i in range(n):
        xi, yi = points[i]
        xj, yj = points[j]
        if ((yi > y) != (yj > y)) and \
                (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


# ---------------------------------------------------------------- background

def paint_background():
    # Warm dark backdrop: vertical falloff + a golden glow behind the food.
    gx, gy = 512.0, 470.0
    for y in range(H):
        # vertical base: deep espresso brown, lighter near the glow band
        t = y / (H - 1.0)
        base = mix((46, 24, 10), (16, 8, 4), t)
        for x in range(W):
            dx = (x - gx) / 620.0
            dy = (y - gy) / 560.0
            d = math.sqrt(dx * dx + dy * dy)
            glow = math.exp(-d * d * 2.6)
            r = base[0] + 96.0 * glow
            g = base[1] + 58.0 * glow
            b = base[2] + 16.0 * glow
            # gentle vignette
            vx = (x - 512.0) / 512.0
            vy = (y - 512.0) / 512.0
            v = 1.0 - 0.22 * (vx * vx + vy * vy)
            put(x, y, int(clamp(r * v)), int(clamp(g * v)), int(clamp(b * v)))


# ---------------------------------------------------------------- wooden board

def paint_board():
    # A rustic round board under the comb, warm wood with grain.
    cx, cy, rx, ry = 512.0, 872.0, 480.0, 168.0
    y0 = max(0, int(cy - ry))
    y1 = min(H - 1, int(cy + ry))
    for y in range(y0, y1 + 1):
        ny = (y - cy) / ry
        half = rx * math.sqrt(max(0.0, 1.0 - ny * ny))
        # wood tone deepens toward the board's lower edge
        t = (y - (cy - ry)) / (2.0 * ry)
        col = mix((122, 74, 34), (74, 42, 18), t)
        # grain: slow sine waves along x
        for x in range(int(cx - half), int(cx + half) + 1):
            g = math.sin(x * 0.021 + y * 0.055 + math.sin(y * 0.02) * 2.0)
            g2 = math.sin(x * 0.006 - y * 0.11)
            shade = 1.0 + 0.07 * g + 0.05 * g2
            # soft rim darkening near the board edge
            edge = smoothstep(0.86, 1.0, abs(x - cx) / max(half, 1.0))
            s = shade * (1.0 - 0.25 * edge)
            blend(x, y, col[0] * s, col[1] * s, col[2] * s, 1.0)
    # soft contact shadow under the board
    ellipse(512, 985, 430, 26, (0, 0, 0), alpha=0.35, soft=18)


# ---------------------------------------------------------------- honeycomb slab

SLAB_CX, SLAB_CY = 512.0, 472.0
SLAB_ANG = -0.10  # slight tilt, radians


def slab_points():
    # A chunky wedge of comb: wide top, slightly narrower base.
    raw = [(-352, -160), (320, -178), (376, -42), (320, 178),
           (-310, 190), (-376, 64), (-372, -84)]
    return [rot(x + SLAB_CX, y + SLAB_CY, SLAB_CX, SLAB_CY, SLAB_ANG)
            for (x, y) in raw]


def paint_comb():
    pts = slab_points()
    # dark crust rim hugging the slab edge
    poly(pts, (96, 52, 10))
    poly_outline(pts, (88, 46, 8), width=16)
    # warm wax face, inset a touch so the crust rim shows
    inner = [rot((x - SLAB_CX) * 0.985 + SLAB_CX,
                 (y - SLAB_CY) * 0.982 + SLAB_CY,
                 SLAB_CX, SLAB_CY, SLAB_ANG) for (x, y) in pts]
    poly(inner, (196, 118, 22))
    # soft light washing down the face from upper left
    ellipse_radial(400, 330, 420, 300, (255, 196, 80), (196, 118, 22),
                   alpha=0.55)

    # hexagonal cells, pointy-top, clipped to the slab
    r = 47.0
    dx = math.sqrt(3.0) * r
    dy = 1.5 * r
    row = 0
    y = SLAB_CY - 160
    while y < SLAB_CY + 185:
        x = SLAB_CX - 352 + (dx / 2.0 if row % 2 else 0.0)
        while x < SLAB_CX + 368:
            if point_in_poly(x, y, pts):
                paint_cell(x, y, r, row)
            x += dx
        y += dy
        row += 1

    # honey drizzle ribbon snaking across the comb
    drizzle()

    # soft shadow the comb casts onto the board, grounding it
    ellipse(512, 706, 350, 26, (0, 0, 0), alpha=0.28, soft=16)


def paint_chunk():
    # A small broken-off piece of comb on the board's right side, so
    # the board is not empty there and the eye finds honey twice.
    cx0, cy0 = 690.0, 812.0
    poly([(cx0 - 118, cy0 - 52), (cx0 + 96, cy0 - 62),
          (cx0 + 128, cy0 + 6), (cx0 + 60, cy0 + 58),
          (cx0 - 96, cy0 + 52), (cx0 - 128, cy0 - 8)],
         (96, 52, 10))
    poly([(cx0 - 110, cy0 - 46), (cx0 + 90, cy0 - 56),
          (cx0 + 118, cy0 + 4), (cx0 + 56, cy0 + 50),
          (cx0 - 88, cy0 + 46), (cx0 - 118, cy0 - 6)],
         (196, 118, 22))
    r = 34.0
    dx = math.sqrt(3.0) * r
    dy = 1.5 * r
    row = 0
    y = cy0 - 44
    chunk_pts = [(cx0 - 110, cy0 - 46), (cx0 + 90, cy0 - 56),
                 (cx0 + 118, cy0 + 4), (cx0 + 56, cy0 + 50),
                 (cx0 - 88, cy0 + 46), (cx0 - 118, cy0 - 6)]
    while y < cy0 + 52:
        x = cx0 - 104 + (dx / 2.0 if row % 2 else 0.0)
        while x < cx0 + 116:
            if point_in_poly(x, y, chunk_pts):
                paint_cell(x, y, r, row)
            x += dx
        y += dy
        row += 1
    # honey oozing from the chunk's edge
    disc(cx0 + 96, cy0 + 34, 9, (240, 150, 20), alpha=1.0)
    disc(cx0 + 108, cy0 + 44, 5, (240, 150, 20), alpha=1.0)


def paint_cell(cx, cy, r, row):
    # cell wall: darker golden ring
    poly(hex_points(cx, cy, r, math.pi / 6.0), (150, 84, 12))
    # honey fill: depth varies by row and by a seeded jitter, so the
    # comb reads organic, not stamped; a few cells hold visibly deeper
    # or paler honey
    depth = 0.5 + 0.5 * ((cy - 300.0) / 340.0)
    jit = rng.uniform(-0.10, 0.10)
    roll = rng.random()
    if roll < 0.16:
        base = mix((226, 128, 14), (176, 84, 6), depth)
    elif roll > 0.86:
        base = mix((255, 204, 90), (244, 168, 48), depth)
    else:
        base = mix((255, 176, 40), (214, 116, 10), clamp(depth + jit, 0.0, 1.0))
    poly(hex_points(cx, cy, r * 0.87, math.pi / 6.0), base)
    # glossy meniscus: brighter honey pooling at the cell's lower half
    inner = hex_points(cx, cy, r * 0.62, math.pi / 6.0)
    poly(inner, mix(base, (255, 214, 110), 0.45), alpha=0.55)
    # a glint where the light catches the honey
    if rng.random() < 0.55:
        gx = cx - r * 0.22 + rng.uniform(-6, 6)
        gy = cy - r * 0.28 + rng.uniform(-5, 5)
        disc(gx, gy, r * 0.10, (255, 240, 190), alpha=0.85, soft=2)
        disc(gx + r * 0.10, gy + r * 0.12, r * 0.05, (255, 244, 210),
             alpha=0.6, soft=1)
    # a few cells hold a tiny bubble in the honey
    if rng.random() < 0.22:
        disc(cx + r * 0.18, cy + r * 0.20, r * 0.07, (255, 228, 160),
             alpha=0.7, soft=1)


def drizzle():
    # A thick ribbon of honey poured in a gentle S across the comb face,
    # with a bright gloss line riding its upper edge. It stays inside
    # the slab so it reads as poured honey, not a stray arc.
    for (y0, amp, phase) in ((392, 26, 0.6), (520, 20, 2.4)):
        path = []
        for t in range(0, 101):
            u = t / 100.0
            x = 215.0 + 590.0 * u
            y = y0 + amp * math.sin(u * math.pi * 1.5 + phase)
            path.append((x, y))
        for i, (x, y) in enumerate(path):
            w = 12.0 + 4.0 * math.sin(i * 0.35)
            disc(x, y, w, (232, 138, 16), alpha=0.95)
        for i, (x, y) in enumerate(path):
            disc(x - 2.0, y - 5.0, 4.5, (255, 214, 110), alpha=0.9)
    # a drip beading off the comb's lower edge
    disc(712, 668, 12, (240, 150, 20), alpha=1.0)
    disc(712, 686, 7, (240, 150, 20), alpha=1.0)


# ---------------------------------------------------------------- honey dipper

def paint_dipper():
    # Handle from the grooved head (resting on the comb, lower left)
    # up to the right, where the hand would hold it.
    hx, hy = 446.0, 566.0
    ang = math.radians(-38.0)  # head->handle direction (up-right)
    ux, uy = math.cos(ang), math.sin(ang)  # along handle
    nx, ny = -uy, ux                        # across handle
    # handle: a long tapered wooden stick
    hlen = 330.0
    hw0, hw1 = 15.0, 11.0
    p1 = (hx + ux * 30 - nx * hw0, hy + uy * 30 - ny * hw0)
    p2 = (hx + ux * 30 + nx * hw0, hy + uy * 30 + ny * hw0)
    p3 = (hx + ux * hlen + nx * hw1, hy + uy * hlen + ny * hw1)
    p4 = (hx + ux * hlen - nx * hw1, hy + uy * hlen - ny * hw1)
    poly([p1, p2, p3, p4], (206, 150, 88))
    # wood grain along the handle
    for off in (-6.0, -1.0, 4.0):
        gx1 = hx + ux * 44 - nx * off
        gy1 = hy + uy * 44 - ny * off
        gx2 = hx + ux * (hlen - 8) - nx * off
        gy2 = hy + uy * (hlen - 8) - ny * off
        line(gx1, gy1, gx2, gy2, (168, 112, 54), width=2, alpha=0.55)
    # warm light on the handle's upper edge
    line(hx + ux * 44 - nx * 9, hy + uy * 44 - ny * 9,
         hx + ux * (hlen - 10) - nx * 9, hy + uy * (hlen - 10) - ny * 9,
         (244, 206, 150), width=3, alpha=0.7)

    # grooved head: a honey-coated capsule stretched along the handle
    # axis (a dipper head is a ridged bulb, not a ball), with soft
    # groove shadows across it so the ridges read.
    ax = hx - ux * 104.0
    ay = hy - uy * 104.0  # far tip of the head
    bx = hx - ux * 8.0
    by = hy - uy * 8.0    # near end, where the handle starts
    hw = 46.0
    poly([(ax - nx * hw, ay - ny * hw), (bx - nx * hw, by - ny * hw),
          (bx + nx * hw, by + ny * hw), (ax + nx * hw, ay + ny * hw)],
         (244, 158, 26))
    disc(ax, ay, hw, (244, 158, 26))
    disc(bx, by, hw, (244, 158, 26))
    # honey sheen along the head's lit side
    for i in range(5):
        t = i / 4.0
        cx = ax + (bx - ax) * t - nx * 16.0
        cy = ay + (by - ay) * t - ny * 16.0
        disc(cx, cy, 20.0 - abs(t - 0.5) * 10.0, (255, 200, 92),
             alpha=0.55, soft=6)
    # strengthened gloss (revision): brighter, larger tip glint plus a
    # second sheen highlight mid-head, so the honey on the dipper reads
    # freshly dipped and glossy.
    disc(ax - 14, ay - 16, 18, (255, 238, 180), alpha=0.92, soft=5)
    disc(ax + (bx - ax) * 0.30 - nx * 18, ay + (by - ay) * 0.30 - ny * 18,
         9, (255, 240, 196), alpha=0.85, soft=3)
    # groove shadows across the capsule
    for d in (30.0, 50.0, 70.0, 88.0):
        cx = hx - ux * d
        cy = hy - uy * d
        line(cx - nx * 42, cy - ny * 42, cx + nx * 42, cy + ny * 42,
             (150, 84, 10), width=4, alpha=0.42)
    # honey beading at the head's lower tip
    disc(ax - 4, ay + 34, 11, (240, 150, 20), alpha=1.0)


# ---------------------------------------------------------------- drip + pool

def paint_drip_and_pool():
    # A slow teardrop of honey falling from the dipper head to the pool.
    tx, ty = 353.0, 706.0
    poly([(tx - 13, ty + 30), (tx - 4, ty - 34), (tx, ty - 52),
          (tx + 4, ty - 34), (tx + 13, ty + 30)], (240, 150, 20))
    disc(tx, ty + 30, 13, (240, 150, 20))
    disc(tx - 4, ty + 6, 4.5, (255, 220, 130), alpha=0.9, soft=1)
    # thin honey thread still joining drip to head
    line(tx, ty - 50, tx + 2, ty - 82, (240, 150, 20), width=5, alpha=0.95)

    # the pool: a glossy ellipse of honey on the board
    px_, py_ = 353.0, 818.0
    ellipse_radial(px_, py_, 132, 40, (255, 190, 70), (196, 104, 8),
                   alpha=1.0)
    # ripple ring where the drip is about to land
    for rr, aa in ((96, 0.5), (74, 0.4)):
        cx0, cy0 = px_, py_
        steps = 90
        for s in range(steps + 1):
            a = 2.0 * math.pi * s / steps
            disc(cx0 + rr * math.cos(a), cy0 + rr * 0.32 * math.sin(a),
                 2.0, (255, 214, 120), alpha=aa)
    # bright specular streak across the pool
    ellipse(px_ - 18, py_ - 10, 52, 9, (255, 238, 180), alpha=0.85, soft=6)
    ellipse(px_ + 34, py_ + 8, 26, 5, (255, 228, 150), alpha=0.6, soft=4)
    # a couple of small honey drops scattered on the board
    for (dx_, dy_, rr_) in ((560, 780, 9), (250, 800, 7), (520, 856, 6)):
        disc(dx_, dy_, rr_, (240, 150, 20))
        disc(dx_ - 2, dy_ - 2, rr_ * 0.35, (255, 224, 150), alpha=0.85)


# ---------------------------------------------------------------- finish

def paint_vignette_and_speckle():
    # Final gentle vignette so the food stays the brightest thing.
    for y in range(H):
        vy = (y - 512.0) / 512.0
        for x in range(W):
            vx = (x - 512.0) / 512.0
            d = vx * vx + vy * vy
            if d > 0.55:
                a = 0.20 * smoothstep(0.55, 1.15, d)
                blend(x, y, 8, 4, 2, a)
    # faint warm speckle on the comb face for texture
    for _ in range(2600):
        x = rng.uniform(190, 840)
        y = rng.uniform(300, 640)
        if point_in_poly(x, y, slab_points()):
            blend(int(x), int(y), 255, 210, 120, rng.uniform(0.05, 0.22))


def write_png(path):
    def chunk(kind, data):
        c = struct.pack(">I", len(data)) + kind + data
        c += struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        return c

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    raw = bytearray()
    for y in range(H):
        raw.append(0)  # filter: none
        raw += px[y * W * 3:(y + 1) * W * 3]
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", ihdr)
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


def main():
    paint_background()
    paint_board()
    paint_comb()
    paint_dipper()
    paint_chunk()
    paint_drip_and_pool()
    paint_vignette_and_speckle()
    n = write_png(OUT)
    print(f"wrote {OUT}: {W}x{H}, {n} bytes")


if __name__ == "__main__":
    main()
