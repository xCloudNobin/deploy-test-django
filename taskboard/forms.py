from django import forms

from .models import Project, Task


class BootstrapForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "field")
            field.widget.attrs.setdefault("required", field.required)


class ProjectForm(BootstrapForm):
    class Meta:
        model = Project
        fields = ["name", "description", "status"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class TaskForm(BootstrapForm):
    class Meta:
        model = Task
        fields = ["project", "title", "description", "status", "priority", "due_date"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project is not None:
            self.fields["project"].queryset = Project.objects.filter(pk=project.pk)
            self.fields["project"].initial = project
            self.fields["project"].widget = forms.HiddenInput()
