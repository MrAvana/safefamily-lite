"""Ready-to-send APN set commands for SafeFamily Lite watches.

Only the APN set-SMS is kept here. The other SMS control commands that the
Android app can compose (``u_sms_nowpos``, ``u_sms_tracking``, ``u_sms_verifi``,
``u_sms_ip``, ``u_sms_phone``) were tested against a retail watch and produced
no reaction, so they are not exposed by the integration.

These examples target Madagascar (MCC 646). Edit ``APN_COMMANDS`` to add or
change operators — each entry is ``(label, sms_body)`` and ``sms_body`` is what
gets shown after the label.

Two watch formats exist:

* legacy watches:  ``APN#<port>#<mccmnc>#<apn>#<user>#<password>#<ip>``
* Apex watches:    ``#APN#=<mccmnc>,<apn>,<user>,<password>,<ip>#``

The watch firmware decides which one it accepts; swap the bodies below if
needed.
"""
from __future__ import annotations

# (label, sms body)
APN_COMMANDS: list[tuple[str, str]] = [
    ("Change APN (Telma)", "APN#0#64604#internet#0#0#0"),
    ("Change APN (Orange MG)", "APN#0#64602#orangenet#0#0#0"),
    ("Change APN (Airtel MG)", "APN#0#64601#internet.mg.airtel.com#0#0#0"),
]


def render_lines() -> list[str]:
    """Return the APN commands as ``"<label>: <body>"`` strings."""
    return [f"{label}: {body}" for label, body in APN_COMMANDS]
