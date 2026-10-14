from django import forms


class StyledFormMixin:
    """Adds the Tailwind component classes from theme/static_src to every widget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                css = "checkbox"
            elif isinstance(widget, forms.RadioSelect):
                css = "radio"
            elif isinstance(widget, forms.ClearableFileInput):
                css = "file-input"
            else:
                css = "input"
            widget.attrs["class"] = f"{css} {widget.attrs.get('class', '')}".strip()
