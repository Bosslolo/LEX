"""Multi-source agreement scorecard for the LEX demo slide."""

from __future__ import annotations

from typing import Any


def build_comparison(
    *,
    csi_presence: float,
    csi_motion: float,
    csi_near_side: str,
    camera_ok: bool,
    camera_count: int,
    named_faces: list[str],
    ble_count: int,
    ble_names: list[str],
) -> dict[str, Any]:
    radio_yes = csi_presence > 0.5 or csi_motion >= 0.35
    camera_yes = camera_ok and camera_count > 0
    phones_yes = ble_count > 0
    faces_yes = len(named_faces) > 0

    # Treat camera(+faces when enrolled) as the visual reference when available
    reference = "camera" if camera_ok else ("phones" if phones_yes else "csi")

    def agree(a: bool, b: bool) -> str:
        if a == b:
            return "agree"
        return "disagree"

    presence_rows = [
        {"source": "csi", "detects_someone": radio_yes, "vs_camera": agree(radio_yes, camera_yes) if camera_ok else "n/a"},
        {"source": "camera", "detects_someone": camera_yes, "vs_camera": "reference" if camera_ok else "offline"},
        {"source": "faces", "detects_someone": faces_yes, "vs_camera": agree(faces_yes, camera_yes) if camera_ok else "n/a"},
        {"source": "phones", "detects_someone": phones_yes, "vs_camera": agree(phones_yes, camera_yes) if camera_ok else "n/a"},
    ]

    # Counting agreement vs camera count
    count_err_phones = abs(ble_count - camera_count) if camera_ok else None
    count_err_faces = abs(len(named_faces) - camera_count) if camera_ok else None

    # Identity overlap: face names vs BLE device names (loose substring match)
    face_set = {n.lower() for n in named_faces}
    ble_set = {n.lower() for n in ble_names if n}
    identity_hits = []
    for face in face_set:
        for phone in ble_set:
            if face in phone or phone in face or (len(face) > 2 and face[:3] in phone):
                identity_hits.append({"face": face, "phone": phone})

    votes = [radio_yes, camera_yes, phones_yes]
    agree_count = sum(1 for v in votes if v == camera_yes) if camera_ok else sum(votes)
    score = {
        "reference": reference,
        "presence_agreement_pct": round(100.0 * agree_count / max(1, len(votes)), 1) if camera_ok else None,
        "camera_count": camera_count,
        "face_count": len(named_faces),
        "ble_count": ble_count,
        "csi_motion_pct": round(csi_motion * 100),
        "csi_near_side": csi_near_side,
        "named_faces": named_faces,
        "ble_names": ble_names[:8],
        "identity_overlap": identity_hits,
        "count_error_phones": count_err_phones,
        "count_error_faces": count_err_faces,
        "rows": presence_rows,
        "headline": _headline(camera_ok, radio_yes, camera_yes, phones_yes, faces_yes, named_faces),
    }
    return score


def _headline(
    camera_ok: bool,
    radio_yes: bool,
    camera_yes: bool,
    phones_yes: bool,
    faces_yes: bool,
    named_faces: list[str],
) -> str:
    if not camera_ok:
        return "Camera offline — radio/phones running without visual reference"
    if camera_yes and radio_yes and phones_yes:
        who = ", ".join(named_faces) if named_faces else "unnamed person(s)"
        return f"All layers active — faces: {who}"
    if camera_yes and not radio_yes:
        return "Camera sees people; radio quiet (off the TX↔RX path?)"
    if radio_yes and not camera_yes:
        return "Radio motion without camera bodies (outside FOV / dark)"
    if phones_yes and not camera_yes and not radio_yes:
        return "Phones nearby, no bodies/motion — devices without occupants?"
    if faces_yes:
        return f"Recognized: {', '.join(named_faces)}"
    return "Room quiet across layers"
