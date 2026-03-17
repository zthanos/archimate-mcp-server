# ArchiMate 3.1 Rules Reference

## Valid Element Types

### Business Layer
| Type | Description |
|---|---|
| `BusinessActor` | Person, organisation, or role |
| `BusinessProcess` | Sequence of business behaviours |

### Application Layer
| Type | Description |
|---|---|
| `ApplicationComponent` | Encapsulates application functionality |
| `ApplicationService` | Externally visible unit of functionality |
| `DataObject` | Passive data element |

### Technology Layer
| Type | Description |
|---|---|
| `Device` | Physical IT resource |
| `Node` | Computational or physical resource (e.g. VM, cluster) |
| `SystemSoftware` | Software environment (OS, middleware, runtime) |

---

## Valid Relationship Types

| Type | Meaning |
|---|---|
| `Assignment` | Actor/role assigned to behaviour |
| `Realization` | Component/service realizes a higher-level concept |
| `Serving` | Element provides services to another |
| `Access` | Element accesses a passive structure (data) |
| `Composition` | Whole–part structural relationship |
| `Aggregation` | Loose whole–part relationship |
| `Association` | Generic/unspecified relationship |
| `Flow` | Transfer of information or control |
| `Triggering` | Causal/temporal dependency between processes |

---

## Allowed Combinations (source, type, target)

### Business
- `BusinessActor` → Assignment → `BusinessProcess`
- `BusinessActor` → Assignment → `BusinessActor`
- `BusinessActor` → Association → `BusinessActor`
- `BusinessActor` → Association → `BusinessProcess`
- `BusinessProcess` → Triggering → `BusinessProcess`
- `BusinessProcess` → Flow → `BusinessProcess`
- `BusinessProcess` → Composition → `BusinessProcess`
- `BusinessProcess` → Aggregation → `BusinessProcess`

### Application — Components
- `ApplicationComponent` → Realization → `ApplicationService`
- `ApplicationComponent` → Realization → `BusinessProcess`
- `ApplicationComponent` → Access → `DataObject`
- `ApplicationComponent` → Serving → `ApplicationComponent`
- `ApplicationComponent` → Serving → `BusinessProcess`
- `ApplicationComponent` → Serving → `BusinessActor`
- `ApplicationComponent` → Composition → `ApplicationComponent`
- `ApplicationComponent` → Aggregation → `ApplicationComponent`
- `ApplicationComponent` → Association → `ApplicationComponent`
- `ApplicationComponent` → Flow → `ApplicationComponent`

### Application — Services
- `ApplicationService` → Serving → `ApplicationComponent`
- `ApplicationService` → Serving → `BusinessProcess`
- `ApplicationService` → Serving → `BusinessActor`
- `ApplicationService` → Access → `DataObject`
- `ApplicationService` → Association → `ApplicationService`
- `ApplicationService` → Flow → `ApplicationService`
- `ApplicationService` → Realization → `BusinessProcess`

### Application — Data
- `DataObject` → Association → `DataObject`
- `DataObject` → Composition → `DataObject`
- `DataObject` → Aggregation → `DataObject`

### Technology — Devices
- `Device` → Composition → `Device`
- `Device` → Aggregation → `Device`
- `Device` → Association → `Device`
- `Device` → Composition → `Node`
- `Device` → Aggregation → `Node`
- `Device` → Composition → `SystemSoftware`
- `Device` → Serving → `Device`
- `Device` → Serving → `ApplicationComponent`
- `Device` → Realization → `ApplicationComponent`

### Technology — Nodes
- `Node` → Composition → `Node`
- `Node` → Aggregation → `Node`
- `Node` → Association → `Node`
- `Node` → Composition → `SystemSoftware`
- `Node` → Aggregation → `SystemSoftware`
- `Node` → Composition → `ApplicationComponent`  ← deployment
- `Node` → Serving → `ApplicationComponent`
- `Node` → Serving → `Node`
- `Node` → Realization → `ApplicationComponent`

### Technology — System Software
- `SystemSoftware` → Composition → `SystemSoftware`
- `SystemSoftware` → Aggregation → `SystemSoftware`
- `SystemSoftware` → Association → `SystemSoftware`
- `SystemSoftware` → Composition → `ApplicationComponent`
- `SystemSoftware` → Serving → `ApplicationComponent`
- `SystemSoftware` → Serving → `SystemSoftware`
- `SystemSoftware` → Realization → `ApplicationComponent`

---

## Common Mistakes

| Mistake | Correct approach |
|---|---|
| `Device` → Composition → `ApplicationComponent` | Use `Node` → Composition → `ApplicationComponent` |
| `BusinessProcess` → Serving → `ApplicationComponent` | Reverse: `ApplicationComponent` → Serving → `BusinessProcess` |
| `ApplicationService` → Realization → `ApplicationComponent` | Reverse: `ApplicationComponent` → Realization → `ApplicationService` |
| Two components with `Realization` to each other | Use `Association` or `Serving` instead |
| Technology element directly `Assignment` to Business | Assignment is only Business layer; use Serving or Realization cross-layer |