from PIL import Image
from struct import pack, unpack
from typing import List, Tuple
import random

class NotEnoughValuesException(Exception):
    pass

class InvalidImageEncodingException(Exception):
    pass

def write_bit(pixels, bit: int, location: Tuple[int, int, int], verbose=False):
    x, y, channel = location
    if verbose: print("Wrote bit {} at {}, {}, {}".format(bit, x, y, channel))
    orig = list(pixels[x, y])
    orig[channel] &= 0b11111110
    orig[channel] |= bit
    pixels[x, y] = tuple(orig)

def write_byte(pixels, byte: int, locations: List[Tuple[int, int, int]], verbose=False):
    assert 0 <= byte <= 255
    bits = []
    while byte > 0:
        bits.append(byte % 2)
        byte //= 2
    bits += [0] * (8-len(bits))
    for i, v in enumerate(bits):
        write_bit(pixels, v, locations[i], verbose)

def read_bit(pixels, location: Tuple[int, int, int], verbose=False) -> int:
    x, y, channel = location
    if verbose: print("Read {} from {}, {}, {}".format(pixels[x, y][channel] & 1, x, y, channel))
    return pixels[x, y][channel] & 1

def read_byte(pixels, locations: List[Tuple[int, int, int]], verbose=False) -> int:
    assert len(locations) == 8
    res = 0
    locations.reverse()
    for location in locations:
        res *= 2
        res += read_bit(pixels, location, verbose)
    if verbose: print("Read", res)
    return res

def encode(image: Image, message: bytes, verbose=False):
    # Load the image.
    image = image.convert("RGB")
    pixels = image.load()
    available = image.width * image.height * 3
    size = len(message)
    if available <= size * 8 + 72:
        raise NotEnoughValuesException("Needs {:d} bits worth of space, only got {:d}"  \
            .format(size * 8 + 72, available))

    # We load a 32bit seed.
    seed = [random.getrandbits(8) for i in range(4)]
    if verbose: print("Seed is {:x}".format(unpack("<I", bytes(seed))[0]))
    random.seed(bytes(seed))

    # Construct the list of valid LSBs.
    valid_spots = []
    for x in range(image.width):
        for y in range(image.height):
            for channel in range(3):
                valid_spots.append((x, y, channel))
    
    # Reserve the first 80 spots for writing metadata, and write it to our pixel list.
    metadata = b"\x90\xbf" + bytes(seed) + pack("<I", size)
    c = 0
    for byte in metadata:
        write_byte(pixels, byte, valid_spots[c:c+8], verbose)
        c += 8
    
    # Now we sample off as many spots as we need to complete the message.
    locations = random.sample(valid_spots[80:], size * 8 + 1)
    c = 0
    for byte in message:
        write_byte(pixels, byte, locations[c:c+8], verbose)
        c += 8
    return image

def decode(image: Image, verbose=False) -> bytes:
    # Load the image.
    image = image.convert("RGB")
    pixels = image.load()

    # Construct the list of valid LSBs.
    valid_spots = []
    for x in range(image.width):
        for y in range(image.height):
            for channel in range(3):
                valid_spots.append((x, y, channel))
    
    # Read off metadata. 
    c = 0
    magic = read_byte(pixels, valid_spots[c:c+8], verbose)
    c += 8
    assert magic == 0x90
    magic = read_byte(pixels, valid_spots[c:c+8], verbose)
    c += 8
    assert magic == 0xbf
    seed = []
    for i in range(4):
        seed.append(read_byte(pixels, valid_spots[c:c+8], verbose))
        c += 8
    size = []
    for i in range(4):
        size.append(read_byte(pixels, valid_spots[c:c+8], verbose))
        c += 8
    seed = bytes(seed)
    size = unpack("<I", bytes(size))[0]
    available = image.height * image.width * 3
    assert available > size * 8 + 64

    # Seed randomizer, and randomize.
    random.seed(seed)
    locations = random.sample(valid_spots[80:], size * 8 + 1)

    # Read off message.
    message = []
    c = 0
    for i in range(size):
        message.append(read_byte(pixels, locations[c:c+8], verbose))
        c += 8
    return bytes(message)

if __name__ == "__main__":
    from argparse import ArgumentParser
    parser = ArgumentParser()
    enc_group = parser.add_mutually_exclusive_group(required=True)
    enc_group.add_argument("--encode", dest="enc", action="store_true", 
        help="Encode message. Requires message if used.")
    enc_group.add_argument("--decode", dest="enc", action="store_false",
        help="Decode image.")
    parser.add_argument("filename", action="store", 
        help="File to use in steganography.")
    parser.add_argument("-o", "--outfile", dest="outfile", default=None, action="store", 
        help="File to write to. Defaults to original file.")
    parser.add_argument("-m", "--message", dest="msg", default=None, action="store", 
        help="Message to write. If omitted in encode mode, will read from stdin.")
    parser.add_argument("-v", "--verbose", dest="verb", action="store_true", default=False,
        help="Be verbose.")

    args = parser.parse_args()

    if args.enc:
        if args.msg is None:
            args.msg = ""
            while True:
                try:
                    a = input()
                    args.msg += a + "\n"
                except EOFError:
                    break
        with Image.open(args.filename) as image:
            res = encode(image, bytes(args.msg, "ascii"), args.verb)
        res.save(args.filename if args.outfile is None else args.outfile)
    else:
        with Image.open(args.filename) as image:
            msg = decode(image, args.verb)
        print(msg.decode())
