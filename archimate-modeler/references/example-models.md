# ArchiMate Example Model Patterns

## Pattern 1: Simple Web Application (3-tier)

```json
{
  "model": { "id": "web-app", "name": "Web Application" },
  "elements": [
    {"id": "ba_user",      "type": "BusinessActor",        "name": "User"},
    {"id": "bp_browse",    "type": "BusinessProcess",       "name": "Browse & Order"},
    {"id": "ac_frontend",  "type": "ApplicationComponent",  "name": "Frontend"},
    {"id": "ac_backend",   "type": "ApplicationComponent",  "name": "Backend API"},
    {"id": "as_api",       "type": "ApplicationService",    "name": "Order API"},
    {"id": "do_order",     "type": "DataObject",            "name": "Order"},
    {"id": "nd_server",    "type": "Node",                  "name": "App Server"},
    {"id": "ss_db",        "type": "SystemSoftware",        "name": "PostgreSQL"}
  ],
  "relationships": [
    {"id": "r1", "type": "Assignment",  "source": "ba_user",     "target": "bp_browse"},
    {"id": "r2", "type": "Realization", "source": "ac_backend",  "target": "as_api"},
    {"id": "r3", "type": "Serving",     "source": "as_api",      "target": "ac_frontend"},
    {"id": "r4", "type": "Access",      "source": "ac_backend",  "target": "do_order"},
    {"id": "r5", "type": "Composition", "source": "nd_server",   "target": "ac_backend"},
    {"id": "r6", "type": "Composition", "source": "nd_server",   "target": "ss_db"}
  ],
  "views": []
}
```

---

## Pattern 2: Microservices Platform

Key structural rules for microservices:
- Each microservice = one `ApplicationComponent` + one `ApplicationService`
- API Gateway = `ApplicationComponent` that routes to all services
- Message broker = `Node` (e.g. Kafka Cluster)
- Each service → `Composition` from the runtime Node (deployment)
- Services communicate via `Association` (sync) or `Flow` (async/event)

```json
{
  "model": { "id": "microservices", "name": "Microservices Platform" },
  "elements": [
    {"id": "ac_gateway",   "type": "ApplicationComponent", "name": "API Gateway"},
    {"id": "ac_svc_a",     "type": "ApplicationComponent", "name": "Service A"},
    {"id": "ac_svc_b",     "type": "ApplicationComponent", "name": "Service B"},
    {"id": "as_svc_a",     "type": "ApplicationService",   "name": "Service A API"},
    {"id": "as_svc_b",     "type": "ApplicationService",   "name": "Service B API"},
    {"id": "do_entity_a",  "type": "DataObject",           "name": "Entity A"},
    {"id": "nd_k8s",       "type": "Node",                 "name": "Kubernetes"},
    {"id": "nd_kafka",     "type": "Node",                 "name": "Kafka"},
    {"id": "ss_redis",     "type": "SystemSoftware",       "name": "Redis"}
  ],
  "relationships": [
    {"id": "r1",  "type": "Realization",  "source": "ac_svc_a",   "target": "as_svc_a"},
    {"id": "r2",  "type": "Realization",  "source": "ac_svc_b",   "target": "as_svc_b"},
    {"id": "r3",  "type": "Association",  "source": "ac_gateway",  "target": "ac_svc_a", "name": "routes"},
    {"id": "r4",  "type": "Association",  "source": "ac_gateway",  "target": "ac_svc_b", "name": "routes"},
    {"id": "r5",  "type": "Flow",         "source": "ac_svc_a",    "target": "ac_svc_b", "name": "event"},
    {"id": "r6",  "type": "Access",       "source": "ac_svc_a",    "target": "do_entity_a"},
    {"id": "r7",  "type": "Composition",  "source": "nd_k8s",      "target": "ac_svc_a", "name": "deploys"},
    {"id": "r8",  "type": "Composition",  "source": "nd_k8s",      "target": "ac_svc_b", "name": "deploys"},
    {"id": "r9",  "type": "Composition",  "source": "nd_kafka",    "target": "ss_redis"}
  ],
  "views": []
}
```

---

## Pattern 3: Event-Driven Architecture

Key rules:
- Producers/consumers = `ApplicationComponent`
- Event bus = `Node`
- Events = `DataObject`
- Producer → `Flow` → Consumer (async)
- Both producer and consumer → `Composition` from event bus Node

---

## ID Naming Conventions

| Prefix | Type |
|---|---|
| `ba_` | BusinessActor |
| `bp_` | BusinessProcess |
| `ac_` | ApplicationComponent |
| `as_` | ApplicationService |
| `do_` | DataObject |
| `dev_` | Device |
| `nd_` | Node |
| `ss_` | SystemSoftware |
| `r` + number | Relationship |