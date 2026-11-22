"""纯 stdlib PNG 读取/裁剪/放大/写出（无 Pillow）。"""
import zlib, struct

def read_png(path):
    data = open(path, "rb").read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, w = 8, b"", None
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos+4])[0]
        typ = data[pos+4:pos+8]
        body = data[pos+8:pos+8+ln]
        pos += 12 + ln
        if typ == b"IHDR":
            w, h, bd, ct, comp, filt, inter = struct.unpack(">IIBBBBB", body)
            assert bd == 8 and inter == 0, (bd, inter)
            nch = {0:1, 2:3, 3:1, 4:2, 6:4}[ct]
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
    raw = zlib.decompress(idat)
    stride = w * nch
    rows, prev, p = [], bytearray(stride), 0
    for _ in range(h):
        f = raw[p]; p += 1
        line = bytearray(raw[p:p+stride]); p += stride
        if f == 1:
            for i in range(nch, stride): line[i] = (line[i] + line[i-nch]) & 255
        elif f == 2:
            for i in range(stride): line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                a = line[i-nch] if i >= nch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i-nch] if i >= nch else 0
                b = prev[i]
                c = prev[i-nch] if i >= nch else 0
                pa, pb, pc = abs(b-c), abs(a-c), abs(a+b-2*c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        rows.append(bytes(line)); prev = line
    return w, h, nch, rows

def write_png(path, w, h, nch, rows):
    ct = {1:0, 3:2, 4:6}[nch]
    raw = b"".join(b"\x00" + r for r in rows)
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t+d) & 0xffffffff)
    hdr = struct.pack(">IIBBBBB", w, h, 8, ct, 0, 0, 0)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", hdr)
                           + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))

def crop_zoom(src, dst, box, z=2):
    w, h, nch, rows = read_png(src)
    x0, y0, x1, y1 = box
    x0, y0 = max(0, x0), max(0, y0); x1, y1 = min(w, x1), min(h, y1)
    out = []
    for y in range(y0, y1):
        line = rows[y][x0*nch:x1*nch]
        big = b"".join(line[i:i+nch] * z for i in range(0, len(line), nch))
        for _ in range(z):
            out.append(big)
    write_png(dst, (x1-x0)*z, (y1-y0)*z, nch, out)
    return (x1-x0)*z, (y1-y0)*z

if __name__ == "__main__":
    import sys
    print(crop_zoom(sys.argv[1], sys.argv[2],
                    tuple(int(v) for v in sys.argv[3:7]), int(sys.argv[7])))
