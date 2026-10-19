"""Ticket representation for an already-issued private ticket."""
import io

import qrcode
from qrcode.image.svg import SvgPathFillImage


def ticket_svg(ticket_code):
    """Encode an existing ticket code without issuing or redeeming it."""
    output = io.BytesIO()
    qrcode.make(ticket_code, image_factory=SvgPathFillImage, border=4).save(output)
    return output.getvalue()
