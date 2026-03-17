from __future__ import annotations

from collections import OrderedDict
from xml.dom import minidom
from xml.etree import ElementTree as ET

from .models import ArchimateModel, Node


NS_ARCHIMATE = "http://www.opengroup.org/xsd/archimate/3.0/"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
NS_DC = "http://purl.org/dc/elements/1.1/"
SCHEMA_LOCATION = (
    "http://www.opengroup.org/xsd/archimate/3.0/ "
    "http://www.opengroup.org/xsd/archimate/3.0/archimate3_Model.xsd"
)

ET.register_namespace("", NS_ARCHIMATE)
ET.register_namespace("xsi", NS_XSI)
ET.register_namespace("dc", NS_DC)


def qname(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def prettify(xml_bytes: bytes) -> str:
    parsed = minidom.parseString(xml_bytes)
    return parsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


def _property_definitions(model: ArchimateModel) -> OrderedDict[str, str]:
    defs: OrderedDict[str, str] = OrderedDict()
    for element in model.elements:
        for prop in element.properties:
            defs.setdefault(prop.key, prop.key)
    for relationship in model.relationships:
        for prop in relationship.properties:
            defs.setdefault(prop.key, prop.key)
    return defs


def export_archimate_exchange_xml(model: ArchimateModel) -> str:
    property_definitions = _property_definitions(model)

    root = ET.Element(
        qname(NS_ARCHIMATE, "model"),
        {
            "identifier": model.model.id,
            qname(NS_XSI, "schemaLocation"): SCHEMA_LOCATION,
        },
    )

    name_el = ET.SubElement(root, qname(NS_ARCHIMATE, "name"))
    name_el.text = model.model.name

    if model.model.documentation:
        doc_el = ET.SubElement(root, qname(NS_ARCHIMATE, "documentation"))
        doc_el.text = model.model.documentation

    propdef_ref_by_key = {
        key: f"propdef_{idx}" for idx, key in enumerate(property_definitions, start=1)
    }

    elements_el = ET.SubElement(root, qname(NS_ARCHIMATE, "elements"))
    for element in model.elements:
        el = ET.SubElement(
            elements_el,
            qname(NS_ARCHIMATE, "element"),
            {
                "identifier": element.id,
                qname(NS_XSI, "type"): element.type,
            },
        )
        n = ET.SubElement(el, qname(NS_ARCHIMATE, "name"))
        n.text = element.name

        if element.documentation:
            d = ET.SubElement(el, qname(NS_ARCHIMATE, "documentation"))
            d.text = element.documentation

        if element.properties:
            props_el = ET.SubElement(el, qname(NS_ARCHIMATE, "properties"))
            for prop in element.properties:
                prop_el = ET.SubElement(
                    props_el,
                    qname(NS_ARCHIMATE, "property"),
                    {"propertyDefinitionRef": propdef_ref_by_key[prop.key]},
                )
                val_el = ET.SubElement(prop_el, qname(NS_ARCHIMATE, "value"))
                val_el.text = prop.value

    rels_el = ET.SubElement(root, qname(NS_ARCHIMATE, "relationships"))
    for relationship in model.relationships:
        rel = ET.SubElement(
            rels_el,
            qname(NS_ARCHIMATE, "relationship"),
            {
                "identifier": relationship.id,
                "source": relationship.source,
                "target": relationship.target,
                qname(NS_XSI, "type"): relationship.type,
            },
        )
        if relationship.name:
            rn = ET.SubElement(rel, qname(NS_ARCHIMATE, "name"))
            rn.text = relationship.name
        if relationship.documentation:
            rd = ET.SubElement(rel, qname(NS_ARCHIMATE, "documentation"))
            rd.text = relationship.documentation
        if relationship.properties:
            props_el = ET.SubElement(rel, qname(NS_ARCHIMATE, "properties"))
            for prop in relationship.properties:
                prop_el = ET.SubElement(
                    props_el,
                    qname(NS_ARCHIMATE, "property"),
                    {"propertyDefinitionRef": propdef_ref_by_key[prop.key]},
                )
                val_el = ET.SubElement(prop_el, qname(NS_ARCHIMATE, "value"))
                val_el.text = prop.value

    if property_definitions:
        prop_defs_el = ET.SubElement(root, qname(NS_ARCHIMATE, "propertyDefinitions"))
        for idx, key in enumerate(property_definitions, start=1):
            prop_def = ET.SubElement(
                prop_defs_el,
                qname(NS_ARCHIMATE, "propertyDefinition"),
                {"identifier": f"propdef_{idx}", "type": "string"},
            )
            n = ET.SubElement(prop_def, qname(NS_ARCHIMATE, "name"))
            n.text = key

    views_el = ET.SubElement(root, qname(NS_ARCHIMATE, "views"))
    diagrams_el = ET.SubElement(views_el, qname(NS_ARCHIMATE, "diagrams"))

    for view in model.views:
        view_el = ET.SubElement(
            diagrams_el,
            qname(NS_ARCHIMATE, "view"),
            {
                "identifier": view.id,
                qname(NS_XSI, "type"): "Diagram",
            },
        )
        vn = ET.SubElement(view_el, qname(NS_ARCHIMATE, "name"))
        vn.text = view.name
        if view.documentation:
            vd = ET.SubElement(view_el, qname(NS_ARCHIMATE, "documentation"))
            vd.text = view.documentation

        def _write_node(parent_el: ET.Element, node: Node) -> None:
            attrs: dict[str, str] = {
                "identifier": node.id,
                "x": str(node.x),
                "y": str(node.y),
                "w": str(node.w),
                "h": str(node.h),
                qname(NS_XSI, "type"): node.node_type,
            }
            if node.element_id is not None:
                attrs["elementRef"] = node.element_id

            node_el = ET.SubElement(parent_el, qname(NS_ARCHIMATE, "node"), attrs)

            for child in node.children:
                _write_node(node_el, child)

        for node in view.nodes:
            _write_node(view_el, node)

        for connection in view.connections:
            ET.SubElement(
                view_el,
                qname(NS_ARCHIMATE, "connection"),
                {
                    "identifier": connection.id,
                    "relationshipRef": connection.relationship_id,
                    "source": connection.source_node_id,
                    "target": connection.target_node_id,
                    qname(NS_XSI, "type"): "Relationship",
                },
            )

    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return prettify(xml_bytes)