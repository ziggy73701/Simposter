from .universal import render as universal_render

# Only one renderer: default
TEMPLATES = {
    "default": universal_render
}

def list_templates():
    return [
        {"id": "default", "name": "Default"}
    ]

def get_renderer(template_id: str):
    if template_id not in TEMPLATES:
        raise KeyError(f"Unknown template_id: {template_id}")
    return TEMPLATES[template_id]
