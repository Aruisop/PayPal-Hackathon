"""Encode an existing private demonstration ticket; never issue or redeem one."""
import io

import qrcode
from qrcode.image.svg import SvgPathFillImage


def ticket_svg(ticket_code):
    output = io.BytesIO()
    qrcode.make(ticket_code, image_factory=SvgPathFillImage, border=4).save(output)
    return output.getvalue()
