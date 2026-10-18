from django.urls import path

from . import views

app_name = "applications"

urlpatterns = [
    path("", views.application_list, name="list"),
    path("new/", views.application_create, name="create"),
    path("<int:pk>/", views.application_detail, name="detail"),
    path("<int:pk>/edit/", views.application_edit, name="edit"),
    path("<int:pk>/upload/", views.upload_sequence, name="upload"),
    path("<int:pk>/submit/", views.submit_application, name="submit"),
    path("<int:pk>/assign/", views.assign_reviewer, name="assign"),
    path("<int:pk>/review/", views.add_review, name="add_review"),
    path("<int:pk>/request-info/", views.request_info, name="request_info"),
    path("<int:pk>/complete-review/", views.complete_review, name="complete_review"),
    path("<int:pk>/decide/", views.decide, name="decide"),
    path("<int:pk>/return/", views.return_to_reviewer, name="return"),
    path("<int:pk>/certificate/", views.certificate, name="certificate"),
    path("<int:pk>/sequences/<int:seq_pk>/", views.sequence_detail, name="sequence"),
    path("<int:pk>/sequences/<int:seq_pk>/report.csv", views.sequence_report_csv, name="sequence_csv"),
    path("<int:pk>/sequences/<int:seq_pk>/package/", views.sequence_package, name="sequence_package"),
    path("<int:pk>/sequences/<int:seq_pk>/files/<path:path>", views.sequence_file, name="sequence_file"),
    path("<int:pk>/sequences/<int:seq_pk>/view/<path:path>", views.sequence_document, name="sequence_document"),
]
