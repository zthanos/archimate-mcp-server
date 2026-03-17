from __future__ import annotations

from .layout import (
    generate_application_view,
    generate_application_cooperation_view,
    generate_technology_view,
    generate_integration_view,
)
from .models import ArchimateModel
from .validation import ValidationError, validate_model


# Map view_id → (generator_fn, view_name)
_DEFAULT_VIEWS: list[tuple[str, str, object]] = [
    (
        "view_default_application",
        "Default Application View",
        generate_application_view,
    ),
    (
        "view_application_cooperation",
        "Application Cooperation View",
        generate_application_cooperation_view,
    ),
    (
        "view_technology",
        "Technology View",
        generate_technology_view,
    ),
    (
        "view_integration",
        "Integration View",
        generate_integration_view,
    ),
]


def build_model_with_default_view(model: ArchimateModel) -> ArchimateModel:
    if not model.views:
        existing_view_ids = set()
    else:
        existing_view_ids = {v.id for v in model.views}

    for view_id, view_name, generator in _DEFAULT_VIEWS:
        if view_id not in existing_view_ids:
            view = generator(model=model, view_id=view_id, view_name=view_name)
            # Only add the view if it has at least one node
            if view.nodes:
                model.views.append(view)

    errors = validate_model(model)
    if errors:
        raise ValidationError("\n".join(errors))

    return model