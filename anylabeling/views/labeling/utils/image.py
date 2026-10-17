import os
import os.path as osp
import base64
import io
import shutil
import zlib

import numpy as np
import PIL.Image
import PIL.ImageOps

from PyQt6 import QtGui

from ...labeling.logger import logger

EXTRA_IMAGE_EXTENSIONS = (".heic", ".heif")
_PILLOW_HEIF_REGISTERED = False

#: A conformant ICC profile is at least this long and carries ``acsp`` at 36.
ICC_MIN_SIZE = 128
ICC_SIGNATURE = b"acsp"


def _jpeg_icc_chunks(data):
    """(sequence, count, payload) triples from a JPEG's APP2 segments."""
    chunks = []
    i = 2  # past the SOI marker
    size = len(data)
    while i + 4 <= size and data[i] == 0xFF:
        marker = data[i + 1]
        if marker == 0xDA:  # start of scan: metadata is over
            break
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            i += 2  # TEM and RSTn carry no length
            continue
        length = int.from_bytes(data[i + 2 : i + 4], "big")
        if length < 2:
            break
        payload = data[i + 4 : i + 2 + length]
        if marker == 0xE2 and payload.startswith(b"ICC_PROFILE\x00"):
            chunks.append((payload[12], payload[13], payload[14:]))
        i += 2 + length
    return chunks


def _png_icc_profile(data):
    """The decompressed ``iCCP`` payload of a PNG, or ``None``."""
    i = 8  # past the PNG signature
    size = len(data)
    while i + 8 <= size:
        length = int.from_bytes(data[i : i + 4], "big")
        kind = data[i + 4 : i + 8]
        body = data[i + 8 : i + 8 + length]
        if kind == b"iCCP":
            split = body.find(b"\x00")
            if split < 0 or split + 2 > len(body):
                return b""
            try:
                return zlib.decompress(body[split + 2 :])
            except zlib.error:
                return b""
        if kind in (b"IDAT", b"IEND"):
            return None
        i += 8 + length + 4
    return None


def _icc_shape_problem(profile):
    """Why this profile is unusable, or ``None`` when it looks sound."""
    if len(profile) < ICC_MIN_SIZE:
        return "配置不足 128 字节（%d）" % len(profile)
    if profile[36:40] != ICC_SIGNATURE:
        return "缺少 acsp 签名"
    declared = int.from_bytes(profile[0:4], "big")
    if declared and declared != len(profile):
        return "声明长度 %d 与实际 %d 不符" % (declared, len(profile))
    if len(profile) < 132:
        return None
    tag_count = int.from_bytes(profile[128:132], "big")
    if tag_count and (132 + tag_count * 12 > len(profile)):
        return "标签表越出配置边界（%d 项）" % tag_count
    for index in range(tag_count):
        # Each entry is a 4-byte tag signature, the offset of its data, and
        # the size of that data.
        entry = profile[132 + index * 12 : 144 + index * 12]
        if len(entry) < 12:
            break
        offset = int.from_bytes(entry[4:8], "big")
        length = int.from_bytes(entry[8:12], "big")
        if length < 12 or offset + length > len(profile) or offset < 128:
            return "第 %d 个标签的偏移或长度无效" % (index + 1)
    return None


def icc_profile_issue(img_data):
    """Return why an embedded ICC profile is broken, or ``None``.

    Qt prints ``qt.gui.icc: fromIccProfile: failed minimal tag size sanity``
    and ``invalid tag offset alignment`` for exactly these files, and
    ``app.py`` mutes that category (``QT_LOGGING_RULES``) -- so a photo whose
    colors are being mis-rendered currently shows the user a wrong image and
    leaves no trace of it anywhere they would look. Labeling against colors
    that are not the colors on the card is a quiet way to build a bad
    dataset, which is why the check is worth doing here.

    Advisory only: nothing about decoding changes, and a profile that cannot
    be inspected (HEIC, or a JPEG this walker gives up on) reads as no issue
    rather than as a warning.
    """
    if not img_data:
        return None
    try:
        if img_data[:2] == b"\xff\xd8":
            chunks = _jpeg_icc_chunks(img_data)
            if not chunks:
                return None
            expected = chunks[0][1]
            if len(chunks) != expected:
                return "分块缺失（读到 %d，声明 %d）" % (len(chunks), expected)
            profile = b"".join(
                payload for _, _, payload in sorted(chunks, key=lambda c: c[0])
            )
        elif img_data[:8] == b"\x89PNG\r\n\x1a\n":
            profile = _png_icc_profile(img_data)
            if profile is None:
                return None
        else:
            return None
    except Exception:  # noqa: BLE001 - a detection never breaks an open
        return None
    if not profile:
        return "内嵌配置为空"
    return _icc_shape_problem(profile)


def ensure_pillow_heif_registered():
    global _PILLOW_HEIF_REGISTERED

    if _PILLOW_HEIF_REGISTERED:
        return True

    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except ImportError:
        return False

    _PILLOW_HEIF_REGISTERED = True
    return True


def get_supported_image_extensions():
    extensions = {
        f".{fmt.data().decode().lower()}"
        for fmt in QtGui.QImageReader.supportedImageFormats()
    }
    extensions.update(EXTRA_IMAGE_EXTENSIONS)
    return sorted(extensions)


def img_data_to_pil(img_data):
    ensure_pillow_heif_registered()
    f = io.BytesIO()
    f.write(img_data)
    img_pil = PIL.Image.open(f)
    return img_pil


def img_data_to_arr(img_data):
    img_pil = img_data_to_pil(img_data)
    img_arr = np.array(img_pil)
    return img_arr


def img_b64_to_arr(img_b64):
    img_data = base64.b64decode(img_b64)
    img_arr = img_data_to_arr(img_data)
    return img_arr


def img_pil_to_data(img_pil):
    f = io.BytesIO()
    img_pil.save(f, format="PNG")
    img_data = f.getvalue()
    return img_data


def pil_to_qimage(img):
    """Convert PIL Image to QImage."""
    img = img.convert("RGBA")  # Ensure image is in RGBA format
    data = np.array(img)
    height, width, channel = data.shape
    bytes_per_line = 4 * width
    qimage = QtGui.QImage(
        data,
        width,
        height,
        bytes_per_line,
        QtGui.QImage.Format.Format_RGBA8888,
    )
    return qimage


def img_data_to_qimage(img_data, filename=None):
    image = QtGui.QImage.fromData(img_data)
    if not image.isNull():
        return image

    if not filename or not filename.lower().endswith(EXTRA_IMAGE_EXTENSIONS):
        return image

    try:
        return pil_to_qimage(img_data_to_pil(img_data)).copy()
    except Exception:
        return image


def img_arr_to_b64(img_arr):
    img_pil = PIL.Image.fromarray(img_arr)
    f = io.BytesIO()
    img_pil.save(f, format="PNG")
    img_bin = f.getvalue()
    if hasattr(base64, "encodebytes"):
        img_b64 = base64.encodebytes(img_bin)
    else:
        img_b64 = base64.encodestring(img_bin)
    return img_b64


def img_data_to_png_data(img_data):
    with io.BytesIO() as f:
        f.write(img_data)
        img = PIL.Image.open(f)

        with io.BytesIO() as f:
            img.save(f, "PNG")
            f.seek(0)
            return f.read()


def get_pil_img_dim(img_path):
    """
    Get the dimensions of a PIL image.

    Args:
        img_path (str or bytes or PIL.Image.Image): The path to the image file or the image data.

    Returns:
        tuple: The dimensions of the image (width, height).
    """
    try:
        ensure_pillow_heif_registered()
        if isinstance(img_path, str):
            with PIL.Image.open(img_path) as img:
                return img.size[0], img.size[1]
        elif isinstance(img_path, bytes):
            with PIL.Image.open(io.BytesIO(img_path)) as img:
                return img.size[0], img.size[1]
        elif isinstance(img_path, PIL.Image.Image):
            return img_path.size[0], img_path.size[1]
        else:
            raise ValueError(f"Invalid image path type: {type(img_path)}")

    except Exception as e:
        logger.error(
            f"Error reading image dimensions from {img_path}: {str(e)}"
        )
        raise


def check_img_exif(filename):
    """Check if image needs EXIF orientation correction"""
    try:
        ensure_pillow_heif_registered()
        with PIL.Image.open(filename) as img:
            exif = img.getexif()
            orientation = exif.get(0x0112, 1)
            return orientation not in (1, None)

    except Exception:
        return False


def process_image_exif(filename):
    """Process image EXIF orientation."""
    try:
        ensure_pillow_heif_registered()
        with PIL.Image.open(filename) as img:
            exif = img.getexif()
            orientation = exif.get(0x0112, 1)
            if orientation in (1, None):
                return

            corrected_img = PIL.ImageOps.exif_transpose(img)

            backup_dir = osp.join(
                osp.dirname(osp.dirname(filename)),
                "x-anylabeling-exif-backup",
            )
            os.makedirs(backup_dir, exist_ok=True)
            backup_filename = osp.join(backup_dir, osp.basename(filename))
            shutil.copy2(filename, backup_filename)
            corrected_img.save(filename)

    except Exception as e:
        logger.error(f"Error processing EXIF orientation for {filename}: {e}")
