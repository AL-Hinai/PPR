from django.urls import path

from . import notes, search, views

app_name = "applications"

urlpatterns = [
    path("", views.application_list, name="list"),
    path("search/", search.search, name="search"),
    path("new/", views.application_create, name="create"),
    path("<int:pk>/", views.application_detail, name="detail"),
    path("<int:pk>/edit/", views.application_edit, name="edit"),
    path("<int:pk>/upload/", views.upload_sequence, name="upload"),
    path("<int:pk>/submit/", views.submit_application, name="submit"),
    path("<int:pk>/validation-status/", views.validation_status, name="validation_status"),
    path("<int:pk>/assign/", views.assign_reviewer, name="assign"),
    path("<int:pk>/review/", views.add_review, name="add_review"),
    path("<int:pk>/request-info/", views.request_info, name="request_info"),
    path("<int:pk>/complete-review/", views.complete_review, name="complete_review"),
    path("<int:pk>/decide/", views.decide, name="decide"),
    path("<int:pk>/return/", views.return_to_reviewer, name="return"),
    path("<int:pk>/certificate/", views.certificate, name="certificate"),
    path("<int:pk>/sequences/<int:seq_pk>/", views.sequence_detail, name="sequence"),
    path("<int:pk>/sequences/<int:seq_pk>/report.csv", views.sequence_report_csv, name="sequence_csv"),
    path("<int:pk>/sequences/<int:seq_pk>/report/", views.sequence_report_print, name="sequence_report"),
    path("<int:pk>/sequences/<int:seq_pk>/package/", views.sequence_package, name="sequence_package"),
    path("<int:pk>/sequences/<int:seq_pk>/files/<path:path>", views.sequence_file, name="sequence_file"),
    path("<int:pk>/sequences/<int:seq_pk>/view/<path:path>", views.sequence_document, name="sequence_document"),
    path("<int:pk>/sequences/<int:seq_pk>/notes/", notes.note_list, name="notes"),
    path("<int:pk>/notes/<int:note_pk>/edit/", notes.note_edit, name="note_edit"),
    path("<int:pk>/notes/<int:note_pk>/delete/", notes.note_delete, name="note_delete"),
    path("<int:pk>/notes/print/", notes.notes_print, name="notes_print"),
    path("<int:pk>/notes/mine.txt", notes.my_notes_text, name="my_notes"),
]
