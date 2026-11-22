"""把 PNG 解码成 ASCII 点阵（只为看清图标轮廓，不产出任何素材）。

用法：python build/_png_probe.py <png> [宽度字符数]
只支持 8 位、非隔行、color type 0/2/3/4/6，够用。
"""
import sys
import zlib
import struct


def paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def decode(path):
    raw = open(path, "rb").read()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    i = 8
    idat = b""
    w = h = bd = ct = 0
    plte = None
    trns = None
    while i < len(raw):
        ln = struct.unpack(">I", raw[i:i + 4])[0]
        typ = raw[i + 4:i + 8]
        body = raw[i + 8:i + 8 + ln]
        i += 12 + ln
        if typ == b"IHDR":
            w, h, bd, ct, comp, filt, inter = struct.unpack(">IIBBBBB", body)
            assert bd == 8 and inter == 0, (bd, inter)
        elif typ == b"PLTE":
            plte = body
        elif typ == b"tRNS":
            trns = body
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
    data = zlib.decompress(idat)
    nch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    stride = w * nch
    out = []
    prev = bytearray(stride)
    pos = 0
    for _y in range(h):
        ft = data[pos]
        pos += 1
        line = bytearray(data[pos:pos + stride])
        pos += stride
        if ft == 1:
            for x in range(nch, stride):
                line[x] = (line[x] + line[x - nch]) & 0xFF
        elif ft == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 0xFF
        elif ft == 3:
            for x in range(stride):
                a = line[x - nch] if x >= nch else 0
                line[x] = (line[x] + ((a + prev[x]) >> 1)) & 0xFF
        elif ft == 4:
            for x in range(stride):
                a = line[x - nch] if x >= nch else 0
                c = prev[x - nch] if x >= nch else 0
                line[x] = (line[x] + paeth(a, prev[x], c)) & 0xFF
        out.append(bytes(line))
        prev = line

    # → 每像素 (r,g,b,a)
    px = []
    for line in out:
        row = []
        for x in range(w):
            if ct == 6:
                r, g, b, a = line[x * 4:x * 4 + 4]
            elif ct == 2:
                r, g, b = line[x * 3:x * 3 + 3]
                a = 255
            elif ct == 0:
                r = g = b = line[x]
                a = 255
            elif ct == 4:
                r = g = b = line[x * 2]
                a = line[x * 2 + 1]
            else:                       # 3：索引
                idx = line[x]
                r, g, b = plte[idx * 3:idx * 3 + 3]
                a = trns[idx] if trns and idx < len(trns) else 255
            row.append((r, g, b, a))
        px.append(row)
    return w, h, px


def main():
    path = sys.argv[1]
    cols = int(sys.argv[2]) if len(sys.argv) > 2 else 48
    w, h, px = decode(path)
    step = max(1, w // cols)
    print("size %dx%d  step %d" % (w, h, step))
    for y in range(0, h, step):
        line = []
        for x in range(0, w, step):
            r, g, b, a = px[y][x]
            if a < 40:
                line.append(" ")
            elif a < 200:
                line.append("+")
            elif (r + g + b) / 3 < 80:
                line.append("#")
            else:
                line.append(".")
        print("%2d|%s|" % (y, "".join(line)))


if __name__ == "__main__":
    main()
