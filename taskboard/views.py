from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from .forms import ProjectForm, TaskForm
from .models import Project, Task


class MessageMixin:
    message_key = None

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            getattr(self, "message", f"{self.model._meta.verbose_name} saved."),
        )
        return response


class ProjectListView(LoginRequiredMixin, ListView):
    model = Project
    template_name = "taskboard/project_list.html"
    context_object_name = "projects"
    paginate_by = 20

    def get_queryset(self):
        qs = Project.objects.all()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        status = self.request.GET.get("status", "").strip()
        if status in Project.Status.values:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "")
        context["status_filter"] = self.request.GET.get("status", "")
        context["status_choices"] = Project.Status.choices
        return context


class ProjectDetailView(LoginRequiredMixin, DetailView):
    model = Project
    template_name = "taskboard/project_detail.html"
    context_object_name = "project"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tasks = self.object.tasks.all()
        q = self.request.GET.get("q", "").strip()
        if q:
            tasks = tasks.filter(title__icontains=q)
        status = self.request.GET.get("status", "").strip()
        if status in Task.Status.values:
            tasks = tasks.filter(status=status)
        priority = self.request.GET.get("priority", "").strip()
        if priority in Task.Priority.values:
            tasks = tasks.filter(priority=priority)
        context["tasks"] = tasks
        context["q"] = q
        context["status_filter"] = status
        context["priority_filter"] = priority
        context["project_task_statuses"] = Task.Status.choices
        context["task_priorities"] = Task.Priority.choices
        context["quick_form"] = TaskForm(project=self.object)
        return context


class ProjectCreateView(LoginRequiredMixin, MessageMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = "taskboard/project_form.html"
    message = "Project created."

    def get_success_url(self):
        return reverse("project-detail", kwargs={"pk": self.object.pk})


class ProjectUpdateView(LoginRequiredMixin, MessageMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    template_name = "taskboard/project_form.html"
    message = "Project updated."

    def get_success_url(self):
        return reverse("project-detail", kwargs={"pk": self.object.pk})


class ProjectDeleteView(LoginRequiredMixin, DeleteView):
    model = Project
    template_name = "taskboard/project_confirm_delete.html"

    def get_success_url(self):
        return reverse("project-list")


class TaskListView(LoginRequiredMixin, ListView):
    model = Task
    template_name = "taskboard/task_list.html"
    context_object_name = "tasks"
    paginate_by = 25

    def get_queryset(self):
        qs = Task.objects.select_related("project").all()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(title__icontains=q)
        status = self.request.GET.get("status", "").strip()
        if status in Task.Status.values:
            qs = qs.filter(status=status)
        priority = self.request.GET.get("priority", "").strip()
        if priority in Task.Priority.values:
            qs = qs.filter(priority=priority)
        project = self.request.GET.get("project", "").strip()
        if project.isdigit():
            qs = qs.filter(project_id=int(project))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "q": self.request.GET.get("q", ""),
                "status_filter": self.request.GET.get("status", ""),
                "priority_filter": self.request.GET.get("priority", ""),
                "project_filter": self.request.GET.get("project", ""),
                "projects": Project.objects.all(),
                "status_choices": Task.Status.choices,
                "priority_choices": Task.Priority.choices,
            }
        )
        return context


class TaskCreateView(LoginRequiredMixin, MessageMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = "taskboard/task_form.html"
    message = "Task created."

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get("project"):
            initial["project"] = self.request.GET.get("project")
        return initial

    def get_success_url(self):
        return reverse("project-detail", kwargs={"pk": self.object.project_id})


class TaskUpdateView(LoginRequiredMixin, MessageMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = "taskboard/task_form.html"
    message = "Task updated."

    def get_success_url(self):
        return reverse("project-detail", kwargs={"pk": self.object.project_id})


class TaskDeleteView(LoginRequiredMixin, DeleteView):
    model = Task
    template_name = "taskboard/task_confirm_delete.html"

    def get_success_url(self):
        return reverse("project-detail", kwargs={"pk": self.object.project_id})
