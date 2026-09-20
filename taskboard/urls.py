from django.urls import path

from . import views

urlpatterns = [
    path("", views.ProjectListView.as_view(), name="project-list"),
    path("projects/new", views.ProjectCreateView.as_view(), name="project-create"),
    path(
        "projects/<int:pk>",
        views.ProjectDetailView.as_view(),
        name="project-detail",
    ),
    path(
        "projects/<int:pk>/edit",
        views.ProjectUpdateView.as_view(),
        name="project-edit",
    ),
    path(
        "projects/<int:pk>/delete",
        views.ProjectDeleteView.as_view(),
        name="project-delete",
    ),
    path("tasks/", views.TaskListView.as_view(), name="task-list"),
    path("tasks/new", views.TaskCreateView.as_view(), name="task-create"),
    path("tasks/<int:pk>/edit", views.TaskUpdateView.as_view(), name="task-edit"),
    path("tasks/<int:pk>/delete", views.TaskDeleteView.as_view(), name="task-delete"),
]
