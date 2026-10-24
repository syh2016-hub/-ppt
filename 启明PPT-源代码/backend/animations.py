"""Minimal PowerPoint-native animation and transition XML writer.

The preset rows below are derived from PowerPoint-authored OOXML effects in the
MIT-licensed ppt-master project (https://github.com/hugohe3/ppt-master),
copyright (c) 2025-2026 Hugo He. Only the five entrance effects needed by the
app are bundled; ids, targets, durations and delays are rewritten per shape.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Iterable

from lxml import etree

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

NSMAP = {"p": P_NS, "a": A_NS, "r": R_NS}


def _qn(tag: str) -> str:
    prefix, local = tag.split(":")
    return f"{{{NSMAP[prefix]}}}{local}"


# PowerPoint-authored entrance presets.
ANIMATION_ROWS: dict[str, str] = {
    "fade": (
        '<p:cTn xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'id="5" presetID="10" presetClass="entr" presetSubtype="0" fill="hold" grpId="0" nodeType="afterEffect">'
        '<p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
        '<p:set><p:cBhvr><p:cTn id="6" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
        '<p:tgtEl><p:spTgt spid="2"/></p:tgtEl><p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>'
        '</p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>'
        '<p:animEffect transition="in" filter="fade"><p:cBhvr><p:cTn id="7" dur="500"/>'
        '<p:tgtEl><p:spTgt spid="2"/></p:tgtEl></p:cBhvr></p:animEffect>'
        '</p:childTnLst></p:cTn>'
    ),
    "fly": (
        '<p:cTn xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'id="5" presetID="2" presetClass="entr" presetSubtype="4" fill="hold" grpId="0" nodeType="afterEffect">'
        '<p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
        '<p:set><p:cBhvr><p:cTn id="6" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
        '<p:tgtEl><p:spTgt spid="2"/></p:tgtEl><p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>'
        '</p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>'
        '<p:anim calcmode="lin" valueType="num"><p:cBhvr additive="base"><p:cTn id="7" dur="500" fill="hold"/>'
        '<p:tgtEl><p:spTgt spid="2"/></p:tgtEl><p:attrNameLst><p:attrName>ppt_x</p:attrName></p:attrNameLst></p:cBhvr>'
        '<p:tavLst><p:tav tm="0"><p:val><p:strVal val="#ppt_x"/></p:val></p:tav>'
        '<p:tav tm="100000"><p:val><p:strVal val="#ppt_x"/></p:val></p:tav></p:tavLst></p:anim>'
        '<p:anim calcmode="lin" valueType="num"><p:cBhvr additive="base"><p:cTn id="8" dur="500" fill="hold"/>'
        '<p:tgtEl><p:spTgt spid="2"/></p:tgtEl><p:attrNameLst><p:attrName>ppt_y</p:attrName></p:attrNameLst></p:cBhvr>'
        '<p:tavLst><p:tav tm="0"><p:val><p:strVal val="1+#ppt_h/2"/></p:val></p:tav>'
        '<p:tav tm="100000"><p:val><p:strVal val="#ppt_y"/></p:val></p:tav></p:tavLst></p:anim>'
        '</p:childTnLst></p:cTn>'
    ),
    "wipe": (
        '<p:cTn xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'id="5" presetID="22" presetClass="entr" presetSubtype="4" fill="hold" grpId="0" nodeType="afterEffect">'
        '<p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
        '<p:set><p:cBhvr><p:cTn id="6" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
        '<p:tgtEl><p:spTgt spid="2"/></p:tgtEl><p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>'
        '</p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>'
        '<p:animEffect transition="in" filter="wipe(down)"><p:cBhvr><p:cTn id="7" dur="500"/>'
        '<p:tgtEl><p:spTgt spid="2"/></p:tgtEl></p:cBhvr></p:animEffect>'
        '</p:childTnLst></p:cTn>'
    ),
    "zoom": (
        '<p:cTn xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'id="5" presetID="23" presetClass="entr" presetSubtype="16" fill="hold" grpId="0" nodeType="afterEffect">'
        '<p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
        '<p:set><p:cBhvr><p:cTn id="6" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
        '<p:tgtEl><p:spTgt spid="2"/></p:tgtEl><p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>'
        '</p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>'
        '<p:anim calcmode="lin" valueType="num"><p:cBhvr><p:cTn id="7" dur="500" fill="hold"/>'
        '<p:tgtEl><p:spTgt spid="2"/></p:tgtEl><p:attrNameLst><p:attrName>ppt_w</p:attrName></p:attrNameLst></p:cBhvr>'
        '<p:tavLst><p:tav tm="0"><p:val><p:fltVal val="0"/></p:val></p:tav>'
        '<p:tav tm="100000"><p:val><p:strVal val="#ppt_w"/></p:val></p:tav></p:tavLst></p:anim>'
        '<p:anim calcmode="lin" valueType="num"><p:cBhvr><p:cTn id="8" dur="500" fill="hold"/>'
        '<p:tgtEl><p:spTgt spid="2"/></p:tgtEl><p:attrNameLst><p:attrName>ppt_h</p:attrName></p:attrNameLst></p:cBhvr>'
        '<p:tavLst><p:tav tm="0"><p:val><p:fltVal val="0"/></p:val></p:tav>'
        '<p:tav tm="100000"><p:val><p:strVal val="#ppt_h"/></p:val></p:tav></p:tavLst></p:anim>'
        '</p:childTnLst></p:cTn>'
    ),
    "dissolve": (
        '<p:cTn xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'id="5" presetID="9" presetClass="entr" presetSubtype="0" fill="hold" grpId="0" nodeType="afterEffect">'
        '<p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
        '<p:set><p:cBhvr><p:cTn id="6" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
        '<p:tgtEl><p:spTgt spid="2"/></p:tgtEl><p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>'
        '</p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>'
        '<p:animEffect transition="in" filter="dissolve"><p:cBhvr><p:cTn id="7" dur="500"/>'
        '<p:tgtEl><p:spTgt spid="2"/></p:tgtEl></p:cBhvr></p:animEffect>'
        '</p:childTnLst></p:cTn>'
    ),
}


def _number_row(
    effect: str,
    shape_id: int,
    row_id: int,
    first_behavior_id: int,
    duration_ms: int,
) -> tuple[etree._Element, int]:
    row = etree.fromstring(ANIMATION_ROWS[effect].encode("utf-8"))
    row.set("id", str(row_id))
    row.set("nodeType", "afterEffect")
    condition = row.find(f".//{_qn('p:stCondLst')}/{_qn('p:cond')}")
    if condition is not None:
        condition.set("delay", "0")
    for target in row.iter(_qn("p:spTgt")):
        target.set("spid", str(shape_id))
    next_id = first_behavior_id
    for ctn in row.iter(_qn("p:cTn")):
        if ctn is row:
            continue
        ctn.set("id", str(next_id))
        next_id += 1
        duration = ctn.get("dur")
        if duration and duration not in {"1", "indefinite"}:
            ctn.set("dur", str(int(duration_ms)))
    return row, next_id


def build_animation_timing(
    *,
    targets: Iterable[tuple[int, str, int, int]],
    media: Iterable[dict[str, object]] = (),
    gap_ms: int = 110,
) -> etree._Element | None:
    """Build one root <p:timing> with autoplay media and entrance animations.

    targets: (shape_id, effect, duration_ms, delay_ms)
    media: {"kind": "audio"|"video", "shape_id": int, "delay_ms": int, "loop": bool}
    """
    target_list = [(int(a), str(b), int(c), int(d)) for a, b, c, d in targets]
    media_list = list(media)
    if not target_list and not media_list:
        return None

    root = etree.Element(_qn("p:timing"), nsmap=NSMAP)
    tn_lst = etree.SubElement(root, _qn("p:tnLst"))
    par = etree.SubElement(tn_lst, _qn("p:par"))
    root_ctn = etree.SubElement(
        par,
        _qn("p:cTn"),
        {"id": "1", "dur": "indefinite", "restart": "never", "nodeType": "tmRoot"},
    )
    child_list = etree.SubElement(root_ctn, _qn("p:childTnLst"))

    next_id = 3
    media_nodes: list[etree._Element] = []
    media_commands: list[dict[str, object]] = []
    for item in media_list:
        kind = "video" if item.get("kind") == "video" else "audio"
        node = etree.Element(_qn(f"p:{kind}"))
        attrs = {"vol": "80000", "showWhenStopped": "0"}
        media_node = etree.SubElement(node, _qn("p:cMediaNode"), attrs)
        ctn_attrs = {"id": str(next_id), "fill": "hold", "display": "0"}
        if kind == "video" and item.get("loop", True):
            ctn_attrs["repeatCount"] = "indefinite"
        ctn = etree.SubElement(media_node, _qn("p:cTn"), ctn_attrs)
        next_id += 1
        start = etree.SubElement(ctn, _qn("p:stCondLst"))
        # Media waits for its playFrom command. This is how PowerPoint's own
        # Record Slide Show output represents autoplay narration/video.
        etree.SubElement(start, _qn("p:cond"), {"delay": "indefinite"})
        if kind == "audio":
            end = etree.SubElement(ctn, _qn("p:endCondLst"))
            end_cond = etree.SubElement(end, _qn("p:cond"), {"evt": "onStopAudio", "delay": "0"})
            end_target = etree.SubElement(end_cond, _qn("p:tgtEl"))
            etree.SubElement(end_target, _qn("p:sldTgt"))
        target = etree.SubElement(media_node, _qn("p:tgtEl"))
        etree.SubElement(target, _qn("p:spTgt"), {"spid": str(item["shape_id"])})
        media_nodes.append(node)
        media_commands.append(item)

    if target_list or media_commands:
        seq = etree.SubElement(child_list, _qn("p:seq"), {"concurrent": "1", "nextAc": "seek"})
        seq_ctn = etree.SubElement(
            seq,
            _qn("p:cTn"),
            {"id": "2", "dur": "indefinite", "nodeType": "mainSeq"},
        )
        seq_children = etree.SubElement(seq_ctn, _qn("p:childTnLst"))
        outer_id = next_id
        next_id += 1
        outer = etree.SubElement(seq_children, _qn("p:par"))
        outer_ctn = etree.SubElement(
            outer,
            _qn("p:cTn"),
            {"id": str(outer_id), "fill": "hold"},
        )
        outer_start = etree.SubElement(outer_ctn, _qn("p:stCondLst"))
        etree.SubElement(outer_start, _qn("p:cond"), {"delay": "indefinite"})
        begin = etree.SubElement(outer_start, _qn("p:cond"), {"evt": "onBegin", "delay": "0"})
        etree.SubElement(begin, _qn("p:tn"), {"val": "2"})
        outer_children = etree.SubElement(outer_ctn, _qn("p:childTnLst"))

        # Trigger every embedded media shape when the slide begins.
        for command in media_commands:
            wrapper_id = next_id
            next_id += 1
            wrapper = etree.SubElement(outer_children, _qn("p:par"))
            wrapper_ctn = etree.SubElement(
                wrapper,
                _qn("p:cTn"),
                {"id": str(wrapper_id), "fill": "hold"},
            )
            wrapper_start = etree.SubElement(wrapper_ctn, _qn("p:stCondLst"))
            etree.SubElement(
                wrapper_start,
                _qn("p:cond"),
                {"delay": str(max(0, int(command.get("delay_ms", 0))))},
            )
            wrapper_children = etree.SubElement(wrapper_ctn, _qn("p:childTnLst"))
            command_ctn = etree.SubElement(
                wrapper_children,
                _qn("p:par"),
            )
            command_cTn = etree.SubElement(
                command_ctn,
                _qn("p:cTn"),
                {
                    "id": str(next_id),
                    "presetID": "1",
                    "presetClass": "mediacall",
                    "presetSubtype": "0",
                    "fill": "hold",
                    "nodeType": "clickEffect",
                },
            )
            next_id += 1
            command_start = etree.SubElement(command_cTn, _qn("p:stCondLst"))
            etree.SubElement(command_start, _qn("p:cond"), {"delay": "0"})
            command_children = etree.SubElement(command_cTn, _qn("p:childTnLst"))
            cmd = etree.SubElement(
                command_children,
                _qn("p:cmd"),
                {"type": "call", "cmd": "playFrom(0.0)"},
            )
            behavior = etree.SubElement(cmd, _qn("p:cBhvr"))
            etree.SubElement(
                behavior,
                _qn("p:cTn"),
                {"id": str(next_id), "dur": "1", "fill": "hold"},
            )
            next_id += 1
            command_target = etree.SubElement(behavior, _qn("p:tgtEl"))
            etree.SubElement(
                command_target,
                _qn("p:spTgt"),
                {"spid": str(command["shape_id"])},
            )

        elapsed = 0
        for index, (shape_id, effect, duration_ms, delay_ms) in enumerate(target_list):
            effect = effect if effect in ANIMATION_ROWS else "fade"
            wrapper_id = next_id
            row_id = next_id + 1
            next_id += 2
            row, next_id = _number_row(
                effect,
                shape_id,
                row_id,
                next_id,
                max(120, duration_ms),
            )
            wrapper = etree.SubElement(outer_children, _qn("p:par"))
            wrapper_ctn = etree.SubElement(
                wrapper,
                _qn("p:cTn"),
                {"id": str(wrapper_id), "fill": "hold"},
            )
            wrapper_start = etree.SubElement(wrapper_ctn, _qn("p:stCondLst"))
            start_delay = elapsed + max(0, delay_ms)
            etree.SubElement(wrapper_start, _qn("p:cond"), {"delay": str(start_delay)})
            wrapper_children = etree.SubElement(wrapper_ctn, _qn("p:childTnLst"))
            row_par = etree.SubElement(wrapper_children, _qn("p:par"))
            row_par.append(row)
            elapsed = start_delay + max(120, duration_ms) + gap_ms
        prev = etree.SubElement(seq, _qn("p:prevCondLst"))
        prev_cond = etree.SubElement(prev, _qn("p:cond"), {"evt": "onPrev", "delay": "0"})
        prev_target = etree.SubElement(prev_cond, _qn("p:tgtEl"))
        etree.SubElement(prev_target, _qn("p:sldTgt"))
        nxt = etree.SubElement(seq, _qn("p:nextCondLst"))
        next_cond = etree.SubElement(nxt, _qn("p:cond"), {"evt": "onNext", "delay": "0"})
        next_target = etree.SubElement(next_cond, _qn("p:tgtEl"))
        etree.SubElement(next_target, _qn("p:sldTgt"))
    # PowerPoint writes media timing after the main animation sequence.
    for node in media_nodes:
        child_list.append(node)
    return root


def build_transition(effect: str = "fade", *, advance_ms: int | None = None) -> etree._Element:
    effect = effect if effect in {"fade", "push", "wipe", "cover", "dissolve", "none"} else "fade"
    attrs = {"spd": "med", "advClick": "1"}
    if advance_ms and advance_ms > 0:
        attrs["advTm"] = str(int(advance_ms))
    transition = etree.Element(_qn("p:transition"), attrs, nsmap=NSMAP)
    if effect == "fade":
        etree.SubElement(transition, _qn("p:fade"))
    elif effect == "push":
        etree.SubElement(transition, _qn("p:push"), {"dir": "l"})
    elif effect == "wipe":
        etree.SubElement(transition, _qn("p:wipe"), {"dir": "l"})
    elif effect == "cover":
        etree.SubElement(transition, _qn("p:cover"), {"dir": "u"})
    elif effect == "dissolve":
        etree.SubElement(transition, _qn("p:dissolve"))
    return transition


def insert_transition_and_timing(slide_element, transition, timing) -> None:
    """Respect PresentationML child order: cSld, clrMapOvr, transition, timing, extLst."""
    for tag in ("p:transition", "p:timing"):
        for existing in slide_element.findall(_qn(tag)):
            slide_element.remove(existing)
    extension = slide_element.find(_qn("p:extLst"))
    insert_at = list(slide_element).index(extension) if extension is not None else len(slide_element)
    if transition is not None:
        slide_element.insert(insert_at, transition)
        insert_at += 1
    if timing is not None:
        slide_element.insert(insert_at, timing)
