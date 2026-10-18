from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Conversation(models.Model):
    """One assistant thread. A reader has one open thread at a time; "New chat" starts another."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assistant_conversations")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = _("assistant conversation")
        verbose_name_plural = _("assistant conversations")

    def __str__(self):
        return f"{self.user} · {self.created_at:%Y-%m-%d %H:%M}"


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user", _("Reader")
        ASSISTANT = "assistant", _("Assistant")

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    # Where the reader was when the question was asked: the medicine and, if any, the document.
    application = models.ForeignKey(
        "applications.Application", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    document_path = models.CharField(max_length=500, blank=True)
    # The tool calls behind an answer: [{"tool", "summary", "ok"}].
    steps = models.JSONField(default=list, blank=True)
    provider = models.CharField(max_length=30, blank=True)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = _("assistant message")
        verbose_name_plural = _("assistant messages")


class DocumentText(models.Model):
    """Extracted text of one page of one dossier document, so the assistant can search and quote it."""

    sequence = models.ForeignKey("applications.Sequence", on_delete=models.CASCADE, related_name="document_texts")
    path = models.CharField(max_length=500)
    page = models.PositiveIntegerField()
    text = models.TextField(blank=True)
    # Stored with the text so search results need not rebuild every sequence's CTD tree.
    title = models.CharField(max_length=300, blank=True)
    section = models.CharField(max_length=500, blank=True)  # CTD heading trail, e.g. "3 Quality › 3.2 Body of data"

    class Meta:
        ordering = ["sequence", "path", "page"]
        constraints = [models.UniqueConstraint(fields=["sequence", "path", "page"], name="assistant_doctext_unique")]
        verbose_name = _("document text")
        verbose_name_plural = _("document texts")
