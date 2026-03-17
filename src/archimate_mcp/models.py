from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


ElementType = Literal[
    "BusinessActor",
    "BusinessProcess",
    "ApplicationComponent",
    "ApplicationService",
    "DataObject",
    "Node",
    "Device",
    "SystemSoftware",
]

RelationshipType = Literal[
    "Serving",
    "Access",
    "Assignment",
    "Realization",
    "Composition",
    "Aggregation",
    "Association",
    "Flow",
    "Triggering",
]


class Property(BaseModel):
    key: str
    value: str


class Element(BaseModel):
    id: str
    type: ElementType
    name: str
    documentation: str | None = None
    properties: list[Property] = Field(default_factory=list)


class Relationship(BaseModel):
    id: str
    type: RelationshipType
    source: str
    target: str
    name: str | None = None
    documentation: str | None = None
    properties: list[Property] = Field(default_factory=list)


class Node(BaseModel):
    id: str
    element_id: str | None = None
    label: str | None = None
    x: int
    y: int
    w: int = 180
    h: int = 55
    node_type: Literal["Element", "Container"] = "Element"
    children: list["Node"] = Field(default_factory=list)


Node.model_rebuild()


class BendPoint(BaseModel):
    x: int
    y: int


class Connection(BaseModel):
    id: str
    relationship_id: str
    source_node_id: str
    target_node_id: str
    bendpoints: list[BendPoint] = Field(default_factory=list)


class View(BaseModel):
    id: str
    name: str
    nodes: list[Node] = Field(default_factory=list)
    connections: list[Connection] = Field(default_factory=list)
    documentation: str | None = None


class ModelInfo(BaseModel):
    id: str
    name: str
    documentation: str | None = None


class ArchimateModel(BaseModel):
    model: ModelInfo
    elements: list[Element] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    views: list[View] = Field(default_factory=list)